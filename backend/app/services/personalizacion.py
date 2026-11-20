"""Personalización de la marca del restaurante: logo, colores y tipografía (función de plan).

Se guarda como un JSON en la tabla `configuracion` (clave `personalizacion`) y los archivos
(logo y fuentes) en el directorio de medios, con nombre aleatorio. Todo lo que llega del
cliente se valida aquí: el front arma CSS con estos datos, así que nada puede traer
caracteres que permitan inyectar estilos.

- Logo: solo PNG, JPG o WEBP (nunca SVG: puede llevar scripts y se serviría desde nuestro dominio).
- Fuentes: WOFF2, WOFF, OTF o TTF, detectadas por sus primeros bytes, o descargadas de
  Google Fonts al servidor (así los visitantes no le piden nada a Google).
- Colores: #rrggbb, con contraste mínimo para que la interfaz no quede ilegible.
"""

import json
import os
import re
import secrets

import httpx
from fastapi import UploadFile
from sqlalchemy import select

from app.core.config import settings
from app.core.errors import Invalido
from app.models import Configuracion
from app.services.medios import borrar_archivo

CLAVE = "personalizacion"
ROLES = ("titulo", "texto")
MAX_LOGO = 2 * 1024 * 1024
MAX_FUENTE = 3 * 1024 * 1024
_CHUNK = 256 * 1024

# Núcleo + detalles. Los de detalle son opcionales: si faltan se derivan de los del núcleo.
COLORES = ("fondo", "texto", "acento", "texto_acento", "superficie", "linea", "ok", "aviso", "error")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FAMILIA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ]{1,58}[A-Za-z0-9]$")
GSTATIC = "https://fonts.gstatic.com/"
# Navegador moderno: Google responde con WOFF2
_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"


# ---------------------------------------------------------------- colores
def _rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def luminancia(h: str) -> float:
    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def validar_colores(colores: dict[str, str | None]) -> dict[str, str]:
    """Normaliza a minúsculas y exige contraste legible. Los colores no enviados se omiten."""
    out: dict[str, str] = {}
    for nombre in COLORES:
        v = colores.get(nombre)
        if v is None:
            continue
        if not HEX.match(v):
            raise Invalido(f"El color de {nombre} debe ser un código como #1a1819")
        out[nombre] = v.lower()
    fondo = out.get("fondo", "#1a1819")
    texto = out.get("texto", "#ffffff")
    acento = out.get("acento", "#ffffff")
    if "texto" in out or "fondo" in out:
        if contraste(texto, fondo) < 4.5:
            raise Invalido("El texto y el fondo se parecen demasiado: no se podría leer. Elige colores más distintos.")
    if "acento" in out or "fondo" in out:
        if contraste(acento, fondo) < 3:
            raise Invalido("El color de acento casi no se distingue del fondo. Elige uno con más contraste.")
    if "texto_acento" in out and contraste(out["texto_acento"], acento) < 4.5:
        raise Invalido("El texto de los botones no se lee sobre el color de acento. Elige uno con más contraste.")
    return out


# ---------------------------------------------------------------- estado guardado
def _vacio() -> dict:
    return {"logo": None, "colores": {}, "titulo": None, "texto": None}


async def leer(session) -> dict:
    fila = await session.get(Configuracion, CLAVE)
    if not fila:
        return _vacio()
    try:
        return {**_vacio(), **json.loads(fila.valor)}
    except ValueError:
        return _vacio()


async def escribir(session, datos: dict, usuario_id: int | None) -> None:
    fila = await session.get(Configuracion, CLAVE)
    valor = json.dumps(datos, ensure_ascii=False)
    if fila:
        fila.valor, fila.actualizado_por_id = valor, usuario_id
    else:
        session.add(Configuracion(clave=CLAVE, valor=valor, actualizado_por_id=usuario_id))


def a_publico(datos: dict) -> dict:
    """Forma que ve el front: rutas de archivos como URL y nada interno."""
    prefijo = settings.media_url_prefix

    def fuente(f: dict | None):
        if not f:
            return None
        return {
            "origen": f["origen"],
            "familia": f["familia"],
            "caras": [
                {"peso": c["peso"], "estilo": c["estilo"], "rango": c.get("rango"), "formato": c["formato"], "url": f"{prefijo}/{c['archivo']}"}
                for c in f["caras"]
            ],
        }

    return {
        "logo_url": f"{prefijo}/{datos['logo']}" if datos.get("logo") else None,
        "colores": datos.get("colores") or {},
        "titulo": fuente(datos.get("titulo")),
        "texto": fuente(datos.get("texto")),
    }


def _archivos_de(fuente: dict | None) -> list[str]:
    return [c["archivo"] for c in (fuente or {}).get("caras", [])]


def borrar_fuente_guardada(fuente: dict | None) -> None:
    for a in _archivos_de(fuente):
        borrar_archivo(a)


