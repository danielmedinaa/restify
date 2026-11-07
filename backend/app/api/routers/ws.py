"""WebSockets en tiempo real.

Personal (caja, cocina, admin):
  1. POST /api/v1/auth/ws-ticket  (con JWT + API key)  -> ticket de un solo uso, 30 s
  2. WS   /ws/staff?ticket=...&sucursal_id=1
  Eventos: comanda.creada, comanda.actualizada, comanda.cerrada, comanda.cancelada,
           comanda.items_cliente, cocina.nuevos, cocina.item_actualizado,
           stock.alerta, stock.alerta_resuelta, menu.actualizado

Cliente:
  WS /ws/pedidos/{tracking_token}
  Eventos: pedido.actualizado (snapshot completo del pedido)
"""

import asyncio
import contextlib
import json

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.realtime import canal_pedido, canal_sucursal, serializar
from app.core.redis import redis_client
from app.models import Comanda, Modulo, Sucursal, Usuario
from app.services.comandas import serializar_publico
from app.services.seguridad import CANAL_SEGURIDAD
from app.services.monedas import monedas_activas

router = APIRouter()

PING_SEG = 25


async def _retransmitir(websocket: WebSocket, canales: list[str]) -> None:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(*canales)

    async def desde_redis():
        async for mensaje in pubsub.listen():
            if mensaje["type"] == "message":
                await websocket.send_text(mensaje["data"])

    async def desde_cliente():
        # Solo escuchamos para detectar desconexión; se ignora cualquier contenido
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=PING_SEG)
            except TimeoutError:
                await websocket.send_text(json.dumps({"tipo": "ping"}))

    tareas = [asyncio.create_task(desde_redis()), asyncio.create_task(desde_cliente())]
    try:
        await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tareas:
            t.cancel()
        for t in tareas:
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, Exception):
                await t
        await pubsub.unsubscribe()
        await pubsub.aclose()


@router.websocket("/ws/staff")
async def ws_staff(
    websocket: WebSocket,
    ticket: str = Query(max_length=100),
    sucursal_id: int | None = Query(default=None),
):
    usuario_id = await redis_client.getdel(f"ws-ticket:{ticket}")
    if not usuario_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    async with SessionLocal() as session:
        usuario = await session.get(Usuario, int(usuario_id))
        if not usuario or not usuario.activo:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        modulos_tiempo_real = (Modulo.comandas, Modulo.caja, Modulo.cocina, Modulo.inventario)
        if not any(usuario.puede(m, "leer") for m in modulos_tiempo_real):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if sucursal_id is not None:
            if not usuario.accede_sucursal(sucursal_id):
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return
            sucursales = [sucursal_id]
        elif usuario.es_superadmin:
            sucursales = list(await session.scalars(select(Sucursal.id)))
        else:
            sucursales = list(usuario.sucursal_ids())
        # Las alertas de seguridad solo le llegan al superadmin
        extra = [CANAL_SEGURIDAD] if usuario.es_superadmin else []

    if not sucursales:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await websocket.send_text(json.dumps({"tipo": "conectado", "data": {"sucursales": sucursales}}))
    await _retransmitir(websocket, [canal_sucursal(s) for s in sucursales] + extra)


@router.websocket("/ws/pedidos/{tracking_token}")
async def ws_pedido(websocket: WebSocket, tracking_token: str):
    if len(tracking_token) > 64:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    async with SessionLocal() as session:
        comanda = await session.scalar(select(Comanda).where(Comanda.tracking_token == tracking_token))
        if not comanda:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        inicial = serializar_publico(comanda, await monedas_activas(session))

    await websocket.accept()
    await websocket.send_text(json.dumps({"tipo": "pedido.actualizado", "data": serializar(inicial)}))
    await _retransmitir(websocket, [canal_pedido(tracking_token)])
