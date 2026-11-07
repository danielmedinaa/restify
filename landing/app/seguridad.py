import secrets

from flask import Flask, request, session


def construir_csp(con_tawk: bool) -> str:
    """Todo desde el mismo origen, sin scripts en línea.

    Con el chat de Tawk.to activado se permiten SOLO sus dominios: su widget vive en iframes,
    usa WebSocket y pone estilos en línea, por eso style-src necesita 'unsafe-inline'.
    """
    tawk = "https://*.tawk.to https://tawk.link https://cdn.jsdelivr.net"
    directivas = {
        "default-src": ["'self'"],
        "img-src": ["'self'", "data:"] + ([tawk] if con_tawk else []),
        "font-src": ["'self'"] + (["https://*.tawk.to", "https://fonts.gstatic.com"] if con_tawk else []),
        "style-src": ["'self'"] + (["https://*.tawk.to", "https://fonts.googleapis.com", "'unsafe-inline'"] if con_tawk else []),
        "script-src": ["'self'"] + ([tawk] if con_tawk else []),
        "connect-src": ["'self'"] + (["https://*.tawk.to", "wss://*.tawk.to"] if con_tawk else []),
        "frame-src": ["https://*.tawk.to"] if con_tawk else ["'none'"],
        "media-src": ["'self'"] + (["https://*.tawk.to"] if con_tawk else []),
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
        "base-uri": ["'none'"],
        "object-src": ["'none'"],
    }
    return "; ".join(f"{d} {' '.join(v)}" for d, v in directivas.items())


CSP = construir_csp(False)


def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido(enviado: str | None) -> bool:
    esperado = session.get("csrf")
    return bool(esperado and enviado and secrets.compare_digest(esperado, enviado))


def ip_cliente() -> str:
    # Detrás de un proxy, ProxyFix (configurado en create_app) ya dejó la IP real aquí
    return request.remote_addr or "desconocida"


def registrar(app: Flask) -> None:
    csp = construir_csp(bool(app.config.get("TAWK_PROPERTY_ID") and app.config.get("TAWK_WIDGET_ID")))

    @app.after_request
    def cabeceras(resp):
        resp.headers.setdefault("Content-Security-Policy", csp)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        resp.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if app.config["ES_PRODUCCION"]:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if request.path.startswith("/static/"):
            resp.headers.setdefault("Cache-Control", "public, max-age=604800")
        return resp

    app.jinja_env.globals["csrf_token"] = token_csrf
