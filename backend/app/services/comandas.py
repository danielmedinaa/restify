from collections import Counter, defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflicto, Invalido, MesaBloqueada, NoEncontrado
from app.core.realtime import canal_pedido, canal_sucursal, emitir, publicar
from app.core.security import new_public_token
from app.models import (
    Cliente,
    Comanda,
    ComandaItem,
    EstadoComanda,
    EstadoItem,
    EstadoTurno,
    Mesa,
    Moneda,
    Operacion,
    OrigenComanda,
    Pago,
    Producto,
    TipoDescuento,
    TurnoCaja,
    Usuario,
    Venta,
)
from app.models.catalogo import disponible_en_sucursal, precio_final
from app.models.comandas import ESTADOS_ACTIVOS_COCINA, ESTADOS_FACTURABLES
from app.models.comandas import AutorMensaje, MensajeComanda
from app.schemas.comandas import ItemIn
from app.services import stock
from app.services.menu import disponibles_por_insumo, porciones
from app.services.monedas import a_principal, monedas_activas, montos_en_monedas, q2
from app.services import config

MAX_ITEMS_POR_COMANDA = 200
CERO = Decimal("0.00")


# ---------------------------------------------------------------- carga
async def obtener_comanda(session: AsyncSession, comanda_id: int, *, bloquear: bool = False) -> Comanda:
    # populate_existing: siempre datos frescos aunque la comanda ya esté en la sesión
    stmt = select(Comanda).where(Comanda.id == comanda_id).execution_options(populate_existing=True)
    if bloquear:
        # Serializa operaciones concurrentes sobre la misma comanda (pagar vs. agregar, etc.)
        stmt = stmt.with_for_update(of=Comanda)
    comanda = await session.scalar(stmt)
    if not comanda:
        raise NoEncontrado("Comanda")
    return comanda


async def obtener_por_tracking(session: AsyncSession, token: str, *, bloquear: bool = False) -> Comanda:
    stmt = select(Comanda.id).where(Comanda.tracking_token == token)
    comanda_id = await session.scalar(stmt)
    if not comanda_id:
        raise NoEncontrado("Pedido")
    return await obtener_comanda(session, comanda_id, bloquear=bloquear)


def _exigir_abierta(comanda: Comanda) -> None:
    if comanda.estado != EstadoComanda.abierta:
        raise Conflicto(f"La comanda está {comanda.estado.value}")


# ---------------------------------------------------------------- cálculos
def items_vigentes(comanda: Comanda) -> list[ComandaItem]:
    return [i for i in comanda.items if i.estado != EstadoItem.cancelado]


def subtotal_comanda(comanda: Comanda) -> Decimal:
    """Platos vigentes que se cobran (las cortesías no)."""
    return q2(sum((i.precio_unitario for i in items_vigentes(comanda) if not i.cortesia), CERO))


def descuento_comanda(comanda: Comanda) -> Decimal:
    sub = subtotal_comanda(comanda)
    if not comanda.descuento_tipo or not comanda.descuento_valor:
        return CERO
    if comanda.descuento_tipo == TipoDescuento.porcentaje:
        return min(q2(sub * comanda.descuento_valor / 100), sub)
    return min(q2(comanda.descuento_valor), sub)


def total_comanda(comanda: Comanda) -> Decimal:
    """Facturable: lo que se vende (con descuento, sin propina ni IGTF)."""
    return subtotal_comanda(comanda) - descuento_comanda(comanda)


def a_pagar_comanda(comanda: Comanda) -> Decimal:
    """Lo que el cliente debe cubrir: facturable + propina (el IGTF va aparte, dentro de cada pago)."""
    return total_comanda(comanda) + q2(comanda.propina or CERO)


def pagado_comanda(comanda: Comanda) -> Decimal:
    """Lo abonado a la cuenta: cada pago menos el IGTF que lleva dentro."""
    return q2(sum((p.monto_principal - (p.igtf or CERO) for p in comanda.pagos), CERO))


def igtf_comanda(comanda: Comanda) -> Decimal:
    return q2(sum((p.igtf or CERO for p in comanda.pagos), CERO))


def numerar_items(comanda: Comanda) -> dict[int, int]:
    """Numera las unidades de cada producto: Hamburguesa #1, Hamburguesa #2..."""
    contador: Counter[int] = Counter()
    numeros = {}
    for item in sorted(comanda.items, key=lambda i: i.id):
        contador[item.producto_id] += 1
        numeros[item.id] = contador[item.producto_id]
    return numeros


