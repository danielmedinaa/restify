"""Reglas de negocio: crear suscripción+instancia, cambiar estado, plan, límites y dominio."""

import hashlib
import secrets
from datetime import timedelta

import dns.exception
import dns.resolver
from flask import current_app

from app import auditoria
from app.extensions import db
from app.infra.aprovisionador import obtener
from app.modelos import ESTADOS, LIMITES, TRANSICIONES, Instancia, Suscripcion, ahora


class ReglaError(Exception):
    """Error de negocio que se muestra al administrador."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _token_nuevo() -> str:
    return "rst_" + secrets.token_urlsafe(40)


def url_instancia(inst: Instancia) -> str:
    cfg = current_app.config
    puerto = f":{cfg['INSTANCIA_PUERTO']}" if cfg["INSTANCIA_PUERTO"] else ""
    return f"{cfg['INSTANCIA_ESQUEMA']}://{inst.subdominio}.{cfg['DOMINIO_BASE']}{puerto}"


def _url_panel() -> str:
    return current_app.config["PANEL_URL"].rstrip("/") + "/api/v1/estado"


def _aplicar(inst: Instancia, resultado) -> None:
    inst.estado_infra = resultado.estado_infra
    inst.error_infra = resultado.error[:500] if resultado.error else None


def crear(cliente, plan, subdominio: str, dias_periodo: int | None = 30) -> tuple[Suscripcion, str]:
    """Crea suscripción activa + instancia y la aprovisiona. Devuelve (suscripción, token en claro)."""
    if not plan.activo:
        raise ReglaError("Ese plan está archivado.")
    token = _token_nuevo()
    s = Suscripcion(cliente=cliente, plan=plan, estado="activa", estado_desde=ahora(),
                    vence_en=ahora() + timedelta(days=dias_periodo) if dias_periodo else None)
    s.instancia = Instancia(subdominio=subdominio, token_hash=hash_token(token), token_prefijo=token[:10])
    db.session.add(s)
    db.session.flush()
    s.instancia.estado_infra = "creando"
    _aplicar(s.instancia, obtener().crear(s.instancia, {"token": token, "panel_url": _url_panel()}))
    auditoria.registrar("suscripcion.crear", "suscripcion", s.id,
                        {"cliente": cliente.id, "plan": plan.nombre, "subdominio": subdominio})
    return s, token


def cambiar_estado(s: Suscripcion, nuevo: str, motivo: str | None = None) -> None:
    if nuevo not in ESTADOS:
        raise ReglaError("Estado desconocido.")
    if nuevo == s.estado:
        return
    if nuevo not in TRANSICIONES[s.estado]:
        raise ReglaError(f"No se puede pasar de {ESTADOS[s.estado].lower()} a {ESTADOS[nuevo].lower()}.")
    if nuevo in ("suspendida", "cancelada") and not (motivo or "").strip():
        raise ReglaError("Indica el motivo.")
    anterior = s.estado
    s.estado, s.motivo_estado, s.estado_desde = nuevo, (motivo or "").strip()[:300] or None, ahora()
    inst, infra = s.instancia, obtener()
    if nuevo in ("activa", "suspendida"):
        # Suspendida sigue encendida: así el sistema responde con el mensaje "Cuenta suspendida" y su motivo
        _aplicar(inst, infra.reanudar(inst))
    else:
        # pausada y cancelada se apagan (cancelada se elimina del todo con "eliminar", tras la retención)
        _aplicar(inst, infra.detener(inst))
    auditoria.registrar(f"suscripcion.{nuevo}", "suscripcion", s.id, {"antes": anterior, "motivo": s.motivo_estado})


def reintentar_creacion(s: Suscripcion) -> None:
    """Si la creación falló (agente apagado, Docker caído…), vuelve a pedirla. El agente es idempotente."""
    inst = s.instancia
    if inst.estado_infra not in ("error", "sin_crear", "creando"):
        raise ReglaError("La instancia ya está creada.")
    if s.estado != "activa":
        raise ReglaError("Solo se crea la instancia de una suscripción activa.")
    _aplicar(inst, obtener().crear(inst, {"token": None, "panel_url": _url_panel()}))
    auditoria.registrar("instancia.reintentar", "instancia", inst.id, {"resultado": inst.estado_infra})


def cambiar_plan(s: Suscripcion, plan) -> None:
    if plan.id == s.plan_id:
        return
    if not plan.activo:
        raise ReglaError("Ese plan está archivado.")
    antes = s.plan.nombre
    s.plan = plan
    auditoria.registrar("suscripcion.plan", "suscripcion", s.id, {"antes": antes, "despues": plan.nombre})


def fijar_ajustes(s: Suscripcion, ajustes: dict) -> None:
    antes = {n: getattr(s, f"ajuste_{n}") for n in LIMITES}
    for n in LIMITES:
        setattr(s, f"ajuste_{n}", ajustes.get(n))
    auditoria.registrar("suscripcion.ajustes", "suscripcion", s.id,
                        {"antes": antes, "despues": {n: ajustes.get(n) for n in LIMITES}})


def rotar_token(inst: Instancia) -> str:
    token = _token_nuevo()
    inst.token_hash, inst.token_prefijo = hash_token(token), token[:10]
    auditoria.registrar("instancia.token", "instancia", inst.id)
    return token


def asignar_dominio(inst: Instancia, dominio: str | None) -> None:
    inst.dominio_propio = dominio or None
    inst.dominio_verificado = False
    inst.dominio_token = secrets.token_hex(16) if dominio else None
    auditoria.registrar("instancia.dominio", "instancia", inst.id, {"dominio": dominio})
    _aplicar(inst, obtener().actualizar_dominio(inst))


def registros_dns(inst: Instancia) -> list[dict]:
    """Lo que el cliente debe configurar en su DNS."""
    base = current_app.config["DOMINIO_BASE"]
    return [
        {"tipo": "CNAME", "nombre": inst.dominio_propio, "valor": f"{inst.subdominio}.{base}",
         "nota": "Apunta el dominio a la instancia (si es el dominio raíz, usa ALIAS/ANAME o un registro A con la IP del servidor)."},
        {"tipo": "TXT", "nombre": f"_restify.{inst.dominio_propio}", "valor": f"restify-verificacion={inst.dominio_token}",
         "nota": "Demuestra que el dominio es del cliente."},
    ]


def verificar_dominio(inst: Instancia) -> bool:
    """Busca el TXT de verificación. Sin él nadie puede reclamar un dominio ajeno."""
    if not inst.dominio_propio:
        raise ReglaError("La instancia no tiene dominio propio.")
    esperado = f"restify-verificacion={inst.dominio_token}"
    try:
        r = dns.resolver.resolve(f"_restify.{inst.dominio_propio}", "TXT", lifetime=5)
        valores = {b"".join(x.strings).decode(errors="ignore") for x in r}
    except dns.exception.DNSException:
        valores = set()
    ok = esperado in valores
    if ok:
        inst.dominio_verificado = True
        _aplicar(inst, obtener().actualizar_dominio(inst))
    auditoria.registrar("instancia.dominio_verificar", "instancia", inst.id,
                        {"dominio": inst.dominio_propio, "ok": ok})
    return ok


def eliminar_instancia(s: Suscripcion) -> None:
    if s.estado != "cancelada":
        raise ReglaError("Cancela la suscripción antes de eliminar la instancia.")
    inst = s.instancia
    resultado = obtener().eliminar(inst)
    if not resultado.ok:
        # No se suelta nada: si se diera por borrada quedarían contenedores huérfanos que nadie administra
        raise ReglaError(f"No se pudo eliminar la instancia, se conserva tal cual. {resultado.error}")
    _aplicar(inst, resultado)
    # Se libera el subdominio y el dominio propio; el registro de la suscripción queda como historial
    sub = inst.subdominio
    inst.subdominio = f"x{inst.id}-{secrets.token_hex(4)}"
    inst.dominio_propio, inst.dominio_verificado, inst.dominio_token = None, False, None
    inst.token_hash = hash_token(secrets.token_urlsafe(32))  # el token viejo deja de servir
    auditoria.registrar("instancia.eliminar", "instancia", inst.id, {"subdominio": sub})


def estado_para_instancia(s: Suscripcion) -> dict:
    return {
        "subdominio": s.instancia.subdominio,
        "estado": s.estado,
        "acceso": s.estado in ("activa",) and (s.vence_en is None or s.vence_en + timedelta(days=3) > ahora()),
        "motivo": s.motivo_estado if s.estado in ("suspendida", "pausada") else None,
        "plan": s.plan.nombre,
        "vence_en": s.vence_en.isoformat() if s.vence_en else None,
        "limites": s.limites(),  # None = ilimitado
    }
