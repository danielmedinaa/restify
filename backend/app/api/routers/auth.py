import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select, update

from app.api.deps import SessionDep, UsuarioActual
from app.core.config import settings
from app.core.errors import NoAutenticado
from app.core.ratelimit import check_rate_limit, client_ip, rate_limit
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    hash_password,
    new_refresh_token,
    password_needs_rehash,
    sha256,
    verify_password,
)
from app.models import Modulo, RefreshToken, Usuario
from app.services import seguridad
from app.schemas.usuarios import CambiarPasswordIn, LoginIn, MeOut, RefreshIn, TokenOut, UsuarioOut, WsTicketOut
from app.services import config

router = APIRouter(prefix="/auth", tags=["Autenticación"])

WS_TICKET_TTL = 30


async def _emitir_tokens(session, usuario: Usuario, request: Request, familia: str | None = None) -> TokenOut:
    refresh = new_refresh_token()
    session.add(
        RefreshToken(
            usuario_id=usuario.id,
            token_hash=sha256(refresh),
            familia=familia or uuid.uuid4().hex,
            expira_en=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            ip=client_ip(request)[:64],
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    await session.commit()
    return TokenOut(
        access_token=create_access_token(usuario.id, usuario.token_version),
        refresh_token=refresh,
        expira_en_seg=settings.access_token_minutes * 60,
    )


async def revocar_sesiones(session, usuario_id: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.usuario_id == usuario_id, RefreshToken.revocado_en.is_(None))
        .values(revocado_en=func.now())
    )


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("login", 10))])
async def login(datos: LoginIn, request: Request, session: SessionDep):
    email = datos.email.lower()
    # Límite adicional por cuenta, sin importar la IP (frena ataques distribuidos)
    await check_rate_limit(f"login-email:{sha256(email)}", 20, 15 * 60)

    usuario = await session.scalar(select(Usuario).where(Usuario.email == email))
    ahora = datetime.now(UTC)
    bloqueado = bool(usuario and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora)
    ok = verify_password(datos.password, usuario.password_hash if usuario else None)

    if not usuario or not ok or not usuario.activo or bloqueado:
        ip = client_ip(request)
        if usuario and not bloqueado:
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= config.get("login_max_attempts"):
                usuario.bloqueado_hasta = ahora + timedelta(minutes=config.get("login_lock_minutes"))
                usuario.intentos_fallidos = 0
                await seguridad.senal("cuenta_bloqueada", f"cuenta:{usuario.id}", usuario_id=usuario.id, email=email, ip=ip)
            await session.commit()
        await seguridad.senal("login_fallido", ip, email=email)
        # Mismo mensaje para todo: no revela si el email existe o si la cuenta está bloqueada
        raise NoAutenticado("Credenciales inválidas")

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_login = ahora
    if password_needs_rehash(usuario.password_hash):
        usuario.password_hash = hash_password(datos.password)
    return await _emitir_tokens(session, usuario, request)


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(rate_limit("refresh", 30))])
async def refresh(datos: RefreshIn, request: Request, session: SessionDep):
    token = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == sha256(datos.refresh_token)).with_for_update()
    )
    if not token:
        raise NoAutenticado("Refresh token inválido")

    ahora = datetime.now(UTC)
    if token.revocado_en or token.usado_en:
        # Reutilización de un token ya rotado: posible robo. Se revoca toda la sesión.
        await seguridad.senal("refresh_reutilizado", client_ip(request), usuario_id=token.usuario_id)
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.familia == token.familia, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=ahora)
        )
        await session.commit()
        raise NoAutenticado("Refresh token inválido")
    if token.expira_en <= ahora:
        raise NoAutenticado("Refresh token expirado")

    usuario = await session.get(Usuario, token.usuario_id)
    if not usuario or not usuario.activo:
        raise NoAutenticado("Refresh token inválido")

    token.usado_en = ahora
    return await _emitir_tokens(session, usuario, request, familia=token.familia)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(datos: RefreshIn, session: SessionDep):
    token = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(datos.refresh_token)))
    if token:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.familia == token.familia, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=func.now())
        )
        await session.commit()


@router.get("/me", response_model=MeOut)
async def me(usuario: UsuarioActual):
    permisos = {
        m.value: {a: usuario.puede(m, a) for a in ("crear", "leer", "editar", "eliminar")} for m in Modulo
    }
    return {**UsuarioOut.model_validate(usuario).model_dump(), "permisos": permisos}


@router.post("/cambiar-password", status_code=status.HTTP_204_NO_CONTENT)
async def cambiar_password(datos: CambiarPasswordIn, usuario: UsuarioActual, session: SessionDep):
    await check_rate_limit(f"cambiar-pwd:{usuario.id}", 5, 15 * 60)
    if not verify_password(datos.password_actual, usuario.password_hash):
        raise NoAutenticado("Contraseña actual incorrecta")
    usuario.password_hash = hash_password(datos.password_nueva)
    usuario.token_version += 1  # invalida todos los access tokens vigentes
    await revocar_sesiones(session, usuario.id)
    await session.commit()


@router.post("/ws-ticket", response_model=WsTicketOut)
async def ws_ticket(usuario: UsuarioActual):
    """Ticket de un solo uso para abrir el WebSocket (evita poner el JWT en la URL)."""
    ticket = secrets.token_urlsafe(32)
    await redis_client.set(f"ws-ticket:{ticket}", usuario.id, ex=WS_TICKET_TTL)
    return {"ticket": ticket, "expira_en_seg": WS_TICKET_TTL}