def seguimiento_url(comanda: Comanda) -> str:
    return f"{config.get("public_tracking_base_url").rstrip('/')}/{comanda.tracking_token}"


def serializar_comanda(comanda: Comanda, monedas: list[Moneda]) -> dict:
    numeros = numerar_items(comanda)
    total = a_pagar_comanda(comanda)
    pagado = pagado_comanda(comanda)
    pendiente = max(total - pagado, CERO)
    return {
        "id": comanda.id,
        "sucursal_id": comanda.sucursal_id,
        "mesa_id": comanda.mesa_id,
        "mesa": comanda.mesa.nombre if comanda.mesa else None,
        "cliente_id": comanda.cliente_id,
        "nombre_cliente": comanda.nombre_cliente or (comanda.cliente.nombre if comanda.cliente else None),
        "telefono_cliente": comanda.telefono_cliente or (comanda.cliente.telefono if comanda.cliente else None),
        "origen": comanda.origen,
        "estado": comanda.estado,
        "notas": comanda.notas,
        "seguimiento_url": seguimiento_url(comanda),
        "items": [
            {
                "id": i.id,
                "producto_id": i.producto_id,
                "nombre": f"{i.nombre_producto} #{numeros[i.id]}",
                "nombre_producto": i.nombre_producto,
                "numero": numeros[i.id],
                "precio_unitario": i.precio_unitario,
                "estado": i.estado,
                "notas": i.notas,
                "sin_insumo_ids": i.sin_insumo_ids or [],
                "estacion_id": i.estacion_id,
                "agregado_por_cliente": i.agregado_por_cliente,
                "cortesia": i.cortesia,
                "cortesia_motivo": i.cortesia_motivo,
                "enviado_en": i.enviado_en,
                "listo_en": i.listo_en,
                "entregado_en": i.entregado_en,
            }
            for i in comanda.items
        ],
        "venta_id": comanda.venta.id if comanda.venta else None,
        # Si la sucursal cobra IGTF, caja suma este % al pagar en divisas
        "igtf_porcentaje": config.get("igtf_porcentaje") if comanda.sucursal.cobra_igtf else None,
        "pagos": [
            {
                "id": p.id,
                "moneda": p.moneda.codigo,
                "monto": p.monto,
                "tasa": p.tasa,
                "operacion": p.operacion.value,
                "monto_principal": p.monto_principal,
                "metodo": p.metodo,
                "referencia": p.referencia,
                "etiqueta": p.etiqueta,
                "igtf": p.igtf,
                "created_at": p.created_at,
            }
            for p in comanda.pagos
        ],
        "descuento": (
            {"tipo": comanda.descuento_tipo, "valor": comanda.descuento_valor, "motivo": comanda.descuento_motivo}
            if comanda.descuento_tipo
            else None
        ),
        "totales": {
            "subtotal": subtotal_comanda(comanda),
            "descuento": descuento_comanda(comanda),
            "facturable": total_comanda(comanda),
            "propina": q2(comanda.propina or CERO),
            "igtf": igtf_comanda(comanda),
            "total": total,
            "pagado": pagado,
            "pendiente": pendiente,
            "vuelto": max(pagado - total, CERO),
            "total_monedas": montos_en_monedas(total, monedas),
            "pendiente_monedas": montos_en_monedas(pendiente, monedas),
        },
        "created_at": comanda.created_at,
        "cerrada_en": comanda.cerrada_en,
        "motivo_cancelacion": comanda.motivo_cancelacion,
    }


def serializar_publico(comanda: Comanda, monedas: list[Moneda]) -> dict:
    numeros = numerar_items(comanda)
    total = a_pagar_comanda(comanda)
    progreso = Counter(i.estado.value for i in comanda.items)
    return {
        "sucursal_id": comanda.sucursal_id,
        "sucursal": comanda.sucursal.nombre,
        "mesa": comanda.mesa.nombre if comanda.mesa else None,
        "estado": comanda.estado,
        "items": [
            {
                "id": i.id,
                "nombre": f"{i.nombre_producto} #{numeros[i.id]}",
                "estado": i.estado,
                "precio_unitario": i.precio_unitario,
                "notas": i.notas,
            }
            for i in comanda.items
        ],
        "total": total,
        "total_monedas": montos_en_monedas(total, monedas),
        "progreso": {e.value: progreso.get(e.value, 0) for e in EstadoItem},
        "created_at": comanda.created_at,
    }


