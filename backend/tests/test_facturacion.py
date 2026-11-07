from datetime import date, datetime
from zoneinfo import ZoneInfo

API = "/api/v1"


async def _venta_cerrada(c, d, cliente_id=None) -> int:
    """Hamburguesa (10 USD, IVA 16 %) + refresco (2 USD, exento), pagada con 12,36 USD: la
    sucursal de estos tests cobra IGTF, así que el pago en divisas lleva 3 % encima."""
    r = await c.post(
        f"{API}/comandas",
        json={
            "sucursal_id": d["sucursal"]["id"],
            "cliente_id": cliente_id,
            "items": [{"producto_id": d["hamburguesa"]["id"]}, {"producto_id": d["refresco"]["id"]}],
            "enviar_a_cocina": True,
        },
    )
    assert r.status_code == 201, r.text
    comanda = r.json()
    for item in comanda["items"]:
        await c.post(f"{API}/cocina/items/{item['id']}/estado", json={"estado": "listo"})
    await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "12.36", "metodo": "efectivo"})
    r = await c.post(f"{API}/comandas/{comanda['id']}/cerrar")
    assert r.status_code == 200, r.text
    ventas = (await c.get(f"{API}/ventas")).json()["items"]
    return next(v["id"] for v in ventas if v["comanda_id"] == comanda["id"])


async def _configurar(c, d):
    r = await c.patch(
        f"{API}/sucursales/{d['sucursal']['id']}",
        json={"rif": "j-12.345.678-9", "razon_social": "Restify C.A.", "domicilio_fiscal": "Av. Principal, Caracas", "cobra_igtf": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rif"] == "J123456789"
    assert (await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"es_fiscal": True})).status_code == 200
    assert (await c.patch(f"{API}/monedas/{d['usd']['id']}", json={"es_divisa": True})).status_code == 200
    assert (await c.patch(f"{API}/productos/{d['refresco']['id']}", json={"alicuota_iva": "0"})).status_code == 200


async def test_documento_para_facturar(admin, datos):
    c, d = admin, datos
    await _configurar(c, d)
    cliente = (
        await c.post(
            f"{API}/clientes",
            json={"nombre": "Inversiones Daniel C.A.", "tipo_documento": "J", "documento": "J-40123456-7", "direccion": "Valencia"},
        )
    ).json()
    assert cliente["documento"] == "401234567"
    venta_id = await _venta_cerrada(c, d, cliente["id"])

    # La tasa se congela al cerrar: cambiarla después no altera el documento
    await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"tasa": "40"})

    r = await c.get(f"{API}/ventas/{venta_id}/fiscal")
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["emisor"]["rif"] == "J-12345678-9" and f["emisor"]["razon_social"] == "Restify C.A."
    assert f["receptor"]["rif"] == "J-40123456-7" and f["receptor"]["consumidor_final"] is False
    assert f["moneda_fiscal"] == "VES" and f["tasa_fiscal"] == "36.500000" and f["tasa_es_actual"] is False

    lineas = {l["descripcion"]: l for l in f["lineas"]}
    assert lineas["Hamburguesa"]["total"] == {"principal": "10.00", "fiscal": "365.00"}
    assert lineas["Refresco"]["exento"] is True

    iva = {r["etiqueta"]: r for r in f["resumen_iva"]}
    # 365 Bs con IVA incluido -> base 314,66 + IVA 50,34
    assert iva["IVA general 16 %"]["base_imponible"] == {"principal": "8.62", "fiscal": "314.66"}
    assert iva["IVA general 16 %"]["iva"] == {"principal": "1.38", "fiscal": "50.34"}
    assert f["exento"] == {"principal": "2.00", "fiscal": "73.00"}
    assert f["total"] == {"principal": "12.00", "fiscal": "438.00"}
    # IGTF 3 % sobre los 12 USD pagados en divisa
    assert f["igtf"]["monto"] == {"principal": "0.36", "fiscal": "13.14"}
    assert f["total_a_pagar"]["fiscal"] == "451.14"
    assert f["leyenda"].startswith("DOCUMENTO SIN VALIDEZ FISCAL")


