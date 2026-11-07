"""Endpoints para el cliente final (sin login). Requieren la API key de la app pública.

El acceso se basa en tokens opacos no adivinables:
  - qr_token: identifica la mesa (va en el QR impreso)
  - tracking_token: identifica un pedido (link de seguimiento que recibe quien pidió)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.api.utils import guardar
from app.core.errors import Conflicto, NoEncontrado
from app.core.ratelimit import check_rate_limit, rate_limit
from app.models import EstadoComanda, Mesa, OrigenComanda, Sucursal
from app.schemas.base import Schema
from app.schemas.catalogo import MenuOut
from app.models import AutorMensaje
from app.schemas.comandas import (
    AgregarItemsPublicoIn,
    ComandaQrIn,
    MensajeIn,
    MensajeOut,
    PedidoCreadoOut,
    PedidoPublicoOut,
)
from app.services import comandas as srv
from app.services import config
from app.services.menu import construir_menu
from app.services.monedas import monedas_activas

router = APIRouter(
    prefix="/public",
    tags=["Público (menú QR y seguimiento)"],
    dependencies=[Depends(rate_limit("publico", lambda: config.get("public_rate_limit_per_minute")))],
)

Token = Annotated[str, Path(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


class MesaPublicaOut(Schema):
    mesa: str
    sucursal: str
    ocupada: bool
    menu: MenuOut


async def _mesa_por_qr(session, qr_token: str) -> Mesa:
    mesa = await session.scalar(select(Mesa).where(Mesa.qr_token == qr_token))
    if not mesa or not mesa.activa or not mesa.qr_habilitado or not mesa.sucursal.activa:
        raise NoEncontrado("Mesa")
    return mesa


@router.get("/mesas/{qr_token}", response_model=MesaPublicaOut)
async def mesa_y_menu(qr_token: Token, session: SessionDep):
    """Lo que ve el cliente al escanear el QR: menú dinámico y si la mesa está ocupada."""
    mesa = await _mesa_por_qr(session, qr_token)
    return {
        "mesa": mesa.nombre,
        "sucursal": mesa.sucursal.nombre,
        "ocupada": await srv.mesa_ocupada(session, mesa.id) is not None,
        "menu": await construir_menu(session, mesa.sucursal),
    }


@router.post("/mesas/{qr_token}/comandas", response_model=PedidoCreadoOut, status_code=status.HTTP_201_CREATED)
async def pedir_desde_qr(qr_token: Token, datos: ComandaQrIn, session: SessionDep):
    """Crea la comanda de la mesa. Queda PENDIENTE hasta que caja la apruebe y la envíe a cocina.

    Si la mesa ya tiene una comanda abierta responde 423 (QR bloqueado).
    """
    await check_rate_limit(f"qr-pedido:{qr_token}", 5, 60)
    mesa = await _mesa_por_qr(session, qr_token)
    comanda = await srv.crear_comanda(
        session,
        sucursal_id=mesa.sucursal_id,
        origen=OrigenComanda.qr,
        items=datos.items,
        mesa_id=mesa.id,
        nombre_cliente=datos.nombre_cliente,
        telefono_cliente=datos.telefono_cliente,
        notas=datos.notas,
    )
    await guardar(session)
    comanda, monedas = await srv.notificar(session, comanda.id, "comanda.creada")
    return {
        "tracking_token": comanda.tracking_token,
        "seguimiento_url": srv.seguimiento_url(comanda),
        "pedido": srv.serializar_publico(comanda, monedas),
    }


@router.get("/sucursales/{sucursal_id}/menu", response_model=MenuOut)
async def menu_publico(sucursal_id: int, session: SessionDep):
    """Menú digital de una sucursal (sin mesa), p. ej. para la web o redes."""
    sucursal = await session.get(Sucursal, sucursal_id)
    if not sucursal or not sucursal.activa:
        raise NoEncontrado("Sucursal")
    return await construir_menu(session, sucursal)


@router.get("/pedidos/{tracking_token}", response_model=PedidoPublicoOut)
async def ver_pedido(tracking_token: Token, session: SessionDep):
    """Estado del pedido plato por plato (pendiente, en cocina, preparando, listo...)."""
    comanda = await srv.obtener_por_tracking(session, tracking_token)
    return srv.serializar_publico(comanda, await monedas_activas(session))


@router.post("/pedidos/{tracking_token}/items", response_model=PedidoPublicoOut)
async def agregar_al_pedido(tracking_token: Token, datos: AgregarItemsPublicoIn, session: SessionDep):
    """El cliente agrega más platos a su comanda abierta (quedan pendientes de aprobación de caja)."""
    await check_rate_limit(f"pedido-items:{tracking_token}", 10, 60)
    comanda = await srv.obtener_por_tracking(session, tracking_token, bloquear=True)
    if comanda.estado != EstadoComanda.abierta:
        raise Conflicto("El pedido ya fue cerrado")
    await srv.agregar_items(session, comanda, datos.items, por_cliente=True)
    await guardar(session)
    comanda, monedas = await srv.notificar(session, comanda.id, "comanda.items_cliente")
    return srv.serializar_publico(comanda, monedas)


@router.get("/pedidos/{tracking_token}/mensajes", response_model=list[MensajeOut])
async def ver_mensajes(tracking_token: Token, session: SessionDep):
    """Chat de la mesa con caja."""
    comanda = await srv.obtener_por_tracking(session, tracking_token)
    return await srv.listar_mensajes(session, comanda.id)


@router.post("/pedidos/{tracking_token}/mensajes", response_model=MensajeOut, status_code=status.HTTP_201_CREATED)
async def escribir_mensaje(tracking_token: Token, datos: MensajeIn, session: SessionDep):
    """El cliente le escribe a caja (pedir la cuenta, avisar de un cambio…)."""
    await check_rate_limit(f"chat:{tracking_token}", 12, 60)
    comanda = await srv.obtener_por_tracking(session, tracking_token, bloquear=True)
    msg = await srv.enviar_mensaje(session, comanda, AutorMensaje.cliente, datos.texto, comanda.nombre_cliente)
    await guardar(session)
    await session.refresh(msg)
    return msg
