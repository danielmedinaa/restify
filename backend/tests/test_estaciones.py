API = "/api/v1"


async def _estacion(c, nombre, **extra):
    r = await c.post(f"{API}/estaciones", json={"nombre": nombre, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def test_crud_de_estaciones(admin):
    c = admin
    cocina = await _estacion(c, "Cocina", orden=0)
    await _estacion(c, "Barra", orden=1)
    assert (await c.post(f"{API}/estaciones", json={"nombre": "Cocina"})).status_code == 409
    assert [e["nombre"] for e in (await c.get(f"{API}/estaciones")).json()] == ["Cocina", "Barra"]

    r = await c.patch(f"{API}/estaciones/{cocina['id']}", json={"nombre": "Cocina caliente", "activa": False})
    assert r.status_code == 200 and r.json()["activa"] is False
    assert (await c.patch(f"{API}/estaciones/999", json={"nombre": "X"})).status_code == 404
    assert (await c.delete(f"{API}/estaciones/{cocina['id']}")).status_code == 204
    assert len((await c.get(f"{API}/estaciones")).json()) == 1


async def test_producto_hereda_estacion_de_su_categoria_o_va_a_cocina(admin):
    c = admin
    cocina = await _estacion(c, "Cocina")
    barra = await _estacion(c, "Barra", orden=1)
    bebidas = (await c.post(f"{API}/categorias", json={"nombre": "Bebidas", "estacion_id": barra["id"]})).json()
    assert bebidas["estacion_id"] == barra["id"]
    # Una categoría sin estación elegida nace en Cocina
    postres = (await c.post(f"{API}/categorias", json={"nombre": "Postres"})).json()
    assert postres["estacion_id"] == cocina["id"]

    pepsi = (await c.post(f"{API}/productos", json={"nombre": "Pepsi", "precio_base": "1", "categoria_id": bebidas["id"]})).json()
    assert pepsi["estacion"]["nombre"] == "Barra"
    flan = (await c.post(f"{API}/productos", json={"nombre": "Flan", "precio_base": "2", "categoria_id": postres["id"]})).json()
    assert flan["estacion"]["nombre"] == "Cocina"
    # Sin categoría ni estación: Cocina
    suelto = (await c.post(f"{API}/productos", json={"nombre": "Suelto", "precio_base": "2"})).json()
    assert suelto["estacion"]["nombre"] == "Cocina"
    # Una estación elegida a mano gana a la de la categoría
    cafe = (await c.post(f"{API}/productos", json={"nombre": "Café", "precio_base": "1", "categoria_id": bebidas["id"], "estacion_id": cocina["id"]})).json()
    assert cafe["estacion"]["nombre"] == "Cocina"
    # Estación inexistente
    assert (await c.post(f"{API}/productos", json={"nombre": "Raro", "precio_base": "1", "estacion_id": 999})).status_code == 404


async def test_pantalla_de_cada_estacion_solo_ve_lo_suyo(admin, datos):
    c, d = admin, datos
    cocina = await _estacion(c, "Cocina")
    barra = await _estacion(c, "Barra", orden=1)
    await c.patch(f"{API}/productos/{d['hamburguesa']['id']}", json={"estacion_id": cocina["id"]})
    await c.patch(f"{API}/productos/{d['refresco']['id']}", json={"estacion_id": barra["id"]})

    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "items": [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"], "cantidad": 2}],
            "enviar_a_cocina": True,
        },
    )
    assert r.status_code == 201, r.text
    assert {i["estacion_id"] for i in r.json()["items"]} == {cocina["id"], barra["id"]}

    def nombres(tablero):
        return sorted(i["nombre"].split(" #")[0] for com in tablero for i in com["items"])

    suc = d["sucursal"]["id"]
    en_cocina = (await c.get(f"{API}/cocina", params={"sucursal_id": suc, "estacion_id": cocina["id"]})).json()
    en_barra = (await c.get(f"{API}/cocina", params={"sucursal_id": suc, "estacion_id": barra["id"]})).json()
    todas = (await c.get(f"{API}/cocina", params={"sucursal_id": suc})).json()
    assert nombres(en_cocina) == ["Hamburguesa"]
    assert nombres(en_barra) == ["Refresco", "Refresco"]
    assert nombres(todas) == ["Hamburguesa", "Refresco", "Refresco"]

    # La barra marca sus bebidas listas sin tocar el plato de la cocina
    for i in en_barra[0]["items"]:
        assert (await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})).status_code == 200
    assert (await c.get(f"{API}/cocina", params={"sucursal_id": suc, "estacion_id": barra["id"]})).json() == []
    assert nombres((await c.get(f"{API}/cocina", params={"sucursal_id": suc, "estacion_id": cocina["id"]})).json()) == ["Hamburguesa"]


async def test_plato_sin_estacion_sale_en_todas_las_pantallas(admin, datos):
    c, d = admin, datos
    cocina = await _estacion(c, "Cocina")
    # El refresco de los datos base se creó antes de que existieran estaciones: sin estación
    assert (await c.get(f"{API}/productos/{d['refresco']['id']}")).json()["estacion"] is None
    r = await c.post(
        f"{API}/comandas",
        json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["refresco"]["id"]}], "enviar_a_cocina": True},
    )
    assert r.status_code == 201
    tablero = (await c.get(f"{API}/cocina", params={"sucursal_id": d["sucursal"]["id"], "estacion_id": cocina["id"]})).json()
    assert len(tablero) == 1


async def test_eliminar_estacion_deja_productos_sin_estacion(admin):
    c = admin
    barra = await _estacion(c, "Barra")
    p = (await c.post(f"{API}/productos", json={"nombre": "Pepsi", "precio_base": "1", "estacion_id": barra["id"]})).json()
    assert (await c.delete(f"{API}/estaciones/{barra['id']}")).status_code == 204
    assert (await c.get(f"{API}/productos/{p['id']}")).json()["estacion"] is None
