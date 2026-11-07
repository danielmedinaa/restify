"""Turnos de caja y arqueo.

Efectivo esperado en la gaveta, por moneda:
    fondo + cobrado en efectivo + ingresos - retiros - vueltos

El vuelto se asume entregado en efectivo de la moneda principal (es como lo calcula caja).
Los métodos que no son efectivo (tarjeta, pago móvil…) se listan para conciliar con el banco.
"""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comanda, EstadoTurno, MetodoPago, Moneda, Pago, TipoMovimientoCaja, TurnoCaja, Usuario, Venta
from app.services.monedas import q2

CERO = Decimal("0.00")


async def resumen_turno(session: AsyncSession, turno: TurnoCaja) -> dict:
    monedas = {m.id: m for m in await session.scalars(select(Moneda))}
    principal = next((m for m in monedas.values() if m.es_principal), None)
    hasta = turno.cerrado_en or datetime.now(UTC)

    pagos = list(await session.scalars(select(Pago).where(Pago.turno_id == turno.id)))
    por_metodo: dict[tuple, list] = defaultdict(lambda: [CERO, 0])
    efectivo_cobrado: dict[int, Decimal] = defaultdict(lambda: CERO)
    for p in pagos:
        acum = por_metodo[(p.metodo, p.moneda_id)]
        acum[0] += p.monto
        acum[1] += 1
        if p.metodo == MetodoPago.efectivo:
            efectivo_cobrado[p.moneda_id] += p.monto

    ventas = (
        await session.execute(
            select(
                func.count(Venta.id),
                func.coalesce(func.sum(Venta.total), 0),
                func.coalesce(func.sum(Venta.descuento), 0),
                func.coalesce(func.sum(Venta.propina), 0),
                func.coalesce(func.sum(Venta.igtf), 0),
                func.coalesce(func.sum(Venta.vuelto), 0),
            )
            .join(Comanda, Comanda.id == Venta.comanda_id)
            .where(
                Venta.sucursal_id == turno.sucursal_id,
                Venta.created_at >= turno.abierto_en,
                Venta.created_at <= hasta,
            )
        )
    ).one()
    n_ventas, facturado, descuentos, propinas, igtf, vueltos = ventas

    fondo = {int(f["moneda_id"]): Decimal(f["monto"]) for f in turno.fondo or []}
    ingresos: dict[int, Decimal] = defaultdict(lambda: CERO)
    retiros: dict[int, Decimal] = defaultdict(lambda: CERO)
    for m in turno.movimientos:
        (ingresos if m.tipo == TipoMovimientoCaja.ingreso else retiros)[m.moneda_id] += m.monto

    ids = set(fondo) | set(efectivo_cobrado) | set(ingresos) | set(retiros) | ({principal.id} if principal else set())
    efectivo = []
    for mid in sorted(ids, key=lambda i: (not monedas[i].es_principal, monedas[i].codigo)):
        m = monedas[mid]
        vuelto_m = q2(Decimal(vueltos)) if m.es_principal else CERO
        esperado = fondo.get(mid, CERO) + efectivo_cobrado[mid] + ingresos[mid] - retiros[mid] - vuelto_m
        efectivo.append(
            {
                "moneda_id": mid,
                "moneda": m.codigo,
                "simbolo": m.simbolo,
                "fondo": q2(fondo.get(mid, CERO)),
                "cobrado": q2(efectivo_cobrado[mid]),
                "ingresos": q2(ingresos[mid]),
                "retiros": q2(retiros[mid]),
                "vueltos": vuelto_m,
                "esperado": q2(esperado),
            }
        )

    return {
        "ventas": n_ventas,
        "facturado": q2(Decimal(facturado)),
        "descuentos": q2(Decimal(descuentos)),
        "propinas": q2(Decimal(propinas)),
        "igtf": q2(Decimal(igtf)),
        "vueltos": q2(Decimal(vueltos)),
        "por_metodo": [
            {
                "metodo": metodo,
                "moneda": monedas[mid].codigo,
                "simbolo": monedas[mid].simbolo,
                "monto": q2(monto),
                "cantidad": n,
            }
            for (metodo, mid), (monto, n) in sorted(por_metodo.items(), key=lambda x: (x[0][0].value, monedas[x[0][1]].codigo))
        ],
        "efectivo": efectivo,
    }


async def serializar_turno(session: AsyncSession, turno: TurnoCaja) -> dict:
    monedas = {m.id: m for m in await session.scalars(select(Moneda))}
    ids_usuarios = {turno.abierto_por_id, turno.cerrado_por_id, *(m.usuario_id for m in turno.movimientos)} - {None}
    nombres = dict((await session.execute(select(Usuario.id, Usuario.nombre).where(Usuario.id.in_(ids_usuarios)))).all())

    def mm(f: dict) -> dict:
        m = monedas[int(f["moneda_id"])]
        return {"moneda_id": m.id, "moneda": m.codigo, "simbolo": m.simbolo, "monto": Decimal(f["monto"])}

    return {
        "id": turno.id,
        "sucursal_id": turno.sucursal_id,
        "sucursal": turno.sucursal.nombre,
        "estado": turno.estado,
        "abierto_por": nombres.get(turno.abierto_por_id),
        "abierto_en": turno.abierto_en,
        "cerrado_por": nombres.get(turno.cerrado_por_id),
        "cerrado_en": turno.cerrado_en,
        "fondo": [mm(f) for f in turno.fondo or []],
        "movimientos": [
            {
                "id": m.id,
                "tipo": m.tipo,
                "moneda": m.moneda.codigo,
                "simbolo": m.moneda.simbolo,
                "monto": m.monto,
                "motivo": m.motivo,
                "usuario": nombres.get(m.usuario_id),
                "created_at": m.created_at,
            }
            for m in turno.movimientos
        ],
        "resumen": await resumen_turno(session, turno),
        "arqueo": [
            {**a, "moneda": monedas[a["moneda_id"]].codigo, "simbolo": monedas[a["moneda_id"]].simbolo} for a in turno.arqueo
        ]
        if turno.arqueo
        else None,
        "notas": turno.notas,
    }


async def turno_abierto(session: AsyncSession, sucursal_id: int) -> TurnoCaja | None:
    return await session.scalar(
        select(TurnoCaja).where(TurnoCaja.sucursal_id == sucursal_id, TurnoCaja.estado == EstadoTurno.abierto)
    )
