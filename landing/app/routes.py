from datetime import date
from urllib.parse import quote

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from app import leads
from app.seguridad import csrf_valido, ip_cliente

bp = Blueprint("landing", __name__)

# QR decorativo de 7x7 (tres esquinas de posición y un relleno fijo)
QR_PATRON = "".join(
    [
        "###.###",
        "#.#.#.#",
        "###.###",
        "..#.#..",
        "###.#.#",
        "#.#..##",
        "###.#.#",
    ]
)


def whatsapp(texto: str = "Hola, quiero una demo de RESTIFY para mi restaurante.") -> str:
    return f"https://wa.me/{current_app.config['WHATSAPP_NUMERO']}?text={quote(texto)}"


@bp.app_context_processor
def contexto():
    cfg = current_app.config
    return {
        "whatsapp": whatsapp,
        "email": cfg["EMAIL"],
        "instagram": cfg["INSTAGRAM"],
        "demo_url": cfg["DEMO_URL"],
        "tawk": (cfg["TAWK_PROPERTY_ID"], cfg["TAWK_WIDGET_ID"]) if cfg["TAWK_PROPERTY_ID"] and cfg["TAWK_WIDGET_ID"] else None,
        "sucursales_opciones": leads.SUCURSALES,
        "qr_patron": QR_PATRON,
        "anio": date.today().year,
        "banner_entorno": cfg["BANNER_ENTORNO"],
    }


def _proximamente() -> bool:
    return current_app.config["MODO"] == "proximamente"


@bp.get("/")
def inicio():
    if _proximamente():
        return render_template("proximamente.html")
    return render_template("index.html", enviado=request.args.get("enviado") == "1", errores={}, form={})


@bp.post("/contacto")
def contacto():
    """Formulario de demo. Con JS responde JSON; sin JS, redirige o vuelve a pintar con errores."""
    if _proximamente():
        abort(404)  # mientras la landing está bloqueada no se reciben solicitudes
    quiere_json = request.is_json or request.accept_mimetypes.best == "application/json"
    datos = request.get_json(silent=True) if request.is_json else request.form
    datos = datos or {}

    def responder(estado: int, **cuerpo):
        if quiere_json:
            return jsonify(cuerpo), estado
        if estado == 200:
            return redirect(url_for("landing.inicio", enviado=1, _anchor="contacto"))
        return render_template("index.html", enviado=False, errores=cuerpo.get("errores", {}), form=datos), estado

    token = request.headers.get("X-CSRF-Token") or datos.get("csrf")
    if not csrf_valido(token):
        return responder(400, ok=False, mensaje="La página expiró. Recárgala e intenta de nuevo.")

    # Campo trampa invisible: los bots lo llenan, las personas no. Se finge éxito.
    if datos.get("sitio_web"):
        return responder(200, ok=True)

    lead, errores = leads.validar(datos)
    if errores:
        return responder(422, ok=False, errores=errores)

    cfg = current_app.config
    ip = leads.hash_ip(ip_cliente(), cfg["SECRET_KEY"])
    if leads.demasiados(cfg["LEADS_DB"], ip, cfg["LEADS_MAX_POR_IP"], cfg["LEADS_VENTANA_MIN"]):
        return responder(429, ok=False, mensaje="Ya recibimos tu solicitud. Te escribimos muy pronto.")

    leads.guardar(cfg["LEADS_DB"], lead, ip)
    current_app.logger.info("Nueva solicitud de demo: %s (%s)", lead["restaurante"] or lead["nombre"], lead["telefono"])
    return responder(200, ok=True)


@bp.get("/salud")
def salud():
    return {"status": "ok"}


@bp.get("/robots.txt")
def robots():
    cfg = current_app.config
    # Ni la página de "Próximamente" ni los ambientes dev/pre deben aparecer en buscadores
    oculto = _proximamente() or bool(cfg["BANNER_ENTORNO"])
    return current_app.response_class(f"User-agent: *\n{'Disallow' if oculto else 'Allow'}: /\n", mimetype="text/plain")


@bp.app_errorhandler(404)
def no_encontrado(_e):
    return render_template("404.html"), 404
