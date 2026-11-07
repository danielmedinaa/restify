from decimal import Decimal

API = "/api/v1"


async def _insumo(c, nombre, unidad):
    r = await c.post(f"{API}/insumos", json={"nombre": nombre, "unidad": unidad})
    assert r.status_code == 201, r.text
    return r.json()


async def test_los_insumos_se_miden_en_g_kg_ml_l_o_unidad(admin):
    for i, u in enumerate(["g", "kg", "ml", "l", "unidad"]):
        assert (await _insumo(admin, f"Insumo {i}", u))["unidad"] == u
    assert (await admin.post(f"{API}/insumos", json={"nombre": "Raro", "unidad": "libra"})).status_code in (400, 422)


async def test_receta_en_kilos_con_gramos_convertidos(admin, datos):
    c, d = admin, datos
    carne_kg = await _insumo(c, "Carne a granel", "kg")
    inv = (
        await c.post(
            f"{API}/inventario",
            json={"sucursal_id": d["sucursal"]["id"], "insumo_id": carne_kg["id"], "cantidad": "2", "stock_minimo": "0.5"},
        )
    ).json()
    # 150 g -> 0,150 kg (el front convierte; el backend guarda en la unidad del insumo)
    receta = (await c.post(f"{API}/recetas", json={"nombre": "Medallón", "ingredientes": [{"insumo_id": carne_kg["id"], "cantidad": "0.150"}]})).json()
    assert receta["ingredientes"][0]["unidad"] == "kg" and receta["ingredientes"][0]["cantidad"] == "0.150"
    producto = (await c.post(f"{API}/productos", json={"nombre": "Medallón", "precio_base": "5", "receta_id": receta["id"]})).json()

    # 2 kg alcanzan para 13 porciones de 150 g
    menu = (await c.get(f"{API}/public/sucursales/{d['sucursal']['id']}/menu")).json()
    p = next(p for cat in menu["categorias"] for p in cat["productos"] if p["id"] == producto["id"])
    assert p["porciones_disponibles"] == 13

    # Descuenta en kilos al preparar
    comanda = (await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": producto["id"], "cantidad": 2}], "enviar_a_cocina": True})).json()
    for i in comanda["items"]:
        await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})
    stock = next(i for i in (await c.get(f"{API}/inventario", params={"limite": 100})).json()["items"] if i["id"] == inv["id"])
    assert Decimal(stock["cantidad"]) == Decimal("1.7")


async def test_costo_por_kg_y_costo_de_la_receta(admin, datos):
    c, d = admin, datos
    carne_kg = await _insumo(c, "Carne a granel", "kg")
    r = await c.patch(f"{API}/insumos/{carne_kg['id']}", json={"costo_unitario": "8.000000"})
    assert r.status_code == 200
    receta = (await c.post(f"{API}/recetas", json={"nombre": "Medallón", "ingredientes": [{"insumo_id": carne_kg["id"], "cantidad": "0.250"}]})).json()
    assert receta["costo"] == "2.00"  # 0,25 kg x 8 por kg


async def test_los_insumos_por_unidad_siguen_siendo_enteros(admin):
    c = admin
    pan = await _insumo(c, "Pan", "unidad")
    r = await c.post(f"{API}/recetas", json={"nombre": "Tostada", "ingredientes": [{"insumo_id": pan["id"], "cantidad": "0.5"}]})
    assert r.status_code in (400, 422)


# ---------- Unidades dinámicas, presentaciones y productos de reventa ----------
async def test_el_administrador_crea_sus_propias_unidades(admin):
    c = admin
    lista = (await c.get(f"{API}/unidades")).json()
    assert {u["codigo"] for u in lista} >= {"g", "kg", "ml", "l", "unidad"}
    r = await c.post(f"{API}/unidades", json={"codigo": "caja", "nombre": "cajas", "abreviatura": "caja", "permite_decimales": False})
    assert r.status_code == 201, r.text
    assert (await c.post(f"{API}/unidades", json={"codigo": "caja", "nombre": "otra", "abreviatura": "x"})).status_code == 409
    assert (await _insumo(c, "Vasos", "caja"))["unidad"] == "caja"
    # En uso: no se elimina ni se desactiva; las de fábrica tampoco se eliminan
    uid = r.json()["id"]
    assert (await c.delete(f"{API}/unidades/{uid}")).status_code == 409
    assert (await c.patch(f"{API}/unidades/{uid}", json={"activa": False})).status_code == 409
    base = next(u for u in lista if u["codigo"] == "g")
    assert (await c.delete(f"{API}/unidades/{base['id']}")).status_code == 409


async def test_unidad_personalizada_con_enteros_y_subunidad(admin):
    c = admin
    await c.post(f"{API}/unidades", json={"codigo": "docena", "nombre": "docenas", "abreviatura": "doc", "permite_decimales": False})
    huevos = await _insumo(c, "Huevos", "docena")
    assert huevos["permite_decimales"] is False and huevos["unidad_abreviatura"] == "doc"
    r = await c.post(f"{API}/recetas", json={"nombre": "Revuelto", "ingredientes": [{"insumo_id": huevos["id"], "cantidad": "0.5"}]})
    assert r.status_code in (400, 422)
    # Subunidad sin equivalencia: inválido
    r = await c.post(f"{API}/unidades", json={"codigo": "lb", "nombre": "libras", "abreviatura": "lb", "subunidad_abreviatura": "oz"})
    assert r.status_code in (400, 422)
    assert (await c.post(f"{API}/unidades", json={"codigo": "lb", "nombre": "libras", "abreviatura": "lb", "subunidad_abreviatura": "oz", "factor_subunidad": "16"})).status_code == 201