def resumen_comanda(comanda: Comanda) -> dict:
    estados = Counter(i.estado for i in comanda.items)
    return {
        "id": comanda.id,
        "sucursal_id": comanda.sucursal_id,
        "mesa_id": comanda.mesa_id,
        "mesa": comanda.mesa.nombre if comanda.mesa else None,
        "nombre_cliente": comanda.nombre_cliente or (comanda.cliente.nombre if comanda.cliente else None),
        "origen": comanda.origen,
        "estado": comanda.estado,
        "total": a_pagar_comanda(comanda),
        "items_pendientes": estados[EstadoItem.pendiente],
        "items_en_cocina": estados[EstadoItem.en_cocina] + estados[EstadoItem.preparando],
        "items_listos": estados[EstadoItem.listo] + estados[EstadoItem.entregado],
        "items_por_servir": estados[EstadoItem.listo],
        "created_at": comanda.created_at,
    }


# ---------------------------------------------------------------- tiempo real
async def notificar(
    session: AsyncSession, comanda_id: int, tipo: str = "comanda.actualizada"
) -> tuple[Comanda, list[Moneda]]:
    """Publica el estado actual tras el commit: al panel de la sucursal y al link del cliente.

    Devuelve la comanda recargada para que el endpoint la serialice sin otra consulta.
    """
    comanda = await obtener_comanda(session, comanda_id)
    monedas = await monedas_activas(session)
    await publicar(canal_sucursal(comanda.sucursal_id), tipo, resumen_comanda(comanda))
    await publicar(canal_pedido(comanda.tracking_token), "pedido.actualizado", serializar_publico(comanda, monedas))
    return comanda, monedas


# ---------------------------------------------------------------- operaciones
async def _validar_mesa(session: AsyncSession, mesa_id: int, sucursal_id: int) -> Mesa:
    mesa = await session.get(Mesa, mesa_id)
    if not mesa or mesa.sucursal_id != sucursal_id:
        raise NoEncontrado("Mesa")
    if not mesa.activa:
        raise Conflicto("La mesa está inactiva")
    return mesa


async def _flush_con_bloqueo_mesa(session: AsyncSession) -> None:
    try:
        await session.flush()
    except IntegrityError as e:
        if "uq_comandas_mesa_abierta" in str(e.orig):
            await session.rollback()
            raise MesaBloqueada() from e
        raise


async def mesa_principal_id(session: AsyncSession, mesa_id: int) -> int:
    """Una mesa unida a otra no tiene comanda propia: vive en la principal."""
    unida = await session.scalar(select(Mesa.unida_a_id).where(Mesa.id == mesa_id))
    return unida or mesa_id


async def mesa_ocupada(session: AsyncSession, mesa_id: int) -> int | None:
    principal = await mesa_principal_id(session, mesa_id)
    return await session.scalar(
        select(Comanda.id).where(Comanda.mesa_id == principal, Comanda.estado == EstadoComanda.abierta)
    )


async def unir_mesas(session: AsyncSession, principal: Mesa, otras: list[Mesa]) -> None:
    """Junta mesas para un grupo grande: la comanda de la principal cubre a todas."""
    if principal.unida_a_id is not None:
        raise Conflicto("Esa mesa ya está unida a otra; sepárala primero")
    for m in otras:
        if m.id == principal.id:
            raise Invalido("Una mesa no se puede unir consigo misma")
        if m.sucursal_id != principal.sucursal_id:
            raise Invalido("Las mesas deben ser de la misma sucursal")
        if m.unida_a_id not in (None, principal.id):
            raise Conflicto(f"La mesa {m.nombre} ya está unida a otra")
        if await session.scalar(select(Mesa.id).where(Mesa.unida_a_id == m.id)):
            raise Conflicto(f"La mesa {m.nombre} tiene otras unidas; sepáralas primero")
        if await mesa_ocupada(session, m.id) and m.unida_a_id is None:
            raise Conflicto(f"La mesa {m.nombre} tiene una comanda abierta; ciérrala antes de unirla")
    for m in otras:
        m.unida_a_id = principal.id
    await session.flush()


