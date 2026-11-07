import os

import click
from flask import Flask, render_template
from markupsafe import Markup
from werkzeug.middleware.proxy_fix import ProxyFix

from app import seguridad
from app.config import Config
from app.extensions import db, migrate
from app.modelos import ACCIONES, ESTADOS, LIMITES, MODULOS, Admin, Plan, Rol

ROLES_BASE = {
    "Superadmin": {"descripcion": "Acceso total. No se puede editar.", "sistema": True, "permisos": {}},
    "Soporte": {
        "descripcion": "Atiende clientes y cambia el estado de las suscripciones.",
        "permisos": {
            "clientes": ["crear", "leer", "editar"],
            "suscripciones": ["leer", "editar"],
            "instancias": ["leer"],
            "planes": ["leer"],
        },
    },
    "Solo lectura": {
        "descripcion": "Puede consultar, no cambia nada.",
        "permisos": {m: ["leer"] for m in ("clientes", "suscripciones", "instancias", "planes")},
    },
}
PLANES_BASE = [  # ejemplos: ajústalos desde el panel
    dict(nombre="Básico", descripcion="Un local, lo esencial.", precio_mensual=29, max_sucursales=1, max_salas=1, max_mesas=15, max_productos=100, max_usuarios=5),
    dict(nombre="Pro", descripcion="Varias sucursales.", precio_mensual=79, max_sucursales=3, max_salas=4, max_mesas=60, max_productos=500, max_usuarios=20),
    dict(nombre="Premium", descripcion="Sin límites prácticos.", precio_mensual=149, max_sucursales=None, max_salas=None, max_mesas=None, max_productos=None, max_usuarios=None),
]


def sembrar() -> None:
    """Crea los roles y planes de ejemplo si no existen (no pisa lo que ya editaste)."""
    for nombre, d in ROLES_BASE.items():
        if not db.session.query(Rol).filter_by(nombre=nombre).first():
            db.session.add(Rol(nombre=nombre, descripcion=d["descripcion"], permisos=d["permisos"], es_sistema=d.get("sistema", False)))
    if not db.session.query(Plan).count():
        db.session.add_all(Plan(**p) for p in PLANES_BASE)
    db.session.commit()


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    if not app.config["SECRET_KEY"] or not app.config["CLAVE_CIFRADO"]:
        raise RuntimeError("Define SECRET_KEY y CLAVE_CIFRADO para producción")
    if app.config["ES_PRODUCCION"] and app.config["SECRET_KEY"] == app.config["CLAVE_CIFRADO"]:
        raise RuntimeError("SECRET_KEY y CLAVE_CIFRADO deben ser distintas")

    saltos = int(os.environ.get("PROXY_SALTOS", "0"))
    if saltos:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos, x_host=saltos)

    db.init_app(app)
    migrate.init_app(app, db)
    seguridad.registrar(app)

    from app.rutas.admin import admin
    from app.rutas.api import api
    from app.rutas.auth import auth, cuenta
    from app.rutas.gestion import gestion

    for bp in (auth, cuenta, gestion, admin, api):
        app.register_blueprint(bp)

    app.jinja_env.globals.update(
        ESTADOS=ESTADOS, LIMITES=LIMITES, MODULOS=MODULOS, ACCIONES=ACCIONES,
        BANNER_ENTORNO=os.environ.get("BANNER_ENTORNO", ""),  # "DESARROLLO" / "PRE PRODUCCION"; vacío en producción
    )

    @app.template_filter("fecha")
    def fecha(v):
        return v.strftime("%d/%m/%Y") if v else "—"

    @app.template_filter("fechahora")
    def fechahora(v):
        return v.strftime("%d/%m/%Y %H:%M") if v else "—"

    @app.template_filter("limite")
    def limite(v):
        return "Ilimitado" if v is None else f"{v:,}".replace(",", ".")

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(400)
    @app.errorhandler(429)
    def error(e):
        return render_template("error.html", e=e), e.code

    @app.errorhandler(500)
    def error_500(_):
        db.session.rollback()
        return render_template("error.html", e=type("E", (), {"code": 500, "description": "Algo salió mal."})()), 500

    @app.cli.command("sembrar")
    def sembrar_cmd():
        """Crea los roles y planes de ejemplo si faltan (las tablas las crea `flask db upgrade`)."""
        sembrar()
        click.echo("Roles y planes listos.")

    @app.cli.command("crear-superadmin")
    @click.option("--email", prompt=True)
    @click.option("--nombre", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def crear_superadmin(email, nombre, password):
        """Crea el primer administrador. La contraseña se pide por consola (no queda en el historial)."""
        email = email.strip().lower()
        if (motivo := seguridad.validar_password(password, email)):
            raise click.ClickException(motivo)
        if db.session.query(Admin).filter_by(email=email).first():
            raise click.ClickException("Ya existe un administrador con ese correo.")
        sembrar()
        rol = db.session.query(Rol).filter_by(es_sistema=True).one()
        db.session.add(Admin(email=email, nombre=nombre.strip(), password_hash=seguridad.hashear(password), rol=rol))
        db.session.commit()
        click.echo("Listo. Al entrar por primera vez te pedirá configurar el 2FA.")

    return app
