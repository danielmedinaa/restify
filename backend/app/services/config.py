"""Configuración editable desde el panel (superadmin).

Cada clave tiene su valor por defecto en el .env (app/core/config.py). Si el superadmin la
cambia en el panel, se guarda en la tabla `configuracion` y manda sobre el .env. Volver al
valor del entorno = borrar la fila.

Lectura: `get("clave")` es sincrónico y lee una copia en memoria por proceso, que se recarga
de la BD como mucho cada 10 s (`refrescar()` corre al inicio de cada petición). Así, con
varios workers, un cambio llega a todos en segundos sin consultar la BD en cada uso.

Los secretos se guardan cifrados con una clave derivada de JWT_SECRET y nunca se devuelven
por la API: solo se informa si están configurados.
"""

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Configuracion

logger = logging.getLogger("restify.config")

TTL_SEG = 10


@dataclass(frozen=True)
class Opcion:
    clave: str
    grupo: str
    etiqueta: str
    descripcion: str
    tipo: str  # entero | decimal | texto | url | zona_horaria | secreto
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    reinicio: bool = False
    extra: dict = field(default_factory=dict)


OPCIONES: list[Opcion] = [
    Opcion("igtf_porcentaje", "Impuestos", "IGTF (%)", "Se suma a los pagos en divisas en las sucursales que cobran IGTF.", "decimal", Decimal(0), Decimal(100)),
    Opcion("timezone", "Regional", "Zona horaria", "Define qué es 'hoy', 'este mes' en ventas, bitácora y libro de ventas.", "zona_horaria"),
    Opcion("qr_vencimiento_min", "Pedidos por QR", "Cancelar pedidos sin confirmar tras (minutos)", "Si caja no aprueba ningún plato en este tiempo, el pedido se cancela y la mesa se libera. 0 = nunca.", "entero", Decimal(0), Decimal(240)),
    Opcion("public_menu_base_url", "Pedidos por QR", "URL del menú (va en los QR)", "Al cambiarla, los QR impresos con la URL anterior dejan de funcionar: vuelve a imprimirlos.", "url"),
    Opcion("public_tracking_base_url", "Pedidos por QR", "URL del seguimiento del pedido", "El enlace que recibe el cliente para ver sus platos en vivo.", "url"),
    Opcion("public_rate_limit_per_minute", "Seguridad", "Peticiones por minuto del menú público", "Por IP. Frena abusos del menú QR sin afectar a clientes normales.", "entero", Decimal(10), Decimal(1000)),
    Opcion("login_max_attempts", "Seguridad", "Intentos de login antes de bloquear", "Al llegar a este número de fallos seguidos, la cuenta se bloquea temporalmente.", "entero", Decimal(3), Decimal(20)),
    Opcion("login_lock_minutes", "Seguridad", "Minutos de bloqueo de la cuenta", "Cuánto dura el bloqueo tras demasiados intentos fallidos.", "entero", Decimal(1), Decimal(1440)),
    Opcion("max_image_mb", "Archivos", "Tamaño máximo de fotos (MB)", "Para las fotos de los productos.", "entero", Decimal(1), Decimal(20)),
    Opcion("max_video_mb", "Archivos", "Tamaño máximo de videos (MB)", "Para los videos de los productos. Si pones un proxy delante, súbele también su límite.", "entero", Decimal(1), Decimal(200)),
    Opcion("cedula_api_app_id", "Integraciones", "Consulta de cédulas · App ID", "De tu cuenta en cedula.com.ve (servicio de terceros, no oficial). Vacío = desactivada.", "texto"),
    # Interna: la guarda la configuración inicial. No aparece en el panel ni se puede editar por la API.
    Opcion("panel_token", "Suscripción", "Token de la instancia", "Lo escribe el cliente al configurar el sistema.", "secreto", extra={"interna": True}),
    Opcion("cedula_api_token", "Integraciones", "Consulta de cédulas · Token", "Se guarda cifrado y nunca se vuelve a mostrar.", "secreto"),
]
POR_CLAVE = {o.clave: o for o in OPCIONES}

_cache: dict[str, Any] = {}
_cargado_en: float = 0.0