async def separar_mesas(session: AsyncSession, mesa_id: int) -> None:
    """Deshace la unión de una mesa unida, o de todo el grupo si es la principal."""
    await session.execute(update(Mesa).where((Mesa.unida_a_id == mesa_id) | (Mesa.id == mesa_id)).values(unida_a_id=None))


async def crear_comanda(
    session: AsyncSession,
    *,
    sucursal_id: int,
    origen: OrigenComanda,
    items: list[ItemIn],
    mesa_id: int | None = None,
    cliente_id: int | None = None,
    nombre_cliente: str | None = None,
    telefono_cliente: str | None = None,
    notas: str | None = None,
    usuario: Usuario | None = None,
) -> Comanda:
    if mesa_id is not None:
        await _validar_mesa(session, mesa_id, sucursal_id)
        mesa_id = await mesa_principal_id(session, mesa_id)  # una mesa unida pide en su principal
        if await mesa_ocupada(session, mesa_id):
            raise MesaBloqueada()
    if cliente_id is not None and not await session.get(Cliente, cliente_id):
        raise NoEncontrado("Cliente")

    comanda = Comanda(
        sucursal_id=sucursal_id,
        mesa_id=mesa_id,
        cliente_id=cliente_id,
        nombre_cliente=nombre_cliente,
        telefono_cliente=telefono_cliente,
        origen=origen,
        notas=notas,
        tracking_token=new_public_token(),
        creada_por_id=usuario.id if usuario else None,
        items=[],
        pagos=[],
    )
    session.add(comanda)
    # El índice único parcial resuelve la carrera de dos escaneos simultáneos
    await _flush_con_bloqueo_mesa(session)
    if items:
        await agregar_items(session, comanda, items, por_cliente=origen == OrigenComanda.qr)
    return comanda


PREFIJO_SIN = "SIN "
SEP_NOTAS = " · "


def _resolver_sin_insumos(producto: Producto, pedidos: list[int], nota: str | None) -> tuple[list[int], str | None]:
    """Valida los ingredientes que se quitan y arma la nota visible para cocina ("SIN cebolla · sin sal")."""
    ids = sorted(set(pedidos))
    if not ids:
        return [], nota
    quitables = {ri.insumo_id: ri.insumo.nombre for ri in producto.receta.ingredientes if ri.removible} if producto.receta else {}
    invalidos = [i for i in ids if i not in quitables]
    if invalidos:
        raise Invalido(f"{producto.nombre}: hay ingredientes que no se pueden quitar")
    sin = PREFIJO_SIN + ", ".join(quitables[i] for i in ids)
    return ids, (sin + SEP_NOTAS + nota if nota else sin)[:255]


def _nota_del_cliente(notas: str | None) -> str | None:
    """Quita el prefijo "SIN ..." de las notas dejando solo el texto libre."""
    if not notas or not notas.startswith(PREFIJO_SIN):
        return notas
    _, _, resto = notas.partition(SEP_NOTAS)
    return resto or None


async def cambiar_sin_insumos(session: AsyncSession, comanda: Comanda, item: ComandaItem, ids: list[int]) -> None:
    """Caja quita o repone ingredientes de un plato que aún no se envía (nada reservado todavía)."""
    _exigir_abierta(comanda)
    if item.estado != EstadoItem.pendiente:
        raise Conflicto("Solo se pueden cambiar los ingredientes de platos pendientes")
    producto = await session.get(Producto, item.producto_id)
    item.sin_insumo_ids, item.notas = _resolver_sin_insumos(producto, ids, _nota_del_cliente(item.notas))
    await session.flush()


