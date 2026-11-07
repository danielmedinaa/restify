"""Dashboard, clientes, planes, suscripciones e instancias."""

from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import auditoria, seguridad as seg
from app.extensions import db
from datetime import UTC
from app.modelos import ESTADOS, LIMITES, TRANSICIONES, Cliente, Instancia, Plan, Suscripcion, ahora
from app.servicios import suscripciones as svc
from app.servicios import validacion as val

gestion = Blueprint("gestion", __name__)


def _o404(modelo, id_):
    obj = db.session.get(modelo, id_)
    if obj is None:
        abort(404)
    return obj


def _fecha(valor: str | None) -> datetime | None:
    try:
        return datetime.combine(date.fromisoformat(valor), time(23, 59), tzinfo=UTC) if valor else None
    except ValueError:
        raise svc.ReglaError("Fecha no válida.")


# ---------------------------------------------------------------- dashboard

@gestion.route("/")
@seg.requiere_login
def inicio():
    por_estado = dict(db.session.query(Suscripcion.estado, func.count()).group_by(Suscripcion.estado).all())
    mrr = (
        db.session.query(func.coalesce(func.sum(Plan.precio_mensual), 0))
        .join(Suscripcion, Suscripcion.plan_id == Plan.id)
        .filter(Suscripcion.estado == "activa")
        .scalar()
    )
    limite = ahora() + timedelta(days=7)
    por_vencer = (
        db.session.query(Suscripcion)
        .filter(Suscripcion.estado.in_(["activa", "pausada"]), Suscripcion.vence_en.isnot(None), Suscripcion.vence_en <= limite)
        .order_by(Suscripcion.vence_en).limit(10).all()
    )
    con_error = db.session.query(Instancia).filter(Instancia.estado_infra == "error").all()
    return render_template(
        "inicio.html", por_estado=por_estado, mrr=mrr, por_vencer=por_vencer, con_error=con_error,
        total_clientes=db.session.query(func.count(Cliente.id)).scalar(), ahora=ahora(),
    )


# ---------------------------------------------------------------- clientes

@gestion.route("/clientes")
@seg.requiere("clientes", "leer")
def clientes():
    q = (request.args.get("q") or "").strip()[:80]
    consulta = db.session.query(Cliente)
    if q:
        patron = f"%{q.replace('%', '').replace('_', '')}%"
        consulta = consulta.outerjoin(Suscripcion).outerjoin(Instancia).filter(
            Cliente.nombre.ilike(patron) | Cliente.email.ilike(patron) | Cliente.rif.ilike(patron)
            | Instancia.subdominio.ilike(patron) | Instancia.dominio_propio.ilike(patron)
        ).distinct()
    return render_template("clientes.html", clientes=consulta.order_by(Cliente.nombre).limit(200).all(), q=q)


@gestion.route("/clientes/nuevo", methods=["GET", "POST"])
@seg.requiere("clientes", "crear")
def cliente_nuevo():
    datos, errores = {}, {}
    if request.method == "POST":
        datos, errores = val.validar_cliente(request.form)
        if not errores:
            c = Cliente(**datos)
            db.session.add(c)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errores["rif"] = "Ya existe un cliente con ese RIF."
            else:
                auditoria.registrar("cliente.crear", "cliente", c.id, {"nombre": c.nombre})
                db.session.commit()
                flash("Cliente creado. Ahora crea su suscripción e instancia.", "ok")
                return redirect(url_for("gestion.cliente", id=c.id))
    return render_template("cliente_form.html", c=datos, errores=errores, nuevo=True)


@gestion.route("/clientes/<int:id>")
@seg.requiere("clientes", "leer")
def cliente(id):
    return render_template("cliente.html", c=_o404(Cliente, id), estados=ESTADOS)