# ---------------------------------------------------------------- subidas
def _tipo_logo(cab: bytes) -> tuple[str, str] | None:
    if cab.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if cab.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if cab[:4] == b"RIFF" and cab[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _tipo_fuente(cab: bytes) -> tuple[str, str] | None:
    """(extensión, formato CSS) por los primeros bytes."""
    if cab[:4] == b"wOF2":
        return "woff2", "woff2"
    if cab[:4] == b"wOFF":
        return "woff", "woff"
    if cab[:4] == b"OTTO":
        return "otf", "opentype"
    if cab[:4] in (b"\x00\x01\x00\x00", b"true"):
        return "ttf", "truetype"
    return None


async def _guardar_stream(archivo: UploadFile, cab: bytes, prefijo: str, ext: str, limite: int) -> str:
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{prefijo}-{secrets.token_hex(12)}.{ext}"
    destino = settings.media_dir / nombre
    tmp = destino.with_suffix(".tmp")
    total = len(cab)
    try:
        with open(tmp, "wb") as f:
            f.write(cab)
            while chunk := await archivo.read(_CHUNK):
                total += len(chunk)
                if total > limite:
                    raise Invalido(f"El archivo supera el máximo de {limite // (1024 * 1024)} MB")
                f.write(chunk)
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()
    return nombre


async def guardar_logo(archivo: UploadFile) -> str:
    cab = await archivo.read(16)
    tipo = _tipo_logo(cab)
    if not tipo:
        raise Invalido("El logo debe ser PNG, JPG o WEBP (el SVG no se acepta por seguridad).")
    return await _guardar_stream(archivo, cab, "marca", tipo[0], MAX_LOGO)


async def guardar_fuente_archivo(archivo: UploadFile, familia: str) -> dict:
    if not FAMILIA.match(familia):
        raise Invalido("El nombre de la fuente solo puede llevar letras, números y espacios (2 a 60 caracteres).")
    cab = await archivo.read(16)
    tipo = _tipo_fuente(cab)
    if not tipo:
        raise Invalido("La fuente debe ser WOFF2, WOFF, OTF o TTF.")
    nombre = await _guardar_stream(archivo, cab, "fuente", tipo[0], MAX_FUENTE)
    return {
        "origen": "archivo",
        "familia": familia,
        "caras": [{"peso": "100 900", "estilo": "normal", "rango": None, "formato": tipo[1], "archivo": nombre}],
    }


# ---------------------------------------------------------------- Google Fonts
_BLOQUE = re.compile(r"(?:/\*\s*([\w-]+)\s*\*/\s*)?@font-face\s*\{([^}]*)\}", re.S)
_SUBCONJUNTOS = {"latin", "latin-ext"}


def parsear_css_google(css: str) -> list[dict]:
    """Extrae las caras (latin y latin-ext) del CSS que devuelve Google. Puro, sin red."""
    caras = []
    for sub, cuerpo in _BLOQUE.findall(css):
        if sub and sub not in _SUBCONJUNTOS:
            continue
        url = re.search(r"url\((https://fonts\.gstatic\.com/[^)\s'\"]+)\)", cuerpo)
        peso = re.search(r"font-weight:\s*([0-9 ]{3,8})\s*;", cuerpo)
        estilo = re.search(r"font-style:\s*(normal|italic)\s*;", cuerpo)
        rango = re.search(r"unicode-range:\s*([^;]+);", cuerpo)
        if not (url and peso and estilo):
            continue
        r = rango.group(1).strip() if rango else None
        if r and not re.fullmatch(r"[0-9A-Fa-f+?,\- U]+", r):
            r = None
        caras.append({"url": url.group(1), "peso": peso.group(1).strip(), "estilo": estilo.group(1), "rango": r})
    return caras


async def _css_google(http: httpx.AsyncClient, familia: str) -> str:
    base = familia.replace(" ", "+")
    for spec in (f"{base}:ital,wght@0,400;0,700;1,400;1,700", f"{base}:wght@400;700", base):
        r = await http.get(f"https://fonts.googleapis.com/css2?family={spec}&display=swap", headers={"User-Agent": _UA})
        if r.status_code == 200:
            return r.text
    raise Invalido("No encontramos esa fuente en Google Fonts. Revisa que el nombre esté escrito igual que en fonts.google.com.")


async def descargar_google(familia: str) -> dict:
    if not FAMILIA.match(familia):
        raise Invalido("El nombre de la fuente solo puede llevar letras, números y espacios (2 a 60 caracteres).")
    guardados: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
            caras = parsear_css_google(await _css_google(http, familia))
            if not caras:
                raise Invalido("Google no devolvió archivos utilizables para esa fuente.")
            por_url: dict[str, str] = {}
            salida = []
            for c in caras[:16]:
                if c["url"] not in por_url:
                    r = await http.get(c["url"], headers={"User-Agent": _UA})
                    if r.status_code != 200 or len(r.content) > MAX_FUENTE or not r.content[:4] == b"wOF2":
                        raise Invalido("No se pudo descargar la fuente de Google. Intenta de nuevo.")
                    nombre = f"fuente-{secrets.token_hex(12)}.woff2"
                    settings.media_dir.mkdir(parents=True, exist_ok=True)
                    (settings.media_dir / nombre).write_bytes(r.content)
                    guardados.append(nombre)
                    por_url[c["url"]] = nombre
                salida.append({"peso": c["peso"], "estilo": c["estilo"], "rango": c["rango"], "formato": "woff2", "archivo": por_url[c["url"]]})
    except httpx.HTTPError as e:
        for n in guardados:
            borrar_archivo(n)
        raise Invalido("No pudimos comunicarnos con Google Fonts. Intenta de nuevo en un momento.") from e
    except Invalido:
        for n in guardados:
            borrar_archivo(n)
        raise
    return {"origen": "google", "familia": familia, "caras": salida}

