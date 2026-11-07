from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflicto
from app.models import Moneda, Operacion

CENTAVO = Decimal("0.01")


def q2(valor: Decimal) -> Decimal:
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def desde_principal(monto: Decimal, tasa: Decimal, operacion: Operacion) -> Decimal:
    """Monto en moneda principal -> monto en la moneda indicada."""
    return q2(monto * tasa if operacion == Operacion.multiplicar else monto / tasa)


def a_principal(monto: Decimal, tasa: Decimal, operacion: Operacion) -> Decimal:
    """Monto en la moneda indicada -> monto en moneda principal."""
    return q2(monto / tasa if operacion == Operacion.multiplicar else monto * tasa)


async def monedas_activas(session: AsyncSession) -> list[Moneda]:
    result = await session.scalars(
        select(Moneda).where(Moneda.activa.is_(True)).order_by(Moneda.es_principal.desc(), Moneda.codigo)
    )
    return list(result)


async def moneda_principal(session: AsyncSession) -> Moneda:
    moneda = await session.scalar(select(Moneda).where(Moneda.es_principal.is_(True)))
    if not moneda:
        raise Conflicto("No hay moneda principal configurada")
    return moneda


def montos_en_monedas(monto: Decimal, monedas: list[Moneda]) -> list[dict]:
    return [
        {"moneda": m.codigo, "simbolo": m.simbolo, "monto": desde_principal(monto, m.tasa, m.operacion)}
        for m in monedas
    ]
