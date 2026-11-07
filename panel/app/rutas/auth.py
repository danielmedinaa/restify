"""Login en dos pasos (contraseña + TOTP), configuración del 2FA y cuenta propia."""

from datetime import timedelta

import pyotp
import segno
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from app import auditoria, seguridad as seg
from app.extensions import db
from app.modelos import Admin, ahora

auth = Blueprint("auth", __name__)
cuenta = Blueprint("cuenta", __name__, url_prefix="/cuenta")

MAX_FALLOS = 5
BLOQUEO_MIN = 15
# Hash de una contraseña inexistente: se verifica igual para que tardar lo mismo no delate qué emails existen
_FALSO = None


def _falso() -> str:
    global _FALSO
    if _FALSO is None:
        _FALSO = seg.hashear("no-existe-" + "x" * 12)
    return _FALSO


def _destino_seguro(ruta: str | None) -> str:
    # Solo rutas internas ("/algo"), nunca "//otro.sitio" ni esquemas
    if ruta and ruta.startswith("/") and not ruta.startswith("//") and "\\" not in ruta:
        return ruta
    return url_for("gestion.inicio")


def _fallo(admin: Admin | None, motivo: str) -> None:
    if admin:
        admin.intentos_fallidos += 1
        if admin.intentos_fallidos >= MAX_FALLOS:
            admin.bloqueado_hasta = ahora() + timedelta(minutes=BLOQUEO_MIN)
            admin.intentos_fallidos = 0
            auditoria.registrar("auth.bloqueo", "admin", admin.id, {"motivo": motivo}, admin=admin)
    seg.registrar_intento(seg.clave_ip("login"))
    auditoria.registrar("auth.fallo", detalle={"motivo": motivo}, admin=admin)
    db.session.commit()


@auth.route("/login", methods=["GET", "POST"])
def login():
    if g.admin:
        return redirect(url_for("gestion.inicio"))
    if request.method == "POST":
        if seg.excedido(seg.clave_ip("login"), 10, 15):
            return render_template("login.html", error="Demasiados intentos. Espera unos minutos."), 429
        email = (request.form.get("email") or "").strip().lower()[:254]
        password = (request.form.get("password") or "")[:200]
        admin = db.session.query(Admin).filter_by(email=email).first()
        valido = seg.verificar_password(admin.password_hash if admin else _falso(), password)
        bloqueado = bool(admin and admin.bloqueado_hasta and admin.bloqueado_hasta > ahora())
        if not (admin and valido and admin.activo) or bloqueado:
            _fallo(admin, "bloqueada" if bloqueado else "credenciales")
            msg = "Cuenta bloqueada temporalmente por demasiados intentos." if bloqueado else "Correo o contraseña incorrectos."
            return render_template("login.html", error=msg, email=email), 401
        # Paso 1 listo: aún no hay sesión de admin, solo una "pre-sesión" de 5 minutos
        session.clear()
        session["pre_admin"] = admin.id
        session["pre_hasta"] = (ahora() + timedelta(minutes=5)).timestamp()
        session["siguiente"] = _destino_seguro(request.args.get("siguiente"))
        seg.token_csrf()
        return redirect(url_for("auth.segundo_paso" if admin.totp_confirmado else "auth.configurar_2fa"))
    return render_template("login.html")


def _pre_admin() -> Admin | None:
    if session.get("pre_hasta", 0) < ahora().timestamp():
        session.pop("pre_admin", None)
        return None
    return db.session.get(Admin, session.get("pre_admin") or 0)


def _completar(admin: Admin):
    destino = session.get("siguiente") or url_for("gestion.inicio")
    seg.iniciar_sesion(admin)
    auditoria.registrar("auth.login", "admin", admin.id, admin=admin)
    db.session.commit()
    return redirect(_destino_seguro(destino))


@auth.route("/login/2fa", methods=["GET", "POST"])
def segundo_paso():
    admin = _pre_admin()
    if not admin or not admin.totp_confirmado:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        if seg.excedido(seg.clave_ip("login"), 10, 15):
            return render_template("login_2fa.html", error="Demasiados intentos. Espera unos minutos."), 429
        codigo = (request.form.get("codigo") or "")[:20]
        ok = seg.verificar_totp(admin, codigo) or seg.usar_codigo_recuperacion(admin, codigo)
        if ok:
            return _completar(admin)
        _fallo(admin, "2fa")
        return render_template("login_2fa.html", error="Código incorrecto."), 401
    return render_template("login_2fa.html")


