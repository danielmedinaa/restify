"""Personalización de la marca (logo, colores y tipografía). Función del plan más completo."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile
from pydantic import Field

from app.api.deps import SessionDep, UsuarioActual, requiere_superadmin
from app.api.utils import guardar
from app.core.errors import Invalido
from app.schemas.base import Schema
from app.core.ratelimit import rate_limit
from app.services import bitacora, config, licencia
from app.services import personalizacion as srv
from app.services.medios import borrar_archivo

NOMBRE = "La personalización"
Rol = Annotated[Literal["titulo", "texto"], Path()]


class CaraOut(Schema):
    peso: str
    estilo: str
    rango: str | None
    formato: str
    url: str


class FuenteOut(Schema):
    origen: str
    familia: str
    caras: list[CaraOut]


class ColoresOut(Schema):
    fondo: str | None = None
    texto: str | None = None
    acento: str | None = None
    texto_acento: str | None = None
    superficie: str | None = None
    linea: str | None = None
    ok: str | None = None
    aviso: str | None = None
    error: str | None = None


class TemaOut(Schema):
    logo_url: str | None = None
    colores: ColoresOut = ColoresOut()
    titulo: FuenteOut | None = None
    texto: FuenteOut | None = None


class EstadoPersonalizacionOut(Schema):
    disponible: bool
    plan: str | None
    tema: TemaOut


class ColoresIn(Schema):
    """Un color en null vuelve al de RESTIFY."""

    fondo: str | None = Field(default=None, max_length=7)
    texto: str | None = Field(default=None, max_length=7)
    acento: str | None = Field(default=None, max_length=7)
    texto_acento: str | None = Field(default=None, max_length=7)
    superficie: str | None = Field(default=None, max_length=7)
    linea: str | None = Field(default=None, max_length=7)
    ok: str | None = Field(default=None, max_length=7)
    aviso: str | None = Field(default=None, max_length=7)
    error: str | None = Field(default=None, max_length=7)


class FuenteGoogleIn(Schema):
    familia: str = Field(min_length=2, max_length=60)


# ---------------------------------------------------------------- pública (lo lee el front para pintar la marca)
publico = APIRouter(
    prefix="/public",
    tags=["Público (menú QR y seguimiento)"],
    dependencies=[Depends(rate_limit("publico", lambda: config.get("public_rate_limit_per_minute")))],
)


async def tema_vigente(session) -> dict:
    """El tema guardado, o vacío si el plan ya no incluye la función (se vuelve a la marca RESTIFY)."""
    if not await licencia.tiene("personalizacion"):
        return srv.a_publico(srv._vacio())
    return srv.a_publico(await srv.leer(session))


@publico.get("/tema", response_model=TemaOut)
async def tema_publico(session: SessionDep):
    return await tema_vigente(session)


# ---------------------------------------------------------------- administración (superadmin)
router = APIRouter(prefix="/personalizacion", tags=["Personalización"], dependencies=[Depends(requiere_superadmin)])


async def _estado(session) -> dict:
    lic = await licencia.obtener()
    return {"disponible": await licencia.tiene("personalizacion"), "plan": lic.plan if lic else None, "tema": srv.a_publico(await srv.leer(session))}


async def _exigir() -> None:
    await licencia.exigir_caracteristica("personalizacion", NOMBRE)


@router.get("", response_model=EstadoPersonalizacionOut)
async def ver(session: SessionDep):
    return await _estado(session)


@router.delete("", response_model=EstadoPersonalizacionOut)
async def restablecer_todo(session: SessionDep, actor: UsuarioActual):
    """Vuelve a la marca original de RESTIFY: sin logo propio, colores ni tipografías."""
    d = await srv.leer(session)
    await srv.escribir(session, srv._vacio(), actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", "Restableció el tema original")
    await guardar(session)
    borrar_archivo(d.get("logo"))
    srv.borrar_fuente_guardada(d.get("titulo"))
    srv.borrar_fuente_guardada(d.get("texto"))
    return await _estado(session)


@router.put("/colores", response_model=EstadoPersonalizacionOut)
async def guardar_colores(datos: ColoresIn, session: SessionDep, actor: UsuarioActual):
    await _exigir()
    nuevos = srv.validar_colores(datos.model_dump())
    d = await srv.leer(session)
    d["colores"] = nuevos
    await srv.escribir(session, d, actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", "Cambió los colores de la marca")
    await guardar(session)
    return await _estado(session)


@router.post("/logo", response_model=EstadoPersonalizacionOut)
async def subir_logo(session: SessionDep, actor: UsuarioActual, archivo: Annotated[UploadFile, File(description="PNG, JPG o WEBP")]):
    await _exigir()
    nombre = await srv.guardar_logo(archivo)
    d = await srv.leer(session)
    anterior, d["logo"] = d.get("logo"), nombre
    await srv.escribir(session, d, actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", "Cambió el logo")
    try:
        await guardar(session)
    except Exception:
        borrar_archivo(nombre)
        raise
    borrar_archivo(anterior)
    return await _estado(session)


@router.delete("/logo", response_model=EstadoPersonalizacionOut)
async def quitar_logo(session: SessionDep, actor: UsuarioActual):
    d = await srv.leer(session)
    anterior, d["logo"] = d.get("logo"), None
    await srv.escribir(session, d, actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", "Quitó el logo")
    await guardar(session)
    borrar_archivo(anterior)
    return await _estado(session)


async def _poner_fuente(session, actor, rol: str, fuente: dict) -> None:
    d = await srv.leer(session)
    anterior, d[rol] = d.get(rol), fuente
    await srv.escribir(session, d, actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", f"Cambió la tipografía de {'los títulos' if rol == 'titulo' else 'los textos'}: {fuente['familia']}")
    try:
        await guardar(session)
    except Exception:
        srv.borrar_fuente_guardada(fuente)
        raise
    srv.borrar_fuente_guardada(anterior)


@router.post("/fuente/{rol}/google", response_model=EstadoPersonalizacionOut)
async def fuente_google(rol: Rol, datos: FuenteGoogleIn, session: SessionDep, actor: UsuarioActual):
    await _exigir()
    await _poner_fuente(session, actor, rol, await srv.descargar_google(datos.familia.strip()))
    return await _estado(session)


@router.post("/fuente/{rol}/archivo", response_model=EstadoPersonalizacionOut)
async def fuente_archivo(
    rol: Rol,
    session: SessionDep,
    actor: UsuarioActual,
    archivo: Annotated[UploadFile, File(description="WOFF2, WOFF, OTF o TTF")],
    familia: Annotated[str, Form(min_length=2, max_length=60)],
):
    await _exigir()
    await _poner_fuente(session, actor, rol, await srv.guardar_fuente_archivo(archivo, familia.strip()))
    return await _estado(session)


@router.delete("/fuente/{rol}", response_model=EstadoPersonalizacionOut)
async def quitar_fuente(rol: Rol, session: SessionDep, actor: UsuarioActual):
    d = await srv.leer(session)
    anterior, d[rol] = d.get(rol), None
    await srv.escribir(session, d, actor.id)
    bitacora.registrar(session, actor, "personalizacion", "editar", f"Restableció la tipografía de {'los títulos' if rol == 'titulo' else 'los textos'}")
    await guardar(session)
    srv.borrar_fuente_guardada(anterior)
    return await _estado(session)