async def agregar_items(
    session: AsyncSession, comanda: Comanda, items_in: list[ItemIn], *, por_cliente: bool
) -> list[ComandaItem]:
    _exigir_abierta(comanda)
    solicitados = Counter()
    for it in items_in:
        solicitados[it.producto_id] += it.cantidad
    if len(comanda.items) + sum(solicitados.values()) > MAX_ITEMS_POR_COMANDA:
        raise Invalido(f"Una comanda admite máximo {MAX_ITEMS_POR_COMANDA} platos")

    productos = {
        p.id: p for p in await session.scalars(select(Producto).where(Producto.id.in_(solicitados.keys())))
    }
    disponibles = await disponibles_por_insumo(session, comanda.sucursal_id) if por_cliente else {}
    errores = []
    for producto_id, cantidad in solicitados.items():
        p = productos.get(producto_id)
        if not p or not p.activo or not disponible_en_sucursal(p, comanda.sucursal_id):
            errores.append({"producto_id": producto_id, "error": "Producto no disponible"})
            continue
        if por_cliente:
            n = porciones(p, disponibles)
            if n is not None and n < cantidad:
                errores.append({"producto_id": producto_id, "error": f"Solo quedan {n} porciones de {p.nombre}"})
    if errores:
        raise Conflicto({"mensaje": "Algunos productos no están disponibles", "errores": errores})

    nuevos = []
    for it in items_in:
        p = productos[it.producto_id]
        sin_ids, notas = _resolver_sin_insumos(p, it.sin_insumo_ids, it.notas)
        # Se congela lo que paga el cliente (con IVA si la sucursal lo suma encima)
        precio = precio_final(p, comanda.sucursal)
        for _ in range(it.cantidad):
            item = ComandaItem(
                comanda_id=comanda.id,
                producto_id=p.id,
                nombre_producto=p.nombre,
                precio_unitario=precio,
                alicuota_iva=p.alicuota_iva,
                notas=notas,
                sin_insumo_ids=sin_ids,
                estacion_id=p.estacion_id,
                agregado_por_cliente=por_cliente,
                reservas=[],
            )
            comanda.items.append(item)
            nuevos.append(item)
    await session.flush()
    return nuevos


async def enviar_a_cocina(session: AsyncSession, comanda: Comanda, item_ids: list[int] | None = None) -> list[ComandaItem]:
    _exigir_abierta(comanda)
    pendientes = [i for i in comanda.items if i.estado == EstadoItem.pendiente]
    if item_ids is not None:
        ids = set(item_ids)
        desconocidos = ids - {i.id for i in comanda.items}
        if desconocidos:
            raise NoEncontrado(f"Items {sorted(desconocidos)}")
        pendientes = [i for i in pendientes if i.id in ids]
    if not pendientes:
        raise Conflicto("No hay platos pendientes para enviar a cocina")

    await stock.reservar_items(session, comanda.sucursal_id, pendientes)
    ahora = datetime.now(UTC)
    for item in pendientes:
        item.estado = EstadoItem.en_cocina
        item.enviado_en = ahora
    await session.flush()
    return pendientes


async def obtener_item(session: AsyncSession, item_id: int) -> tuple[Comanda, ComandaItem]:
    comanda_id = await session.scalar(select(ComandaItem.comanda_id).where(ComandaItem.id == item_id))
    if not comanda_id:
        raise NoEncontrado("Plato")
    comanda = await obtener_comanda(session, comanda_id, bloquear=True)
    item = next(i for i in comanda.items if i.id == item_id)
    return comanda, item


async def cambiar_estado_cocina(
    session: AsyncSession, comanda: Comanda, item: ComandaItem, estado: EstadoItem, usuario: Usuario
) -> None:
    _exigir_abierta(comanda)
    if item.estado not in ESTADOS_ACTIVOS_COCINA:
        raise Conflicto(f"El plato está {item.estado.value}, no en cocina")
    if estado == EstadoItem.preparando:
        if item.estado != EstadoItem.en_cocina:
            raise Conflicto("El plato ya está en preparación")
        item.estado = EstadoItem.preparando
    elif estado == EstadoItem.listo:
        await stock.consumir_item(session, item, usuario.id)
        item.estado = EstadoItem.listo
        item.listo_en = datetime.now(UTC)
        item.listo_por_id = usuario.id
    await session.flush()


async def entregar_item(session: AsyncSession, comanda: Comanda, item: ComandaItem) -> None:
    _exigir_abierta(comanda)
    if item.estado != EstadoItem.listo:
        raise Conflicto("Solo se pueden entregar platos listos")
    item.estado = EstadoItem.entregado
    item.entregado_en = datetime.now(UTC)
    await session.flush()


