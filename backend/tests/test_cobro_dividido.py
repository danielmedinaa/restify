from decimal import Decimal

API = "/api/v1"


async def _comanda_servida(c, d, hamburguesas=1, refrescos=2) -> dict:
    """Total: hamburguesas x 10 + refrescos x 2 (USD, sin IVA encima)."""
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "1000"})
    await c.post(f"{API}/inventario/{d['inv_pan']['id']}/entrada", json={"cantidad": "50"})
    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "items": [
                {"producto_id": p["id"], "cantidad": n}
                for p, n in ((d["hamburguesa"], hamburguesas), (d["refresco"], refrescos))
                if n
            ],
            "enviar_a_cocina": True,
        },
    )
    assert r.status_code == 201, r.text
    comanda = r.json()
    for i in comanda["items"]:
        await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})
    return (await c.get(f"{API}/comandas/{comanda['id']}")).json()


async def _pagar(c, d, comanda_id, monto, etiqueta=None, metodo="efectivo"):
    return await c.post(
        f"{API}/comandas/{comanda_id}/pagos",
        json={"moneda_id": d["usd"]["id"], "monto": str(monto), "metodo": metodo, "etiqueta": etiqueta},
    )


async def test_por_platos_cada_persona_paga_lo_suyo_y_la_cuenta_se_cubre(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d)  # 10 + 2 + 2 = 14
    cid = comanda["id"]
    hamb, ref1, ref2 = (i["id"] for i in comanda["items"])
    grupos = {"grupos": [{"etiqueta": "Ana", "item_ids": [hamb]}, {"etiqueta": "Luis", "item_ids": [ref1, ref2]}]}
    div = (await c.post(f"{API}/comandas/{cid}/division", json=grupos)).json()
    assert [(p["etiqueta"], p["monto"]) for p in div["partes"]] == [("Ana", "10.00"), ("Luis", "4.00")]

    r = await _pagar(c, d, cid, "10", "Ana")
    assert r.status_code == 201, r.text
    div = (await c.post(f"{API}/comandas/{cid}/division", json=grupos)).json()
    assert div["partes"][0]["pagado"] == "10.00" and div["partes"][1]["pagado"] == "0.00"
    assert (await c.get(f"{API}/comandas/{cid}")).json()["totales"]["pendiente"] == "4.00"

    # Cobrar a Luis lo restante cubre la cuenta y se puede cerrar
    await _pagar(c, d, cid, "4", "Luis")
    totales = (await c.get(f"{API}/comandas/{cid}")).json()["totales"]
    assert totales["pendiente"] == "0.00"
    assert (await c.post(f"{API}/comandas/{cid}/cerrar")).status_code == 200


async def test_partes_iguales_absorben_el_redondeo_en_la_ultima(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d, hamburguesas=1, refrescos=2)  # 14 / 3
    partes = (await c.get(f"{API}/comandas/{comanda['id']}/division", params={"partes": 3})).json()["partes"]
    montos = [Decimal(p["monto"]) for p in partes]
    assert len(montos) == 3 and sum(montos) == Decimal("14.00")
    assert montos == [Decimal("4.67"), Decimal("4.67"), Decimal("4.66")]  # la última absorbe el redondeo


async def test_vaca_aportes_libres_hasta_cubrir(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d)  # 14
    cid = comanda["id"]
    for etiqueta, monto in [("Ana", "5"), ("Luis", "6.50"), ("Aporte 3", "2.50")]:
        assert (await _pagar(c, d, cid, monto, etiqueta)).status_code == 201
        pagos = (await c.get(f"{API}/comandas/{cid}")).json()["pagos"]
    assert [p["etiqueta"] for p in pagos] == ["Ana", "Luis", "Aporte 3"]
    totales = (await c.get(f"{API}/comandas/{cid}")).json()["totales"]
    assert totales["pagado"] == "14.00" and totales["pendiente"] == "0.00"

    # Quitar un aporte (se equivocaron de monto) vuelve a abrir lo pendiente
    luis = next(p for p in pagos if p["etiqueta"] == "Luis")
    assert (await c.delete(f"{API}/comandas/{cid}/pagos/{luis['id']}")).status_code == 200
    assert (await c.get(f"{API}/comandas/{cid}")).json()["totales"]["pendiente"] == "6.50"


async def test_no_se_cierra_con_aportes_incompletos(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d)
    await _pagar(c, d, comanda["id"], "5", "Ana")
    assert (await c.post(f"{API}/comandas/{comanda['id']}/cerrar")).status_code == 409


async def test_el_cobro_se_registra_por_lo_aplicado_y_el_vuelto_no_entra_a_caja(admin, datos):
    """El modal registra lo que abona (40), no el billete (50): el vuelto es solo del mostrador."""
    c, d = admin, datos
    comanda = await _comanda_servida(c, d, hamburguesas=4, refrescos=0)  # 40
    await c.post(f"{API}/caja/turnos", json={"sucursal_id": d["sucursal"]["id"], "efectivo_inicial": [{"moneda_id": d["usd"]["id"], "monto": "0"}]})
    r = await _pagar(c, d, comanda["id"], "40", "Persona 1")
    assert r.status_code == 201, r.text
    detalle = (await c.get(f"{API}/comandas/{comanda['id']}")).json()
    assert detalle["totales"]["pagado"] == "40.00" and detalle["totales"]["vuelto"] == "0.00"


async def test_pagar_de_mas_genera_vuelto_en_la_comanda(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d, hamburguesas=1, refrescos=0)  # 10
    await _pagar(c, d, comanda["id"], "20", "Ana")
    t = (await c.get(f"{API}/comandas/{comanda['id']}")).json()["totales"]
    assert t["pendiente"] == "0.00" and t["vuelto"] == "10.00"


async def test_pago_con_etiqueta_larga_o_monto_invalido_se_rechaza(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_servida(c, d)
    assert (await _pagar(c, d, comanda["id"], "5", "x" * 61)).status_code == 422
    assert (await _pagar(c, d, comanda["id"], "0", "Ana")).status_code == 422
    assert (await _pagar(c, d, comanda["id"], "-3", "Ana")).status_code == 422
