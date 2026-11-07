import asyncio
import json
from datetime import date
from decimal import Decimal

from app.core.realtime import canal_pedido, canal_sucursal
from app.core.redis import redis_client

API = "/api/v1"
CLIENTE = {"nombre_cliente": "Ana Pérez", "telefono_cliente": "+58 414 123 4567"}


async def inventario(c, inv_id) -> dict:
    r = await c.get(f"{API}/inventario", params={"limite": 100})
    return next(i for i in r.json()["items"] if i["id"] == inv_id)


async def productos_menu(c, sucursal_id) -> dict:
    r = await c.get(f"{API}/public/sucursales/{sucursal_id}/menu")
    assert r.status_code == 200, r.text
    return {p["nombre"]: p for cat in r.json()["categorias"] for p in cat["productos"]}


async def test_flujo_completo_qr_cocina_stock_pago_venta(admin, datos):
    """El ejemplo de Daniel: hamburguesa de 150 g con 200 g en stock -> quedan 50 g y salta la alerta."""
    c, d = admin, datos

    # 1. Cliente escanea el QR: ve el menú con precios en USD y VES
    r = await c.get(f"{API}/public/mesas/{d['qr']}")
    assert r.status_code == 200
    menu = {p["nombre"]: p for cat in r.json()["menu"]["categorias"] for p in cat["productos"]}
    assert menu["Hamburguesa"]["porciones_disponibles"] == 1
    assert {m["moneda"]: m["monto"] for m in menu["Hamburguesa"]["precios"]} == {"USD": "10.00", "VES": "365.00"}
    assert r.json()["ocupada"] is False

    # 2. Pide una hamburguesa y un refresco
    r = await c.post(
        f"{API}/public/mesas/{d['qr']}/comandas",
        json={
            "nombre_cliente": "Daniel",
            "telefono_cliente": "0412-555-1234",
            "items": [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"]}],
        },
    )
    assert r.status_code == 201, r.text
    tracking = r.json()["tracking_token"]
    assert r.json()["seguimiento_url"].endswith(tracking)
    assert [i["estado"] for i in r.json()["pedido"]["items"]] == ["pendiente", "pendiente"]

    # 3. QR bloqueado: nadie más puede abrir comanda en esa mesa
    r = await c.post(f"{API}/public/mesas/{d['qr']}/comandas", json={**CLIENTE, "items": [{"producto_id": d["refresco"]["id"]}]})
    assert r.status_code == 423
    assert (await c.get(f"{API}/public/mesas/{d['qr']}")).json()["ocupada"] is True

    # 4. Caja ve la comanda y la envía a cocina -> se reserva el stock
    comandas = (await c.get(f"{API}/comandas")).json()["items"]
    assert len(comandas) == 1 and comandas[0]["items_pendientes"] == 2
    comanda_id = comandas[0]["id"]
    r = await c.post(f"{API}/comandas/{comanda_id}/enviar-cocina")
    assert r.status_code == 200, r.text
    inv = await inventario(c, d["inv_carne"]["id"])
    assert (Decimal(inv["cantidad"]), Decimal(inv["reservado"]), Decimal(inv["disponible"])) == (200, 150, 50)

    # El menú ya no ofrece hamburguesas: solo quedan 50 g disponibles
    assert "Hamburguesa" not in await productos_menu(c, d["sucursal"]["id"])

    # 5. Cocina ve los platos y marca la hamburguesa como lista -> se descuentan los 150 g
    tablero = (await c.get(f"{API}/cocina", params={"sucursal_id": d["sucursal"]["id"]})).json()
    items = {i["nombre"]: i for i in tablero[0]["items"]}
    assert set(items) == {"Hamburguesa #1", "Refresco #1"}

    canal = redis_client.pubsub()
    await canal.subscribe(canal_sucursal(d["sucursal"]["id"]), canal_pedido(tracking))
    await canal.get_message(timeout=1)
    await canal.get_message(timeout=1)

    r = await c.post(f"{API}/cocina/items/{items['Hamburguesa #1']['id']}/estado", json={"estado": "listo"})
    assert r.status_code == 200, r.text
    inv = await inventario(c, d["inv_carne"]["id"])
    assert (Decimal(inv["cantidad"]), Decimal(inv["reservado"]), inv["bajo_minimo"]) == (50, 0, True)

    # 6. Alerta de stock mínimo (persistida y en tiempo real)
    alertas = (await c.get(f"{API}/alertas")).json()["items"]
    assert len(alertas) == 1
    assert alertas[0]["mensaje"] == "Stock bajo de Carne molida: quedan 50 g (mínimo 60 g)"

    eventos = []
    for _ in range(10):
        m = await canal.get_message(ignore_subscribe_messages=True, timeout=1)
        if m:
            eventos.append(json.loads(m["data"]))
    tipos = [e["tipo"] for e in eventos]
    assert "stock.alerta" in tipos
    assert "cocina.item_actualizado" in tipos
    assert "pedido.actualizado" in tipos
    # El dinero y las cantidades viajan como string, igual que en REST (nunca como float)
    por_tipo = {e["tipo"]: e["data"] for e in eventos}
    assert isinstance(por_tipo["cocina.item_actualizado"]["total"], str)
    assert por_tipo["stock.alerta"]["cantidad"] == "50.000"
    assert isinstance(por_tipo["pedido.actualizado"]["total"], str)
    await canal.aclose()

    # 7. El cliente ve qué plato está listo y cuál falta
    pedido = (await c.get(f"{API}/public/pedidos/{tracking}")).json()
    estados = {i["nombre"]: i["estado"] for i in pedido["items"]}
    assert estados == {"Hamburguesa #1": "listo", "Refresco #1": "en_cocina"}

    # 8. No se puede cerrar con platos en cocina
    await c.post(f"{API}/cocina/items/{items['Refresco #1']['id']}/estado", json={"estado": "preparando"})
    r = await c.post(f"{API}/comandas/{comanda_id}/cerrar")
    assert r.status_code == 409
    await c.post(f"{API}/cocina/items/{items['Refresco #1']['id']}/estado", json={"estado": "listo"})

    # 9. Pago mixto: 5 USD + 255.50 VES (= 7 USD) -> total 12 USD
    r = await c.post(f"{API}/comandas/{comanda_id}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "5", "metodo": "efectivo"})
    assert r.status_code == 201, r.text
    r = await c.post(
        f"{API}/comandas/{comanda_id}/cerrar",
    )
    assert r.status_code == 409  # pago incompleto
    r = await c.post(
        f"{API}/comandas/{comanda_id}/pagos",
        json={"moneda_id": d["ves"]["id"], "monto": "255.50", "metodo": "pago_movil", "referencia": "123456"},
    )
    assert r.status_code == 201, r.text
    tot = r.json()["totales"]
    assert (tot["total"], tot["pagado"], tot["pendiente"]) == ("12.00", "12.00", "0.00")

    # 10. Cierre: genera la venta y libera la mesa
    r = await c.post(f"{API}/comandas/{comanda_id}/cerrar")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "cerrada"
    assert all(i["estado"] == "entregado" for i in r.json()["items"])
    assert (await c.get(f"{API}/public/mesas/{d['qr']}")).json()["ocupada"] is False

    # 11. Ventas con filtros y detalle de platos
    hoy = (await c.get(f"{API}/ventas", params={"dia": date.today().isoformat()})).json()
    ventas = (await c.get(f"{API}/ventas", params={"anio": date.today().year, "monto_min": "10"})).json()
    assert ventas["total"] == 1
    assert (await c.get(f"{API}/ventas", params={"monto_min": "13"})).json()["total"] == 0
    venta = (await c.get(f"{API}/ventas/{ventas['items'][0]['id']}")).json()
    assert venta["total"] == "12.00" and venta["mesa"] == "Mesa 1" and venta["nombre_cliente"] == "Daniel"
    assert [i["nombre"] for i in venta["comanda"]["items"]] == ["Hamburguesa #1", "Refresco #1"]
    assert {p["moneda"] for p in venta["comanda"]["pagos"]} == {"USD", "VES"}
    assert hoy["total"] in (0, 1)  # depende de la zona horaria configurada vs. UTC del contenedor

    resumen = (await c.get(f"{API}/ventas/resumen", params={"agrupar": "mes"})).json()
    assert resumen["cantidad_ventas"] == 1 and resumen["total"] == "12.00"
    assert {p["producto"] for p in resumen["productos_top"]} == {"Hamburguesa", "Refresco"}


async def test_dos_hamburguesas_se_siguen_por_separado(admin, datos):
    c, d = admin, datos
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "300", "motivo": "Compra"})
    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "mesa_id": d["mesa"]["id"],
            "items": [{"producto_id": d["hamburguesa"]["id"], "cantidad": 2}],
            "enviar_a_cocina": True,
        },
    )
    assert r.status_code == 201, r.text
    comanda = r.json()
    assert [i["nombre"] for i in comanda["items"]] == ["Hamburguesa #1", "Hamburguesa #2"]
    inv = await inventario(c, d["inv_carne"]["id"])
    assert Decimal(inv["reservado"]) == 300

    primera = comanda["items"][0]["id"]
    await c.post(f"{API}/cocina/items/{primera}/estado", json={"estado": "listo"})
    inv = await inventario(c, d["inv_carne"]["id"])
    assert (Decimal(inv["cantidad"]), Decimal(inv["reservado"])) == (350, 150)

    pedido = (await c.get(f"{API}/public/pedidos/{comanda['seguimiento_url'].rsplit('/', 1)[1]}")).json()
    assert pedido["progreso"]["listo"] == 1 and pedido["progreso"]["en_cocina"] == 1
    assert pedido["sucursal_id"] == d["sucursal"]["id"]

    abiertas = (await c.get(f"{API}/comandas", params={"mesa_id": d["mesa"]["id"]})).json()["items"]
    assert abiertas[0]["mesa_id"] == d["mesa"]["id"]
    assert (abiertas[0]["items_por_servir"], abiertas[0]["items_listos"]) == (1, 1)