async def cancelar_item(session: AsyncSession, comanda: Comanda, item: ComandaItem) -> None:
    _exigir_abierta(comanda)
    if item.estado in ESTADOS_FACTURABLES:
        raise Conflicto("El plato ya fue preparado; no se puede cancelar")
    if item.estado == EstadoItem.cancelado:
        raise Conflicto("El plato ya está cancelado")
    if item.estado in ESTADOS_ACTIVOS_COCINA:
        await stock.liberar_item(session, item)
    item.estado = EstadoItem.cancelado
    item.cancelado_en = datetime.now(UTC)
    await session.flush()


async def cancelar_comanda(session: AsyncSession, comanda: Comanda, motivo: str, usuario: Usuario | None) -> None:
    _exigir_abierta(comanda)
    if comanda.pagos:
        raise Conflicto("La comanda tiene pagos registrados; elimínalos antes de cancelar")
    ahora = datetime.now(UTC)
    for item in comanda.items:
        if item.estado in ESTADOS_ACTIVOS_COCINA:
            await stock.liberar_item(session, item)
        if item.estado not in ESTADOS_FACTURABLES and item.estado != EstadoItem.cancelado:
            item.estado = EstadoItem.cancelado
            item.cancelado_en = ahora
    comanda.estado = EstadoComanda.cancelada
    if comanda.mesa_id:
        await separar_mesas(session, comanda.mesa_id)
    comanda.motivo_cancelacion = motivo
    comanda.cerrada_en = ahora
    comanda.cerrada_por_id = usuario.id if usuario else None
    await session.flush()


async def actualizar_comanda(session: AsyncSession, comanda: Comanda, datos: dict) -> None:
    _exigir_abierta(comanda)
    if "mesa_id" in datos and datos["mesa_id"] != comanda.mesa_id:
        if datos["mesa_id"] is not None:
            await _validar_mesa(session, datos["mesa_id"], comanda.sucursal_id)
    if datos.get("cliente_id") is not None and not await session.get(Cliente, datos["cliente_id"]):
        raise NoEncontrado("Cliente")
    for campo, valor in datos.items():
        setattr(comanda, campo, valor)
    await _flush_con_bloqueo_mesa(session)


async def registrar_pago(
    session: AsyncSession,
    comanda: Comanda,
    *,
    moneda_id: int,
    monto: Decimal,
    metodo,
    referencia: str | None,
    etiqueta: str | None,
    usuario: Usuario,
) -> Pago:
    _exigir_abierta(comanda)
    moneda = await session.get(Moneda, moneda_id)
    if not moneda or not moneda.activa:
        raise NoEncontrado("Moneda")
    total = a_pagar_comanda(comanda)
    if total <= 0:
        raise Conflicto("La comanda no tiene platos por cobrar")
    if pagado_comanda(comanda) >= total:
        raise Conflicto("La comanda ya está pagada por completo")

    monto_principal = a_principal(monto, moneda.tasa, moneda.operacion)
    # Pago en divisas en una sucursal agente de percepción: el pago incluye el IGTF
    # (monto = abono + 3 %), así que la parte de impuesto es monto · 3/103.
    igtf = CERO
    if comanda.sucursal.cobra_igtf and moneda.es_divisa:
        pct = config.get("igtf_porcentaje")
        igtf = q2(monto_principal * pct / (100 + pct))
    turno_id = await session.scalar(
        select(TurnoCaja.id).where(TurnoCaja.sucursal_id == comanda.sucursal_id, TurnoCaja.estado == EstadoTurno.abierto)
    )

    pago = Pago(
        comanda_id=comanda.id,
        moneda_id=moneda.id,
        moneda=moneda,
        monto=monto,
        tasa=moneda.tasa,
        operacion=moneda.operacion,
        monto_principal=monto_principal,
        igtf=igtf,
        turno_id=turno_id,
        metodo=metodo,
        referencia=referencia,
        etiqueta=etiqueta,
        registrado_por_id=usuario.id,
    )
    comanda.pagos.append(pago)
    await session.flush()
    return pago


async def eliminar_pago(session: AsyncSession, comanda: Comanda, pago_id: int) -> None:
    _exigir_abierta(comanda)
    pago = next((p for p in comanda.pagos if p.id == pago_id), None)
    if not pago:
        raise NoEncontrado("Pago")
    comanda.pagos.remove(pago)
    await session.delete(pago)
    await session.flush()


