from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select, update

from app.api.deps import SessionDep, UsuarioActual, requiere, requiere_superadmin, sucursales_visibles
from app.api.routers.auth import revocar_sesiones
from app.api.utils import Limite, Offset, aplicar_cambios, guardar, insertar, obtener_o_404, paginar
from app.core.errors import Conflicto, Invalido, NoEncontrado, Prohibido
from app.core.security import hash_password, new_api_key
from app.models import Accion, AlertaSeguridad, ApiKey, Auditoria, Bitacora, Modulo, Rol, RolPermiso, Sucursal, Usuario, usuario_sucursal
from app.schemas.base import Pagina, Schema
from app.schemas.catalogo import BitacoraOut
from app.services import bitacora, config, licencia
from app.schemas.usuarios import (
    ApiKeyCreadaOut,
    ApiKeyIn,
    ApiKeyOut,
    ModuloOut,
    PermisoIn,
    RolIn,
    RolOut,
    RolUpdate,
    SucursalIn,
    SucursalOut,
    SucursalUpdate,
    UsuarioIn,
    UsuarioOut,
    UsuarioUpdate,
)

ACCIONES = [a.value for a in Accion]

# ============================================================ Roles
roles = APIRouter(prefix="/roles", tags=["Roles y permisos"])


def _validar_otorgables(actor: Usuario, permisos: list[PermisoIn]) -> None:
    """Un usuario no puede otorgar permisos que él mismo no tiene."""
    if actor.es_superadmin:
        return
    for p in permisos:
        for a in ACCIONES:
            if getattr(p, a) and not actor.puede(p.modulo, a):
                raise Prohibido(f"No puedes otorgar '{a}' en '{p.modulo.value}' porque no tienes ese permiso")


def _rol_dentro_de_permisos(actor: Usuario, rol: Rol) -> bool:
    if actor.es_superadmin:
        return True
    return all(not getattr(p, a) or actor.puede(p.modulo, a) for p in rol.permisos for a in ACCIONES)


def _set_permisos(rol: Rol, permisos: list[PermisoIn]) -> None:
    rol.permisos = [RolPermiso(**p.model_dump(mode="json")) for p in permisos]


@roles.get("/modulos", response_model=list[ModuloOut], dependencies=[Depends(requiere(Modulo.roles, Accion.leer))])
async def listar_modulos():
    """Catálogo de módulos y acciones para armar la matriz de permisos en el frontend."""
    return [{"modulo": m.value, "acciones": ACCIONES} for m in Modulo]


@roles.get("", response_model=list[RolOut], dependencies=[Depends(requiere(Modulo.roles, Accion.leer))])
async def listar_roles(session: SessionDep):
    return (await session.scalars(select(Rol).order_by(Rol.nombre))).all()


@roles.get("/{rol_id}", response_model=RolOut, dependencies=[Depends(requiere(Modulo.roles, Accion.leer))])
async def obtener_rol(rol_id: int, session: SessionDep):
    return await obtener_o_404(session, Rol, rol_id, "Rol")


@roles.post("", response_model=RolOut, status_code=status.HTTP_201_CREATED)
async def crear_rol(
    datos: RolIn, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.roles, Accion.crear))
):
    _validar_otorgables(actor, datos.permisos)
    rol = Rol(nombre=datos.nombre, descripcion=datos.descripcion)
    _set_permisos(rol, datos.permisos)
    session.add(rol)
    await insertar(session, "Ya existe un rol con ese nombre")
    bitacora.registrar(session, actor, "roles", "crear", f"Creó el rol {rol.nombre}", entidad="rol", entidad_id=rol.id)
    await guardar(session, "Ya existe un rol con ese nombre")
    return rol


@roles.patch("/{rol_id}", response_model=RolOut)
async def editar_rol(
    rol_id: int, datos: RolUpdate, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.roles, Accion.editar))
):
    rol = await obtener_o_404(session, Rol, rol_id, "Rol")
    if not actor.es_superadmin and actor.rol_id == rol.id:
        raise Prohibido("No puedes editar tu propio rol")
    if not _rol_dentro_de_permisos(actor, rol):
        raise Prohibido("Este rol tiene permisos superiores a los tuyos")
    if datos.permisos is not None:
        _validar_otorgables(actor, datos.permisos)
        # Borrar antes de insertar para no chocar con UNIQUE(rol_id, modulo)
        rol.permisos.clear()
        await session.flush()
        _set_permisos(rol, datos.permisos)
    aplicar_cambios(rol, datos, excluir={"permisos"})
    bitacora.registrar(
        session, actor, "roles", "editar",
        f"Editó el rol {rol.nombre}" + (" y sus permisos" if datos.permisos is not None else ""),
        entidad="rol", entidad_id=rol.id,
    )
    await guardar(session, "Ya existe un rol con ese nombre")
    await session.refresh(rol)
    return rol


