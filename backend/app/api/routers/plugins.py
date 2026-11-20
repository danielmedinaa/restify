"""Plugins: instalación con firma de RESTIFY y permisos aprobados por el administrador (solo superadmin)."""

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field

from app.api.deps import SessionDep, UsuarioActual, requiere_superadmin
from app.api.utils import guardar, obtener_o_404
from app.core.errors import Conflicto, Invalido
from app.models import Plugin
from app.schemas.base import Schema
from app.services import bitacora
from app.services import plugins as srv
from sqlalchemy import select

router = APIRouter(prefix="/plugins", tags=["Plugins"], dependencies=[Depends(requiere_superadmin)])

Permiso = Annotated[str, Field(max_length=60)]


class PaqueteIn(Schema):
    manifiesto: dict
    firma: str | None = Field(default=None, max_length=200)


class InstalarIn(PaqueteIn):
    permisos_aprobados: list[Permiso] = Field(default_factory=list, max_length=30)


class PermisosIn(Schema):
    permisos_aprobados: list[Permiso] = Field(max_length=30)


class PermisoOut(Schema):
    permiso: str
    sensible: bool
    descripcion: str


class InspeccionOut(Schema):
    firmado: bool
    huella: str
    manifiesto: srv.Manifiesto
    permisos: list[PermisoOut]
    ya_instalado: bool


class PluginOut(Schema):
    id: int
    slug: str
    nombre: str
    version: str
    autor: str
    firmado: bool
    huella: str
    activo: bool
    permisos_pedidos: list[PermisoOut]
    permisos_aprobados: list[str]
    token_prefijo: str
    ultimo_uso: datetime | None
    created_at: datetime


class PluginInstaladoOut(PluginOut):
    token: str  # se muestra solo esta vez


def _out(p: Plugin) -> dict:
    m = json.loads(p.manifiesto)
    cat = srv.catalogo()
    return {
        "id": p.id, "slug": p.slug, "nombre": p.nombre, "version": p.version, "autor": p.autor, "firmado": p.firmado,
        "huella": p.huella, "activo": p.activo, "token_prefijo": p.token_prefijo, "ultimo_uso": p.ultimo_uso, "created_at": p.created_at,
        "permisos_pedidos": [{"permiso": x, **cat[x]} for x in m.get("permisos", []) if x in cat],
        "permisos_aprobados": srv.permisos_de(p),
    }


def _subconjunto(aprobados: list[str], pedidos: list[str]) -> list[str]:
    extra = sorted(set(aprobados) - set(pedidos))
    if extra:
        raise Invalido(f"No puedes aprobar permisos que el plugin no pidió: {', '.join(extra)}")
    return sorted(set(aprobados))


@router.get("/catalogo")
async def ver_catalogo():
    """Permisos que un plugin puede pedir (para mostrarlos con su descripción)."""
    return srv.catalogo()


@router.get("", response_model=list[PluginOut])
async def listar(session: SessionDep):
    return [_out(p) for p in (await session.scalars(select(Plugin).order_by(Plugin.nombre))).all()]


@router.post("/inspeccionar", response_model=InspeccionOut)
async def inspeccionar(datos: PaqueteIn, session: SessionDep):
    """Revisa un paquete sin instalarlo: firma, permisos que pide y si ya está instalado."""
    r = srv.inspeccionar(datos.model_dump())
    existe = await session.scalar(select(Plugin.id).where(Plugin.slug == r["manifiesto"].slug))
    return {"firmado": r["firmado"], "huella": r["huella"], "manifiesto": r["manifiesto"], "permisos": r["permisos"], "ya_instalado": existe is not None}


@router.post("", response_model=PluginInstaladoOut, status_code=201)
async def instalar(datos: InstalarIn, session: SessionDep, actor: UsuarioActual):
    r = srv.inspeccionar({"manifiesto": datos.manifiesto, "firma": datos.firma})
    m = r["manifiesto"]
    if await session.scalar(select(Plugin.id).where(Plugin.slug == m.slug)):
        raise Conflicto("Ese plugin ya está instalado. Desinstálalo primero para cambiar de versión.")
    aprobados = _subconjunto(datos.permisos_aprobados, m.permisos)
    token, prefijo, hash_ = srv.nuevo_token()
    p = Plugin(
        slug=m.slug, nombre=m.nombre, version=m.version, autor=m.autor,
        manifiesto=srv.canonico(r["bruto"]).decode(), firma=r["firma"], huella=r["huella"], firmado=r["firmado"],
        permisos_aprobados=json.dumps(aprobados), token_hash=hash_, token_prefijo=prefijo, instalado_por_id=actor.id,
    )
    session.add(p)
    await session.flush()
    bitacora.registrar(
        session, actor, "plugins", "instalar", f"Instaló el plugin {m.nombre} {m.version}",
        entidad="plugin", entidad_id=p.id, datos={"huella": r["huella"], "firmado": r["firmado"], "permisos": aprobados},
    )
    await guardar(session)
    return {**_out(p), "token": token}


@router.put("/{plugin_id}/permisos", response_model=PluginOut)
async def cambiar_permisos(plugin_id: int, datos: PermisosIn, session: SessionDep, actor: UsuarioActual):
    p = await obtener_o_404(session, Plugin, plugin_id, "Plugin")
    pedidos = json.loads(p.manifiesto).get("permisos", [])
    p.permisos_aprobados = json.dumps(_subconjunto(datos.permisos_aprobados, pedidos))
    bitacora.registrar(session, actor, "plugins", "editar", f"Cambió los permisos del plugin {p.nombre}", entidad="plugin", entidad_id=p.id, datos={"permisos": json.loads(p.permisos_aprobados)})
    await guardar(session)
    return _out(p)


@router.put("/{plugin_id}/activo", response_model=PluginOut)
async def activar(plugin_id: int, activo: bool, session: SessionDep, actor: UsuarioActual):
    p = await obtener_o_404(session, Plugin, plugin_id, "Plugin")
    p.activo = activo
    bitacora.registrar(session, actor, "plugins", "editar", f"{'Activó' if activo else 'Pausó'} el plugin {p.nombre}", entidad="plugin", entidad_id=p.id)
    await guardar(session)
    return _out(p)


@router.post("/{plugin_id}/token", response_model=PluginInstaladoOut)
async def rotar_token(plugin_id: int, session: SessionDep, actor: UsuarioActual):
    """Cambia el token: el anterior deja de servir al instante."""
    p = await obtener_o_404(session, Plugin, plugin_id, "Plugin")
    token, p.token_prefijo, p.token_hash = srv.nuevo_token()
    bitacora.registrar(session, actor, "plugins", "editar", f"Rotó el token del plugin {p.nombre}", entidad="plugin", entidad_id=p.id)
    await guardar(session)
    return {**_out(p), "token": token}


@router.delete("/{plugin_id}", status_code=204)
async def desinstalar(plugin_id: int, session: SessionDep, actor: UsuarioActual):
    p = await obtener_o_404(session, Plugin, plugin_id, "Plugin")
    bitacora.registrar(session, actor, "plugins", "eliminar", f"Desinstaló el plugin {p.nombre}", entidad="plugin", entidad_id=p.id)
    await session.delete(p)
    await guardar(session)