# ---------------------------------------------------------------- cifrado de secretos
def _fernet() -> Fernet:
    clave = hashlib.sha256(f"restify-config:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(clave))


def _cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def _descifrar(texto: str) -> str | None:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken:
        # Cambió JWT_SECRET: el secreto ya no se puede leer y hay que cargarlo de nuevo
        logger.error("No se pudo descifrar un secreto de configuración; vuelve a cargarlo en el panel")
        return None


# ---------------------------------------------------------------- validación
def validar(clave: str, valor: Any) -> Any:
    """Convierte y valida lo que llega del panel. Lanza ValueError con un mensaje para el usuario."""
    o = POR_CLAVE.get(clave)
    if o is None:
        raise ValueError(f"'{clave}' no es configurable")
    texto = str(valor).strip()
    if o.tipo in ("entero", "decimal"):
        try:
            n = Decimal(texto.replace(",", "."))
        except InvalidOperation:
            raise ValueError(f"{o.etiqueta}: escribe un número") from None
        if o.tipo == "entero" and n != n.to_integral_value():
            raise ValueError(f"{o.etiqueta}: debe ser un número entero")
        if (o.minimo is not None and n < o.minimo) or (o.maximo is not None and n > o.maximo):
            raise ValueError(f"{o.etiqueta}: debe estar entre {o.minimo} y {o.maximo}")
        return int(n) if o.tipo == "entero" else n
    if o.tipo == "url":
        u = urlparse(texto)
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ValueError(f"{o.etiqueta}: escribe una URL completa (https://…)")
        return texto.rstrip("/")
    if o.tipo == "zona_horaria":
        try:
            ZoneInfo(texto)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"{o.etiqueta}: zona horaria desconocida (ej. America/Caracas)") from None
        return texto
    if len(texto) > 500:
        raise ValueError(f"{o.etiqueta}: demasiado largo")
    return texto


def _desde_bd(o: Opcion, crudo: str) -> Any:
    valor = json.loads(crudo)
    if o.tipo == "secreto":
        return _descifrar(valor)
    if o.tipo == "decimal":
        return Decimal(valor)
    return valor


def _a_bd(o: Opcion, valor: Any) -> str:
    if o.tipo == "secreto":
        return json.dumps(_cifrar(str(valor)))
    return json.dumps(str(valor) if isinstance(valor, Decimal) else valor)


# ---------------------------------------------------------------- lectura
def por_defecto(clave: str) -> Any:
    return getattr(settings, clave)


def get(clave: str) -> Any:
    """Valor vigente: el del panel si existe, si no el del .env."""
    if clave in _cache and _cache[clave] not in (None, ""):
        return _cache[clave]
    return por_defecto(clave)


def origen(clave: str) -> str:
    return "panel" if clave in _cache else "entorno"


async def refrescar(forzar: bool = False) -> None:
    global _cache, _cargado_en
    if not forzar and time.monotonic() - _cargado_en < TTL_SEG:
        return
    async with SessionLocal() as session:
        filas = (await session.scalars(select(Configuracion))).all()
    nuevo = {}
    for f in filas:
        if (o := POR_CLAVE.get(f.clave)) is not None:
            try:
                nuevo[f.clave] = _desde_bd(o, f.valor)
            except (ValueError, InvalidOperation):
                logger.error("Valor de configuración ilegible: %s", f.clave)
    _cache, _cargado_en = nuevo, time.monotonic()


def invalidar() -> None:
    """Fuerza la recarga en la próxima lectura (tests y cambios desde el panel)."""
    global _cache, _cargado_en
    _cache, _cargado_en = {}, 0.0


async def guardar(session, cambios: dict[str, Any], usuario_id: int) -> list[str]:
    """Aplica los cambios (None = volver al valor del entorno). Devuelve las claves que cambiaron."""
    hechas = []
    for clave, valor in cambios.items():
        o = POR_CLAVE[clave]
        fila = await session.get(Configuracion, clave)
        if valor is None or (o.tipo in ("texto", "secreto") and str(valor).strip() == ""):
            if fila:
                await session.delete(fila)
                hechas.append(clave)
            continue
        limpio = validar(clave, valor)
        crudo = _a_bd(o, limpio)
        if fila:
            if o.tipo != "secreto" and fila.valor == crudo:
                continue
            fila.valor, fila.actualizado_por_id = crudo, usuario_id
        else:
            session.add(Configuracion(clave=clave, valor=crudo, actualizado_por_id=usuario_id))
        hechas.append(clave)
    return hechas


def listar() -> list[dict]:
    """Para el panel: cada opción con su valor vigente (los secretos, solo si están configurados)."""
    salida = []
    for o in OPCIONES:
        if o.extra.get("interna"):
            continue
        secreto = o.tipo == "secreto"
        vigente = get(o.clave)
        defecto = por_defecto(o.clave)
        salida.append(
            {
                "clave": o.clave,
                "grupo": o.grupo,
                "etiqueta": o.etiqueta,
                "descripcion": o.descripcion,
                "tipo": o.tipo,
                "minimo": o.minimo,
                "maximo": o.maximo,
                "valor": None if secreto else (str(vigente) if vigente is not None else None),
                "por_defecto": None if secreto else (str(defecto) if defecto not in (None, "") else None),
                "configurado": bool(vigente),
                "origen": origen(o.clave),
            }
        )
    return salida
