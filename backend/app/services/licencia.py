"""Suscripción de esta instancia: estado y límites del plan, consultados al panel de RESTIFY.

Se activa solo si PANEL_URL y PANEL_TOKEN están definidos; sin ellos no hay restricciones
(desarrollo y tests). La respuesta se guarda en memoria `licencia_cache_segundos`; si el panel no
responde se sigue con el último estado conocido, y si nunca respondió se deja operar (una caída
nuestra no debe tumbar el restaurante de un cliente que paga).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import config

logger = logging.getLogger("restify.licencia")

# Nombre del límite en el panel -> cómo se le dice al usuario
ETIQUETAS = {
    "max_sucursales": "sucursales",
    "max_salas": "salas",
    "max_mesas": "mesas",
    "max_productos": "productos",
    "max_usuarios": "usuarios",
}

MENSAJES_ESTADO = {
    "pausada": "Esta cuenta está pausada. Contacta a RESTIFY para reanudarla.",
    "suspendida": "Esta cuenta está suspendida. Contacta a RESTIFY para regularizarla.",
    "cancelada": "Esta cuenta fue dada de baja.",
    "pendiente": "Esta cuenta aún no está activa.",
}


@dataclass
class Licencia:
    acceso: bool = True
    subdominio: str | None = None
    estado: str = "activa"
    motivo: str | None = None
    plan: str | None = None
    vence_en: str | None = None
    limites: dict[str, int | None] = field(default_factory=dict)


_cache: Licencia | None = None
_expira = 0.0
_lock = asyncio.Lock()


def token() -> str:
    """El del .env (instancias antiguas) o el que el cliente escribió en la configuración inicial."""
    return settings.panel_token or str(config.get("panel_token") or "")


def activa() -> bool:
    return bool(settings.panel_url and token())


def requiere_token() -> bool:
    """¿Esta instancia se rige por un panel? Sin PANEL_URL (desarrollo) no hay token que pedir."""
    return bool(settings.panel_url)


def reiniciar() -> None:
    """Olvida lo guardado (pruebas)."""
    global _cache, _expira
    _cache, _expira = None, 0.0


async def _consultar(token_: str | None = None) -> Licencia | None:
    try:
        async with httpx.AsyncClient(timeout=settings.panel_timeout_segundos) as http:
            r = await http.get(settings.panel_url, headers={"Authorization": f"Bearer {token_ or token()}"})
    except httpx.HTTPError as e:
        logger.warning("No se pudo consultar el panel: %s", e)
        return None
    if r.status_code in (401, 403):
        # Token revocado o instancia eliminada: se trata como cuenta no activa
        logger.error("El panel rechazó el token de esta instancia (revocado o instancia eliminada)")
        return Licencia(acceso=False, estado="cancelada", motivo=None)
    if r.status_code != 200:
        logger.warning("El panel respondió %s", r.status_code)
        return None
    d = r.json()
    return Licencia(
        acceso=bool(d.get("acceso")),
        subdominio=d.get("subdominio"),
        estado=str(d.get("estado", "activa")),
        motivo=d.get("motivo"),
        plan=d.get("plan"),
        vence_en=d.get("vence_en"),
        limites=d.get("limites") or {},
    )


async def obtener() -> Licencia | None:
    """Licencia vigente, o None si el control está desactivado / el panel nunca respondió."""
    global _cache, _expira
    if not activa():
        return None
    if _cache is not None and time.monotonic() < _expira:
        return _cache
    async with _lock:
        if _cache is not None and time.monotonic() < _expira:
            return _cache
        nueva = await _consultar()
        if nueva is not None:
            _cache = nueva
            _expira = time.monotonic() + settings.licencia_cache_segundos
        else:
            _expira = time.monotonic() + 10  # reintenta pronto, mientras tanto usa lo último que sabe
        return _cache


def _error(codigo: str, mensaje: str, **extra) -> HTTPException:
    # 402: la cuenta o el plan no permiten esto. El front muestra `mensaje` tal cual.
    return HTTPException(status.HTTP_402_PAYMENT_REQUIRED, jsonable_encoder({"codigo": codigo, "mensaje": mensaje, **extra}))


async def exigir_acceso() -> None:
    """Dependencia global: bloquea todo si la suscripción no está activa."""
    lic = await obtener()
    if lic is not None and not lic.acceso:
        msg = MENSAJES_ESTADO.get(lic.estado, "El acceso a esta cuenta está bloqueado.")
        if lic.estado == "activa":
            msg = "La suscripción de esta cuenta venció. Contacta a RESTIFY para renovarla."
        raise _error("suscripcion_inactiva", msg, estado=lic.estado, motivo=lic.motivo)


async def exigir_cupo(session: AsyncSession, limite: str, contar: Select) -> None:
    """Antes de crear algo: falla si ya se llegó al máximo del plan. `contar` cuenta lo existente."""
    lic = await obtener()
    if lic is None:
        return
    maximo = lic.limites.get(limite)
    if maximo is None:  # ilimitado
        return
    actual = await session.scalar(select(func.count()).select_from(contar.subquery()))
    if (actual or 0) >= maximo:
        nombre = ETIQUETAS.get(limite, limite)
        raise _error(
            "limite_plan",
            f"Tu plan {lic.plan or ''} permite hasta {maximo} {nombre}. Pide un cambio de plan para agregar más.".replace("plan  ", "plan "),
            limite=limite,
            maximo=maximo,
            actual=actual,
        )


async def verificar_token(token_: str) -> Licencia:
    """Para la configuración inicial: ¿este token es de esta instancia y su cuenta está activa?"""
    lic = await _consultar(token_.strip())
    if lic is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No pudimos comunicarnos con RESTIFY para validar el token. Intenta de nuevo en un momento.")
    if lic.estado == "cancelada" and lic.subdominio is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Token incorrecto. Revisa que lo copiaste completo.")
    if settings.instancia_subdominio and lic.subdominio != settings.instancia_subdominio:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ese token es de otra instancia.")
    if not lic.acceso:
        raise _error("suscripcion_inactiva", MENSAJES_ESTADO.get(lic.estado, "La suscripción de esta cuenta no está activa."), estado=lic.estado, motivo=lic.motivo)
    return lic