async def test_registrar_factura_y_libro(admin, datos):
    c, d = admin, datos
    await _configurar(c, d)
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "300"})
    v1 = await _venta_cerrada(c, d)
    v2 = await _venta_cerrada(c, d)

    f = (await c.get(f"{API}/ventas/{v1}/fiscal")).json()
    assert f["receptor"]["consumidor_final"] is True
    assert any("consumidor final" in a for a in f["avisos"])
    assert (await c.get(f"{API}/ventas", params={"facturada": "false"})).json()["total"] == 2

    # El receptor exige el tipo cuando hay documento
    r = await c.put(f"{API}/ventas/{v1}/factura", json={"numero_factura": "000123", "numero_control": "00-000456", "receptor_documento": "12345678"})
    assert r.status_code == 422

    body = {
        "numero_factura": "000123",
        "numero_control": "00-000456",
        "receptor_tipo_documento": "V",
        "receptor_documento": "12.345.678",
        "receptor_razon_social": "Daniel Medina",
    }
    r = await c.put(f"{API}/ventas/{v1}/factura", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["numero_factura"] == "000123" and r.json()["receptor"]["rif"] == "V-12345678"
    assert (await c.get(f"{API}/ventas", params={"facturada": "false"})).json()["total"] == 1

    # Mismo número de factura en otra venta de la sucursal -> 409
    r = await c.put(f"{API}/ventas/{v2}/factura", json={**body, "numero_control": "00-000457"})
    assert r.status_code == 409

    hoy = date.today()
    r = await c.get(f"{API}/ventas/libro")
    assert r.status_code == 422  # sin período
    r = await c.get(f"{API}/ventas/libro", params={"fecha_desde": hoy.replace(day=1).isoformat()})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    filas = r.text.lstrip("﻿").strip().splitlines()
    assert filas[0] == "LIBRO DE VENTAS" and "RIF J-12345678-9" in filas[1]
    datos_libro = [f for f in filas if f.startswith(("0", "1", "2", "3")) or "Factura;" in f]
    assert len(datos_libro) == 1  # la única factura registrada
    assert "Factura;000123;00-000456;;V-12345678;Daniel Medina;438,00;73,00;314,66;50,34" in datos_libro[0]
    assert filas[-1].startswith("TOTALES;") and "438,00" in filas[-1]

    # Deshacer el registro la devuelve a pendientes
    r = await c.delete(f"{API}/ventas/{v1}/factura")
    assert r.status_code == 200 and r.json()["numero_factura"] is None
    assert (await c.get(f"{API}/ventas", params={"facturada": "false"})).json()["total"] == 2


async def test_validaciones_fiscales(admin, datos):
    c, d = admin, datos
    r = await c.post(f"{API}/clientes", json={"nombre": "Sin tipo", "documento": "12345678"})
    assert r.status_code == 422
    r = await c.patch(f"{API}/sucursales/{d['sucursal']['id']}", json={"rif": "ABC"})
    assert r.status_code == 422
    r = await c.patch(f"{API}/productos/{d['hamburguesa']['id']}", json={"alicuota_iva": "120"})
    assert r.status_code == 422
    # Mismo número con distinto prefijo son personas distintas
    assert (await c.post(f"{API}/clientes", json={"nombre": "A", "tipo_documento": "V", "documento": "12345678"})).status_code == 201
    assert (await c.post(f"{API}/clientes", json={"nombre": "B", "tipo_documento": "J", "documento": "12345678"})).status_code == 201
    assert (await c.post(f"{API}/clientes", json={"nombre": "C", "tipo_documento": "V", "documento": "12345678"})).status_code == 409
    # Solo una moneda fiscal
    await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"es_fiscal": True})
    await c.patch(f"{API}/monedas/{d['usd']['id']}", json={"es_fiscal": True})
    monedas = {m["codigo"]: m for m in (await c.get(f"{API}/monedas")).json()}
    assert monedas["USD"]["es_fiscal"] is True and monedas["VES"]["es_fiscal"] is False


