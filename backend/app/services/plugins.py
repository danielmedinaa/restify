"""Plugins: paquetes firmados por RESTIFY que el administrador de cada restaurante aprueba.

Dos candados:
  1. Firma (Ed25519): solo se instala lo que RESTIFY firmó. La clave privada nunca está aquí.
  2. Permisos: el administrador aprueba solo los que el plugin pidió, y puede quitarlos.

La firma cubre el manifiesto exacto (incluidos permisos, versión y huella de la imagen del
servicio), así que cualquier cambio exige firmar de nuevo. Los plugins no corren dentro del
backend: son servicios aparte que usan un token con solo los permisos aprobados.
"""

import base64
import hashlib
import json
import re
import secrets
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import Invalido
from app.core.security import sha256
from app.models import Accion, Modulo, Plugin
from app.schemas.base import Schema

# Módulos que ningún plugin puede pedir: administrar usuarios, roles o ver la bitácora
PROHIBIDOS = {Modulo.usuarios.value, Modulo.roles.value, Modulo.bitacora.value}
# Pedirlos obliga a una advertencia clara al aprobar
SENSIBLES = {Modulo.ventas.value, Modulo.caja.value, Modulo.clientes.value, Modulo.compras.value}
# Permisos propios de los plugins que no son un módulo del sistema
EXTRA = {"cobros:crear": "Crear cobros en un proveedor de pagos", "cobros:confirmar": "Confirmar pagos recibidos (aprueba pedidos)"}
EXTRA_SENSIBLES = {"cobros:confirmar"}
EVENTO = re.compile(r"^[a-z_]+\.[a-z_]+$")


def catalogo() -> dict[str, dict]:
    """Todos los permisos que un plugin puede pedir, con su descripción y si son sensibles."""
    out: dict[str, dict] = {}
    for m in Modulo:
        if m.value in PROHIBIDOS:
            continue
        for a in Accion:
            clave = f"{m.value}:{a.value}"
            out[clave] = {"sensible": m.value in SENSIBLES or a == Accion.eliminar, "descripcion": f"{a.value.capitalize()} en {m.value}"}
    for clave, d in EXTRA.items():
        out[clave] = {"sensible": clave in EXTRA_SENSIBLES, "descripcion": d}
    return out


class Manifiesto(Schema):
    slug: str = Field(pattern=r"^[a-z][a-z0-9-]{2,39}$")
    nombre: str = Field(min_length=2, max_length=80)
    version: str = Field(pattern=r"^\d{1,4}\.\d{1,4}\.\d{1,4}$")
    autor: str = Field(min_length=2, max_length=80)
    descripcion: str = Field(default="", max_length=300)
    permisos: list[str] = Field(default_factory=list, max_length=30)
    eventos: list[str] = Field(default_factory=list, max_length=20)
    capacidades: list[Literal["cobro"]] = Field(default_factory=list)
    # Servicio externo del plugin (https). La huella fija la imagen exacta que se revisó.
    url_servicio: str | None = Field(default=None, max_length=200, pattern=r"^https://[^\s/]+(/[^\s]*)?$")
    huella_imagen: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("permisos")
    @classmethod
    def _permisos(cls, v: list[str]) -> list[str]:
        validos = catalogo()
        malos = [p for p in v if p not in validos]
        if malos:
            raise ValueError(f"Permisos no permitidos o desconocidos: {', '.join(malos)}")
        if len(set(v)) != len(v):
            raise ValueError("Hay permisos repetidos")
        return v

    @field_validator("eventos")
    @classmethod
    def _eventos(cls, v: list[str]) -> list[str]:
        if any(not EVENTO.match(e) for e in v):
            raise ValueError("Nombre de evento no válido")
        return v


def canonico(manifiesto: dict) -> bytes:
    return json.dumps(manifiesto, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def huella_de(manifiesto: dict) -> str:
    return hashlib.sha256(canonico(manifiesto)).hexdigest()


def _firma_valida(manifiesto: dict, firma_b64: str) -> bool:
    try:
        firma = base64.b64decode(firma_b64, validate=True)
    except ValueError:
        return False
    for clave in settings.plugin_claves_publicas:
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(clave)).verify(firma, canonico(manifiesto))
            return True
        except (InvalidSignature, ValueError):
            continue
    return False


def revocado(slug: str, version: str, huella: str) -> bool:
    return bool({slug, f"{slug}@{version}", f"sha256:{huella}"} & set(settings.plugins_revocados))


def inspeccionar(paquete: dict[str, Any]) -> dict:
    """Valida un paquete {manifiesto, firma}. Falla si la firma no es de RESTIFY (salvo desarrollo)."""
    bruto = paquete.get("manifiesto")
    if not isinstance(bruto, dict):
        raise Invalido("El paquete no trae manifiesto")
    firma = paquete.get("firma")
    firmado = isinstance(firma, str) and _firma_valida(bruto, firma)
    if not firmado:
        if firma or not (settings.plugins_permitir_sin_firma and not settings.is_production):
            raise Invalido("La firma del plugin no es válida: solo se instalan plugins firmados por RESTIFY")
    try:
        m = Manifiesto.model_validate(bruto)
    except ValidationError as e:
        raise Invalido("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())) from e
    huella = huella_de(bruto)
    if revocado(m.slug, m.version, huella):
        raise Invalido("Este plugin fue retirado por RESTIFY y no se puede instalar")
    cat = catalogo()
    return {
        "manifiesto": m,
        "bruto": bruto,
        "firma": firma if firmado else None,
        "firmado": firmado,
        "huella": huella,
        "permisos": [{"permiso": p, **cat[p]} for p in m.permisos],
    }


# ---------------------------------------------------------------- token
def nuevo_token() -> tuple[str, str, str]:
    """(token completo, prefijo, hash). El completo solo se muestra una vez."""
    prefijo = secrets.token_hex(4)
    token = f"rsp_{prefijo}_{secrets.token_urlsafe(32)}"
    return token, prefijo, sha256(token)


async def autenticar(session, token: str) -> Plugin | None:
    """El plugin dueño de un token, o None si no existe, está desactivado o fue revocado."""
    partes = token.split("_", 2)
    if len(partes) != 3 or partes[0] != "rsp":
        return None
    p = await session.scalar(select(Plugin).where(Plugin.token_prefijo == partes[1], Plugin.activo.is_(True)))
    if not p or not secrets.compare_digest(p.token_hash, sha256(token)) or revocado(p.slug, p.version, p.huella):
        return None
    return p


def permisos_de(p: Plugin) -> list[str]:
    return json.loads(p.permisos_aprobados or "[]")