async def test_stock_insuficiente_no_se_envia_a_cocina(admin, datos):
    c, d = admin, datos
    r = await c.post(
        f"{API}/comandas",
        json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["hamburguesa"]["id"], "cantidad": 2}]},
    )
    assert r.status_code == 201
    r = await c.post(f"{API}/comandas/{r.json()['id']}/enviar-cocina")
    assert r.status_code == 409
    assert r.json()["detail"]["faltantes"][0]["insumo"] == "Carne molida"
    inv = await inventario(c, d["inv_carne"]["id"])
    assert Decimal(inv["reservado"]) == 0  # todo o nada


async def test_cliente_no_puede_pedir_mas_de_lo_disponible(admin, datos):
    r = await admin.post(
        f"{API}/public/mesas/{datos['qr']}/comandas",
        json={**CLIENTE, "items": [{"producto_id": datos["hamburguesa"]["id"], "cantidad": 2}]},
    )
    assert r.status_code == 409
    assert "Solo quedan 1" in r.json()["detail"]["errores"][0]["error"]


async def test_cancelar_libera_reserva_y_mesa(admin, datos):
    c, d = admin, datos
    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "mesa_id": d["mesa"]["id"],
            "items": [{"producto_id": d["hamburguesa"]["id"]}],
            "enviar_a_cocina": True,
        },
    )
    comanda_id = r.json()["id"]
    assert Decimal((await inventario(c, d["inv_carne"]["id"]))["reservado"]) == 150

    r = await c.post(f"{API}/comandas/{comanda_id}/cancelar", json={"motivo": "Cliente se fue"})
    assert r.status_code == 200, r.text
    inv = await inventario(c, d["inv_carne"]["id"])
    assert (Decimal(inv["cantidad"]), Decimal(inv["reservado"])) == (200, 0)
    assert (await c.get(f"{API}/mesas/{d['mesa']['id']}")).json()["ocupada"] is False
    assert (await c.get(f"{API}/ventas")).json()["total"] == 0


