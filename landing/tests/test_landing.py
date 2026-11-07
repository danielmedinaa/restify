import re

import pytest

from app import create_app
from app.config import Config


@pytest.fixture
def client(tmp_path):
    class ConfigTest(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        LEADS_DB = tmp_path / "leads.sqlite3"
        LEADS_MAX_POR_IP = 2

    return create_app(ConfigTest).test_client()


def _csrf(client) -> str:
    html = client.get("/").get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def _lead(**extra):
    return {"nombre": "Daniel", "restaurante": "La Parrilla", "telefono": "+58 412 555 1234", "sucursales": "1", **extra}


def test_portada_y_cabeceras(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "RESTIFY" in html and "<em>en sincronía</em>" in html
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    # Sin estilos ni scripts en línea: la CSP estricta no los permitiría
    assert " style=" not in html and "<script>" not in html


def test_contacto_json_ok(client):
    token = _csrf(client)
    r = client.post("/contacto", json={**_lead(), "csrf": token}, headers={"X-CSRF-Token": token})
    assert r.status_code == 200 and r.get_json() == {"ok": True}


def test_contacto_sin_csrf(client):
    client.get("/")
    r = client.post("/contacto", json=_lead())
    assert r.status_code == 400


def test_contacto_valida_campos(client):
    token = _csrf(client)
    r = client.post("/contacto", json={"nombre": "D", "telefono": "abc", "csrf": token}, headers={"X-CSRF-Token": token})
    assert r.status_code == 422
    assert set(r.get_json()["errores"]) == {"nombre", "telefono"}


def test_contacto_sin_js_redirige(client):
    token = _csrf(client)
    r = client.post("/contacto", data={**_lead(), "csrf": token})
    assert r.status_code == 302 and "enviado=1" in r.headers["Location"]
    assert "Te escribimos hoy" in client.get("/?enviado=1").get_data(as_text=True)


def test_honeypot_y_limite(client):
    token = _csrf(client)
    h = {"X-CSRF-Token": token}
    # Un bot que llena el campo trampa recibe "ok" pero no se guarda nada
    assert client.post("/contacto", json={**_lead(), "sitio_web": "spam"}, headers=h).status_code == 200
    assert client.post("/contacto", json=_lead(), headers=h).status_code == 200
    assert client.post("/contacto", json=_lead(), headers=h).status_code == 200
    assert client.post("/contacto", json=_lead(), headers=h).status_code == 429


def test_404(client):
    r = client.get("/no-existe")
    assert r.status_code == 404 and "no existe" in r.get_data(as_text=True)


def test_produccion_exige_secret_key():
    class Prod(Config):
        SECRET_KEY = ""

    with pytest.raises(RuntimeError):
        create_app(Prod)


def test_chat_tawk_solo_si_esta_configurado(tmp_path):
    class ConTawk(Config):
        TESTING = True
        SECRET_KEY = "x"
        LEADS_DB = tmp_path / "l.sqlite3"
        TAWK_PROPERTY_ID = "abc123"
        TAWK_WIDGET_ID = "w1"

    r = create_app(ConTawk).test_client().get("/")
    html = r.get_data(as_text=True)
    assert 'data-propiedad="abc123"' in html and "js/tawk.js" in html
    assert "https://*.tawk.to" in r.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"].split("script-src")[1].split(";")[0]


def test_sin_tawk_la_csp_sigue_cerrada(client):
    r = client.get("/")
    assert "tawk" not in r.get_data(as_text=True) and "tawk" not in r.headers["Content-Security-Policy"]
