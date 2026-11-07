import os
import secrets
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


class Config:
    ENV = os.environ.get("PANEL_ENV", "development")
    ES_PRODUCCION = ENV == "production"
    ES_TEST = ENV == "test"

    SECRET_KEY = os.environ.get("SECRET_KEY") or ("" if ES_PRODUCCION else secrets.token_urlsafe(32))
    CLAVE_CIFRADO = os.environ.get("CLAVE_CIFRADO") or ("" if ES_PRODUCCION else secrets.token_urlsafe(32))

    # Postgres: postgresql+psycopg://usuario:clave@host:5432/base
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "postgresql+psycopg://panel:panel@localhost:5433/panel")

    SESSION_COOKIE_NAME = "__Host-panel" if ES_PRODUCCION else "panel"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    SESSION_COOKIE_SECURE = ES_PRODUCCION
    MAX_CONTENT_LENGTH = 64 * 1024

    SESION_INACTIVIDAD_MIN = int(os.environ.get("SESION_INACTIVIDAD_MIN", "20"))
    SESION_MAXIMA_HORAS = int(os.environ.get("SESION_MAXIMA_HORAS", "8"))

    # Instancias: <subdominio>.<DOMINIO_BASE>
    DOMINIO_BASE = os.environ.get("DOMINIO_BASE", "restify.localhost").lower()
    INSTANCIA_ESQUEMA = os.environ.get("INSTANCIA_ESQUEMA", "http")
    INSTANCIA_PUERTO = os.environ.get("INSTANCIA_PUERTO", "")

    # URL con la que las instancias consultan su estado (en el VPS: https://panel.restify.com.ve)
    PANEL_URL = os.environ.get("PANEL_URL", "http://localhost:8030")

    # URL con la que las instancias llegan al panel DESDE SU RED (en local: contenedor "panel" en restify-net)
    PANEL_URL_INTERNA = os.environ.get("PANEL_URL_INTERNA", "http://panel:8000")
    ZONA_HORARIA_INSTANCIAS = os.environ.get("ZONA_HORARIA_INSTANCIAS", "America/Caracas")

    # Agente de instancias (corre en el servidor, fuera del panel). Ver infra/README.md
    AGENTE_SOCKET = os.environ.get("AGENTE_SOCKET", "/run/agente/agente.sock")
    AGENTE_SECRETO = os.environ.get("AGENTE_SECRETO", "")

    APROVISIONADOR = os.environ.get("APROVISIONADOR", "simulado")
    DIR_INSTANCIAS = Path(os.environ.get("DIR_INSTANCIAS", RAIZ / "data" / "instancias"))

    # Pruebas: argon2 más barato para que la suite no tarde
    ARGON_RAPIDO = ES_TEST


class ConfigTest(Config):
    ENV = "test"
    ES_PRODUCCION = False
    ES_TEST = True
    TESTING = True
    # Por defecto SQLite en memoria; TEST_DATABASE_URL corre la suite contra Postgres
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite://")
    ARGON_RAPIDO = True
    APROVISIONADOR = "simulado"
    SESSION_COOKIE_NAME = "panel"
    SESSION_COOKIE_SECURE = False
    DIR_INSTANCIAS = Path("/tmp/restify-panel-test-instancias")