@auth.route("/login/2fa/configurar", methods=["GET", "POST"])
def configurar_2fa():
    """Primer ingreso: el 2FA es obligatorio, no se puede entrar sin configurarlo."""
    admin = _pre_admin()
    if not admin or admin.totp_confirmado:
        return redirect(url_for("auth.login"))
    if "totp_pendiente" not in session:
        session["totp_pendiente"] = pyotp.random_base32()
    secreto = session["totp_pendiente"]
    uri = pyotp.TOTP(secreto).provisioning_uri(name=admin.email, issuer_name="RESTIFY Panel")
    if request.method == "POST":
        admin.totp_secreto = seg.cifrar(secreto)
        admin.totp_ultimo_paso = 0
        if seg.verificar_totp(admin, request.form.get("codigo", "")):
            admin.totp_confirmado = True
            claros, hashes = seg.generar_codigos_recuperacion()
            admin.codigos_recuperacion = hashes
            session.pop("totp_pendiente", None)
            auditoria.registrar("auth.2fa_activado", "admin", admin.id, admin=admin)
            db.session.commit()
            session["codigos_mostrar"] = claros
            session["pre_hasta"] = (ahora() + timedelta(minutes=5)).timestamp()
            return redirect(url_for("auth.codigos"))
        db.session.rollback()
        return render_template("configurar_2fa.html", qr=segno.make(uri).svg_data_uri(scale=5), secreto=secreto,
                               error="Código incorrecto. Revisa la hora de tu teléfono."), 400
    return render_template("configurar_2fa.html", qr=segno.make(uri).svg_data_uri(scale=5), secreto=secreto)


@auth.route("/login/codigos", methods=["GET", "POST"])
def codigos():
    """Muestra los códigos de recuperación UNA vez, antes de entrar."""
    admin = _pre_admin()
    claros = session.get("codigos_mostrar")
    if not admin or not claros:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        session.pop("codigos_mostrar", None)
        return _completar(admin)
    return render_template("codigos.html", codigos=claros)


@auth.route("/salir", methods=["POST"])
def salir():
    if g.admin:
        auditoria.registrar("auth.salir", "admin", g.admin.id)
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login"))


@auth.route("/salud")
def salud():
    return {"ok": True}


# ---------------------------------------------------------------- cuenta propia

@cuenta.route("/password", methods=["GET", "POST"])
@seg.requiere_login
def password():
    if request.method == "POST":
        actual = request.form.get("actual", "")
        nueva = request.form.get("nueva", "")
        error = None
        if not seg.verificar_password(g.admin.password_hash, actual):
            error = "La contraseña actual no es correcta."
        elif nueva == actual:
            error = "La nueva contraseña debe ser distinta."
        elif nueva != request.form.get("repetir", ""):
            error = "Las contraseñas no coinciden."
        else:
            error = seg.validar_password(nueva, g.admin.email)
        if error:
            return render_template("cuenta_password.html", error=error), 400
        g.admin.password_hash = seg.hashear(nueva)
        g.admin.debe_cambiar_password = False
        g.admin.version_sesion += 1  # cierra las demás sesiones
        auditoria.registrar("auth.password", "admin", g.admin.id)
        db.session.commit()
        seg.iniciar_sesion(g.admin)
        db.session.commit()
        flash("Contraseña actualizada. Se cerraron tus otras sesiones.", "ok")
        return redirect(url_for("gestion.inicio"))
    return render_template("cuenta_password.html")


@cuenta.route("/codigos", methods=["GET", "POST"])
@seg.requiere_login
def regenerar_codigos():
    if request.method == "POST":
        if not seg.verificar_password(g.admin.password_hash, request.form.get("actual", "")):
            return render_template("cuenta_codigos.html", error="Contraseña incorrecta."), 400
        claros, hashes = seg.generar_codigos_recuperacion()
        g.admin.codigos_recuperacion = hashes
        auditoria.registrar("auth.codigos_regenerados", "admin", g.admin.id)
        db.session.commit()
        return render_template("codigos.html", codigos=claros, desde_cuenta=True)
    return render_template("cuenta_codigos.html")