async def test_caja_asigna_mesa_manual_y_sin_mesa(admin, datos):
    c, d = admin, datos
    # Para llevar: sin mesa
    r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "nombre_cliente": "Para llevar"})
    assert r.status_code == 201 and r.json()["mesa_id"] is None
    para_llevar = r.json()["id"]

    # Otra comanda ocupa la mesa 1
    r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "mesa_id": d["mesa"]["id"]})
    assert r.status_code == 201

    # Asignar manualmente la mesa ocupada -> 423; una libre -> ok
    r = await c.patch(f"{API}/comandas/{para_llevar}", json={"mesa_id": d["mesa"]["id"]})
    assert r.status_code == 423
    r = await c.patch(f"{API}/comandas/{para_llevar}", json={"mesa_id": d["mesa2"]["id"]})
    assert r.status_code == 200 and r.json()["mesa"] == "Mesa 2"


async def test_mesa_sin_qr_habilitado(admin, datos):
    c, d = admin, datos
    await c.patch(f"{API}/mesas/{d['mesa']['id']}", json={"qr_habilitado": False})
    assert (await c.get(f"{API}/public/mesas/{d['qr']}")).status_code == 404
    # Caja igual puede abrir la comanda en esa mesa
    r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "mesa_id": d["mesa"]["id"]})
    assert r.status_code == 201


async def test_cliente_agrega_platos_a_comanda_abierta(admin, datos):
    c, d = admin, datos
    r = await c.post(f"{API}/public/mesas/{d['qr']}/comandas", json={**CLIENTE, "items": [{"producto_id": d["refresco"]["id"]}]})
    tracking = r.json()["tracking_token"]
    r = await c.post(f"{API}/public/pedidos/{tracking}/items", json={"items": [{"producto_id": d["refresco"]["id"]}]})
    assert r.status_code == 200, r.text
    assert [i["nombre"] for i in r.json()["items"]] == ["Refresco #1", "Refresco #2"]


async def test_precio_y_disponibilidad_por_sucursal(admin, datos):
    c, d = admin, datos
    url = f"{API}/productos/{d['refresco']['id']}/sucursales/{d['sucursal']['id']}"
    r = await c.put(url, json={"precio": "2.50", "disponible": True})
    assert r.status_code == 200, r.text
    assert (await productos_menu(c, d["sucursal"]["id"]))["Refresco"]["precio"] == "2.50"

    await c.put(url, json={"precio": None, "disponible": False})
    assert "Refresco" not in await productos_menu(c, d["sucursal"]["id"])


