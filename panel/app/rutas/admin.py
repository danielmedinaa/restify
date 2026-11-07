"""Administradores del panel, roles con matriz de permisos y consulta de la bitácora."""

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app import auditoria, seguridad as seg
from app.extensions import db
from app.modelos import ACCIONES, MODULOS, Admin, Evento, Rol, ahora
from app.servicios.validacion import _EMAIL, texto

admin = Blueprint("admin", __name__)


def _o404(modelo, id_):
    obj = db.session.get(modelo, id_)
    if obj is None:
        abort(404)
    return obj


def _permisos_del_form() -> dict:
    return {m: [a for a in ACCIONES if request.form.get(f"{m}.{a}")] for m in MODULOS if any(request.form.get(f"{m}.{a}") for a in ACCIONES)}


# ---------------------------------------------------------------- administradores

@admin.route("/usuarios")
@seg.requiere("usuarios", "leer")
def usuarios():
    return render_template("usuarios.html", usuarios=db.session.query(Admin).order_by(Admin.nombre).all())


@admin.route("/usuarios/nuevo", methods=["GET", "POST"])
@admin.route("/usuarios/<int:id>", methods=["GET", "POST"])
@seg.requiere_login
def usuario_form(id=None):
    if not g.admin.puede("usuarios", "editar" if id else "crear"):
        abort(403)
    u = _o404(Admin, id) if id else None
    if u and u.id == g.admin.id:
        flash("Tu propia cuenta se gestiona en «Mi cuenta» (no puedes cambiar tu rol ni desactivarte).", "error")
        return redirect(url_for("admin.usuarios"))
    roles = db.session.query(Rol).order_by(Rol.nombre).all()
    # Solo se puede asignar un rol cuyos permisos uno mismo tiene
    asignables = [r for r in roles if seg.puede_otorgar(g.admin, {} if r.es_sistema and not g.admin.rol.es_sistema else r.permisos) and (g.admin.rol.es_sistema or not r.es_sistema)]
    errores, d = {}, {}
    if request.method == "POST":
        d = {"nombre": texto(request.form.get("nombre"), 80), "email": texto(request.form.get("email"), 254).lower()}
        if len(d["nombre"]) < 2:
            errores["nombre"] = "Escribe el nombre."
        if not _EMAIL.match(d["email"]):
            errores["email"] = "Correo no válido."
        rol = next((r for r in asignables if str(r.id) == request.form.get("rol_id")), None)
        if rol is None:
            errores["rol_id"] = "Elige un rol que puedas asignar."
        password = request.form.get("password", "")
        if u is None and (e := seg.validar_password(password, d["email"])):
            errores["password"] = e
        if not errores:
            if u is None:
                u = Admin(email=d["email"], nombre=d["nombre"], rol=rol, password_hash=seg.hashear(password),
                          debe_cambiar_password=True)
                db.session.add(u)
                accion = "usuario.crear"
            else:
                if u.rol.es_sistema and not g.admin.rol.es_sistema:
                    abort(403)
                if rol.id != u.rol_id or request.form.get("activo") != "1":
                    u.version_sesion += 1
                u.nombre, u.email, u.rol = d["nombre"], d["email"], rol
                u.activo = request.form.get("activo") == "1"
                accion = "usuario.editar"
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errores["email"] = "Ya existe un administrador con ese correo."
            else:
                auditoria.registrar(accion, "admin", u.id, {"email": u.email, "rol": rol.nombre, "activo": u.activo})
                db.session.commit()
                flash("Administrador guardado." + (" Deberá cambiar su contraseña y configurar el 2FA al entrar." if accion.endswith("crear") else ""), "ok")
                return redirect(url_for("admin.usuarios"))
    return render_template("usuario_form.html", u=u, d=d or u, roles=asignables, errores=errores)


