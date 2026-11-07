API = "/api/v1"
CLIENTE = {"nombre_cliente": "Ana Pérez", "telefono_cliente": "0412-555-1234"}


async def _mesa(c, d, nombre, **extra):
    r = await c.post(f"{API}/mesas", json={"sucursal_id": d["sucursal"]["id"], "nombre": nombre, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def _mesas(c, d) -> dict:
    return {m["nombre"]: m for m in (await c.get(f"{API}/mesas", params={"sucursal_id": d["sucursal"]["id"]})).json()}


async def test_zonas_y_posicion_de_las_mesas(admin, datos):
    c, d = admin, datos
    suc = d["sucursal"]["id"]
    salon = (await c.post(f"{API}/zonas", json={"sucursal_id": suc, "nombre": "Salón"})).json()
    terraza = (await c.post(f"{API}/zonas", json={"sucursal_id": suc, "nombre": "Terraza", "orden": 1})).json()
    assert (await c.post(f"{API}/zonas", json={"sucursal_id": suc, "nombre": "Salón"})).status_code == 409
    assert [z["nombre"] for z in (await c.get(f"{API}/zonas", params={"sucursal_id": suc})).json()] == ["Salón", "Terraza"]

    m = await _mesa(c, d, "T1", zona_id=terraza["id"], forma="redonda", ancho=2, alto=2, pos_x=4, pos_y=1)
    assert (m["zona_id"], m["forma"], m["ancho"], m["alto"], m["pos_x"], m["pos_y"]) == (terraza["id"], "redonda", 2, 2, 4, 1)

    # Se edita el tamaño, la forma y la zona
    r = await c.patch(f"{API}/mesas/{m['id']}", json={"forma": "rectangular", "ancho": 6, "zona_id": salon["id"]})
    assert r.status_code == 200 and (r.json()["forma"], r.json()["ancho"], r.json()["zona_id"]) == ("rectangular", 6, salon["id"])
    # Tamaño fuera de rango o forma inválida
    assert (await c.patch(f"{API}/mesas/{m['id']}", json={"ancho": 9})).status_code == 422
    assert (await c.patch(f"{API}/mesas/{m['id']}", json={"alto": 0})).status_code == 422
    assert (await c.patch(f"{API}/mesas/{m['id']}", json={"forma": "triangular"})).status_code == 422

    # Renombrar y eliminar una zona deja las mesas sin zona
    assert (await c.patch(f"{API}/zonas/{salon['id']}", json={"nombre": "Salón principal"})).json()["nombre"] == "Salón principal"
    assert (await c.delete(f"{API}/zonas/{salon['id']}")).status_code == 204
    assert (await _mesas(c, d))["T1"]["zona_id"] is None


async def test_una_mesa_no_puede_ir_a_la_zona_de_otra_sucursal(admin, datos):
    c, d = admin, datos
    otra = (await c.post(f"{API}/sucursales", json={"nombre": "Norte"})).json()
    zona_ajena = (await c.post(f"{API}/zonas", json={"sucursal_id": otra["id"], "nombre": "Salón"})).json()
    r = await c.post(f"{API}/mesas", json={"sucursal_id": d["sucursal"]["id"], "nombre": "X", "zona_id": zona_ajena["id"]})
    assert r.status_code == 409
    assert (await c.patch(f"{API}/mesas/{d['mesa']['id']}", json={"zona_id": zona_ajena["id"]})).status_code == 409
    assert (await c.patch(f"{API}/mesas/{d['mesa']['id']}", json={"zona_id": 9999})).status_code == 404


async def test_unir_mesas_comparten_comanda_y_se_separan_al_cerrar(admin, datos):
    c, d = admin, datos
    m1, m2 = d["mesa"], d["mesa2"]
    m3 = await _mesa(c, d, "Mesa 3")

    r = await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m2["id"], m3["id"]]})
    assert r.status_code == 200, r.text
    mesas = await _mesas(c, d)
    assert mesas["Mesa 2"]["unida_a_id"] == m1["id"] and mesas["Mesa 3"]["unida_a_id"] == m1["id"] and mesas["Mesa 1"]["unida_a_id"] is None

    # Abrir una comanda en una mesa unida la deja en la principal
    comanda = (await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "mesa_id": m2["id"], "items": [{"producto_id": d["refresco"]["id"]}]})).json()
    assert comanda["mesa_id"] == m1["id"]
    mesas = await _mesas(c, d)
    assert all(mesas[n]["ocupada"] and mesas[n]["comanda_abierta_id"] == comanda["id"] for n in ("Mesa 1", "Mesa 2", "Mesa 3"))
    # Todas bloquean al QR y a una segunda comanda
    assert (await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "mesa_id": m3["id"]})).status_code == 423
    assert (await c.get(f"{API}/public/mesas/{d['qr']}")).json()["ocupada"] is True

    # Al cerrar la comanda el grupo se separa solo
    await c.post(f"{API}/comandas/{comanda['id']}/cancelar", json={"motivo": "Prueba"})
    mesas = await _mesas(c, d)
    assert all(m["unida_a_id"] is None and not m["ocupada"] for m in mesas.values())


