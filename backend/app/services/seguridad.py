"""Detección de comportamiento sospechoso y alertas de seguridad.

Cada señal suma en un contador de Redis por origen (IP o usuario). Al pasar el umbral se
crea una AlertaSeguridad, en su propia transacción (la petición que la disparó suele
terminar en error y hacer rollback) y se publica en tiempo real para los superadmin.
Una misma alerta no se repite antes de 30 minutos para el mismo origen.
"""

import logging
from dataclasses import dataclass

from app.core.database import SessionLocal
from app.core.realtime import publicar
from app.core.redis import redis_client
from app.models import AlertaSeguridad

logger = logging.getLogger("restify.seguridad")

CANAL_SEGURIDAD = "restify:seguridad"
SILENCIO_SEG = 30 * 60


@dataclass(frozen=True)
class Regla:
    umbral: int
    ventana_seg: int
    severidad: str
    titulo: str
    detalle: str  # admite {n}, {origen} y los datos extra


REGLAS = {
    "login_fallido": Regla(5, 600, "alta", "Intentos de acceso fallidos", "{n} intentos de inicio de sesión fallidos desde {origen} en 10 minutos (último correo: {email})."),
    "cuenta_bloqueada": Regla(1, 1, "alta", "Cuenta bloqueada por intentos fallidos", "La cuenta {email} se bloqueó temporalmente tras varios intentos fallidos desde {origen}."),
    "refresh_reutilizado": Regla(1, 1, "critica", "Posible robo de sesión", "Se reutilizó un token de sesión ya usado (usuario #{usuario_id}, desde {origen}). La sesión se cerró por seguridad."),
    "api_key_invalida": Regla(10, 600, "alta", "API key inválida repetida", "{n} peticiones con una API key falsa o revocada desde {origen} en 10 minutos."),
    "acceso_denegado": Regla(8, 300, "media", "Intentos de acceso sin permiso", "El usuario #{usuario_id} intentó {n} veces en 5 minutos acciones sin permiso (última: {accion})."),
    "rate_limit": Regla(3, 600, "media", "Exceso de peticiones", "{origen} superó el límite de peticiones {n} veces en 10 minutos ({clave})."),
}


async def senal(tipo: str, origen: str | None, *, usuario_id: int | None = None, **extra) -> None:
    """Registra una señal sospechosa. Nunca lanza: la seguridad no debe tumbar la petición."""
    try:
        regla = REGLAS[tipo]
        origen = origen or "desconocido"
        clave = f"seg:{tipo}:{origen}"
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(clave)
            pipe.expire(clave, regla.ventana_seg, nx=True)
            n, _ = await pipe.execute()
        if n < regla.umbral:
            return
        # Una alerta por origen y tipo cada 30 minutos
        if not await redis_client.set(f"seg-alerta:{tipo}:{origen}", 1, nx=True, ex=SILENCIO_SEG):
            return
        ip = origen if not origen.startswith("usuario:") else extra.get("ip")
        valores = {"n": n, "origen": origen, "usuario_id": usuario_id, "email": "—", "accion": "—", "clave": "—", **extra}
        async with SessionLocal() as session:
            alerta = AlertaSeguridad(
                tipo=tipo,
                severidad=regla.severidad,
                titulo=regla.titulo,
                detalle=regla.detalle.format(**valores)[:500],
                ip=ip,
                usuario_id=usuario_id,
                datos={k: str(v) for k, v in extra.items()},
            )
            session.add(alerta)
            await session.commit()
            await publicar(CANAL_SEGURIDAD, "seguridad.alerta", serializar(alerta))
        logger.warning("Alerta de seguridad [%s] %s", regla.severidad, alerta.detalle)
    except Exception:
        logger.exception("No se pudo registrar la señal de seguridad %s", tipo)


def serializar(a: AlertaSeguridad) -> dict:
    return {
        "id": a.id,
        "created_at": a.created_at,
        "tipo": a.tipo,
        "severidad": a.severidad,
        "titulo": a.titulo,
        "detalle": a.detalle,
        "ip": a.ip,
        "usuario_id": a.usuario_id,
        "revisada": a.revisada,
        "revisada_en": a.revisada_en,
    }
