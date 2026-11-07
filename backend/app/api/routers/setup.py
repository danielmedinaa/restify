"""Configuración inicial de una instancia nueva (sin usuarios todavía).

El front muestra un asistente: token de la instancia -> administrador -> primera sucursal -> moneda.
Todo se envía junto al final y se crea en una sola transacción; en cuanto existe un usuario estos
endpoints dejan de funcionar para siempre.

Seguridad: sin usuarios nadie puede iniciar sesión, así que el control es el TOKEN que RESTIFY le
entrega al cliente (validado contra el panel de RESTIFY). Si la instancia no depende de un panel
(PANEL_URL vacío, desarrollo) no se pide token.
"""

from fastapi import APIRouter, Depends
from pydantic import EmailStr, Field
from sqlalchemy import exists, select, text

from app.api.deps import SessionDep
from app.core.errors import Conflicto, Invalido
from app.core.ratelimit import rate_limit
from app.core.security import hash_password
from app.models import Moneda, Operacion, Sucursal, Usuario
from app.schemas.base import Nombre, Schema
from app.schemas.usuarios import Password, SucursalIn
from app.services import config, licencia

router = APIRouter(prefix="/public/setup", tags=["Configuración inicial"])

_LOCK = 7_401_001  # advisory lock: dos "terminar" a la vez no pueden crear dos administradores


class EstadoOut(Schema):
    pendiente: bool
    requiere_token: bool


class TokenIn(Schema):
    token: str = Field(min_length=10, max_length=200)


class PlanOut(Schema):
    plan: str | None
    vence_en: str | None
    limites: dict[str, int | None]


class AdminIn(Schema):
    nombre: Nombre
    email: EmailStr
    password: Password


class MonedaInicialIn(Schema):
    codigo: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    nombre: str = Field(min_length=1, max_length=60)
    simbolo: str = Field(min_length=1, max_length=8)


class CompletarIn(Schema):
    token: str | None = Field(default=None, max_length=200)
    admin: AdminIn
    sucursal: SucursalIn
    moneda: MonedaInicialIn
    zona_horaria: str | None = Field(default=None, max_length=60)


async def _sin_usuarios(session) -> bool:
    return not await session.scalar(select(exists().where(Usuario.id.is_not(None))))


@router.get("/estado", response_model=EstadoOut)
async def estado(session: SessionDep):
    return EstadoOut(pendiente=await _sin_usuarios(session), requiere_token=licencia.requiere_token())


@router.post("/token", response_model=PlanOut, dependencies=[Depends(rate_limit("setup-token", 10))])
async def validar_token(datos: TokenIn, session: SessionDep):
    """Paso 1: confirma el token y devuelve el plan contratado para mostrarlo."""
    if not await _sin_usuarios(session):
        raise Conflicto("Esta instancia ya está configurada")
    lic = await licencia.verificar_token(datos.token)
    return PlanOut(plan=lic.plan, vence_en=lic.vence_en, limites=lic.limites)


@router.post("/completar", status_code=201, dependencies=[Depends(rate_limit("setup-completar", 5))])
async def completar(datos: CompletarIn, session: SessionDep):
    if licencia.requiere_token():
        if not datos.token:
            raise Conflicto("Falta el token de la instancia")
        await licencia.verificar_token(datos.token)

    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    if not await _sin_usuarios(session):
        raise Conflicto("Esta instancia ya está configurada")

    admin = Usuario(
        email=datos.admin.email.lower(),
        nombre=datos.admin.nombre,
        password_hash=hash_password(datos.admin.password),
        es_superadmin=True,
    )
    session.add(admin)
    session.add(Sucursal(**datos.sucursal.model_dump()))
    if not await session.scalar(select(exists().where(Moneda.es_principal.is_(True)))):
        session.add(Moneda(codigo=datos.moneda.codigo, nombre=datos.moneda.nombre, simbolo=datos.moneda.simbolo,
                           es_principal=True, tasa=1, operacion=Operacion.multiplicar))
    await session.flush()

    cambios = {}
    if datos.zona_horaria:
        cambios["timezone"] = datos.zona_horaria
    if datos.token:
        cambios["panel_token"] = datos.token.strip()
    if cambios:
        try:
            await config.guardar(session, cambios, admin.id)
        except ValueError as e:
            raise Invalido(str(e)) from e
    await session.commit()
    config.invalidar()
    licencia.reiniciar()
    return {"ok": True}
