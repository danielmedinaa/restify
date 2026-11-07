"""Eventos en tiempo real vía Redis pub/sub (funciona con varios workers/réplicas).

Los servicios encolan eventos en la sesión con `emitir()` y se publican solo
después de un commit exitoso con `commit_y_publicar()`, para no notificar
cambios que terminaron en rollback.
"""

import json
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client

_EVENTOS_KEY = "eventos_pendientes"


def canal_sucursal(sucursal_id: int) -> str:
    return f"restify:sucursal:{sucursal_id}"


def canal_pedido(tracking_token: str) -> str:
    return f"restify:pedido:{tracking_token}"


def emitir(session: AsyncSession, canal: str, tipo: str, data: Any) -> None:
    session.info.setdefault(_EVENTOS_KEY, []).append((canal, tipo, data))


def serializar(data: Any) -> Any:
    """Igual que las respuestas REST: el dinero y las cantidades (Decimal) viajan como
    string. jsonable_encoder por defecto los convierte a float y perdería precisión."""
    return jsonable_encoder(data, custom_encoder={Decimal: str})


async def publicar(canal: str, tipo: str, data: Any) -> None:
    await redis_client.publish(canal, json.dumps({"tipo": tipo, "data": serializar(data)}))


async def commit_y_publicar(session: AsyncSession) -> None:
    await session.commit()
    eventos = session.info.pop(_EVENTOS_KEY, [])
    for canal, tipo, data in eventos:
        if callable(data):
            data = await data()
        await publicar(canal, tipo, data)
