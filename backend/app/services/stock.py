"""Stock dinámico por sucursal.

Ciclo de un plato:
  enviar a cocina -> se RESERVA lo que pide la receta (si no alcanza, 409)
  marcar listo    -> se DESCUENTA del stock físico y se consume la reserva
  cancelar        -> se LIBERA la reserva (si aún no estaba listo)

Todas las filas de inventario se bloquean con SELECT ... FOR UPDATE en orden de id
para que pedidos simultáneos no dejen stock negativo ni generen deadlocks.
"""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflicto, Invalido
from app.core.realtime import canal_sucursal, emitir
from app.models import (
    AlertaStock,
    ComandaItem,
    EstadoAlerta,
    EstadoReserva,
    Inventario,
    MovimientoStock,
    Producto,
    ReservaStock,
    TipoMovimiento,
)


def _fmt(cantidad: Decimal) -> str:
    return f"{cantidad.normalize():f}"


async def bloquear_inventarios(
    session: AsyncSession, *, sucursal_id: int | None = None, insumo_ids=None, inventario_ids=None
) -> list[Inventario]:
    stmt = (
        select(Inventario)
        .order_by(Inventario.id)
        .with_for_update(of=Inventario)
        .execution_options(populate_existing=True)
    )
    if inventario_ids is not None:
        stmt = stmt.where(Inventario.id.in_(inventario_ids))
    else:
        stmt = stmt.where(Inventario.sucursal_id == sucursal_id, Inventario.insumo_id.in_(insumo_ids))
    return list(await session.scalars(stmt))


async def revisar_alerta(session: AsyncSession, inv: Inventario) -> None:
    """Crea una alerta si el stock quedó en el mínimo o por debajo; la resuelve si se repuso."""
    activa = await session.scalar(
        select(AlertaStock).where(AlertaStock.inventario_id == inv.id, AlertaStock.estado == EstadoAlerta.activa)
    )
    unidad = inv.insumo.unidad_abreviatura
    if inv.cantidad <= inv.stock_minimo:
        mensaje = (
            f"Stock bajo de {inv.insumo.nombre}: quedan {_fmt(inv.cantidad)} {unidad} "
            f"(mínimo {_fmt(inv.stock_minimo)} {unidad})"
        )
        if activa:
            activa.cantidad = inv.cantidad
            activa.mensaje = mensaje
        else:
            activa = AlertaStock(
                inventario_id=inv.id,
                sucursal_id=inv.sucursal_id,
                cantidad=inv.cantidad,
                stock_minimo=inv.stock_minimo,
                mensaje=mensaje,
            )
            session.add(activa)
        emitir(
            session,
            canal_sucursal(inv.sucursal_id),
            "stock.alerta",
            {
                "inventario_id": inv.id,
                "insumo_id": inv.insumo_id,
                "insumo": inv.insumo.nombre,
                "unidad": unidad,
                "cantidad": inv.cantidad,
                "stock_minimo": inv.stock_minimo,
                "mensaje": mensaje,
            },
        )
    elif activa:
        activa.estado = EstadoAlerta.resuelta
        activa.resuelta_en = datetime.now(UTC)
        emitir(
            session,
            canal_sucursal(inv.sucursal_id),
            "stock.alerta_resuelta",
            {"inventario_id": inv.id, "insumo": inv.insumo.nombre, "cantidad": inv.cantidad},
        )


def _movimiento(inv: Inventario, tipo: TipoMovimiento, delta: Decimal, motivo, usuario_id, item_id=None):
    return MovimientoStock(
        inventario_id=inv.id,
        tipo=tipo,
        cantidad=delta,
        saldo=inv.cantidad,
        motivo=motivo,
        usuario_id=usuario_id,
        comanda_item_id=item_id,
    )


async def registrar_entrada(session: AsyncSession, inv_id: int, cantidad: Decimal, motivo, usuario_id) -> Inventario:
    [inv] = await bloquear_inventarios(session, inventario_ids=[inv_id])
    inv.cantidad += cantidad
    session.add(_movimiento(inv, TipoMovimiento.entrada, cantidad, motivo, usuario_id))
    await revisar_alerta(session, inv)
    return inv


async def registrar_merma(session: AsyncSession, inv_id: int, cantidad: Decimal, motivo, usuario_id) -> Inventario:
    [inv] = await bloquear_inventarios(session, inventario_ids=[inv_id])
    if inv.cantidad - cantidad < inv.reservado:
        raise Conflicto(
            f"No se puede registrar la merma: quedarían {_fmt(inv.cantidad - cantidad)} y hay "
            f"{_fmt(inv.reservado)} reservados para platos en cocina"
        )
    inv.cantidad -= cantidad
    session.add(_movimiento(inv, TipoMovimiento.merma, -cantidad, motivo, usuario_id))
    await revisar_alerta(session, inv)
    return inv


