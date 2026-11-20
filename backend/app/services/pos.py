"""Conector genérico de cobros por API: sirve para cualquier proveedor que hable HTTP + JSON.

Nada de código por proveedor: el superadmin describe en la configuración cómo se arma la
petición de cobro (URL, cabeceras, cuerpo con {{variables}}) y cómo leer la respuesta
(rutas del id, del enlace de pago y del estado). Las llaves van aparte, cifradas, y se usan
como {{secreto.nombre}}.

Seguridad: como el servidor hace la llamada con una URL que escribe un usuario, solo se
permiten URL https hacia direcciones públicas (nunca la red interna ni localhost), sin
seguir redirecciones, con tiempo y tamaño máximos.
"""

import asyncio
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.errors import Invalido
from app.models import PosDispositivo
from app.services import config

TIMEOUT_S = 15
MAX_RESPUESTA = 1024 * 1024
VAR = re.compile(r"\{\{\s*([a-z_][a-z0-9_.]*)\s*\}\}", re.I)
METODOS = {"GET", "POST", "PUT", "PATCH"}


# ---------------------------------------------------------------- plantillas
def render(valor: Any, ctx: dict[str, Any]) -> Any:
    """Reemplaza {{variable}} en textos, listas y diccionarios. Un texto que es SOLO una variable
    conserva su tipo (un número sigue siendo número). Una variable desconocida es un error."""
    if isinstance(valor, str):
        completo = VAR.fullmatch(valor.strip())
        if completo:
            return _resolver(completo.group(1), ctx)
        return VAR.sub(lambda m: str(_resolver(m.group(1), ctx)), valor)
    if isinstance(valor, list):
        return [render(v, ctx) for v in valor]
    if isinstance(valor, dict):
        return {k: render(v, ctx) for k, v in valor.items()}
    return valor


def _resolver(clave: str, ctx: dict[str, Any]) -> Any:
    actual: Any = ctx
    for parte in clave.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            raise Invalido(f"La variable {{{{{clave}}}}} no existe o no tiene valor")
        actual = actual[parte]
    return actual


def extraer(datos: Any, ruta: str | None) -> Any:
    """Lee un valor de un JSON con ruta de puntos: 'data.payment_url' o 'items.0.id'."""
    if not ruta:
        return None
    actual = datos
    for parte in ruta.split("."):
        if isinstance(actual, list) and parte.isdigit() and int(parte) < len(actual):
            actual = actual[int(parte)]
        elif isinstance(actual, dict) and parte in actual:
            actual = actual[parte]
        else:
            return None
    return actual


# ---------------------------------------------------------------- seguridad de la URL
def _ip_publica(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified)


async def verificar_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise Invalido("La dirección debe ser https y sin usuario ni contraseña dentro")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    except OSError as e:
        raise Invalido("No se pudo resolver la dirección del proveedor") from e
    if not infos or not all(_ip_publica(i[4][0]) for i in infos):
        raise Invalido("Esa dirección apunta a una red privada o interna, no se permite")


# ---------------------------------------------------------------- secretos
def guardar_secretos(disp: PosDispositivo, nuevos: dict[str, str | None]) -> None:
    """Mezcla: un valor reemplaza, None borra, y lo no enviado se conserva."""
    actuales = leer_secretos(disp)
    for nombre, valor in nuevos.items():
        if valor is None or valor == "":
            actuales.pop(nombre, None)
        else:
            actuales[nombre] = valor
    disp.secretos = config._cifrar(json.dumps(actuales)) if actuales else None


def leer_secretos(disp: PosDispositivo) -> dict[str, str]:
    if not disp.secretos:
        return {}
    claro = config._descifrar(disp.secretos)
    return json.loads(claro) if claro else {}


def leer_config(disp: PosDispositivo) -> dict:
    return json.loads(disp.config) if disp.config else {}


# ---------------------------------------------------------------- llamadas
async def _llamar(disp: PosDispositivo, op: dict, ctx: dict[str, Any]) -> tuple[int, Any]:
    cfg = leer_config(disp)
    base = str(cfg.get("base_url", "")).rstrip("/")
    ctx = {**ctx, "secreto": leer_secretos(disp)}
    metodo = str(op.get("metodo", "POST")).upper()
    if metodo not in METODOS:
        raise Invalido("Método HTTP no permitido")
    url = base + str(render(op.get("ruta", ""), ctx))
    await verificar_url(url)
    cabeceras = {str(k): str(render(v, ctx)) for k, v in {**cfg.get("cabeceras", {}), **op.get("cabeceras", {})}.items()}
    cuerpo = render(op["cuerpo"], ctx) if op.get("cuerpo") is not None else None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as http:
            r = await http.request(metodo, url, headers=cabeceras, json=cuerpo if metodo != "GET" else None)
    except httpx.HTTPError as e:
        raise Invalido("No se pudo comunicar con el proveedor de pagos") from e
    if len(r.content) > MAX_RESPUESTA:
        raise Invalido("La respuesta del proveedor es demasiado grande")
    try:
        datos = r.json()
    except ValueError:
        datos = {"texto": r.text[:500]}
    return r.status_code, datos


async def crear_cobro(disp: PosDispositivo, *, monto: str, moneda: str, referencia: str, nombre: str = "", descripcion: str = "") -> dict:
    cfg = leer_config(disp)
    if disp.tipo != "api" or not cfg.get("crear"):
        raise Invalido("Este punto de cobro no está conectado por API")
    ctx = {"monto": float(monto), "monto_texto": monto, "moneda": moneda, "referencia": referencia, "nombre": nombre, "descripcion": descripcion}
    estado, datos = await _llamar(disp, cfg["crear"], ctx)
    if not 200 <= estado < 300:
        raise Invalido({"mensaje": "El proveedor rechazó el cobro", "estado_http": estado, "respuesta": datos})
    return {
        "id_externo": _texto(extraer(datos, cfg["crear"].get("id_path"))),
        "url_pago": _texto(extraer(datos, cfg["crear"].get("url_path"))),
        "respuesta": datos,
    }


async def consultar_cobro(disp: PosDispositivo, id_externo: str) -> dict:
    cfg = leer_config(disp)
    op = cfg.get("consultar")
    if disp.tipo != "api" or not op:
        raise Invalido("Este punto de cobro no tiene consulta de estado configurada")
    estado, datos = await _llamar(disp, op, {"id": id_externo})
    if not 200 <= estado < 300:
        raise Invalido({"mensaje": "El proveedor no pudo consultar el cobro", "estado_http": estado, "respuesta": datos})
    valor = _texto(extraer(datos, op.get("estado_path")))
    pagado = {str(x).lower() for x in op.get("pagado", [])}
    return {"estado_proveedor": valor, "pagado": valor is not None and valor.lower() in pagado, "respuesta": datos}


def _texto(v: Any) -> str | None:
    return None if v is None else str(v)