async def cerrar_comanda(session: AsyncSession, comanda: Comanda, usuario: Usuario) -> Venta:
    _exigir_abierta(comanda)
    sin_terminar = [
        i.id for i in comanda.items if i.estado in (EstadoItem.pendiente, *ESTADOS_ACTIVOS_COCINA)
    ]
    if sin_terminar:
        raise Conflicto(
            {
                "mensaje": "Hay platos sin terminar. Márcalos listos o cancélalos antes de cerrar.",
                "item_ids": sin_terminar,
            }
        )
    facturables = [i for i in comanda.items if i.estado in ESTADOS_FACTURABLES]
    if not facturables:
        raise Conflicto("La comanda no tiene platos para facturar; cancélala en su lugar")

    total = total_comanda(comanda)
    a_pagar = a_pagar_comanda(comanda)
    pagado = pagado_comanda(comanda)
    if pagado < a_pagar:
        raise Conflicto({"mensaje": "Pago incompleto", "total": a_pagar, "pagado": pagado, "pendiente": a_pagar - pagado})

    ahora = datetime.now(UTC)
    for item in facturables:
        if item.estado == EstadoItem.listo:
            item.estado = EstadoItem.entregado
            item.entregado_en = ahora
    comanda.estado = EstadoComanda.cerrada
    if comanda.mesa_id:
        await separar_mesas(session, comanda.mesa_id)  # el grupo se fue: las mesas vuelven a su lugar
    comanda.cerrada_en = ahora
    comanda.cerrada_por_id = usuario.id

    venta = Venta(
        comanda_id=comanda.id,
        sucursal_id=comanda.sucursal_id,
        cliente_id=comanda.cliente_id,
        total=total,
        descuento=descuento_comanda(comanda),
        propina=q2(comanda.propina or CERO),
        igtf=igtf_comanda(comanda),
        pagado=pagado,
        vuelto=pagado - a_pagar,
        cantidad_items=len(facturables),
        cerrada_por_id=usuario.id,
    )
    # Congela la tasa de la moneda fiscal (Bs) con la que pagó el cliente: la del último pago
    # en bolívares; si pagó todo en divisas, la vigente al cobrar.
    fiscal = await session.scalar(select(Moneda).where(Moneda.es_fiscal.is_(True)))
    if fiscal:
        pago_fiscal = next((p for p in reversed(comanda.pagos) if p.moneda_id == fiscal.id), None)
        venta.moneda_fiscal = fiscal.codigo
        if pago_fiscal:
            venta.tasa_fiscal, venta.operacion_fiscal = pago_fiscal.tasa, pago_fiscal.operacion
        elif fiscal.es_principal:
            venta.tasa_fiscal, venta.operacion_fiscal = Decimal(1), Operacion.multiplicar
        else:
            venta.tasa_fiscal, venta.operacion_fiscal = fiscal.tasa, fiscal.operacion
    session.add(venta)
    await session.flush()
    return venta


# ---------------------------------------------------------------- división de cuenta
def _pagado_por_etiqueta(comanda: Comanda) -> dict[str, Decimal]:
    pagado: dict[str, Decimal] = defaultdict(lambda: CERO)
    for p in comanda.pagos:
        if p.etiqueta:
            pagado[p.etiqueta] += p.monto_principal - (p.igtf or CERO)
    return pagado


def dividir_partes_iguales(comanda: Comanda, partes: int, monedas: list[Moneda]) -> dict:
    total = a_pagar_comanda(comanda)
    base = q2(total / partes)
    montos = [base] * partes
    montos[-1] = total - base * (partes - 1)  # el último absorbe el redondeo
    pagado = _pagado_por_etiqueta(comanda)
    return {
        "total": total,
        "pendiente": max(total - pagado_comanda(comanda), CERO),
        "partes": [
            {
                "etiqueta": f"Parte {n}",
                "monto": m,
                "montos_monedas": montos_en_monedas(m, monedas),
                "pagado": pagado.get(f"Parte {n}", CERO),
            }
            for n, m in enumerate(montos, start=1)
        ],
    }


