import asyncio
import json

from app.core.realtime import canal_pedido, canal_sucursal
from app.core.redis import redis_client

API = "/api/v1"
CLIENTE = {"nombre_cliente": "Ana Pérez", "telefono_cliente": "0412-555-1234"}


async def _pedido(c, d) -> tuple[str, int]:
    r = await c.post(f"{API}/public/mesas/{d['qr']}/comandas", json={**CLIENTE, "items": [{"producto_id": d["refresco"]["id"]}]})
    assert r.status_code == 201, r.text
    return r.json()["tracking_token"], (await c.get(f"{API}/comandas")).json()["items"][0]["id"]


async def test_conversacion_entre_la_mesa_y_caja(admin, datos):
    c, d = admin, datos
    tracking, comanda_id = await _pedido(c, d)

    # El cliente escribe; caja lo ve
    r = await c.post(f"{API}/public/pedidos/{tracking}/mensajes", json={"texto": "¿Pueden traer la cuenta?"})
    assert r.status_code == 201, r.text
    assert r.json()["autor"] == "cliente" and r.json()["autor_nombre"] == "Ana Pérez"
    vistos = (await c.get(f"{API}/comandas/{comanda_id}/mensajes")).json()
    assert [(m["autor"], m["texto"]) for m in vistos] == [("cliente", "¿Pueden traer la cuenta?")]

    # Caja responde; el cliente lo ve en su link
    r = await c.post(f"{API}/comandas/{comanda_id}/mensajes", json={"texto": "Enseguida"})
    assert r.status_code == 201 and r.json()["autor"] == "personal" and r.json()["autor_nombre"] == "admin"
    hilo = (await c.get(f"{API}/public/pedidos/{tracking}/mensajes")).json()
    assert [m["texto"] for m in hilo] == ["¿Pueden traer la cuenta?", "Enseguida"]


async def test_validaciones_del_chat(admin, datos):
    c, d = admin, datos
    tracking, comanda_id = await _pedido(c, d)
    assert (await c.post(f"{API}/public/pedidos/{tracking}/mensajes", json={"texto": ""})).status_code == 422
    assert (await c.post(f"{API}/public/pedidos/{tracking}/mensajes", json={"texto": "x" * 501})).status_code == 422
    assert (await c.post(f"{API}/public/pedidos/{'a' * 20}/mensajes", json={"texto": "hola"})).status_code == 404
    assert (await c.get(f"{API}/comandas/9999/mensajes")).status_code == 404


async def test_no_se_escribe_en_una_comanda_cerrada(admin, datos):
    c, d = admin, datos
    tracking, comanda_id = await _pedido(c, d)
    await c.post(f"{API}/comandas/{comanda_id}/cancelar", json={"motivo": "Prueba"})
    assert (await c.post(f"{API}/public/pedidos/{tracking}/mensajes", json={"texto": "hola"})).status_code == 409
    assert (await c.post(f"{API}/comandas/{comanda_id}/mensajes", json={"texto": "hola"})).status_code == 409


async def test_el_mensaje_se_publica_a_caja_y_al_cliente(admin, datos):
    c, d = admin, datos
    tracking, comanda_id = await _pedido(c, d)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(canal_sucursal(d["sucursal"]["id"]), canal_pedido(tracking))
    await pubsub.get_message(timeout=1)
    await pubsub.get_message(timeout=1)

    await c.post(f"{API}/public/pedidos/{tracking}/mensajes", json={"texto": "Una servilleta, porfa"})
    recibidos = []
    for _ in range(2):
        m = await pubsub.get_message(ignore_subscribe_messages=True, timeout=2)
        if m:
            recibidos.append(json.loads(m["data"]))
    await pubsub.aclose()
    assert {r["tipo"] for r in recibidos} == {"chat.mensaje"}
    al_panel = next(r["data"] for r in recibidos if "comanda_id" in r["data"])
    assert al_panel["comanda_id"] == comanda_id and al_panel["mesa"] == "Mesa 1" and al_panel["autor"] == "cliente"