async def registrar_ajuste(session: AsyncSession, inv_id: int, cantidad_real: Decimal, motivo, usuario_id):
    [inv] = await bloquear_inventarios(session, inventario_ids=[inv_id])
    if cantidad_real < inv.reservado:
        raise Conflicto(
            f"El conteo ({_fmt(cantidad_real)}) es menor a lo reservado para platos en cocina "
            f"({_fmt(inv.reservado)}). Cancela esos platos o márcalos listos antes de ajustar."
        )
    delta = cantidad_real - inv.cantidad
    inv.cantidad = cantidad_real
    session.add(_movimiento(inv, TipoMovimiento.ajuste, delta, motivo, usuario_id))
    await revisar_alerta(session, inv)
    return inv


async def reservar_items(session: AsyncSession, sucursal_id: int, items: list[ComandaItem]) -> None:
    """Reserva el stock de varios items a la vez; todo o nada."""
    productos = {
        p.id: p
        for p in await session.scalars(select(Producto).where(Producto.id.in_({i.producto_id for i in items})))
    }

    necesidades: dict[int, Decimal] = defaultdict(Decimal)
    por_item: list[tuple[ComandaItem, list[tuple[int, Decimal]]]] = []
    for item in items:
        lineas = productos[item.producto_id].consumo(set(item.sin_insumo_ids or []))
        for insumo_id, cant in lineas:
            necesidades[insumo_id] += cant
        por_item.append((item, lineas))

    if not necesidades:
        return

    inventarios = {
        inv.insumo_id: inv
        for inv in await bloquear_inventarios(session, sucursal_id=sucursal_id, insumo_ids=list(necesidades))
    }

    faltantes = []
    for insumo_id, requerido in necesidades.items():
        inv = inventarios.get(insumo_id)
        disponible = inv.disponible if inv else Decimal(0)
        if disponible < requerido:
            faltantes.append(
                {
                    "insumo_id": insumo_id,
                    "insumo": inv.insumo.nombre if inv else None,
                    "requerido": requerido,
                    "disponible": disponible,
                }
            )
    if faltantes:
        raise Conflicto({"mensaje": "Stock insuficiente para enviar a cocina", "faltantes": faltantes})

    for item, lineas in por_item:
        for insumo_id, cant in lineas:
            inv = inventarios[insumo_id]
            inv.reservado += cant
            session.add(ReservaStock(comanda_item_id=item.id, inventario_id=inv.id, cantidad=cant))


async def _reservas_activas(session: AsyncSession, item: ComandaItem) -> list[ReservaStock]:
    return list(
        await session.scalars(
            select(ReservaStock)
            .where(ReservaStock.comanda_item_id == item.id, ReservaStock.estado == EstadoReserva.reservada)
            .with_for_update()
        )
    )


async def consumir_item(session: AsyncSession, item: ComandaItem, usuario_id: int | None) -> list[Inventario]:
    """Plato listo: descuenta del stock físico lo reservado."""
    reservas = await _reservas_activas(session, item)
    if not reservas:
        return []
    inventarios = {
        inv.id: inv
        for inv in await bloquear_inventarios(session, inventario_ids=[r.inventario_id for r in reservas])
    }
    for r in reservas:
        inv = inventarios[r.inventario_id]
        inv.cantidad -= r.cantidad
        inv.reservado -= r.cantidad
        r.estado = EstadoReserva.consumida
        session.add(
            _movimiento(
                inv,
                TipoMovimiento.consumo,
                -r.cantidad,
                f"Comanda #{item.comanda_id} - {item.nombre_producto}",
                usuario_id,
                item.id,
            )
        )
    for inv in inventarios.values():
        await revisar_alerta(session, inv)
    return list(inventarios.values())


async def liberar_item(session: AsyncSession, item: ComandaItem) -> None:
    reservas = await _reservas_activas(session, item)
    if not reservas:
        return
    inventarios = {
        inv.id: inv
        for inv in await bloquear_inventarios(session, inventario_ids=[r.inventario_id for r in reservas])
    }
    for r in reservas:
        inventarios[r.inventario_id].reservado -= r.cantidad
        r.estado = EstadoReserva.liberada


def validar_cantidad_unidad(cantidad: Decimal, insumo) -> None:
    if not insumo.permite_decimales and cantidad != cantidad.to_integral_value():
        raise Invalido(f"{insumo.nombre} se mide en {insumo.unidad_ref.nombre}: usa cantidades enteras")


def resolver_cantidad(insumo, cantidad: Decimal, presentacion_id: int | None) -> Decimal:
    """Con presentación, `cantidad` son envases (3 cajas x24 = 72 unidades); sin ella, ya viene en la unidad del insumo."""
    if presentacion_id is None:
        return cantidad
    pres = next((p for p in insumo.presentaciones if p.id == presentacion_id), None)
    if pres is None:
        raise Invalido(f"{insumo.nombre} no tiene esa presentación")
    if cantidad != cantidad.to_integral_value():
        raise Invalido("Las presentaciones se cuentan en envases enteros")
    return cantidad * pres.cantidad