async def test_iva_encima_y_tasa_del_pago(admin, datos):
    """Sucursal que suma el IVA encima, producto al 12 %, y la factura con la tasa a la que pagó."""
    c, d = admin, datos
    await _configurar(c, d)
    await c.patch(f"{API}/sucursales/{d['sucursal']['id']}", json={"precios_incluyen_iva": False, "cobra_igtf": False})
    await c.patch(f"{API}/productos/{d['hamburguesa']['id']}", json={"alicuota_iva": "12"})

    menu = (await c.get(f"{API}/public/sucursales/{d['sucursal']['id']}/menu")).json()
    assert menu["precios_incluyen_iva"] is False
    h = next(p for cat in menu["categorias"] for p in cat["productos"] if p["nombre"] == "Hamburguesa")
    assert (h["precio"], h["precio_sin_iva"], h["alicuota_iva"]) == ("11.20", "10.00", "12.00")

    r = await c.post(
        f"{API}/comandas",
        json={"sucursal_id": d["sucursal"]["id"], "items": [{"producto_id": d["hamburguesa"]["id"]}], "enviar_a_cocina": True},
    )
    comanda = r.json()
    assert comanda["items"][0]["precio_unitario"] == "11.20"  # caja cobra con el IVA sumado
    await c.post(f"{API}/cocina/items/{comanda['items'][0]['id']}/estado", json={"estado": "listo"})

    # Paga 5 USD; sube la tasa a 40 y paga el resto (6,20 USD = 248 Bs) en bolívares
    await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["usd"]["id"], "monto": "5", "metodo": "efectivo"})
    await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"tasa": "40"})
    r = await c.post(f"{API}/comandas/{comanda['id']}/pagos", json={"moneda_id": d["ves"]["id"], "monto": "248", "metodo": "pago_movil"})
    assert r.status_code == 201, r.text
    assert (await c.post(f"{API}/comandas/{comanda['id']}/cerrar")).status_code == 200
    await c.patch(f"{API}/monedas/{d['ves']['id']}", json={"tasa": "45"})  # cambios posteriores no afectan

    venta_id = (await c.get(f"{API}/ventas")).json()["items"][0]["id"]
    f = (await c.get(f"{API}/ventas/{venta_id}/fiscal")).json()
    assert f["tasa_fiscal"] == "40.000000"
    r12 = f["resumen_iva"][0]
    assert r12["etiqueta"] == "IVA 12 %"
    assert r12["base_imponible"] == {"principal": "10.00", "fiscal": "400.00"}
    assert r12["iva"] == {"principal": "1.20", "fiscal": "48.00"}
    assert f["total"]["fiscal"] == "448.00"


async def test_registrar_cliente_desde_la_factura(admin, datos):
    c, d = admin, datos
    await _configurar(c, d)
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "300"})
    v1 = await _venta_cerrada(c, d)
    v2 = await _venta_cerrada(c, d)

    # La comanda cerrada dice qué venta generó (caja la usa para ir a facturar)
    venta = (await c.get(f"{API}/ventas/{v1}")).json()
    assert (await c.get(f"{API}/comandas/{venta['comanda_id']}")).json()["venta_id"] == v1

    receptor = {"receptor_tipo_documento": "J", "receptor_documento": "J-50123456-1", "receptor_razon_social": "Comercial La Esquina C.A."}
    # Sin documento no se puede registrar como cliente
    r = await c.put(f"{API}/ventas/{v1}/factura", json={"numero_factura": "1", "numero_control": "00-1", "guardar_cliente": True})
    assert r.status_code == 422

    r = await c.put(f"{API}/ventas/{v1}/factura", json={"numero_factura": "1", "numero_control": "00-1", **receptor, "guardar_cliente": True})
    assert r.status_code == 200, r.text
    cliente_id = r.json()["cliente_id"]
    assert cliente_id is not None
    cliente = (await c.get(f"{API}/clientes/{cliente_id}")).json()
    assert (cliente["tipo_documento"], cliente["documento"], cliente["nombre"]) == ("J", "501234561", "Comercial La Esquina C.A.")

    # El mismo RIF en otra venta reutiliza al cliente (y completa su dirección), no lo duplica
    r = await c.put(
        f"{API}/ventas/{v2}/factura",
        json={"numero_factura": "2", "numero_control": "00-2", **receptor, "receptor_domicilio": "Maracay", "guardar_cliente": True},
    )
    assert r.json()["cliente_id"] == cliente_id
    assert (await c.get(f"{API}/clientes/{cliente_id}")).json()["direccion"] == "Maracay"
    assert (await c.get(f"{API}/clientes", params={"q": "Esquina"})).json()["total"] == 1


