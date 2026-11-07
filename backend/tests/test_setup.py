"""Configuración inicial de una instancia nueva."""

import pytest

from app.core.config import settings
from app.services import config, licencia

API = "/api/v1"
PASSWORD = "ClaveSegura123"
CUERPO = {
    "admin": {"nombre": "Dueña", "email": "Duena@Resto.com", "password": PASSWORD},
    "sucursal": {"nombre": "Centro", "direccion": "Av. Principal", "rif": "J-12345678-9", "razon_social": "Resto C.A."},
    "moneda": {"codigo": "USD", "nombre": "Dólar", "simbolo": "$"},
    "zona_horaria": "America/Caracas",
}


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setattr(settings, "panel_url", "http://panel/api/v1/estado")
    monkeypatch.setattr(settings, "instancia_subdominio", "resto")
    validos = {"rst_bueno_1234567890": ("resto", True), "rst_ajeno_1234567890": ("otro", True), "rst_suspendido_12345": ("resto", False)}

    async def consultar(token_=None):
        token_ = token_ or licencia.token()
        if token_ not in validos:
            return licencia.Licencia(acceso=False, estado="cancelada")  # el panel responde 401
        sub, ok = validos[token_]
        return licencia.Licencia(acceso=ok, estado="activa" if ok else "suspendida", subdominio=sub, plan="Pro",
                                 limites={"max_sucursales": 3, "max_mesas": None})

    monkeypatch.setattr(licencia, "_consultar", consultar)
    licencia.reiniciar()
    yield
    licencia.reiniciar()


async def test_instancia_nueva_se_configura_y_se_cierra_el_asistente(client):
    r = await client.get(f"{API}/public/setup/estado")
    assert r.json() == {"pendiente": True, "requiere_token": False}

    r = await client.post(f"{API}/public/setup/completar", json=CUERPO)
    assert r.status_code == 201, r.text

    assert (await client.get(f"{API}/public/setup/estado")).json()["pendiente"] is False
    # Ya no se puede volver a ejecutar (ni para crear otro administrador)
    r = await client.post(f"{API}/public/setup/completar", json=CUERPO)
    assert r.status_code == 409

    # Quedó todo listo: entra con el administrador y ve su sucursal y moneda
    r = await client.post(f"{API}/auth/login", json={"email": "duena@resto.com", "password": PASSWORD})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert [s["nombre"] for s in (await client.get(f"{API}/sucursales", headers=h)).json()] == ["Centro"]
    assert [m["codigo"] for m in (await client.get(f"{API}/monedas", headers=h)).json()] == ["USD"]
    assert (await client.get(f"{API}/auth/me", headers=h)).json()["es_superadmin"] is True


async def test_datos_invalidos_no_dejan_nada_a_medias(client):
    for cambio in ({"admin": {**CUERPO["admin"], "password": "corta"}}, {"moneda": {**CUERPO["moneda"], "codigo": "usd"}},
                   {"zona_horaria": "Marte/Olimpo"}):
        r = await client.post(f"{API}/public/setup/completar", json={**CUERPO, **cambio})
        assert r.status_code == 422, r.text
    assert (await client.get(f"{API}/public/setup/estado")).json()["pendiente"] is True


async def test_con_panel_se_exige_un_token_valido_de_esta_instancia(client, panel):
    assert (await client.get(f"{API}/public/setup/estado")).json()["requiere_token"] is True

    r = await client.post(f"{API}/public/setup/token", json={"token": "rst_inventado_123456"})
    assert r.status_code == 422 and "incorrecto" in r.json()["detail"]
    r = await client.post(f"{API}/public/setup/token", json={"token": "rst_ajeno_1234567890"})
    assert r.status_code == 422 and "otra instancia" in r.json()["detail"]
    r = await client.post(f"{API}/public/setup/token", json={"token": "rst_suspendido_12345"})
    assert r.status_code == 402 and r.json()["detail"]["estado"] == "suspendida"
    r = await client.post(f"{API}/public/setup/token", json={"token": "rst_bueno_1234567890"})
    assert r.status_code == 200 and r.json()["plan"] == "Pro" and r.json()["limites"]["max_sucursales"] == 3

    # Sin token o con uno malo no se crea nada
    assert (await client.post(f"{API}/public/setup/completar", json=CUERPO)).status_code == 409
    assert (await client.post(f"{API}/public/setup/completar", json={**CUERPO, "token": "rst_ajeno_1234567890"})).status_code == 422
    assert (await client.get(f"{API}/public/setup/estado")).json()["pendiente"] is True

    r = await client.post(f"{API}/public/setup/completar", json={**CUERPO, "token": "rst_bueno_1234567890"})
    assert r.status_code == 201, r.text
    # El token quedó guardado (cifrado) y la instancia ya se rige por el panel
    await config.refrescar(forzar=True)
    assert licencia.token() == "rst_bueno_1234567890" and licencia.activa()


async def test_el_token_guardado_no_se_ve_ni_se_edita_desde_el_panel(client, panel):
    await client.post(f"{API}/public/setup/completar", json={**CUERPO, "token": "rst_bueno_1234567890"})
    login = (await client.post(f"{API}/auth/login", json={"email": "duena@resto.com", "password": PASSWORD})).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    opciones = (await client.get(f"{API}/configuracion", headers=h)).json()
    assert "panel_token" not in {o["clave"] for o in opciones}
    r = await client.put(f"{API}/configuracion", headers=h, json={"valores": {"panel_token": "rst_otro"}})
    assert r.status_code == 422