@roles.delete("/{rol_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_rol(
    rol_id: int, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.roles, Accion.eliminar))
):
    rol = await obtener_o_404(session, Rol, rol_id, "Rol")
    if not _rol_dentro_de_permisos(actor, rol):
        raise Prohibido("Este rol tiene permisos superiores a los tuyos")
    if await session.scalar(select(func.count()).where(Usuario.rol_id == rol.id)):
        raise Conflicto("Hay usuarios con este rol; reasígnalos primero")
    bitacora.registrar(session, actor, "roles", "eliminar", f"Eliminó el rol {rol.nombre}", entidad="rol", entidad_id=rol.id)
    await session.delete(rol)
    await guardar(session)


# ============================================================ Usuarios
usuarios = APIRouter(prefix="/usuarios", tags=["Usuarios"])


async def _validar_asignaciones(session, actor: Usuario, rol_id, sucursal_ids, es_superadmin) -> list[Sucursal] | None:
    if es_superadmin and not actor.es_superadmin:
        raise Prohibido("Solo un superadministrador puede crear o promover superadministradores")
    if rol_id is not None:
        rol = await obtener_o_404(session, Rol, rol_id, "Rol")
        if not _rol_dentro_de_permisos(actor, rol):
            raise Prohibido("No puedes asignar un rol con permisos superiores a los tuyos")
    if sucursal_ids is None:
        return None
    ids = set(sucursal_ids)
    if not actor.es_superadmin and not ids <= actor.sucursal_ids():
        raise Prohibido("Solo puedes asignar sucursales a las que tienes acceso")
    sucursales = list(await session.scalars(select(Sucursal).where(Sucursal.id.in_(ids))))
    if len(sucursales) != len(ids):
        raise NoEncontrado("Sucursal")
    return sucursales


def _puede_gestionar(actor: Usuario, objetivo: Usuario) -> None:
    if objetivo.es_superadmin and not actor.es_superadmin:
        raise Prohibido("No puedes modificar a un superadministrador")
    if not actor.es_superadmin and objetivo.rol and not _rol_dentro_de_permisos(actor, objetivo.rol):
        raise Prohibido("Este usuario tiene permisos superiores a los tuyos")


@usuarios.get("", response_model=Pagina[UsuarioOut])
async def listar_usuarios(
    session: SessionDep,
    actor: Usuario = Depends(requiere(Modulo.usuarios, Accion.leer)),
    q: str | None = Query(default=None, max_length=100),
    sucursal_id: int | None = None,
    activo: bool | None = None,
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Usuario).order_by(Usuario.nombre)
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(or_(Usuario.nombre.ilike(patron), Usuario.email.ilike(patron)))
    if activo is not None:
        stmt = stmt.where(Usuario.activo.is_(activo))
    ids = sucursales_visibles(actor, sucursal_id)
    if ids is not None:
        stmt = stmt.where(
            Usuario.id.in_(select(usuario_sucursal.c.usuario_id).where(usuario_sucursal.c.sucursal_id.in_(ids)))
        )
    return await paginar(session, stmt, limite, offset)


@usuarios.get("/{usuario_id}", response_model=UsuarioOut, dependencies=[Depends(requiere(Modulo.usuarios, Accion.leer))])
async def obtener_usuario(usuario_id: int, session: SessionDep):
    return await obtener_o_404(session, Usuario, usuario_id, "Usuario")


@usuarios.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
async def crear_usuario(
    datos: UsuarioIn, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.usuarios, Accion.crear))
):
    await licencia.exigir_cupo(session, "max_usuarios", select(Usuario.id).where(Usuario.activo.is_(True)))
    sucursales = await _validar_asignaciones(session, actor, datos.rol_id, datos.sucursal_ids, datos.es_superadmin)
    usuario = Usuario(
        email=datos.email.lower(),
        nombre=datos.nombre,
        password_hash=hash_password(datos.password),
        rol_id=datos.rol_id,
        es_superadmin=datos.es_superadmin,
        activo=datos.activo,
        sucursales=sucursales or [],
    )
    session.add(usuario)
    await insertar(session, "Ya existe un usuario con ese email")
    bitacora.registrar(session, actor, "usuarios", "crear", f"Creó al usuario {usuario.nombre} ({usuario.email})", entidad="usuario", entidad_id=usuario.id)
    await guardar(session, "Ya existe un usuario con ese email")
    await session.refresh(usuario)
    return usuario


