"""Pedidos por QR sin confirmar: si caja no aprueba ningún plato en N minutos, se cancelan
solos y la mesa queda libre (el cliente ya lo vio anunciado al pedir)."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, select

from app.core.database import SessionLocal
from app.core.realtime import commit_y_publicar
from app.core.redis import redis_client
from app.models import Bitacora, Comanda, ComandaItem, EstadoComanda, EstadoItem, OrigenComanda, Pago
from app.services import comandas as srv
from app.services import config

logger = logging.getLogger("restify.vencimientos")


async def cancelar_vencidas(minutos: int | None = None) -> list[int]:
    minutos = config.get("qr_vencimiento_min") if minutos is None else minutos
    if minutos <= 0:
        return []
    limite = datetime.now(UTC) - timedelta(minutes=minutos)
    confirmado = exists().where(
        ComandaItem.comanda_id == Comanda.id, ComandaItem.estado.not_in([EstadoItem.pendiente, EstadoItem.cancelado])
    )
    canceladas = []
    async with SessionLocal() as session:
        ids = list(
            await session.scalars(
                select(Comanda.id).where(
                    Comanda.origen == OrigenComanda.qr,
                    Comanda.estado == EstadoComanda.abierta,
                    Comanda.created_at < limite,
                    ~confirmado,
                    ~exists().where(Pago.comanda_id == Comanda.id),
                )
            )
        )
        for comanda_id in ids:
            comanda = await srv.obtener_comanda(session, comanda_id, bloquear=True)
            if comanda.estado != EstadoComanda.abierta or comanda.pagos:
                continue
            await srv.cancelar_por_vencimiento(session, comanda, minutos)
            session.add(
                Bitacora(
                    usuario_nombre="Sistema",
                    sucursal_id=comanda.sucursal_id,
                    modulo="comandas",
                    accion="vencida",
                    descripcion=f"Canceló el pedido por QR #{comanda.id} porque nadie lo confirmó en {minutos} minutos",
                    entidad="comanda",
                    entidad_id=comanda.id,
                )
            )
            await commit_y_publicar(session)
            await srv.notificar(session, comanda.id, "comanda.cancelada")
            canceladas.append(comanda.id)
    if canceladas:
        logger.info("Pedidos QR vencidos cancelados: %s", canceladas)
    return canceladas


async def bucle() -> None:
    """Revisa cada minuto. Con varios workers, un candado en Redis evita trabajo doble."""
    while True:
        await asyncio.sleep(60)
        try:
            if await redis_client.set("lock:vencimientos", 1, nx=True, ex=55):
                await config.refrescar()
                await cancelar_vencidas()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falló la revisión de pedidos vencidos")
