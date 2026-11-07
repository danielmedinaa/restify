"""Suscripción y límites del plan, consultados al panel de RESTIFY (el panel se simula)."""

import pytest

from app.core.config import settings
from app.services import licencia

API = "/api/v1"


@pytest.fixture
def panel(monkeypatch):
    """Activa el control y deja que cada test decida qué responde el panel."""
    monkeypatch.setattr(settings, "panel_url", "http://panel/api/v1/estado")
    monkeypatch.setattr(settings, "panel_token", "rst_test")
    estado = {"estado": "activa", "acceso": True, "motivo": None, "plan": "Básico", "vence_en": None,
              "limites": {"max_sucursales": None, "max_salas": None, "max_mesas": None, "max_productos": None, "max_usuarios": None}}

    async def consultar():
        return licencia.Licencia(**{k: estado[k] for k in ("acceso", "estado", "motivo", "plan", "vence_en", "limites")})

    monkeypatch.setattr(licencia, "_consultar", consultar)
    licencia.reiniciar()
    yield estado
    licencia.reiniciar()


async def test_sin_panel_configurado_no_hay_restricciones(admin, datos):
    assert not licencia.activa()
    assert (await admin.get(f"{API}/sucursales")).status_code == 200


async def test_cuenta_suspendida_bloquea_todo_con_mensaje(admin, client, panel):
    panel["acceso"], panel["estado"], panel["motivo"] = False, "suspendida", "Pago pendiente"
    licencia.reiniciar()
    for r in (await admin.get(f"{API}/sucursales"), await client.post(f"{API}/auth/login", json={"email": "a@b.com", "password": "x"})):
        assert r.status_code == 402
        d = r.json()["detail"]
        assert d["codigo"] == "suscripcion_inactiva" and d["estado"] == "suspendida" and "suspendida" in d["mensaje"]
    # El health check no se bloquea (el orquestador necesita saber que el contenedor vive)
    assert (await client.get("/health")).status_code == 200
    # Al reactivarse el panel, vuelve en cuanto vence la caché
    panel["acceso"], panel["estado"] = True, "activa"
    licencia.reiniciar()
    assert (await admin.get(f"{API}/sucursales")).status_code == 200


async def test_limite_de_sucursales_y_mesas(admin, datos, panel):
    # `datos` ya creó 1 sucursal y 2 mesas con el control apagado
    panel["limites"].update(max_sucursales=1, max_mesas=2)
    licencia.reiniciar()
    r = await admin.post(f"{API}/sucursales", json={"nombre": "Norte"})
    assert r.status_code == 402
    d = r.json()["detail"]
    assert d["codigo"] == "limite_plan" and d["maximo"] == 1 and "1 sucursales" in d["mensaje"]
    r = await admin.post(f"{API}/mesas", json={"sucursal_id": datos["sucursal"]["id"], "nombre": "Mesa 3"})
    assert r.status_code == 402 and r.json()["detail"]["limite"] == "max_mesas"
    # Subir el plan en el panel lo libera sin reiniciar nada
    panel["limites"].update(max_sucursales=2, max_mesas=None)
    licencia.reiniciar()
    assert (await admin.post(f"{API}/sucursales", json={"nombre": "Norte"})).status_code == 201
    assert (await admin.post(f"{API}/mesas", json={"sucursal_id": datos["sucursal"]["id"], "nombre": "Mesa 3"})).status_code == 201


async def test_limite_de_productos_usuarios_y_salas(admin, datos, panel):
    panel["limites"].update(max_productos=2, max_usuarios=1, max_salas=0)
    licencia.reiniciar()
    r = await admin.post(f"{API}/productos", json={"nombre": "Postre", "precio_base": "3"})
    assert r.status_code == 402 and r.json()["detail"]["limite"] == "max_productos"
    r = await admin.post(f"{API}/usuarios", json={"email": "n@x.com", "nombre": "Nuevo", "password": "ClaveSegura123", "rol_id": 1})
    assert r.status_code == 402 and r.json()["detail"]["limite"] == "max_usuarios"
    r = await admin.post(f"{API}/zonas", json={"sucursal_id": datos["sucursal"]["id"], "nombre": "Terraza"})
    assert r.status_code == 402 and r.json()["detail"]["limite"] == "max_salas"


async def test_si_el_panel_cae_se_usa_el_ultimo_estado(admin, datos, panel, monkeypatch):
    panel["limites"].update(max_sucursales=1)
    licencia.reiniciar()
    assert (await admin.post(f"{API}/sucursales", json={"nombre": "Norte"})).status_code == 402

    async def caido():
        return None

    monkeypatch.setattr(licencia, "_consultar", caido)
    licencia._expira = 0  # fuerza la reconsulta: falla y conserva el límite anterior
    assert (await admin.post(f"{API}/sucursales", json={"nombre": "Norte"})).status_code == 402


async def test_si_el_panel_nunca_respondio_no_se_bloquea(admin, datos, panel, monkeypatch):
    async def caido():
        return None

    monkeypatch.setattr(licencia, "_consultar", caido)
    licencia.reiniciar()
    assert (await admin.get(f"{API}/sucursales")).status_code == 200