async def test_reglas_para_unir(admin, datos):
    c, d = admin, datos
    m1, m2 = d["mesa"], d["mesa2"]
    m3 = await _mesa(c, d, "Mesa 3")
    m4 = await _mesa(c, d, "Mesa 4")

    assert (await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m1["id"]]})).status_code == 422
    assert (await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": []})).status_code == 422
    assert (await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m2["id"]]})).status_code == 200
    # Una unida no puede ser principal ni unirse a otro grupo
    assert (await c.post(f"{API}/mesas/{m2['id']}/unir", json={"mesa_ids": [m3["id"]]})).status_code == 409
    assert (await c.post(f"{API}/mesas/{m3['id']}/unir", json={"mesa_ids": [m2["id"]]})).status_code == 409
    # Una mesa con comanda abierta no se suma a otra
    await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "mesa_id": m4["id"]})
    assert (await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m4["id"]]})).status_code == 409
    # Pero la principal sí puede tener comanda ya abierta
    await c.post(f"{API}/comandas/{(await _mesas(c, d))['Mesa 4']['comanda_abierta_id']}/cancelar", json={"motivo": "x"})
    otra = (await c.post(f"{API}/sucursales", json={"nombre": "Norte"})).json()
    m_ajena = await _mesa_en(c, otra, "Z1")
    assert (await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m_ajena["id"]]})).status_code == 422
    assert (await c.post(f"{API}/mesas/9999/unir", json={"mesa_ids": [m3["id"]]})).status_code == 404


async def _mesa_en(c, sucursal, nombre):
    r = await c.post(f"{API}/mesas", json={"sucursal_id": sucursal["id"], "nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()


async def test_separar_una_mesa_o_todo_el_grupo(admin, datos):
    c, d = admin, datos
    m1, m2 = d["mesa"], d["mesa2"]
    m3 = await _mesa(c, d, "Mesa 3")
    await c.post(f"{API}/mesas/{m1['id']}/unir", json={"mesa_ids": [m2["id"], m3["id"]]})

    # Separar una unida: solo ella sale
    r = await c.post(f"{API}/mesas/{m2['id']}/separar")
    assert r.status_code == 200 and r.json()["unida_a_id"] is None
    mesas = await _mesas(c, d)
    assert mesas["Mesa 3"]["unida_a_id"] == m1["id"]
    # Separar la principal: se deshace todo el grupo
    await c.post(f"{API}/mesas/{m1['id']}/separar")
    assert all(m["unida_a_id"] is None for m in (await _mesas(c, d)).values())


async def test_pedido_por_qr_de_una_mesa_unida_va_a_la_principal(admin, datos):
    c, d = admin, datos
    await c.post(f"{API}/mesas/{d['mesa2']['id']}/unir", json={"mesa_ids": [d["mesa"]["id"]]})  # Mesa 2 principal; Mesa 1 (con QR) unida
    r = await c.post(f"{API}/public/mesas/{d['qr']}/comandas", json={**CLIENTE, "items": [{"producto_id": d["refresco"]["id"]}]})
    assert r.status_code == 201, r.text
    comanda = (await c.get(f"{API}/comandas")).json()["items"][0]
    assert comanda["mesa_id"] == d["mesa2"]["id"]