async def test_anulacion_con_nota_de_credito_y_cierre_del_dia(admin, datos):
    c, d = admin, datos
    await _configurar(c, d)
    await c.post(f"{API}/inventario/{d['inv_carne']['id']}/entrada", json={"cantidad": "300"})
    v1 = await _venta_cerrada(c, d)
    v2 = await _venta_cerrada(c, d)
    factura = {"numero_factura": "000900", "numero_control": "00-000900"}
    assert (await c.put(f"{API}/ventas/{v1}/factura", json=factura)).status_code == 200
    assert (await c.put(f"{API}/ventas/{v2}/factura", json={"numero_factura": "000901", "numero_control": "00-000901"})).status_code == 200

    # Sin factura no hay nada que anular
    nota = {"nota_credito_numero": "NC-001", "nota_credito_control": "00-NC001", "motivo": "Error en el monto"}
    v3 = await _venta_cerrada(c, d)
    assert (await c.put(f"{API}/ventas/{v3}/anulacion", json=nota)).status_code == 409
    assert (await c.put(f"{API}/ventas/{v1}/anulacion", json={**nota, "motivo": "x"})).status_code == 422

    r = await c.put(f"{API}/ventas/{v1}/anulacion", json=nota)
    assert r.status_code == 200, r.text
    assert r.json()["anulada_en"] and r.json()["nota_credito_numero"] == "NC-001"
    # Ya anulada, ni se anula de nuevo ni se le quita el registro sin deshacer antes
    assert (await c.put(f"{API}/ventas/{v1}/anulacion", json={**nota, "nota_credito_numero": "NC-002"})).status_code == 409
    assert (await c.delete(f"{API}/ventas/{v1}/factura")).status_code == 409
    # El mismo número de nota en otra venta -> 409
    assert (await c.put(f"{API}/ventas/{v2}/anulacion", json=nota)).status_code == 409

    # El libro lleva la factura y su nota de crédito en negativo; los totales netean
    r = await c.get(f"{API}/ventas/libro", params={"fecha_desde": date.today().replace(day=1).isoformat()})
    texto = r.text.lstrip("﻿")
    assert "Nota de crédito;NC-001;00-NC001;000900" in texto
    assert "-438,00" in texto

    # Cierre del día: la anulada no cuenta como venta
    r = await c.get(f"{API}/ventas/cierre-dia", params={"dia": datetime.now(ZoneInfo("America/Caracas")).date().isoformat(), "sucursal_id": d["sucursal"]["id"]})
    assert r.status_code == 200, r.text
    cierre = r.json()
    assert cierre["ventas"] == 2 and cierre["anuladas"] == 1, cierre
    assert cierre["facturadas"] == 1 and cierre["pendientes_facturar"] == 1
    assert cierre["total"] == "876.00" and cierre["moneda"] == "VES"
    assert cierre["iva"][0]["etiqueta"] == "IVA general 16 %"
    assert "No sustituye" in cierre["leyenda"]

    # Deshacer la anulación
    r = await c.delete(f"{API}/ventas/{v1}/anulacion")
    assert r.status_code == 200 and r.json()["anulada_en"] is None