@gestion.route("/clientes/<int:id>/editar", methods=["GET", "POST"])
@seg.requiere("clientes", "editar")
def cliente_editar(id):
    c = _o404(Cliente, id)
    datos, errores = {}, {}
    if request.method == "POST":
        datos, errores = val.validar_cliente(request.form)
        if not errores:
            for k, v in datos.items():
                setattr(c, k, v)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errores["rif"] = "Ya existe un cliente con ese RIF."
            else:
                auditoria.registrar("cliente.editar", "cliente", c.id)
                db.session.commit()
                flash("Cliente actualizado.", "ok")
                return redirect(url_for("gestion.cliente", id=c.id))
    return render_template("cliente_form.html", c=datos or c, errores=errores, nuevo=False, cliente=c)


# ---------------------------------------------------------------- planes

@gestion.route("/planes")
@seg.requiere("planes", "leer")
def planes():
    usos = dict(db.session.query(Suscripcion.plan_id, func.count()).group_by(Suscripcion.plan_id).all())
    return render_template("planes.html", planes=db.session.query(Plan).order_by(Plan.precio_mensual).all(), usos=usos)


@gestion.route("/planes/nuevo", methods=["GET", "POST"])
@gestion.route("/planes/<int:id>", methods=["GET", "POST"])
@seg.requiere_login
def plan_form(id=None):
    accion = "editar" if id else "crear"
    if not g.admin.puede("planes", accion):
        abort(403)
    plan = _o404(Plan, id) if id else None
    datos, errores = {}, {}
    if request.method == "POST":
        datos, errores = val.validar_plan(request.form)
        if not errores:
            if plan is None:
                plan = Plan(**datos)
                db.session.add(plan)
                antes = None
            else:
                antes = {k: getattr(plan, k) for k in datos}
                for k, v in datos.items():
                    setattr(plan, k, v)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errores["nombre"] = "Ya existe un plan con ese nombre."
            else:
                auditoria.registrar(f"plan.{accion}", "plan", plan.id,
                                    {"antes": {k: str(v) for k, v in (antes or {}).items()},
                                     "despues": {k: str(v) for k, v in datos.items()}})
                db.session.commit()
                flash("Plan guardado. Las suscripciones que lo usan ya tienen los nuevos límites.", "ok")
                return redirect(url_for("gestion.planes"))
    return render_template("plan_form.html", plan=plan, p=datos or plan, errores=errores, limites=LIMITES)


@gestion.route("/planes/<int:id>/archivar", methods=["POST"])
@seg.requiere("planes", "eliminar")
def plan_archivar(id):
    plan = _o404(Plan, id)
    plan.activo = not plan.activo
    auditoria.registrar("plan.archivar" if not plan.activo else "plan.restaurar", "plan", plan.id)
    db.session.commit()
    flash("Plan archivado: no se ofrece a clientes nuevos." if not plan.activo else "Plan restaurado.", "ok")
    return redirect(url_for("gestion.planes"))


# ---------------------------------------------------------------- suscripciones e instancias

@gestion.route("/suscripciones")
@seg.requiere("suscripciones", "leer")
def suscripciones():
    estado = request.args.get("estado")
    q = db.session.query(Suscripcion).join(Cliente).order_by(Cliente.nombre)
    if estado in ESTADOS:
        q = q.filter(Suscripcion.estado == estado)
    return render_template("suscripciones.html", subs=q.limit(300).all(), estado=estado, estados=ESTADOS)