async def test_reposicion_y_compra_por_presentacion(admin, datos):
    c, d = admin, datos
    lata = await _insumo(c, "Pepsi lata", "unidad")
    r = await c.put(f"{API}/insumos/{lata['id']}/presentaciones", json={"presentaciones": [{"nombre": "Caja x24", "cantidad": "24"}, {"nombre": "Pack x6", "cantidad": "6"}]})
    assert r.status_code == 200, r.text
    caja = next(p for p in r.json()["presentaciones"] if p["nombre"] == "Caja x24")
    inv = (await c.post(f"{API}/inventario", json={"sucursal_id": d["sucursal"]["id"], "insumo_id": lata["id"]})).json()
    r = await c.post(f"{API}/inventario/{inv['id']}/entrada", json={"cantidad": "3", "presentacion_id": caja["id"]})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["cantidad"]) == 72
    # Envases enteros y presentación ajena
    assert (await c.post(f"{API}/inventario/{inv['id']}/entrada", json={"cantidad": "1.5", "presentacion_id": caja["id"]})).status_code in (400, 422)
    assert (await c.post(f"{API}/inventario/{inv['id']}/entrada", json={"cantidad": "1", "presentacion_id": 9999})).status_code in (400, 422)
    # Compra: 2 cajas por 48 -> 48 latas a 1 c/u
    moneda = (await c.get(f"{API}/monedas")).json()[0]
    r = await c.post(f"{API}/compras", json={"sucursal_id": d["sucursal"]["id"], "moneda_id": moneda["id"], "items": [{"insumo_id": lata["id"], "cantidad": "2", "presentacion_id": caja["id"], "subtotal": "48"}]})
    assert r.status_code == 201, r.text
    assert Decimal(r.json()["items"][0]["cantidad"]) == 48
    assert Decimal(r.json()["items"][0]["costo_unitario"]) == 1


async def test_producto_sin_receta_descuenta_directo_su_insumo(admin, datos):
    c, d = admin, datos
    suc = d["sucursal"]["id"]
    lata = await _insumo(c, "Pepsi lata", "unidad")
    inv = (await c.post(f"{API}/inventario", json={"sucursal_id": suc, "insumo_id": lata["id"], "cantidad": "5", "stock_minimo": "1"})).json()
    pepsi = (await c.post(f"{API}/productos", json={"nombre": "Pepsi", "precio_base": "2", "insumo_id": lata["id"]})).json()
    assert pepsi["control_stock"] == "directo" and Decimal(pepsi["cantidad_por_venta"]) == 1
    # Receta e insumo directo a la vez: no
    receta = (await c.post(f"{API}/recetas", json={"nombre": "Algo", "ingredientes": [{"insumo_id": lata["id"], "cantidad": "1"}]})).json()
    assert (await c.post(f"{API}/productos", json={"nombre": "Mixto", "precio_base": "1", "insumo_id": lata["id"], "receta_id": receta["id"]})).status_code in (400, 422)

    menu = (await c.get(f"{API}/public/sucursales/{suc}/menu")).json()
    p = next(p for cat in menu["categorias"] for p in cat["productos"] if p["id"] == pepsi["id"])
    assert p["porciones_disponibles"] == 5

    comanda = (await c.post(f"{API}/comandas", json={"sucursal_id": suc, "items": [{"producto_id": pepsi["id"], "cantidad": 2}], "enviar_a_cocina": True})).json()
    items = (await c.get(f"{API}/inventario", params={"limite": 100})).json()["items"]
    fila = next(i for i in items if i["id"] == inv["id"])
    assert Decimal(fila["reservado"]) == 2
    for i in comanda["items"]:
        await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})
    fila = next(i for i in (await c.get(f"{API}/inventario", params={"limite": 100})).json()["items"] if i["id"] == inv["id"])
    assert Decimal(fila["cantidad"]) == 3 and Decimal(fila["reservado"]) == 0
    # Sin stock suficiente no se puede enviar a cocina
    r = await c.post(f"{API}/comandas", json={"sucursal_id": suc, "items": [{"producto_id": pepsi["id"], "cantidad": 4}], "enviar_a_cocina": True})
    assert r.status_code == 409

    # Pasar a "sin control de stock" y a receta
    r = await c.patch(f"{API}/productos/{pepsi['id']}", json={"insumo_id": None})
    assert r.json()["control_stock"] == "ninguno"
    r = await c.patch(f"{API}/productos/{pepsi['id']}", json={"receta_id": receta["id"]})
    assert r.json()["control_stock"] == "receta"
    r = await c.patch(f"{API}/productos/{pepsi['id']}", json={"insumo_id": lata["id"]})
    assert r.json()["control_stock"] == "directo" and r.json()["receta_id"] is None
