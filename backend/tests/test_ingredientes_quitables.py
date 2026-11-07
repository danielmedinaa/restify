API = "/api/v1"


async def _hamburguesa_con_cebolla(c, d):
    """Hamburguesa 150 g de carne + pan (no quitables) + 20 g de cebolla (quitable)."""
    cebolla = (await c.post(f"{API}/insumos", json={"nombre": "Cebolla", "unidad": "g"})).json()
    inv = (
        await c.post(
            f"{API}/inventario",
            json={"sucursal_id": d["sucursal"]["id"], "insumo_id": cebolla["id"], "cantidad": "500", "stock_minimo": "50"},
        )
    ).json()
    receta = (
        await c.post(
            f"{API}/recetas",
            json={
                "nombre": "Hamburguesa con cebolla",
                "ingredientes": [
                    {"insumo_id": d["carne"]["id"], "cantidad": "150", "removible": False},
                    {"insumo_id": d["pan"]["id"], "cantidad": "1", "removible": False},
                    {"insumo_id": cebolla["id"], "cantidad": "20"},
                ],
            },
        )
    ).json()
    producto = (await c.post(f"{API}/productos", json={"nombre": "Hamburguesa especial", "precio_base": "11", "receta_id": receta["id"]})).json()
    return cebolla, inv, producto


async def _stock(c, inv_id):
    return next(i for i in (await c.get(f"{API}/inventario", params={"limite": 100})).json()["items"] if i["id"] == inv_id)


async def test_el_menu_solo_ofrece_quitar_lo_marcado_como_quitable(admin, datos):
    c, d = admin, datos
    cebolla, _, producto = await _hamburguesa_con_cebolla(c, d)
    assert [x["removible"] for x in (await c.get(f"{API}/recetas")).json()[-1]["ingredientes"]] == [False, False, True]
    menu = (await c.get(f"{API}/public/sucursales/{d['sucursal']['id']}/menu")).json()
    p = next(p for cat in menu["categorias"] for p in cat["productos"] if p["id"] == producto["id"])
    assert p["ingredientes"] == [{"insumo_id": cebolla["id"], "nombre": "Cebolla"}]


async def test_sin_cebolla_no_reserva_ni_descuenta_cebolla(admin, datos):
    c, d = admin, datos
    cebolla, inv_cebolla, producto = await _hamburguesa_con_cebolla(c, d)
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "300"})
    r = await c.post(
        f"{API}/public/mesas/{d['qr']}/comandas",
        json={
            "nombre_cliente": "Ana Pérez",
            "telefono_cliente": "0412-555-1234",
            "items": [
                {"producto_id": producto["id"], "sin_insumo_ids": [cebolla["id"]], "notas": "bien cocida"},
                {"producto_id": producto["id"]},
            ],
        },
    )
    assert r.status_code == 201, r.text
    comanda = (await c.get(f"{API}/comandas")).json()["items"][0]
    items = (await c.get(f"{API}/comandas/{comanda['id']}")).json()["items"]
    sin, con = items
    assert sin["sin_insumo_ids"] == [cebolla["id"]] and sin["notas"] == "SIN Cebolla · bien cocida"
    assert con["sin_insumo_ids"] == [] and con["notas"] is None

    assert (await c.post(f"{API}/comandas/{comanda['id']}/enviar-cocina")).status_code == 200
    # Reserva: 2 de carne y pan, pero solo UNA cebolla (20 g)
    assert (await _stock(c, d["inv_carne"]["id"]))["reservado"] == "300.000"
    assert (await _stock(c, inv_cebolla["id"]))["reservado"] == "20.000"

    for i in items:
        await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})
    assert (await _stock(c, inv_cebolla["id"]))["cantidad"] == "480.000"
    assert (await _stock(c, d["inv_carne"]["id"]))["cantidad"] == "200.000"  # 500 - 2 x 150


async def test_no_se_puede_quitar_lo_que_no_es_quitable(admin, datos):
    c, d = admin, datos
    _, _, producto = await _hamburguesa_con_cebolla(c, d)
    r = await c.post(
        f"{API}/public/mesas/{d['qr']}/comandas",
        json={
            "nombre_cliente": "Ana Pérez",
            "telefono_cliente": "0412-555-1234",
            "items": [{"producto_id": producto["id"], "sin_insumo_ids": [d["carne"]["id"]]}],
        },
    )
    assert r.status_code in (400, 422), r.text


async def test_caja_cambia_los_ingredientes_solo_de_platos_pendientes(admin, datos):
    c, d = admin, datos
    cebolla, inv_cebolla, producto = await _hamburguesa_con_cebolla(c, d)
    comanda = (await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": producto["id"]}]})).json()
    item = comanda["items"][0]
    base = f"{API}/comandas/{comanda['id']}/items/{item['id']}"

    assert (await c.get(f"{base}/ingredientes")).json() == [{"insumo_id": cebolla["id"], "nombre": "Cebolla"}]
    r = await c.put(f"{base}/sin-ingredientes", json={"sin_insumo_ids": [cebolla["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["notas"] == "SIN Cebolla"
    # Volver a ponerla
    r = await c.put(f"{base}/sin-ingredientes", json={"sin_insumo_ids": []})
    assert r.json()["items"][0]["notas"] is None
    # Ingrediente ajeno a la receta
    assert (await c.put(f"{base}/sin-ingredientes", json={"sin_insumo_ids": [d["pan"]["id"]]})).status_code in (400, 422)

    # Ya enviado a cocina (stock reservado): no se toca
    await c.put(f"{base}/sin-ingredientes", json={"sin_insumo_ids": [cebolla["id"]]})
    await c.post(f"{API}/comandas/{comanda['id']}/enviar-cocina")
    assert (await c.put(f"{base}/sin-ingredientes", json={"sin_insumo_ids": []})).status_code == 409
    assert (await _stock(c, inv_cebolla["id"]))["reservado"] == "0.000"