def dividir_por_items(comanda: Comanda, grupos: list, monedas: list[Moneda]) -> dict:
    vigentes = {i.id: i for i in items_vigentes(comanda)}
    # Descuento y propina se reparten en proporción a lo que consume cada grupo
    sub = subtotal_comanda(comanda)
    factor = a_pagar_comanda(comanda) / sub if sub else Decimal(1)
    asignados: set[int] = set()
    pagado = _pagado_por_etiqueta(comanda)
    partes = []
    for g in grupos:
        ids = set(g.item_ids)
        if desconocidos := ids - vigentes.keys():
            raise Invalido(f"Items inexistentes o cancelados: {sorted(desconocidos)}")
        if repetidos := ids & asignados:
            raise Invalido(f"Items asignados a más de un grupo: {sorted(repetidos)}")
        asignados |= ids
        monto = q2(sum((vigentes[i].precio_unitario for i in ids if not vigentes[i].cortesia), CERO) * factor)
        partes.append(
            {
                "etiqueta": g.etiqueta,
                "monto": monto,
                "montos_monedas": montos_en_monedas(monto, monedas),
                "pagado": pagado.get(g.etiqueta, CERO),
                "item_ids": sorted(ids),
            }
        )
    total = a_pagar_comanda(comanda)
    sin_asignar = max(total - sum((p["monto"] for p in partes), CERO), CERO)
    return {
        "total": total,
        "pendiente": max(total - pagado_comanda(comanda), CERO),
        "partes": partes,
        "sin_asignar": sin_asignar,
    }



# ---------------------------------------------------------------- descuentos, propina y cortesías
async def aplicar_descuento(session: AsyncSession, comanda: Comanda, tipo, valor, motivo) -> None:
    _exigir_abierta(comanda)
    if tipo is None:
        comanda.descuento_tipo = comanda.descuento_valor = comanda.descuento_motivo = None
    else:
        if tipo == TipoDescuento.porcentaje and valor > 100:
            raise Invalido("El descuento no puede pasar de 100 %")
        comanda.descuento_tipo, comanda.descuento_valor, comanda.descuento_motivo = tipo, valor, motivo
    if pagado_comanda(comanda) > a_pagar_comanda(comanda):
        raise Conflicto("Con ese descuento lo ya pagado supera el total; elimina algún pago primero")
    await session.flush()


async def fijar_propina(session: AsyncSession, comanda: Comanda, monto: Decimal) -> None:
    _exigir_abierta(comanda)
    comanda.propina = q2(monto)
    await session.flush()


async def marcar_cortesia(session: AsyncSession, comanda: Comanda, item: ComandaItem, cortesia: bool, motivo: str | None) -> None:
    _exigir_abierta(comanda)
    if item.estado == EstadoItem.cancelado:
        raise Conflicto("El plato está cancelado")
    item.cortesia = cortesia
    item.cortesia_motivo = motivo if cortesia else None
    if pagado_comanda(comanda) > a_pagar_comanda(comanda):
        raise Conflicto("Lo ya pagado supera el nuevo total; elimina algún pago primero")
    await session.flush()


async def cancelar_por_vencimiento(session: AsyncSession, comanda: Comanda, minutos: int) -> None:
    """Pedido por QR que nadie confirmó a tiempo: se cancela y libera la mesa."""
    await cancelar_comanda(session, comanda, f"Sin confirmar en {minutos} minutos", None)


# ---------------------------------------------------------------- chat mesa <-> caja
async def listar_mensajes(session: AsyncSession, comanda_id: int) -> list[MensajeComanda]:
    return list(
        await session.scalars(
            select(MensajeComanda).where(MensajeComanda.comanda_id == comanda_id).order_by(MensajeComanda.id)
        )
    )


async def enviar_mensaje(
    session: AsyncSession, comanda: Comanda, autor: AutorMensaje, texto: str, autor_nombre: str | None
) -> MensajeComanda:
    """Guarda el mensaje y lo publica al panel de la sucursal y al link del cliente (tras el commit)."""
    _exigir_abierta(comanda)
    msg = MensajeComanda(comanda_id=comanda.id, autor=autor, autor_nombre=autor_nombre, texto=texto)
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    datos = {
        "id": msg.id,
        "autor": msg.autor,
        "autor_nombre": msg.autor_nombre,
        "texto": msg.texto,
        "created_at": msg.created_at,
    }
    emitir(session, canal_pedido(comanda.tracking_token), "chat.mensaje", datos)
    emitir(
        session,
        canal_sucursal(comanda.sucursal_id),
        "chat.mensaje",
        {**datos, "comanda_id": comanda.id, "mesa": comanda.mesa.nombre if comanda.mesa else None},
    )
    return msg
