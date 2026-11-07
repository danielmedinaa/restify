from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import Comanda
from app.services.vencimientos import cancelar_vencidas
from tests.conftest import crear_usuario, login

API = "/api/v1"
CLIENTE = {"nombre_cliente": "Ana Pérez", "telefono_cliente": "0414 123 4567"}


async def _comanda_lista(c, d, items, **extra) -> dict:
    """Comanda con todos sus platos listos, lista para cobrar."""
    r = await c.post(f"{API}/comandas", json={"sucursal_id": d["sucursal"]["id"], "items": items, "enviar_a_cocina": True, **extra})
    assert r.status_code == 201, r.text
    comanda = r.json()
    for i in comanda["items"]:
        await c.post(f"{API}/cocina/items/{i['id']}/estado", json={"estado": "listo"})
    return (await c.get(f"{API}/comandas/{comanda['id']}")).json()


async def test_turno_de_caja_y_arqueo(admin, datos):
    c, d = admin, datos
    suc = d["sucursal"]["id"]
    assert (await c.get(f"{API}/caja/turno-actual", params={"sucursal_id": suc})).json() is None

    r = await c.post(f"{API}/caja/turnos", json={"sucursal_id": suc, "fondo": [{"moneda_id": d["usd"]["id"], "monto": "20"}]})
    assert r.status_code == 201, r.text
    turno = r.json()
    assert (await c.post(f"{API}/caja/turnos", json={"sucursal_id": suc})).status_code == 409  # uno abierto por sucursal

    comanda = await _comanda_lista(c, d, [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"]}])
    await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["ves"]["id"], "monto": "36.50", "metodo": "pago_movil"})
    await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "15", "metodo": "efectivo"})
    assert (await c.post(f"{API}/comandas/{comanda['id']}/cerrar")).status_code == 200  # vuelto: 15 + 1 - 12 = 4 USD

    r = await c.post(f"{API}/caja/turnos/{turno['id']}/movimientos", json={"tipo": "retiro", "moneda_id": d["usd"]["id"], "monto": "5", "motivo": "Pago al panadero"})
    assert r.status_code == 201, r.text
    resumen = r.json()["resumen"]
    assert resumen["ventas"] == 1 and resumen["facturado"] == "12.00" and resumen["vueltos"] == "4.00"
    usd = next(e for e in resumen["efectivo"] if e["moneda"] == "USD")
    assert usd["esperado"] == "26.00"  # 20 fondo + 15 cobrado - 5 retiro - 4 vuelto
    metodos = {(m["metodo"], m["moneda"]): m["monto"] for m in resumen["por_metodo"]}
    assert metodos == {("efectivo", "USD"): "15.00", ("pago_movil", "VES"): "36.50"}

    r = await c.post(f"{API}/caja/turnos/{turno['id']}/cerrar", json={"contado": [{"moneda_id": d["usd"]["id"], "monto": "25"}]})
    assert r.status_code == 200, r.text
    arqueo = r.json()["arqueo"]
    assert arqueo[0]["esperado"] == "26.00" and arqueo[0]["contado"] == "25.00" and arqueo[0]["diferencia"] == "-1.00"
    assert (await c.post(f"{API}/caja/turnos/{turno['id']}/cerrar", json={"contado": []})).status_code == 409
    bitacora = [e["descripcion"] for e in (await c.get(f"{API}/bitacora", params={"modulo": "caja"})).json()["items"]]
    assert any("descuadre $ -1,00" in t for t in bitacora)


async def test_compras_actualizan_stock_y_costos(admin, datos):
    c, d = admin, datos
    prov = (await c.post(f"{API}/proveedores", json={"nombre": "Carnicería El Toro", "rif": "J-12345678-0"})).json()
    r = await c.post(
        f"{API}/compras",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "proveedor_id": prov["id"],
            "numero_documento": "F-998",
            "moneda_id": d["ves"]["id"],
            "items": [{"insumo_id": d["carne"]["id"], "cantidad": "1000", "subtotal": "3650"}],
        },
    )
    assert r.status_code == 201, r.text
    compra = r.json()
    assert compra["total_principal"] == "100.00" and compra["items"][0]["costo_unitario"] == "0.100000"

    inv = next(i for i in (await c.get(f"{API}/inventario")).json()["items"] if i["id"] == d["inv_carne"]["id"])
    assert Decimal(inv["cantidad"]) == 1200
    carne = next(i for i in (await c.get(f"{API}/insumos")).json() if i["id"] == d["carne"]["id"])
    assert carne["costo_unitario"] == "0.100000"

    # Sin costo del pan la receta no tiene costo; al cargarlo, sí
    receta = (await c.get(f"{API}/recetas/{d['receta']['id']}")).json()
    assert receta["costo"] is None
    await c.patch(f"{API}/insumos/{d['pan']['id']}", json={"costo_unitario": "0.5"})
    receta = (await c.get(f"{API}/recetas/{d['receta']['id']}")).json()
    assert receta["costo"] == "15.50"  # 150 g x 0,10 + 1 pan x 0,50

    filas = {f["producto"]: f for f in (await c.get(f"{API}/rentabilidad", params={"sucursal_id": d["sucursal"]["id"]})).json()}
    h = filas["Hamburguesa"]
    assert (h["precio_sin_iva"], h["costo"], h["margen"]) == ("8.62", "15.50", "-6.88")
    assert filas["Refresco"]["sin_receta"] is True


