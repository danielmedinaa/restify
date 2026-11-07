from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import NoAutenticado, Prohibido
from app.core.security import constant_time_equals, decode_access_token, parse_api_key_prefix, sha256
from app.models import Accion, ApiKey, Modulo, Usuario
from app.services import seguridad
from app.services.bitacora import ip_actual

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def verificar_api_key(
    request: Request,
    session: SessionDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key", max_length=200)] = None,
) -> ApiKey:
    """Toda app cliente (panel, cocina, menú público) debe enviar una API key válida."""
    ip = request.client.host if request.client else None
    if not x_api_key or not (prefijo := parse_api_key_prefix(x_api_key)):
        await seguridad.senal("api_key_invalida", ip)
        raise NoAutenticado("API key requerida o inválida")
    api_key = await session.scalar(select(ApiKey).where(ApiKey.prefijo == prefijo, ApiKey.activa.is_(True)))
    if not api_key or not constant_time_equals(api_key.key_hash, sha256(x_api_key)):
        await seguridad.senal("api_key_invalida", ip)
        raise NoAutenticado("API key requerida o inválida")

    ahora = datetime.now(UTC)
    if not api_key.ultimo_uso or ahora - api_key.ultimo_uso > timedelta(minutes=5):
        await session.execute(update(ApiKey).where(ApiKey.id == api_key.id).values(ultimo_uso=ahora))
        await session.commit()
    request.state.api_key_id = api_key.id
    return api_key


async def usuario_desde_token(session: AsyncSession, token: str) -> Usuario:
    try:
        payload = decode_access_token(token)
        usuario_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise NoAutenticado("Token inválido o expirado")

    usuario = await session.get(Usuario, usuario_id)
    if not usuario or not usuario.activo or usuario.token_version != payload["tv"]:
        raise NoAutenticado("Token inválido o expirado")
    return usuario


async def get_usuario_actual(
    request: Request,
    session: SessionDep,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if not credenciales or credenciales.scheme.lower() != "bearer":
        raise NoAutenticado()
    usuario = await usuario_desde_token(session, credenciales.credentials)
    request.state.usuario_id = usuario.id
    ip_actual.set(request.client.host if request.client else None)
    return usuario


UsuarioActual = Annotated[Usuario, Depends(get_usuario_actual)]


def requiere(modulo: Modulo, accion: Accion):
    """Dependencia: exige el permiso CRUD del módulo según el rol del usuario."""

    async def dependency(usuario: UsuarioActual) -> Usuario:
        if not usuario.puede(modulo, accion):
            await seguridad.senal(
                "acceso_denegado", f"usuario:{usuario.id}", usuario_id=usuario.id,
                accion=f"{accion.value} en {modulo.value}", ip=ip_actual.get(),
            )
            raise Prohibido(f"Sin permiso para {accion.value} en {modulo.value}")
        return usuario

    return dependency


async def requiere_superadmin(usuario: UsuarioActual) -> Usuario:
    if not usuario.es_superadmin:
        raise Prohibido("Solo un superadministrador puede realizar esta acción")
    return usuario


def verificar_sucursal(usuario: Usuario, sucursal_id: int) -> None:
    if not usuario.accede_sucursal(sucursal_id):
        raise Prohibido("No tienes acceso a esta sucursal")


def sucursales_visibles(usuario: Usuario, sucursal_id: int | None) -> list[int] | None:
    """Filtro de sucursales para listados. None = sin restricción (superadmin sin filtro)."""
    if sucursal_id is not None:
        verificar_sucursal(usuario, sucursal_id)
        return [sucursal_id]
    if usuario.es_superadmin:
        return None
    return list(usuario.sucursal_ids())
