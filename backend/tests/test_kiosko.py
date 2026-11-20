"""Caja automática: el cliente arma su pedido en la pantalla del local y lo paga en caja."""

from app.services import licencia
from tests.test_licencia import panel  # noqa: F401  (fixture que simula al panel)

API = "/api/v1"


def _pedido(d, nombre="Ana"):
    return {"nombre_cliente": nombre, "items": [{"producto_id": d["refresco"]["id"], "cantidad": 2}]}


async def test_autopedido_con_turno_que_sube_y_llega_a_caja(admin, datos):
    suc = datos["sucursal"]["id"]
    pantalla = (await admin.get(f"{API}/public/sucursales/{suc}/kiosko")).json()
    assert pantalla["disponible"] is True and pantalla["menu"]["categorias"]

    r1 = await admin.post(f"{API}/public/sucursales/{suc}/kiosko/pedidos", json=_pedido(datos))
    r2 = await admin.post(f"{API}/public/sucursales/{suc}/kiosko/pedidos", json=_pedido(datos, "Luis"))
    assert r1.status_code == 201, r1.text
    assert (r1.json()["pedido"]["turno"], r2.json()["pedido"]["turno"]) == (1, 2)
    assert r1.json()["pedido"]["mesa"] is None

    # Caja lo ve como autopedido, con su turno y los platos por aprobar
    lista = (await admin.get(f"{API}/comandas", params={"estado": "abierta"})).json()
    items = lista["items"] if isinstance(lista, dict) else lista
    kioskos = [c for c in items if c["origen"] == "kiosko"]
    assert sorted(c["turno"] for c in kioskos) == [1, 2]
    assert all(c["items_pendientes"] == 2 for c in kioskos)


async def test_datos_y_plan(admin, datos, panel):  # noqa: F811
    suc = datos["sucursal"]["id"]
    # El nombre es obligatorio; el teléfono no
    sin_nombre = {"items": [{"producto_id": datos["refresco"]["id"], "cantidad": 1}]}
    assert (await admin.post(f"{API}/public/sucursales/{suc}/kiosko/pedidos", json=sin_nombre)).status_code == 422
    # Sin la función en el plan: la pantalla avisa y el pedido se rechaza
    licencia.reiniciar()
    assert (await admin.get(f"{API}/public/sucursales/{suc}/kiosko")).json()["disponible"] is False
    r = await admin.post(f"{API}/public/sucursales/{suc}/kiosko/pedidos", json=_pedido(datos))
    assert r.status_code == 402 and r.json()["detail"]["codigo"] == "caracteristica_plan"
    panel["caracteristicas"]["kiosko"] = True
    licencia.reiniciar()
    assert (await admin.post(f"{API}/public/sucursales/{suc}/kiosko/pedidos", json=_pedido(datos))).status_code == 201
