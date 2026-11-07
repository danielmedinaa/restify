from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field

from app.models import Modulo
from app.schemas.base import Nombre, Schema, TextoCorto
from app.schemas.fiscal import Rif


def _validar_password(v: str) -> str:
    if len(v) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    if v.lower() == v or v.upper() == v or not any(c.isdigit() for c in v):
        raise ValueError("La contraseña debe combinar mayúsculas, minúsculas y números")
    return v


def _permisos_unicos(v: list["PermisoIn"] | None) -> list["PermisoIn"] | None:
    if v is not None and len({p.modulo for p in v}) != len(v):
        raise ValueError("Módulo repetido en permisos")
    return v


Password = Annotated[str, Field(max_length=128), AfterValidator(_validar_password)]


# ---------- Auth ----------
class LoginIn(Schema):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(Schema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expira_en_seg: int


class RefreshIn(Schema):
    refresh_token: str = Field(max_length=200)


class CambiarPasswordIn(Schema):
    password_actual: str = Field(max_length=128)
    password_nueva: Password


class WsTicketOut(Schema):
    ticket: str
    expira_en_seg: int


# ---------- Sucursales ----------
class SucursalIn(Schema):
    nombre: Nombre
    direccion: TextoCorto | None = None
    telefono: str | None = Field(default=None, max_length=40)
    activa: bool = True
    rif: Rif = None
    razon_social: Annotated[str | None, Field(max_length=160)] = None
    domicilio_fiscal: TextoCorto | None = None
    cobra_igtf: bool = False
    precios_incluyen_iva: bool = True


class SucursalUpdate(Schema):
    nombre: Nombre | None = None
    direccion: TextoCorto | None = None
    telefono: str | None = Field(default=None, max_length=40)
    activa: bool | None = None
    rif: Rif = None
    razon_social: Annotated[str | None, Field(max_length=160)] = None
    domicilio_fiscal: TextoCorto | None = None
    cobra_igtf: bool | None = None
    precios_incluyen_iva: bool | None = None


class SucursalOut(Schema):
    id: int
    nombre: str
    direccion: str | None
    telefono: str | None
    activa: bool
    rif: str | None
    razon_social: str | None
    domicilio_fiscal: str | None
    cobra_igtf: bool
    precios_incluyen_iva: bool


# ---------- Roles ----------
class PermisoIn(Schema):
    modulo: Modulo
    crear: bool = False
    leer: bool = False
    editar: bool = False
    eliminar: bool = False


class PermisoOut(PermisoIn):
    modulo: str


class RolIn(Schema):
    nombre: Nombre
    descripcion: TextoCorto | None = None
    permisos: Annotated[list[PermisoIn], AfterValidator(_permisos_unicos)] = []


class RolUpdate(Schema):
    nombre: Nombre | None = None
    descripcion: TextoCorto | None = None
    permisos: Annotated[list[PermisoIn] | None, AfterValidator(_permisos_unicos)] = None


class RolOut(Schema):
    id: int
    nombre: str
    descripcion: str | None
    permisos: list[PermisoOut]


class ModuloOut(Schema):
    modulo: str
    acciones: list[str]


# ---------- Usuarios ----------
class UsuarioIn(Schema):
    email: EmailStr
    nombre: Nombre
    password: Password
    rol_id: int | None = None
    sucursal_ids: list[int] = []
    es_superadmin: bool = False
    activo: bool = True


class UsuarioUpdate(Schema):
    email: EmailStr | None = None
    nombre: Nombre | None = None
    password: Password | None = None
    rol_id: int | None = None
    sucursal_ids: list[int] | None = None
    es_superadmin: bool | None = None
    activo: bool | None = None


class RolResumen(Schema):
    id: int
    nombre: str


class SucursalResumen(Schema):
    id: int
    nombre: str


class UsuarioOut(Schema):
    id: int
    email: str
    nombre: str
    es_superadmin: bool
    activo: bool
    rol: RolResumen | None
    sucursales: list[SucursalResumen]
    ultimo_login: datetime | None
    created_at: datetime


class MeOut(UsuarioOut):
    permisos: dict[str, dict[str, bool]]


# ---------- API keys ----------
class ApiKeyIn(Schema):
    nombre: Nombre


class ApiKeyOut(Schema):
    id: int
    nombre: str
    prefijo: str
    activa: bool
    ultimo_uso: datetime | None
    created_at: datetime


class ApiKeyCreadaOut(ApiKeyOut):
    clave: str = Field(description="Se muestra UNA sola vez. Guárdala en un lugar seguro.")
