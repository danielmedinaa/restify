"""Puntos de cobro (POS): manual o por API genérica, con llaves cifradas y protección SSRF."""

import functools
import json

import httpx
import pytest

from app.core.errors import Invalido
from app.services import pos as srv

API = "/api/v1"

CONFIG = {
    "base_url": "https://api.proveedor.test/v1",
    "cabeceras": {"Authorization": "Bearer {{secreto.api_key}}"},
    "crear": {
        "metodo": "POST",
        "ruta": "/cobros",
        "cuerpo": {"monto": "{{monto}}", "ref": "{{referencia}}", "nota": "Pedido {{referencia}} de {{nombre}}"},
        "id_path": "data.id",
        "url_path": "data.links.0.url",
    },
    "consultar": {"metodo": "GET", "ruta": "/cobros/{{id}}", "estado_path": "data.status", "pagado": ["PAID", "CONCILIATED"]},
}


def test_plantillas_conservan_tipos_y_rechazan_variables_desconocidas():
    ctx = {"monto": 14.5, "referencia": "A1", "secreto": {"k": "xyz"}}
    assert srv.render({"m": "{{monto}}", "t": "ref {{referencia}}", "h": ["Bearer {{secreto.k}}"]}, ctx) == {"m": 14.5, "t": "ref A1", "h": ["Bearer xyz"]}
    with pytest.raises(Invalido):
        srv.render("{{no_existe}}", ctx)
    assert srv.extraer({"a": {"b": [{"c": 7}]}}, "a.b.0.c") == 7 and srv.extraer({"a": 1}, "a.b") is None


@pytest.mark.parametrize("url", ["http://api.test/x", "https://127.0.0.1/x", "https://localhost/x", "https://10.0.0.5/x", "https://169.254.169.254/latest", "https://[::1]/x", "https://u:p@api.test/x"])
async def test_no_permite_urls_inseguras(url):
    with pytest.raises(Invalido):
        await srv.verificar_url(url)


@pytest.fixture
def proveedor(monkeypatch):
    """Simula al proveedor: sin red ni DNS. Guarda lo último que recibió."""
    visto = {}

    def responder(req: httpx.Request) -> httpx.Response:
        visto["req"] = req
        if req.method == "POST":
            return httpx.Response(201, json={"data": {"id": "c-1", "links": [{"url": "https://pago.proveedor.test/c-1"}]}})
        return httpx.Response(200, json={"data": {"status": "PAID"}})

    async def sin_dns(url):
        return None

    monkeypatch.setattr(srv, "verificar_url", sin_dns)
    monkeypatch.setattr(srv.httpx, "AsyncClient", functools.partial(httpx.AsyncClient, transport=httpx.MockTransport(responder)))
    return visto


async def test_crud_cifra_secretos_y_no_los_devuelve(admin, proveedor):
    r = await admin.post(f"{API}/pos", json={"nombre": "Cobrix", "tipo": "api", "config": CONFIG, "secretos": {"api_key": "cbx_live_SECRETO"}})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["secretos_configurados"] == ["api_key"] and "SECRETO" not in json.dumps(d)
    assert "SECRETO" not in json.dumps((await admin.get(f"{API}/pos")).json())

    # Editar sin mandar secretos los conserva; null los borra
    r = await admin.put(f"{API}/pos/{d['id']}", json={"nombre": "Cobrix 2", "tipo": "api", "config": CONFIG})
    assert r.json()["secretos_configurados"] == ["api_key"]
    r = await admin.put(f"{API}/pos/{d['id']}", json={"nombre": "Cobrix 2", "tipo": "api", "config": CONFIG, "secretos": {"api_key": None}})
    assert r.json()["secretos_configurados"] == []


async def test_cobro_de_prueba_y_consulta(admin, proveedor):
    d = (await admin.post(f"{API}/pos", json={"nombre": "Proveedor", "tipo": "api", "config": CONFIG, "secretos": {"api_key": "k123"}})).json()
    r = await admin.post(f"{API}/pos/{d['id']}/cobro-prueba", json={"monto": "20.50"})
    assert r.status_code == 200, r.text
    assert r.json()["id_externo"] == "c-1" and r.json()["url_pago"] == "https://pago.proveedor.test/c-1"
    enviado = proveedor["req"]
    assert enviado.headers["authorization"] == "Bearer k123"  # la llave se usó, descifrada
    assert json.loads(enviado.content) == {"monto": 20.5, "ref": f"prueba-{d['id']}", "nota": f"Pedido prueba-{d['id']} de Prueba RESTIFY"}

    r = await admin.get(f"{API}/pos/{d['id']}/cobro/c-1")
    assert r.json() == {"estado_proveedor": "PAID", "pagado": True, "respuesta": {"data": {"status": "PAID"}}}


async def test_validaciones(admin):
    # La URL del proveedor debe ser pública y https (sin DNS simulado, localhost se rechaza)
    malo = {**CONFIG, "base_url": "https://localhost/api"}
    assert (await admin.post(f"{API}/pos", json={"nombre": "X", "tipo": "api", "config": malo})).status_code == 422
    assert (await admin.post(f"{API}/pos", json={"nombre": "X", "tipo": "api"})).status_code == 422
    assert (await admin.post(f"{API}/pos", json={"nombre": "X", "tipo": "api", "config": {**CONFIG, "base_url": "http://a.test"}})).status_code == 422
    # Manual no necesita configuración
    assert (await admin.post(f"{API}/pos", json={"nombre": "Datáfono del banco", "tipo": "manual"})).status_code == 201
