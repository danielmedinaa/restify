from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Configuracion
from tests.conftest import PASSWORD, login

API = "/api/v1"


async def _opciones(c) -> dict:
    return {o["clave"]: o for o in (await c.get(f"{API}/configuracion")).json()}


async def test_configuracion_reemplaza_el_entorno(admin, datos):
    c, d = admin, datos
    op = await _opciones(c)
    assert op["igtf_porcentaje"]["origen"] == "entorno" and op["igtf_porcentaje"]["valor"] == "3"

    r = await c.put(f"{API}/configuracion", json={"valores": {"igtf_porcentaje": "5", "qr_vencimiento_min": "30"}})
    assert r.status_code == 200, r.text
    op = {o["clave"]: o for o in r.json()}
    assert (op["igtf_porcentaje"]["valor"], op["igtf_porcentaje"]["origen"]) == ("5", "panel")

    # El nuevo IGTF se usa al cobrar en divisas
    await c.patch(f"{API}/sucursales/{d['sucursal']['id']}", json={"cobra_igtf": True})
    await c.patch(f"{API}/monedas/{d['usd']['id']}", json={"es_divisa": True})
    comanda = (await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["refresco"]["id"]}]})).json()
    assert comanda["igtf_porcentaje"] == "5"

    # null = volver al .env
    r = await c.put(f"{API}/configuracion", json={"valores": {"igtf_porcentaje": None}})
    assert {o["clave"]: o for o in r.json()}["igtf_porcentaje"]["origen"] == "entorno"


async def test_validaciones(admin):
    for valores in ({"igtf_porcentaje": "150"}, {"timezone": "Marte/Olympus"}, {"public_menu_base_url": "no-es-url"}, {"login_max_attempts": "2.5"}, {"inventada": "1"}):
        r = await admin.put(f"{API}/configuracion", json={"valores": valores})
        assert r.status_code == 422, valores


async def test_secretos_cifrados_y_nunca_devueltos(admin):
    r = await admin.put(f"{API}/configuracion", json={"valores": {"cedula_api_app_id": "app-123", "cedula_api_token": "token-super-secreto"}})
    token = {o["clave"]: o for o in r.json()}["cedula_api_token"]
    assert token["configurado"] is True and token["valor"] is None
    async with SessionLocal() as s:
        guardado = (await s.scalar(select(Configuracion.valor).where(Configuracion.clave == "cedula_api_token")))
    assert "token-super-secreto" not in guardado
    texto = " ".join(e["descripcion"] for e in (await admin.get(f"{API}/bitacora")).json()["items"])
    assert "Consulta de cédulas · Token" in texto and "token-super-secreto" not in texto

    # Vacío = quitarlo
    r = await admin.put(f"{API}/configuracion", json={"valores": {"cedula_api_token": ""}})
    assert {o["clave"]: o for o in r.json()}["cedula_api_token"]["configurado"] is False


async def test_solo_superadmin(admin, datos):
    rol = (await admin.post(f"{API}/roles", json={"nombre": "Gerente", "permisos": [{"modulo": "ventas", "leer": True}]})).json()
    await admin.post(f"{API}/usuarios", json={"email": "g@restify.com", "nombre": "G", "password": PASSWORD, "rol_id": rol["id"]})
    t = await login(admin, "g@restify.com")
    r = await admin.get(f"{API}/configuracion", headers={"Authorization": f"Bearer {t['access_token']}"})
    assert r.status_code == 403
