import re

from tests.conftest import PASSWORD, login

API = "/api/v1"


async def test_codigos_internos_automaticos_y_manuales(admin, datos):
    c = admin
    # Los insumos del escenario base se crearon sin código: el sistema los genera
    assert re.fullmatch(r"INS-\d{4}", datos["carne"]["codigo"])
    assert re.fullmatch(r"PRD-\d{4}", datos["hamburguesa"]["codigo"])
    assert re.fullmatch(r"REC-\d{4}", datos["receta"]["codigo"])

    r = await c.post(f"{API}/insumos", json={"nombre": "Queso", "unidad": "g", "codigo": " que-01 ", "codigo_barras": "7591234567890"})
    assert r.status_code == 201, r.text
    assert (r.json()["codigo"], r.json()["codigo_barras"]) == ("QUE-01", "7591234567890")
    # Código repetido -> 409
    r = await c.post(f"{API}/insumos", json={"nombre": "Otro", "unidad": "g", "codigo": "QUE-01"})
    assert r.status_code == 409
    r = await c.post(f"{API}/insumos", json={"nombre": "Malo", "unidad": "g", "codigo": "con espacios"})
    assert r.status_code == 422


async def test_buscar_por_codigo_barras_y_nombre(admin, datos):
    c, d = admin, datos
    suc = d["sucursal"]["id"]
    await c.patch(f"{API}/insumos/{d['carne']['id']}", json={"codigo_barras": "7590001112223"})

    por_codigo = (await c.get(f"{API}/inventario/buscar", params={"sucursal_id": suc, "q": d["carne"]["codigo"].lower()})).json()
    assert len(por_codigo) == 1 and por_codigo[0]["coincidencia"] == "codigo"
    assert por_codigo[0]["inventario"]["cantidad"] == "200.000"

    por_barras = (await c.get(f"{API}/inventario/buscar", params={"sucursal_id": suc, "q": "7590001112223"})).json()
    assert por_barras[0]["insumo"]["nombre"] == "Carne molida" and por_barras[0]["coincidencia"] == "codigo_barras"

    por_nombre = (await c.get(f"{API}/inventario/buscar", params={"sucursal_id": suc, "q": "pan"})).json()
    assert [x["insumo"]["nombre"] for x in por_nombre] == ["Pan de hamburguesa"]

    # Un insumo que no está en el inventario de la sucursal vuelve sin inventario
    nuevo = (await c.post(f"{API}/insumos", json={"nombre": "Sal", "unidad": "g"})).json()
    r = (await c.get(f"{API}/inventario/buscar", params={"sucursal_id": suc, "q": nuevo["codigo"]})).json()
    assert r[0]["inventario"] is None

    etiqueta = await c.get(f"{API}/insumos/{d['carne']['id']}/etiqueta")
    assert etiqueta.status_code == 200 and etiqueta.headers["content-type"].startswith("image/svg+xml")


async def test_bitacora_registra_quien_y_que(admin, datos):
    c, d = admin, datos
    inv = d["inv_carne"]["id"]
    await c.post(f"{API}/inventario/{inv}/entrada", json={"cantidad": "300", "motivo": "Compra"})
    await c.post(f"{API}/inventario/{inv}/ajuste", json={"cantidad_real": "480", "motivo": "Conteo"})
    await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"tasa": "40"})

    r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["refresco"]["id"]}], "enviar_a_cocina": True})
    comanda = r.json()
    await c.post(f"{API}/cocina/items/{comanda['items'][0]['id']}/estado", json={"estado": "listo"})
    await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "2", "metodo": "efectivo"})
    await c.post(f"{API}/comandas/{comanda['id']}/cerrar")

    inventario = (await c.get(f"{API}/bitacora", params={"modulo": "inventario"})).json()["items"]
    textos = [e["descripcion"] for e in inventario]
    assert "Repuso 300 g de Carne molida en Centro (200 g → 500 g) · Compra" in textos
    assert "Ajustó el conteo de Carne molida en Centro: 500 g → 480 g · Conteo" in textos
    assert all(e["usuario_nombre"] == "admin" and e["sucursal"] == "Centro" for e in inventario)

    todo = [e["descripcion"] for e in (await c.get(f"{API}/bitacora", params={"limite": 100})).json()["items"]]
    assert any(t.startswith("Cambió la tasa de VES: 36.5 → 40") for t in todo)
    assert any(t.startswith(f"Cobró la comanda #{comanda['id']} (para llevar)") for t in todo)
    assert any("Registró un pago de $ 2,00 (efectivo)" in t for t in todo)
    assert any(t.startswith("Creó el producto Hamburguesa") for t in todo)

    buscado = (await c.get(f"{API}/bitacora", params={"q": "carne"})).json()
    assert buscado["total"] >= 2


async def test_bitacora_requiere_permiso(admin, datos):
    rol = (await admin.post(f"{API}/roles", json={"nombre": "Cajero", "permisos": [{"modulo": "caja", "leer": True}]})).json()
    await admin.post(
        f"{API}/usuarios",
        json={"email": "caja@restify.com", "nombre": "Caja", "password": PASSWORD, "rol_id": rol["id"], "sucursal_ids": [datos["sucursal"]["id"]]},
    )
    tokens = await login(admin, "caja@restify.com")
    r = await admin.get(f"{API}/bitacora", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 403