@usuarios.patch("/{usuario_id}", response_model=UsuarioOut)
async def editar_usuario(
    usuario_id: int,
    datos: UsuarioUpdate,
    session: SessionDep,
    actor: Usuario = Depends(requiere(Modulo.usuarios, Accion.editar)),
):
    usuario = await obtener_o_404(session, Usuario, usuario_id, "Usuario")
    _puede_gestionar(actor, usuario)
    if usuario.id == actor.id and (datos.rol_id is not None or datos.es_superadmin is not None):
        raise Prohibido("No puedes cambiar tu propio rol")
    sucursales = await _validar_asignaciones(session, actor, datos.rol_id, datos.sucursal_ids, datos.es_superadmin)

    invalidar = False
    if sucursales is not None:
        usuario.sucursales = sucursales
    if datos.password is not None:
        usuario.password_hash = hash_password(datos.password)
        invalidar = True
    if datos.email is not None:
        usuario.email = datos.email.lower()
    if datos.activo is False or (datos.rol_id is not None and datos.rol_id != usuario.rol_id):
        invalidar = True
    cambios = list(aplicar_cambios(usuario, datos, excluir={"sucursal_ids", "password", "email"}))
    cambios += [c for c in ("sucursal_ids", "password", "email") if getattr(datos, c) is not None]
    bitacora.registrar(
        session, actor, "usuarios", "editar",
        f"Editó al usuario {usuario.nombre}: {', '.join(c.replace('sucursal_ids', 'sucursales').replace('password', 'contraseña') for c in cambios) or 'sin cambios'}",
        entidad="usuario", entidad_id=usuario.id,
    )
    if invalidar:
        usuario.token_version += 1
        await revocar_sesiones(session, usuario.id)
    await guardar(session, "Ya existe un usuario con ese email")
    await session.refresh(usuario)
    return usuario


@usuarios.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desactivar_usuario(
    usuario_id: int, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.usuarios, Accion.eliminar))
):
    """Desactiva (no borra) para conservar la trazabilidad de comandas y ventas."""
    usuario = await obtener_o_404(session, Usuario, usuario_id, "Usuario")
    if usuario.id == actor.id:
        raise Conflicto("No puedes desactivarte a ti mismo")
    _puede_gestionar(actor, usuario)
    usuario.activo = False
    usuario.token_version += 1
    await revocar_sesiones(session, usuario.id)
    bitacora.registrar(session, actor, "usuarios", "desactivar", f"Desactivó al usuario {usuario.nombre}", entidad="usuario", entidad_id=usuario.id)
    await guardar(session)


# ============================================================ Sucursales
sucursales = APIRouter(prefix="/sucursales", tags=["Sucursales"])


@sucursales.get("", response_model=list[SucursalOut])
async def listar_sucursales(session: SessionDep, actor: Usuario = Depends(requiere(Modulo.sucursales, Accion.leer))):
    stmt = select(Sucursal).order_by(Sucursal.nombre)
    if not actor.es_superadmin:
        stmt = stmt.where(Sucursal.id.in_(actor.sucursal_ids()))
    return (await session.scalars(stmt)).all()


@sucursales.get("/{sucursal_id}", response_model=SucursalOut)
async def obtener_sucursal(
    sucursal_id: int, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.sucursales, Accion.leer))
):
    sucursales_visibles(actor, sucursal_id)
    return await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")


@sucursales.post("", response_model=SucursalOut, status_code=status.HTTP_201_CREATED)
async def crear_sucursal(
    datos: SucursalIn, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.sucursales, Accion.crear))
):
    await licencia.exigir_cupo(session, "max_sucursales", select(Sucursal.id).where(Sucursal.activa.is_(True)))
    sucursal = Sucursal(**datos.model_dump())
    session.add(sucursal)
    if not actor.es_superadmin:
        actor.sucursales.append(sucursal)  # quien la crea tiene acceso a ella
    await insertar(session, "Ya existe una sucursal con ese nombre")
    bitacora.registrar(session, actor, "sucursales", "crear", f"Creó la sucursal {sucursal.nombre}", sucursal_id=sucursal.id, entidad="sucursal", entidad_id=sucursal.id)
    await guardar(session, "Ya existe una sucursal con ese nombre")
    return sucursal