async def test_descuento_propina_y_cortesia(admin, datos):
    c, d = admin, datos
    comanda = await _comanda_lista(c, d, [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"]}])
    cid = comanda["id"]
    refresco = next(i for i in comanda["items"] if i["nombre_producto"] == "Refresco")

    assert (await c.put(f"{API}/comandas/{cid}/items/{refresco['id']}/cortesia", json={"cortesia": True})).status_code == 422  # sin motivo
    r = await c.put(f"{API}/comandas/{cid}/items/{refresco['id']}/cortesia", json={"cortesia": True, "motivo": "Cliente frecuente"})
    assert r.json()["totales"]["subtotal"] == "10.00"
    r = await c.put(f"{API}/comandas/{cid}/descuento", json={"tipo": "porcentaje", "valor": "10", "motivo": "Promo martes"})
    t = r.json()["totales"]
    assert (t["descuento"], t["facturable"]) == ("1.00", "9.00")
    r = await c.put(f"{API}/comandas/{cid}/propina", json={"porcentaje": "10"})
    t = r.json()["totales"]
    assert (t["propina"], t["total"]) == ("0.90", "9.90")

    await c.post(f"{API}/comandas/{cid}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "9.90", "metodo": "efectivo"})
    assert (await c.post(f"{API}/comandas/{cid}/cerrar")).status_code == 200
    venta = (await c.get(f"{API}/ventas")).json()["items"][0]
    assert (venta["total"], venta["descuento"], venta["propina"], venta["vuelto"]) == ("9.00", "1.00", "0.90", "0.00")
    fiscal = (await c.get(f"{API}/ventas/{venta['id']}/fiscal")).json()
    assert [l["descripcion"] for l in fiscal["lineas"]] == ["Hamburguesa"]  # la cortesía no se factura
    assert fiscal["total"]["principal"] == "9.00"


async def test_igtf_se_cobra_en_caja(admin, datos):
    c, d = admin, datos
    await c.patch(f"{API}/sucursales/{d['sucursal']['id']}", json={"cobra_igtf": True})
    await c.patch(f"{API}/monedas/{d['usd']['id']}", json={"es_divisa": True})
    comanda = await _comanda_lista(c, d, [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"]}])
    r = await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "12.36", "metodo": "efectivo"})
    t = r.json()["totales"]
    assert (r.json()["pagos"][0]["igtf"], t["igtf"], t["pendiente"]) == ("0.36", "0.36", "0.00")
    assert (await c.post(f"{API}/comandas/{comanda['id']}/cerrar")).status_code == 200
    venta = (await c.get(f"{API}/ventas")).json()["items"][0]
    assert (venta["total"], venta["igtf"]) == ("12.00", "0.36")


async def test_alertas_de_seguridad(client):
    await crear_usuario("jefe@restify.com", superadmin=True)
    for _ in range(5):
        await client.post(f"{API}/auth/login", json={"email": "jefe@restify.com", "password": "MalaClave123"})
    await crear_usuario("seg@restify.com", superadmin=True)
    t = await login(client, "seg@restify.com")
    # Reutilizar un refresh token ya rotado = posible robo de sesión
    t2 = (await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})).json()
    await client.post(f"{API}/auth/refresh", json={"refresh_token": t["refresh_token"]})

    h = {"Authorization": f"Bearer {t2['access_token']}"}
    alertas = (await client.get(f"{API}/seguridad/alertas", params={"pendientes": True}, headers=h)).json()["items"]
    tipos = {a["tipo"]: a for a in alertas}
    assert tipos["login_fallido"]["severidad"] == "alta"
    assert tipos["cuenta_bloqueada"]["severidad"] == "alta"
    assert tipos["refresh_reutilizado"]["severidad"] == "critica"

    # La reutilización revocó toda la sesión: se entra de nuevo para marcar las alertas como revisadas
    h = {"Authorization": f"Bearer {(await login(client, 'seg@restify.com'))['access_token']}"}
    assert (await client.post(f"{API}/seguridad/alertas/revisar", headers=h)).status_code == 204
    assert (await client.get(f"{API}/seguridad/alertas", params={"pendientes": True}, headers=h)).json()["total"] == 0


async def test_pedido_qr_vencido_se_cancela_solo(admin, datos):
    c, d = admin, datos
    r = await c.post(f"{API}/public/mesas/{d['qr']}/comandas", json={**CLIENTE, "items": [{"producto_id": d["refresco"]["id"]}]})
    assert r.status_code == 201
    comanda_id = (await c.get(f"{API}/comandas")).json()["items"][0]["id"]

    assert await cancelar_vencidas(15) == []  # todavía no vence
    async with SessionLocal() as s:
        await s.execute(update(Comanda).where(Comanda.id == comanda_id).values(created_at=datetime.now(UTC) - timedelta(minutes=16)))
        await s.commit()
    assert await cancelar_vencidas(15) == [comanda_id]
    comanda = (await c.get(f"{API}/comandas/{comanda_id}")).json()
    assert comanda["estado"] == "cancelada" and comanda["motivo_cancelacion"] == "Sin confirmar en 15 minutos"
    assert (await c.get(f"{API}/mesas/{d['mesa']['id']}")).json()["ocupada"] is False
    entrada = (await c.get(f"{API}/bitacora", params={"q": "nadie lo confirmó"})).json()["items"][0]
    assert entrada["usuario_nombre"] == "Sistema"


async def test_consulta_cedula_desactivada_por_defecto(admin):
    r = await admin.get(f"{API}/clientes/consulta-externa", params={"tipo": "V", "numero": "12345678"})
    assert r.status_code == 503
