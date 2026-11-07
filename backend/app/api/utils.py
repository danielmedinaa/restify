from typing import Annotated, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflicto, NoEncontrado
from app.core.realtime import commit_y_publicar

M = TypeVar("M")

Limite = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


async def obtener_o_404(session: AsyncSession, modelo: type[M], id_: int, nombre: str) -> M:
    obj = await session.get(modelo, id_)
    if obj is None:
        raise NoEncontrado(nombre)
    return obj


async def paginar(session: AsyncSession, stmt: Select, limite: int, offset: int) -> dict:
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = (await session.scalars(stmt.limit(limite).offset(offset))).unique().all()
    return {"total": total or 0, "limite": limite, "offset": offset, "items": list(items)}


def aplicar_cambios(obj, datos: BaseModel, excluir: set[str] | None = None) -> dict:
    """Aplica los campos enviados y devuelve solo los que de verdad cambiaron (para la bitácora)."""
    enviados = datos.model_dump(exclude_unset=True, exclude=excluir or set())
    cambios = {campo: valor for campo, valor in enviados.items() if getattr(obj, campo, None) != valor}
    for campo, valor in enviados.items():
        setattr(obj, campo, valor)
    return cambios


def _conflicto(e: IntegrityError, mensaje_duplicado: str) -> Conflicto:
    codigo = getattr(e.orig, "sqlstate", None) or getattr(getattr(e.orig, "__cause__", None), "sqlstate", None)
    if codigo == "23503":
        return Conflicto("El registro está en uso o referencia datos inexistentes")
    return Conflicto(mensaje_duplicado)


async def guardar(session: AsyncSession, mensaje_duplicado: str = "Ya existe un registro con esos datos") -> None:
    """Commit + publicación de eventos; convierte violaciones de unicidad/FK en 409."""
    try:
        await commit_y_publicar(session)
    except IntegrityError as e:
        await session.rollback()
        raise _conflicto(e, mensaje_duplicado) from e


async def insertar(session: AsyncSession, mensaje_duplicado: str = "Ya existe un registro con esos datos") -> None:
    """Flush para obtener id y valores generados (código interno) antes del commit, con el mismo 409."""
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise _conflicto(e, mensaje_duplicado) from e