@admin.route("/usuarios/<int:id>/reiniciar", methods=["POST"])
@seg.requiere("usuarios", "editar")
def usuario_reiniciar(id):
    """Si pierde el celular: se borra su 2FA, se cierran sus sesiones y debe volver a configurarlo."""
    u = _o404(Admin, id)
    if u.id == g.admin.id or (u.rol.es_sistema and not g.admin.rol.es_sistema):
        abort(403)
    if not seg.confirmar_password():
        flash("Confirma tu contraseña para reiniciar el 2FA.", "error")
        return redirect(url_for("admin.usuario_form", id=id))
    u.totp_secreto, u.totp_confirmado, u.totp_ultimo_paso, u.codigos_recuperacion = None, False, 0, []
    u.version_sesion += 1
    u.bloqueado_hasta, u.intentos_fallidos = None, 0
    auditoria.registrar("usuario.reiniciar_2fa", "admin", u.id)
    db.session.commit()
    flash("2FA reiniciado: configurará uno nuevo en su próximo ingreso.", "ok")
    return redirect(url_for("admin.usuarios"))


# ---------------------------------------------------------------- roles

@admin.route("/roles")
@seg.requiere("roles", "leer")
def roles():
    return render_template("roles.html", roles=db.session.query(Rol).order_by(Rol.nombre).all(), modulos=MODULOS)


@admin.route("/roles/nuevo", methods=["GET", "POST"])
@admin.route("/roles/<int:id>", methods=["GET", "POST"])
@seg.requiere_login
def rol_form(id=None):
    if not g.admin.puede("roles", "editar" if id else "crear"):
        abort(403)
    rol = _o404(Rol, id) if id else None
    if rol and (rol.es_sistema or rol.id == g.admin.rol_id):
        flash("Ese rol no se puede editar (es del sistema o es el tuyo).", "error")
        return redirect(url_for("admin.roles"))
    errores = {}
    if request.method == "POST":
        nombre, permisos = texto(request.form.get("nombre"), 60), _permisos_del_form()
        if len(nombre) < 2:
            errores["nombre"] = "Escribe el nombre del rol."
        if not seg.puede_otorgar(g.admin, permisos):
            errores["permisos"] = "No puedes otorgar permisos que tú no tienes."
        if not errores:
            if rol is None:
                rol = Rol(nombre=nombre)
                db.session.add(rol)
            rol.nombre, rol.descripcion, rol.permisos = nombre, texto(request.form.get("descripcion"), 200) or None, permisos
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errores["nombre"] = "Ya existe un rol con ese nombre."
            else:
                # Los permisos cambiaron: se cierran las sesiones de quienes tienen este rol
                for u in rol.usuarios:
                    u.version_sesion += 1
                auditoria.registrar("rol.guardar", "rol", rol.id, {"nombre": nombre, "permisos": permisos})
                db.session.commit()
                flash("Rol guardado. Quienes lo tienen deberán iniciar sesión de nuevo.", "ok")
                return redirect(url_for("admin.roles"))
    return render_template("rol_form.html", rol=rol, modulos=MODULOS, acciones=ACCIONES, errores=errores,
                           mios=g.admin.rol.permisos if not g.admin.rol.es_sistema else None)


@admin.route("/roles/<int:id>/eliminar", methods=["POST"])
@seg.requiere("roles", "eliminar")
def rol_eliminar(id):
    rol = _o404(Rol, id)
    if rol.es_sistema or rol.usuarios:
        flash("No se puede eliminar: es del sistema o tiene administradores asignados.", "error")
    else:
        auditoria.registrar("rol.eliminar", "rol", rol.id, {"nombre": rol.nombre})
        db.session.delete(rol)
        db.session.commit()
        flash("Rol eliminado.", "ok")
    return redirect(url_for("admin.roles"))


# ---------------------------------------------------------------- auditoría

@admin.route("/auditoria")
@seg.requiere("auditoria", "leer")
def bitacora():
    q = db.session.query(Evento).order_by(Evento.id.desc())
    accion = (request.args.get("accion") or "").strip()[:60]
    if accion:
        q = q.filter(Evento.accion.like(accion.replace("%", "") + "%"))
    integra, roto = auditoria.verificar_cadena() if request.args.get("verificar") else (None, None)
    return render_template("auditoria.html", eventos=q.limit(300).all(), accion=accion, integra=integra, roto=roto)
