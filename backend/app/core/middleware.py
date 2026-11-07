import logging
from collections.abc import Callable

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Auditoria

logger = logging.getLogger("restify")

_METODOS_AUDITADOS = {"POST", "PUT", "PATCH", "DELETE"}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        es_docs = scope["path"].startswith(("/docs", "/redoc", "/openapi.json"))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                extra = {
                    b"x-content-type-options": b"nosniff",
                    b"x-frame-options": b"DENY",
                    b"referrer-policy": b"no-referrer",
                    b"cross-origin-opener-policy": b"same-origin",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
                }
                if not es_docs:
                    extra[b"content-security-policy"] = b"default-src 'none'; frame-ancestors 'none'"
                if settings.is_production:
                    extra[b"strict-transport-security"] = b"max-age=63072000; includeSubDomains"
                existentes = {k.lower() for k, _ in headers}
                headers.extend((k, v) for k, v in extra.items() if k not in existentes)
            await send(message)

        await self.app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Corta peticiones con cuerpo demasiado grande (también si vienen sin Content-Length)."""

    def __init__(self, app: ASGIApp, limite_default: int, limite_uploads: Callable[[], int]):
        self.app = app
        self.limite_default = limite_default
        self.limite_uploads = limite_uploads

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        limite = self.limite_uploads() if scope["path"].endswith("/medios/archivo") else self.limite_default
        for k, v in scope.get("headers", []):
            if k == b"content-length" and v.isdigit() and int(v) > limite:
                respuesta = JSONResponse(
                    {"detail": "Cuerpo de la petición demasiado grande"}, status.HTTP_413_CONTENT_TOO_LARGE
                )
                return await respuesta(scope, receive, send)

        recibido = 0

        async def receive_wrapper() -> Message:
            nonlocal recibido
            message = await receive()
            if message["type"] == "http.request":
                recibido += len(message.get("body", b""))
                if recibido > limite:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Cuerpo de la petición demasiado grande")
            return message

        await self.app(scope, receive_wrapper, send)


class AuditMiddleware:
    """Registra toda operación de escritura: quién, qué ruta, resultado e IP."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _METODOS_AUDITADOS:
            return await self.app(scope, receive, send)

        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            state = scope.get("state", {})
            try:
                async with SessionLocal() as session:
                    session.add(
                        Auditoria(
                            usuario_id=state.get("usuario_id"),
                            api_key_id=state.get("api_key_id"),
                            metodo=scope["method"],
                            ruta=scope["path"][:255],
                            status_code=status_code,
                            ip=(scope.get("client") or ("",))[0][:64] or None,
                        )
                    )
                    await session.commit()
            except Exception:  # la auditoría nunca debe tumbar la petición
                logger.exception("No se pudo registrar auditoría")
