import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.deps import verificar_api_key
from app.api.routers import admin, auth, caja, catalogo, compras, operaciones, publico, setup, ws
from app.core.config import settings
from app.core.database import engine
from app.core.middleware import AuditMiddleware, BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.redis import redis_client
from app.services import config, licencia, vencimientos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("restify")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    tarea = asyncio.create_task(vencimientos.bucle())
    yield
    tarea.cancel()
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    # Documentación interactiva desactivada en producción
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# El orden importa: el último agregado es el más externo
app.add_middleware(AuditMiddleware)
app.add_middleware(
    BodySizeLimitMiddleware,
    limite_default=1 * 1024 * 1024,
    limite_uploads=lambda: (config.get("max_video_mb") + 1) * 1024 * 1024,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    max_age=600,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(Exception)
async def error_no_controlado(request: Request, exc: Exception):
    # Nunca exponer trazas ni detalles internos al cliente
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Error interno del servidor"}, status_code=500)


API_PREFIX = "/api/v1"
async def cargar_configuracion() -> None:
    """Valores editables desde el panel: recarga barata (como mucho cada 10 s por proceso)."""
    await config.refrescar()


protegido = [Depends(verificar_api_key), Depends(cargar_configuracion), Depends(licencia.exigir_acceso)]

for r in (auth.router, admin.roles, admin.usuarios, admin.sucursales, admin.seguridad, admin.bitacora_router, caja.router, compras.router, catalogo.router, operaciones.router, publico.router, setup.router):
    app.include_router(r, prefix=API_PREFIX, dependencies=protegido)
app.include_router(ws.router)

app.mount(settings.media_url_prefix, StaticFiles(directory=settings.media_dir, check_dir=False), name="media")


@app.get("/health", tags=["Salud"], include_in_schema=False)
async def health():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await redis_client.ping()
    return {"status": "ok"}