@gestion.route("/clientes/<int:id>/suscripcion", methods=["GET", "POST"])
@seg.requiere("suscripciones", "crear")
def suscripcion_nueva(id):
    c = _o404(Cliente, id)
    planes = db.session.query(Plan).filter_by(activo=True).order_by(Plan.precio_mensual).all()
    errores, sub = {}, ""
    if request.method == "POST":
        sub = (request.form.get("subdominio") or "").strip().lower()
        plan = db.session.get(Plan, int(request.form["plan_id"])) if request.form.get("plan_id", "").isdigit() else None
        if plan is None or not plan.activo:
            errores["plan_id"] = "Elige un plan."
        if e := val.validar_subdominio(sub):
            errores["subdominio"] = e
        if not errores:
            try:
                s, token = svc.crear(c, plan, sub)
                db.session.commit()
            except svc.ReglaError as e:
                db.session.rollback()
                errores["plan_id"] = str(e)
            except IntegrityError:
                db.session.rollback()
                errores["subdominio"] = "Ese subdominio ya está en uso."
            else:
                return render_template("token.html", s=s, token=token, url=svc.url_instancia(s.instancia), nuevo=True)
    return render_template("suscripcion_nueva.html", c=c, planes=planes, errores=errores, sub=sub,
                           base=current_app.config["DOMINIO_BASE"])


@gestion.route("/suscripciones/<int:id>")
@seg.requiere("suscripciones", "leer")
def suscripcion(id):
    s = _o404(Suscripcion, id)
    planes = db.session.query(Plan).filter((Plan.activo.is_(True)) | (Plan.id == s.plan_id)).order_by(Plan.precio_mensual).all()
    dns = svc.registros_dns(s.instancia) if s.instancia.dominio_propio else []
    return render_template("suscripcion.html", s=s, planes=planes, estados=ESTADOS, limites=LIMITES, dns=dns,
                           permitidos=TRANSICIONES[s.estado], url=svc.url_instancia(s.instancia))


def _con_regla(accion):
    """Ejecuta una acción de negocio; los errores de regla se muestran sin romper la página."""
    try:
        accion()
        db.session.commit()
        return True
    except svc.ReglaError as e:
        db.session.rollback()
        flash(str(e), "error")
        return False


@gestion.route("/suscripciones/<int:id>/estado", methods=["POST"])
@seg.requiere("suscripciones", "editar")
def suscripcion_estado(id):
    s = _o404(Suscripcion, id)
    nuevo = request.form.get("estado", "")
    if nuevo == "cancelada" and not seg.confirmar_password():
        flash("Para cancelar confirma tu contraseña.", "error")
    elif _con_regla(lambda: svc.cambiar_estado(s, nuevo, request.form.get("motivo"))):
        flash(f"Suscripción {ESTADOS[nuevo].lower()}.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/plan", methods=["POST"])
@seg.requiere("suscripciones", "editar")
def suscripcion_plan(id):
    s = _o404(Suscripcion, id)
    plan = db.session.get(Plan, int(request.form["plan_id"])) if request.form.get("plan_id", "").isdigit() else None
    if plan is None:
        abort(400)
    if _con_regla(lambda: svc.cambiar_plan(s, plan)):
        flash("Plan actualizado: los nuevos límites aplican de inmediato.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/limites", methods=["POST"])
@seg.requiere("suscripciones", "editar")
def suscripcion_limites(id):
    s = _o404(Suscripcion, id)
    errores: dict = {}
    ajustes = {n: val.entero_o_none(request.form.get(n), n, errores) for n in LIMITES}
    if errores:
        flash("Revisa los límites: " + " ".join(errores.values()), "error")
    else:
        svc.fijar_ajustes(s, ajustes)
        db.session.commit()
        flash("Límites a la medida guardados.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/vencimiento", methods=["POST"])
@seg.requiere("suscripciones", "editar")
def suscripcion_vencimiento(id):
    s = _o404(Suscripcion, id)

    def aplicar():
        nuevo = _fecha(request.form.get("vence_en"))
        antes = s.vence_en.date().isoformat() if s.vence_en else None
        s.vence_en = nuevo
        auditoria.registrar("suscripcion.vencimiento", "suscripcion", s.id,
                            {"antes": antes, "despues": nuevo.date().isoformat() if nuevo else None})

    if _con_regla(aplicar):
        flash("Vencimiento actualizado.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/dominio", methods=["POST"])
