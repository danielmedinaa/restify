"""Cabeceras, CSRF, límites de intentos, contraseñas, 2FA y control de acceso del panel."""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from functools import wraps

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, current_app, flash, g, redirect, request, session, url_for

from app.extensions import db
from app.modelos import Admin, Intento, ahora

CSP = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data:",
        "script-src 'self'",
        "style-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "object-src 'none'",
    ]
)

# ---------------------------------------------------------------- contraseñas

_hasher: PasswordHasher | None = None


def hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        _hasher = (
            PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
            if current_app.config["ARGON_RAPIDO"]
            else PasswordHasher()  # argon2id con los parámetros recomendados
        )
    return _hasher


def hashear(password: str) -> str:
    return hasher().hash(password)


def verificar_password(hash_: str, password: str) -> bool:
    try:
        return hasher().verify(hash_, password)
    except (VerificationError, InvalidHashError):
        return False


_COMUNES = {"password123", "contraseña123", "restify12345", "administrador", "1234567890ab"}


def validar_password(password: str, email: str = "") -> str | None:
    """Devuelve el motivo si la contraseña no sirve, o None."""
    if len(password) < 12:
        return "La contraseña debe tener al menos 12 caracteres."
    if len(password) > 128:
        return "La contraseña es demasiado larga (máximo 128)."
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)):
        return "Combina mayúsculas, minúsculas y números."
    if password.lower() in _COMUNES or (email and email.split("@")[0].lower() in password.lower()):
        return "Esa contraseña es demasiado predecible."
    return None


# ---------------------------------------------------------------- 2FA

def _fernet() -> Fernet:
    clave = hashlib.sha256(current_app.config["CLAVE_CIFRADO"].encode()).digest()
    return Fernet(base64.urlsafe_b64encode(clave))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descifrar(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def verificar_totp(admin: Admin, codigo: str) -> bool:
    """Acepta el código de ±30 s, pero cada paso solo una vez (anti-replay)."""
    codigo = re.sub(r"\s", "", codigo or "")
    secreto = descifrar(admin.totp_secreto) if admin.totp_secreto else None
    if not secreto or not re.fullmatch(r"\d{6}", codigo):
        return False
    totp = pyotp.TOTP(secreto)
    ahora_ts = int(ahora().timestamp())
    for desfase in (-1, 0, 1):
        paso = ahora_ts // 30 + desfase
        if paso <= admin.totp_ultimo_paso:
            continue
        if hmac.compare_digest(totp.at(paso * 30), codigo):
            admin.totp_ultimo_paso = paso
            return True
    return False


def generar_codigos_recuperacion() -> tuple[list[str], list[str]]:
    """(códigos en claro para mostrar una vez, hashes para guardar)."""
    claros = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(8)]
    return claros, [_hash_codigo(c) for c in claros]


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().lower().encode()).hexdigest()


def usar_codigo_recuperacion(admin: Admin, codigo: str) -> bool:
    h = _hash_codigo(codigo or "")
    for guardado in list(admin.codigos_recuperacion or []):
        if hmac.compare_digest(guardado, h):
            admin.codigos_recuperacion = [c for c in admin.codigos_recuperacion if c != guardado]
            return True
    return False


# ---------------------------------------------------------------- límite de intentos

def ip_cliente() -> str:
    return request.remote_addr or "desconocida"


def clave_ip(prefijo: str) -> str:
    sal = current_app.config["SECRET_KEY"]
    return f"{prefijo}:{hashlib.sha256(f'{sal}:{ip_cliente()}'.encode()).hexdigest()[:40]}"


def hash_ip() -> str:
    return clave_ip("ip").split(":", 1)[1]


def excedido(clave: str, maximo: int, ventana_min: int) -> bool:
    desde = ahora() - timedelta(minutes=ventana_min)
    n = db.session.query(Intento).filter(Intento.clave == clave, Intento.creado_en >= desde).count()
    return n >= maximo


def registrar_intento(clave: str) -> None:
    db.session.add(Intento(clave=clave))
    # Limpieza barata de lo viejo
    db.session.query(Intento).filter(Intento.creado_en < ahora() - timedelta(days=1)).delete()
    db.session.commit()


# ---------------------------------------------------------------- CSRF

def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido() -> bool:
    esperado = session.get("csrf")
    enviado = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
    return bool(esperado and enviado and secrets.compare_digest(esperado, enviado))


# ---------------------------------------------------------------- sesión y permisos

def iniciar_sesion(admin: Admin) -> None:
    session.clear()
    session.permanent = False
    session["admin_id"] = admin.id
    session["version"] = admin.version_sesion
    session["inicio"] = ahora().timestamp()
    session["visto"] = ahora().timestamp()
    admin.ultimo_acceso = ahora()
    admin.intentos_fallidos = 0
    admin.bloqueado_hasta = None
    token_csrf()


def cargar_admin() -> Admin | None:
    """Admin de la sesión si sigue siendo válida (existe, activo, misma versión, sin caducar)."""
    if "admin_id" not in session:
        return None
    cfg = current_app.config
    t = ahora().timestamp()
    admin = db.session.get(Admin, session["admin_id"])
    valida = (
        admin is not None
        and admin.activo
        and admin.version_sesion == session.get("version")
        and t - session.get("visto", 0) < cfg["SESION_INACTIVIDAD_MIN"] * 60
        and t - session.get("inicio", 0) < cfg["SESION_MAXIMA_HORAS"] * 3600
    )
    if not valida:
        session.clear()
        return None
    session["visto"] = t
    return admin


def requiere_login(vista):
    @wraps(vista)
    def envoltura(*a, **k):
        if g.admin is None:
            return redirect(url_for("auth.login", siguiente=request.path if request.method == "GET" else None))
        if g.admin.debe_cambiar_password and request.endpoint not in ("cuenta.password", "auth.salir", "static"):
            return redirect(url_for("cuenta.password"))
        return vista(*a, **k)

    return envoltura


def requiere(modulo: str, accion: str):
    def deco(vista):
        @wraps(vista)
        @requiere_login
        def envoltura(*a, **k):
            if not g.admin.puede(modulo, accion):
                from app import auditoria

                auditoria.registrar("acceso.denegado", detalle={"modulo": modulo, "accion": accion, "ruta": request.path})
                abort(403)
            return vista(*a, **k)

        return envoltura

    return deco


def confirmar_password() -> bool:
    """Acciones destructivas: se vuelve a pedir la contraseña del administrador."""
    p = request.form.get("confirmar_password", "")
    return bool(p) and verificar_password(g.admin.password_hash, p)


def puede_otorgar(admin: Admin, permisos: dict) -> bool:
    """Nadie da permisos que no tiene."""
    if admin.rol.es_sistema:
        return True
    return all(admin.puede(m, a) for m, acciones in permisos.items() for a in acciones)


# ---------------------------------------------------------------- registro en la app

def registrar(app: Flask) -> None:
    @app.before_request
    def antes():
        g.admin = cargar_admin()
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.path.startswith("/api/"):
            if not csrf_valido():
                abort(400, "Formulario caducado: recarga la página e inténtalo de nuevo.")
        # Todo POST de una sesión que no es la de un admin completo solo llega a login/2FA

    @app.after_request
    def cabeceras(resp):
        h = resp.headers
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if app.config["ES_PRODUCCION"]:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        if request.path.startswith("/static/"):
            h.setdefault("Cache-Control", "public, max-age=604800")
        else:
            # Páginas con datos de clientes: que ningún navegador ni proxy las guarde
            h["Cache-Control"] = "no-store"
            h["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    app.jinja_env.globals["csrf_token"] = token_csrf
