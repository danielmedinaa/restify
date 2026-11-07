"""Consulta opcional de cédulas en api.cedula.com.ve (servicio de terceros, no oficial).

Desactivada si no hay credenciales. El token solo vive en el servidor, las respuestas se
guardan 30 días en Redis (menos consultas y menos datos viajando) y solo se usa para
autocompletar el nombre cuando el cliente aún no está registrado.
"""

import json
import logging

import httpx

from app.core.redis import redis_client
from app.services import config

logger = logging.getLogger("restify.cedulas")

URL = "https://api.cedula.com.ve/api/v1"
CACHE_SEG = 30 * 24 * 3600


class ConsultaNoDisponible(Exception):
    pass


def configurada() -> bool:
    return bool(config.get("cedula_api_app_id") and config.get("cedula_api_token"))


async def consultar(tipo: str, numero: str) -> dict | None:
    """Devuelve {nombre, rif, zona} o None si la cédula no aparece."""
    if not configurada():
        raise ConsultaNoDisponible("La consulta de cédulas no está configurada")
    clave = f"cedula:{tipo}{numero}"
    if (guardado := await redis_client.get(clave)) is not None:
        return json.loads(guardado) or None

    params = {"app_id": config.get("cedula_api_app_id"), "token": config.get("cedula_api_token"), "nacionalidad": tipo, "cedula": numero}
    try:
        async with httpx.AsyncClient(timeout=6) as cliente:
            r = await cliente.get(URL, params=params)
        cuerpo = r.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Consulta de cédula falló: %s", type(e).__name__)  # sin params: llevan el token
        raise ConsultaNoDisponible("El servicio de consulta no respondió") from e

    data = cuerpo.get("data") if isinstance(cuerpo, dict) and not cuerpo.get("error") else None
    if not data:
        await redis_client.set(clave, json.dumps({}), ex=24 * 3600)  # "no existe" se recuerda 1 día
        return None
    nombre = " ".join(p for p in (data.get("primer_nombre"), data.get("segundo_nombre"), data.get("primer_apellido"), data.get("segundo_apellido")) if p)
    cne = data.get("cne") or {}
    resultado = {
        "nombre": nombre.title(),
        "rif": data.get("rif") or None,
        "zona": ", ".join(p for p in (cne.get("parroquia"), cne.get("municipio"), cne.get("estado")) if p).title() or None,
    }
    await redis_client.set(clave, json.dumps(resultado), ex=CACHE_SEG)
    return resultado