@seg.requiere("instancias", "editar")
def instancia_dominio(id):
    s = _o404(Suscripcion, id)
    dominio = (request.form.get("dominio") or "").strip().lower().rstrip(".")
    if dominio and (e := val.validar_dominio_propio(dominio, s.instancia.id)):
        flash(e, "error")
    else:
        svc.asignar_dominio(s.instancia, dominio or None)
        db.session.commit()
        flash("Dominio guardado. Pásale al cliente los registros DNS." if dominio else "Dominio propio quitado.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/dominio/verificar", methods=["POST"])
@seg.requiere("instancias", "editar")
def instancia_dominio_verificar(id):
    s = _o404(Suscripcion, id)
    try:
        ok = svc.verificar_dominio(s.instancia)
        db.session.commit()
        flash("Dominio verificado." if ok else "Todavía no vemos el registro TXT. El DNS puede tardar en propagarse.",
              "ok" if ok else "error")
    except svc.ReglaError as e:
        db.session.rollback()
        flash(str(e), "error")
    return redirect(url_for("gestion.suscripcion", id=id))


SERVICIOS_LOGS = ("api", "front", "db", "redis")


@gestion.route("/suscripciones/<int:id>/contenedores")
@seg.requiere("instancias", "editar")
def instancia_contenedores(id):
    """Contenedores de la instancia y, si se pide un servicio, sus últimos logs."""
    from app.infra import aprovisionador

    s = _o404(Suscripcion, id)
    apr = aprovisionador.obtener()
    lista, error = apr.contenedores(s.instancia)
    servicio = request.args.get("servicio")
    texto = log_error = None
    lineas = request.args.get("lineas", 200, type=int)
    lineas = max(10, min(lineas, 1000))
    if servicio:
        if servicio not in SERVICIOS_LOGS:
            abort(404)
        texto, log_error = apr.logs(s.instancia, servicio, lineas)
        auditoria.registrar("instancia.logs", "instancia", s.instancia.id, {"servicio": servicio, "lineas": lineas})
        db.session.commit()
    return render_template("instancia_contenedores.html", s=s, contenedores=lista, error=error,
                           servicio=servicio, logs=texto, log_error=log_error, lineas=lineas)


@gestion.route("/suscripciones/<int:id>/reintentar", methods=["POST"])
@seg.requiere("instancias", "editar")
def instancia_reintentar(id):
    s = _o404(Suscripcion, id)
    if _con_regla(lambda: svc.reintentar_creacion(s)):
        flash("Instancia creada." if s.instancia.estado_infra == "en_linea" else "No se pudo crear: " + (s.instancia.error_infra or ""), "ok" if s.instancia.estado_infra == "en_linea" else "error")
    return redirect(url_for("gestion.suscripcion", id=id))


@gestion.route("/suscripciones/<int:id>/token", methods=["POST"])
@seg.requiere("instancias", "editar")
def instancia_token(id):
    s = _o404(Suscripcion, id)
    if not seg.confirmar_password():
        flash("Para rotar el token confirma tu contraseña.", "error")
        return redirect(url_for("gestion.suscripcion", id=id))
    token = svc.rotar_token(s.instancia)
    db.session.commit()
    return render_template("token.html", s=s, token=token, url=svc.url_instancia(s.instancia), nuevo=False)


@gestion.route("/suscripciones/<int:id>/eliminar", methods=["POST"])
@seg.requiere("instancias", "eliminar")
def instancia_eliminar(id):
    s = _o404(Suscripcion, id)
    if request.form.get("subdominio") != s.instancia.subdominio or not seg.confirmar_password():
        flash("Escribe el subdominio exacto y tu contraseña para eliminar.", "error")
    elif _con_regla(lambda: svc.eliminar_instancia(s)):
        flash("Instancia eliminada.", "ok")
    return redirect(url_for("gestion.suscripcion", id=id))
