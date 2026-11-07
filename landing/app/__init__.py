import os
import re

import click
from flask import Flask
from markupsafe import Markup, escape
from werkzeug.middleware.proxy_fix import ProxyFix

from app import contenido, leads, seguridad
from app.config import Config

_RESALTE = re.compile(r"\*(.+?)\*")


def resaltar(texto: str) -> Markup:
    """'Tu restaurante, *en sincronía*.' -> el fragmento entre asteriscos va en <em> (lo demás se escapa)."""
    return Markup(_RESALTE.sub(lambda m: f"<em>{m.group(1)}</em>", str(escape(texto))))


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Define SECRET_KEY para producción")

    # Detrás de nginx/Caddy: confía en X-Forwarded-For solo si se indica cuántos proxies hay
    saltos = int(os.environ.get("PROXY_SALTOS", "0"))
    if saltos:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=saltos, x_proto=saltos, x_host=saltos)

    seguridad.registrar(app)
    app.jinja_env.filters["resaltar"] = resaltar
    app.jinja_env.globals["c"] = contenido

    from app.routes import bp

    app.register_blueprint(bp)

    @app.cli.command("leads")
    @click.option("--salida", type=click.Path(dir_okay=False), help="Archivo CSV de salida (por defecto, la consola)")
    def exportar_leads(salida):
        """Exporta las solicitudes de demo en CSV."""
        datos = leads.exportar_csv(app.config["LEADS_DB"])
        if salida:
            with open(salida, "w", encoding="utf-8", newline="") as f:
                f.write(datos)
            click.echo(f"Leads exportados a {salida}")
        else:
            click.echo(datos)

    return app
