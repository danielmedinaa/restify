import os
import secrets
from pathlib import Path


class Config:
    ENV = os.environ.get("LANDING_ENV", "development")
    ES_PRODUCCION = ENV == "production"

    # Firma la cookie de sesión (token CSRF). En producción es obligatoria.
    SECRET_KEY = os.environ.get("SECRET_KEY") or ("" if ES_PRODUCCION else secrets.token_urlsafe(32))

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = ES_PRODUCCION
    MAX_CONTENT_LENGTH = 32 * 1024  # el formulario de contacto no necesita más

    LEADS_DB = Path(os.environ.get("LEADS_DB", Path(__file__).resolve().parent.parent / "data" / "leads.sqlite3"))

    # Contacto que se muestra en la página
    WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "584120000000")  # solo dígitos, con código de país
    EMAIL = os.environ.get("CONTACTO_EMAIL", "hola@restify.app")
    INSTAGRAM = os.environ.get("INSTAGRAM", "restify.app")
    DEMO_URL = os.environ.get("DEMO_URL", "")  # link a la app de demostración, si existe

    # "proximamente" = en vez de la landing se muestra una página de "Próximamente" y se bloquea el formulario.
    # Cualquier otro valor = landing abierta. (Acepta "próximamente" con tilde.)
    MODO = "proximamente" if os.environ.get("LANDING_MODO", "").strip().lower().replace("ó", "o") == "proximamente" else "abierta"

    # Banner fijo de ambiente: "DESARROLLO" o "PRE PRODUCCION". Vacío (producción) = sin banner.
    BANNER_ENTORNO = os.environ.get("BANNER_ENTORNO", "")

    # Chat de Tawk.to (asistente). Vacío = no se carga. Están en el código de instalación:
    # https://embed.tawk.to/<TAWK_PROPERTY_ID>/<TAWK_WIDGET_ID>
    TAWK_PROPERTY_ID = os.environ.get("TAWK_PROPERTY_ID", "")
    TAWK_WIDGET_ID = os.environ.get("TAWK_WIDGET_ID", "")

    # Límite de envíos del formulario por IP
    LEADS_MAX_POR_IP = int(os.environ.get("LEADS_MAX_POR_IP", "3"))
    LEADS_VENTANA_MIN = int(os.environ.get("LEADS_VENTANA_MIN", "30"))
