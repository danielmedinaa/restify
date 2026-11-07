"""Subida segura de fotos y videos de productos.

- El tipo se detecta por los magic bytes del archivo (nunca por extensión o Content-Type del cliente).
- Tamaño máximo validado mientras se escribe a disco.
- Nombre aleatorio en disco: el nombre original del cliente nunca se usa en rutas.
"""

import os
import secrets

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import Invalido
from app.models import TipoMedio
from app.services import config

_CHUNK = 1024 * 1024


def detectar_tipo(cabecera: bytes) -> tuple[TipoMedio, str, str] | None:
    """Devuelve (tipo, mime, extensión) o None si no es un formato permitido."""
    if cabecera.startswith(b"\xff\xd8\xff"):
        return TipoMedio.imagen, "image/jpeg", "jpg"
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return TipoMedio.imagen, "image/png", "png"
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return TipoMedio.imagen, "image/webp", "webp"
    if cabecera[4:8] == b"ftyp":
        marca = cabecera[8:12]
        if marca in (b"avif", b"avis"):
            return TipoMedio.imagen, "image/avif", "avif"
        if marca == b"qt  ":
            return TipoMedio.video, "video/quicktime", "mov"
        return TipoMedio.video, "video/mp4", "mp4"
    if cabecera.startswith(b"\x1a\x45\xdf\xa3"):
        return TipoMedio.video, "video/webm", "webm"
    return None


async def guardar_archivo(archivo: UploadFile) -> dict:
    cabecera = await archivo.read(32)
    detectado = detectar_tipo(cabecera)
    if not detectado:
        raise Invalido("Formato no permitido. Usa JPG, PNG, WEBP, AVIF, MP4, MOV o WEBM.")
    tipo, mime, ext = detectado
    limite_mb = config.get("max_image_mb") if tipo == TipoMedio.imagen else config.get("max_video_mb")
    limite = limite_mb * 1024 * 1024

    settings.media_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{secrets.token_hex(16)}.{ext}"
    destino = settings.media_dir / nombre
    tmp = destino.with_suffix(".tmp")

    tamano = len(cabecera)
    try:
        with open(tmp, "wb") as f:
            f.write(cabecera)
            while chunk := await archivo.read(_CHUNK):
                tamano += len(chunk)
                if tamano > limite:
                    raise Invalido(f"El archivo supera el máximo de {limite_mb} MB para {tipo.value}")
                f.write(chunk)
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()

    return {
        "tipo": tipo,
        "mime": mime,
        "archivo": nombre,
        "tamano_bytes": tamano,
        "url": f"{settings.media_url_prefix}/{nombre}",
    }


def borrar_archivo(nombre: str | None) -> None:
    if not nombre:
        return
    ruta = (settings.media_dir / nombre).resolve()
    # Defensa en profundidad: nunca borrar fuera del directorio de medios
    if ruta.parent == settings.media_dir.resolve() and ruta.exists():
        ruta.unlink()