async def test_division_de_cuenta(admin, datos):
    c, d = admin, datos
    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "items": [{"producto_id": d["refresco"]["id"], "cantidad": 3}, {"producto_id": d["hamburguesa"]["id"]}],
        },
    )
    comanda = r.json()
    cid = comanda["id"]

    r = await c.get(f"{API}/comandas/{cid}/division", params={"partes": 3})
    partes = [Decimal(p["monto"]) for p in r.json()["partes"]]
    assert sum(partes) == Decimal("16.00") and len(partes) == 3

    ids = [i["id"] for i in comanda["items"]]
    r = await c.post(
        f"{API}/comandas/{cid}/division",
        json={"grupos": [{"etiqueta": "Ana", "item_ids": ids[:2]}, {"etiqueta": "Luis", "item_ids": [ids[3]]}]},
    )
    assert r.status_code == 200, r.text
    div = r.json()
    assert [p["monto"] for p in div["partes"]] == ["4.00", "10.00"]
    assert div["sin_asignar"] == "2.00"

    await c.post(f"{API}/comandas/{cid}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "4", "metodo": "efectivo", "etiqueta": "Ana"})
    div = (await c.post(f"{API}/comandas/{cid}/division", json={"grupos": [{"etiqueta": "Ana", "item_ids": ids[:2]}]})).json()
    assert div["partes"][0]["pagado"] == "4.00"


async def test_merma_y_ajuste_respetan_reservas(admin, datos):
    c, d = admin, datos
    await c.post(
        f"{API}/comandas",
        json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["hamburguesa"]["id"]}], "enviar_a_cocina": True},
    )
    inv_id = d["inv_carne"]["id"]
    r = await c.post(f"{API}/inventario/{inv_id}/merma", json={"cantidad": "100", "motivo": "Se dañó"})
    assert r.status_code == 409
    r = await c.post(f"{API}/inventario/{inv_id}/ajuste", json={"cantidad_real": "180", "motivo": "Conteo semanal"})
    assert r.status_code == 200 and Decimal(r.json()["cantidad"]) == 180
    movs = (await c.get(f"{API}/inventario/{inv_id}/movimientos")).json()["items"]
    assert [m["tipo"] for m in movs] == ["ajuste", "entrada"]


async def test_concurrencia_no_sobrevende(admin, datos):
    """Dos cajas envían a cocina a la vez: solo una consigue la única porción."""
    c, d = admin, datos
    ids = []
    for _ in range(2):
        r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["hamburguesa"]["id"]}]})
        ids.append(r.json()["id"])
    respuestas = await asyncio.gather(*(c.post(f"{API}/comandas/{i}/enviar-cocina") for i in ids))
    assert sorted(r.status_code for r in respuestas) == [200, 409]
    assert Decimal((await inventario(c, d["inv_carne"]["id"]))["reservado"]) == 150


async def test_posicion_de_mesa_en_el_plano(admin, datos):
    url = f"{API}/mesas/{datos['mesa']['id']}"
    r = await admin.patch(url, json={"pos_x": 3, "pos_y": 1})
    assert r.status_code == 200, r.text
    assert (r.json()["pos_x"], r.json()["pos_y"]) == (3, 1)
    assert (await admin.patch(url, json={"pos_x": 100})).status_code == 422
    r = await admin.patch(url, json={"pos_x": None, "pos_y": None})  # quitar del plano
    assert (r.json()["pos_x"], r.json()["pos_y"]) == (None, None)


async def test_pedido_qr_exige_nombre_y_telefono_validos(admin, datos):
    url = f"{API}/public/mesas/{datos['qr']}/comandas"
    item = {"items": [{"producto_id": datos["refresco"]["id"]}]}
    for malo in (
        {},
        {"nombre_cliente": "Ana", "telefono_cliente": "123"},
        {"nombre_cliente": "x1", "telefono_cliente": "04121234567"},
        {"nombre_cliente": "Ana", "telefono_cliente": "0212 123 4567"},  # fijo: no es celular
    ):
        r = await admin.post(url, json={**item, **malo})
        assert r.status_code == 422, malo
    r = await admin.post(url, json={**item, "nombre_cliente": "  María  José ", "telefono_cliente": "0412-123.45.67"})
    assert r.status_code == 201, r.text
    comanda_id = (await admin.get(f"{API}/comandas")).json()["items"][0]["id"]
    c = (await admin.get(f"{API}/comandas/{comanda_id}")).json()
    assert (c["nombre_cliente"], c["telefono_cliente"]) == ("María José", "+584121234567")
