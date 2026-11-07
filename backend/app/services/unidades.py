"""Unidades de medida dinámicas: las de fábrica siempre existen; el administrador agrega las suyas."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Invalido
from app.models import UNIDADES_BASE, UnidadMedida


async def asegurar_base(session: AsyncSession) -> None:
    """Crea las unidades de fábrica que falten (idempotente)."""
    existentes = set(await session.scalars(select(UnidadMedida.codigo)))
    nuevas = [
        UnidadMedida(
            codigo=c, nombre=n, abreviatura=a, permite_decimales=d, subunidad_abreviatura=sa, factor_subunidad=f, es_base=True
        )
        for c, n, a, d, sa, f in UNIDADES_BASE
        if c not in existentes
    ]
    if nuevas:
        session.add_all(nuevas)
        await session.flush()


async def unidad_activa(session: AsyncSession, codigo: str) -> UnidadMedida:
    await asegurar_base(session)
    unidad = await session.scalar(select(UnidadMedida).where(UnidadMedida.codigo == codigo))
    if unidad is None:
        raise Invalido(f"La unidad «{codigo}» no existe; créala en Unidades de medida")
    if not unidad.activa:
        raise Invalido(f"La unidad «{unidad.nombre}» está desactivada")
    return unidad
