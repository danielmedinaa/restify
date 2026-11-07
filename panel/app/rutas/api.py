"""API que consumen las instancias de Restify para saber si pueden operar y con qué límites."""

import hmac

from flask import Blueprint, jsonify, request

from app import seguridad as seg
from app.extensions import db
from app.modelos import Instancia, ahora
from app.servicios.suscripciones import estado_para_instancia, hash_token

api = Blueprint("api", __name__, url_prefix="/api/v1")

# Instancia "falsa" para que un token inexistente tarde igual que uno válido
_FALSO = hash_token("x")


@api.route("/estado")
def estado():
    """GET /api/v1/estado con `Authorization: Bearer rst_...`. Cada instancia solo ve lo suyo."""
    if seg.excedido(seg.clave_ip("api"), 120, 1):
        return jsonify(error="demasiadas_peticiones"), 429
    cabecera = request.headers.get("Authorization", "")
    token = cabecera[7:].strip() if cabecera.lower().startswith("bearer ") else ""
    inst = db.session.query(Instancia).filter_by(token_hash=hash_token(token)).first() if token else None
    if inst is None or not hmac.compare_digest(inst.token_hash, hash_token(token)):
        seg.registrar_intento(seg.clave_ip("api"))
        return jsonify(error="no_autorizado"), 401
    inst.ultima_consulta = ahora()
    db.session.commit()
    resp = jsonify(estado_para_instancia(inst.suscripcion))
    resp.headers["Cache-Control"] = "private, max-age=30"
    return resp