@sucursales.patch("/{sucursal_id}", response_model=SucursalOut)
async def editar_sucursal(
    sucursal_id: int,
    datos: SucursalUpdate,
    session: SessionDep,
    actor: Usuario = Depends(requiere(Modulo.sucursales, Accion.editar)),
):
    sucursales_visibles(actor, sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    cambios = aplicar_cambios(sucursal, datos)
    if cambios:
        bitacora.registrar(
            session, actor, "sucursales", "editar", f"Editó la sucursal {sucursal.nombre}: {', '.join(cambios)}",
            sucursal_id=sucursal.id, entidad="sucursal", entidad_id=sucursal.id,
        )
    await guardar(session, "Ya existe una sucursal con ese nombre")
    return sucursal


@sucursales.delete("/{sucursal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desactivar_sucursal(
    sucursal_id: int, session: SessionDep, actor: Usuario = Depends(requiere(Modulo.sucursales, Accion.eliminar))
):
    sucursales_visibles(actor, sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    sucursal.activa = False
    bitacora.registrar(session, actor, "sucursales", "desactivar", f"Desactivó la sucursal {sucursal.nombre}", sucursal_id=sucursal.id, entidad="sucursal", entidad_id=sucursal.id)
    await guardar(session)


# ============================================================ Bitácora
bitacora_router = APIRouter(prefix="/bitacora", tags=["Bitácora"])


@bitacora_router.get("", response_model=Pagina[BitacoraOut])
async def listar_bitacora(
    session: SessionDep,
    actor: Usuario = Depends(requiere(Modulo.bitacora, Accion.leer)),
    sucursal_id: int | None = None,
    usuario_id: int | None = None,
    modulo: str | None = Query(default=None, max_length=30),
    q: str | None = Query(default=None, max_length=100, description="Busca en la descripción"),
    desde: date | None = None,
    hasta: date | None = None,
    limite: Limite = 50,
    offset: Offset = 0,
):
    """Quién hizo qué y cuándo. Las acciones sin sucursal (catálogo, usuarios) se ven siempre."""
    stmt = select(Bitacora).order_by(Bitacora.id.desc())
    ids = sucursales_visibles(actor, sucursal_id)
    if ids is not None:
        stmt = stmt.where(or_(Bitacora.sucursal_id.in_(ids), Bitacora.sucursal_id.is_(None)) if sucursal_id is None else Bitacora.sucursal_id.in_(ids))
    if usuario_id is not None:
        stmt = stmt.where(Bitacora.usuario_id == usuario_id)
    if modulo:
        stmt = stmt.where(Bitacora.modulo == modulo)
    if q:
        stmt = stmt.where(Bitacora.descripcion.ilike(f"%{q}%"))
    local = func.timezone(config.get("timezone"), Bitacora.created_at)
    if desde:
        stmt = stmt.where(func.date(local) >= desde)
    if hasta:
        stmt = stmt.where(func.date(local) <= hasta)
    pagina = await paginar(session, stmt, limite, offset)
    nombres = dict((await session.execute(select(Sucursal.id, Sucursal.nombre))).all())
    pagina["items"] = [
        {**BitacoraOut.model_validate(e).model_dump(), "sucursal": nombres.get(e.sucursal_id)} for e in pagina["items"]
    ]
    return pagina


# ============================================================ API keys y auditoría (solo superadmin)
seguridad = APIRouter(tags=["Seguridad"], dependencies=[Depends(requiere_superadmin)])


@seguridad.get("/api-keys", response_model=list[ApiKeyOut])
async def listar_api_keys(session: SessionDep):
    return (await session.scalars(select(ApiKey).order_by(ApiKey.id))).all()


@seguridad.post("/api-keys", response_model=ApiKeyCreadaOut, status_code=status.HTTP_201_CREATED)
async def crear_api_key(datos: ApiKeyIn, session: SessionDep, actor: UsuarioActual):
    clave, prefijo, key_hash = new_api_key()
    api_key = ApiKey(nombre=datos.nombre, prefijo=prefijo, key_hash=key_hash, creada_por_id=actor.id)
    session.add(api_key)
    await guardar(session)
    return {**ApiKeyOut.model_validate(api_key).model_dump(), "clave": clave}


@seguridad.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revocar_api_key(api_key_id: int, session: SessionDep):
    api_key = await obtener_o_404(session, ApiKey, api_key_id, "API key")
    api_key.activa = False
    await guardar(session)


class AlertaSeguridadOut(Schema):
    id: int
    created_at: datetime
    tipo: str
    severidad: str
    titulo: str
    detalle: str
    ip: str | None
    usuario_id: int | None
    revisada: bool
    revisada_en: datetime | None


@seguridad.get("/seguridad/alertas", response_model=Pagina[AlertaSeguridadOut])
async def listar_alertas_seguridad(
    session: SessionDep, pendientes: bool | None = None, limite: Limite = 50, offset: Offset = 0
):
    """Comportamientos sospechosos detectados (fuerza bruta, robo de sesión, API keys falsas…)."""
    stmt = select(AlertaSeguridad).order_by(AlertaSeguridad.id.desc())
    if pendientes is not None:
        stmt = stmt.where(AlertaSeguridad.revisada.is_(not pendientes))
    return await paginar(session, stmt, limite, offset)


@seguridad.post("/seguridad/alertas/revisar", status_code=status.HTTP_204_NO_CONTENT)
async def revisar_alertas(session: SessionDep, actor: UsuarioActual, ids: list[int] | None = None):
    """Marca alertas como revisadas (sin ids: todas las pendientes)."""
    stmt = update(AlertaSeguridad).where(AlertaSeguridad.revisada.is_(False))
    if ids:
        stmt = stmt.where(AlertaSeguridad.id.in_(ids))
    await session.execute(stmt.values(revisada=True, revisada_por_id=actor.id, revisada_en=func.now()))
    bitacora.registrar(session, actor, "usuarios", "revisar_alertas", "Marcó como revisadas las alertas de seguridad")
    await guardar(session)


class OpcionConfigOut(Schema):
    clave: str
    grupo: str
    etiqueta: str
    descripcion: str
    tipo: str
    minimo: Decimal | None
    maximo: Decimal | None
    valor: str | None = None
    por_defecto: str | None = None
    configurado: bool
    origen: str  # panel | entorno


class ConfigIn(Schema):
    """{clave: valor}. null (o vacío en textos/secretos) = volver al valor del .env."""

    valores: dict[str, str | None]


@seguridad.get("/configuracion", response_model=list[OpcionConfigOut])
async def ver_configuracion():
    """Lo que se puede cambiar desde el panel, con su valor vigente y el del .env. Los secretos no se devuelven."""
    await config.refrescar(forzar=True)
    return config.listar()


@seguridad.put("/configuracion", response_model=list[OpcionConfigOut])
async def guardar_configuracion(datos: ConfigIn, session: SessionDep, actor: UsuarioActual):
    if any(config.POR_CLAVE[c].extra.get("interna") for c in datos.valores if c in config.POR_CLAVE):
        raise Invalido("Esa opción no se puede cambiar desde aquí")
    try:
        cambiadas = await config.guardar(session, datos.valores, actor.id)
    except (ValueError, KeyError) as e:
        raise Invalido(str(e).strip("'")) from e
    if cambiadas:
        nombres = ", ".join(config.POR_CLAVE[c].etiqueta for c in cambiadas)  # nunca el valor: puede ser un secreto
        bitacora.registrar(session, actor, "configuracion", "editar", f"Cambió la configuración: {nombres}", datos={"claves": cambiadas})
    await guardar(session)
    await config.refrescar(forzar=True)
    return config.listar()


class AuditoriaOut(Schema):
    id: int
    usuario_id: int | None
    api_key_id: int | None
    metodo: str
    ruta: str
    status_code: int
    ip: str | None
    created_at: datetime


@seguridad.get("/auditoria", response_model=Pagina[AuditoriaOut])
async def listar_auditoria(
    session: SessionDep,
    usuario_id: int | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Auditoria).order_by(Auditoria.id.desc())
    if usuario_id is not None:
        stmt = stmt.where(Auditoria.usuario_id == usuario_id)
    if desde:
        stmt = stmt.where(Auditoria.created_at >= desde)
    if hasta:
        stmt = stmt.where(Auditoria.created_at <= hasta)
    return await paginar(session, stmt, limite, offset)
