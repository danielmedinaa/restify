"""Bitácora encadenada por hash. Se escribe en la misma transacción que la acción auditada."""

import hashlib
import json

from flask import g, has_request_context

from app.extensions import db
from app.modelos import Evento, ahora

GENESIS = "0" * 64


def _calcular(prev: str, e: Evento) -> str:
    cuerpo = json.dumps(
        [e.creado_en.replace(tzinfo=None).isoformat(), e.admin_id, e.admin_email, e.accion, e.entidad,
         e.entidad_id, e.detalle, e.ip_hash],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(f"{prev}|{cuerpo}".encode()).hexdigest()


def registrar(accion: str, entidad: str | None = None, entidad_id: int | None = None,
              detalle: dict | None = None, admin=None) -> Evento:
    from app.seguridad import hash_ip

    admin = admin or (g.get("admin") if has_request_context() else None)
    ultimo = db.session.query(Evento).order_by(Evento.id.desc()).first()
    e = Evento(
        creado_en=ahora(),
        admin_id=admin.id if admin else None,
        admin_email=admin.email if admin else None,
        accion=accion,
        entidad=entidad,
        entidad_id=entidad_id,
        detalle=detalle or {},
        ip_hash=hash_ip() if has_request_context() else None,
        hash_prev=ultimo.hash if ultimo else GENESIS,
    )
    e.hash = _calcular(e.hash_prev, e)
    db.session.add(e)
    db.session.flush()
    return e


def verificar_cadena() -> tuple[bool, int | None]:
    """(íntegra, id del primer evento alterado)."""
    prev = GENESIS
    for e in db.session.query(Evento).order_by(Evento.id):
        # SQLite devuelve las fechas sin zona; el hash se calculó sin ella, así que coincide
        if e.hash_prev != prev or _calcular(prev, e) != e.hash:
            return False, e.id
        prev = e.hash
    return True, None
