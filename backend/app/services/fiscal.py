"""Documento para facturar a mano (talonario o máquina fiscal).

El sistema no emite la factura: arma los datos que el restaurante copia en ella
(emisor, receptor, líneas, IVA por alícuota, IGTF y total en bolívares) y luego
guarda el número de factura y de control que se usaron.

El precio congelado en cada plato es lo que pagó el cliente, con IVA (si la sucursal
suma el IVA encima, se aplicó al pedirlo): la base imponible se obtiene dividiendo.
Los montos en bolívares se calculan línea por línea (precio unitario convertido x
cantidad) y los totales son la suma de esas líneas, para que el documento cuadre
al céntimo como cuadraría una factura escrita a mano.
"""

import csv
import io
from collections import defaultdict
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import Comanda, EstadoItem, Moneda, Operacion, Venta
from app.schemas.fiscal import formato_rif
from app.services.monedas import desde_principal, q2
from app.services import config

LEYENDA = "DOCUMENTO SIN VALIDEZ FISCAL · No sustituye a la factura"
CERO = Decimal("0.00")
CIEN = Decimal(100)


def etiqueta_alicuota(alicuota: Decimal) -> str:
    if alicuota == 0:
        return "Exento"
    pct = f"{alicuota.normalize():f}"
    if alicuota == 16:
        return f"IVA general {pct} %"
    if alicuota == 8:
        return f"IVA reducido {pct} %"
    return f"IVA {pct} %"


class _Conversor:
    """Convierte de la moneda principal a la fiscal con la tasa congelada de la venta."""

    def __init__(self, tasa: Decimal | None, operacion: Operacion | None):
        self.tasa, self.operacion = tasa, operacion

    def __call__(self, monto: Decimal) -> Decimal | None:
        if self.tasa is None:
            return None
        return desde_principal(monto, self.tasa, self.operacion or Operacion.multiplicar)


def _par(principal: Decimal, fiscal: Decimal | None) -> dict:
    return {"principal": q2(principal), "fiscal": None if fiscal is None else q2(fiscal)}


def _base_e_iva(total: Decimal, alicuota: Decimal) -> tuple[Decimal, Decimal]:
    """Desglosa un total con IVA incluido en base imponible + IVA."""
    if alicuota == 0:
        return total, CERO
    base = q2(total / (1 + alicuota / CIEN))
    return base, total - base


def emisor_de(sucursal) -> dict:
    return {
        "nombre_comercial": sucursal.nombre,
        "razon_social": sucursal.razon_social,
        "rif": formato_rif(sucursal.rif[:1], sucursal.rif[1:]) if sucursal.rif else None,
        "domicilio_fiscal": sucursal.domicilio_fiscal or sucursal.direccion,
        "telefono": sucursal.telefono,
    }


def datos_fiscales(venta: Venta, comanda: Comanda, principal: Moneda, fiscal_actual: Moneda | None) -> dict:
    sucursal = comanda.sucursal
    avisos: list[str] = []

    # ---- tasa: la congelada al cerrar (la del pago en Bs). En ventas viejas sin ella se busca
    # en sus pagos en la moneda fiscal; solo si no hay ninguno se usa la de hoy.
    tasa_es_actual = False
    pago_fiscal = None
    if venta.tasa_fiscal is None and fiscal_actual is not None:
        pago_fiscal = next((p for p in reversed(comanda.pagos) if p.moneda_id == fiscal_actual.id), None)
    if venta.tasa_fiscal is not None:
        moneda_fiscal, tasa, operacion = venta.moneda_fiscal, venta.tasa_fiscal, venta.operacion_fiscal
    elif pago_fiscal is not None:
        moneda_fiscal, tasa, operacion = fiscal_actual.codigo, pago_fiscal.tasa, pago_fiscal.operacion
    elif fiscal_actual is not None:
        moneda_fiscal = fiscal_actual.codigo
        tasa = Decimal(1) if fiscal_actual.es_principal else fiscal_actual.tasa
        operacion = Operacion.multiplicar if fiscal_actual.es_principal else fiscal_actual.operacion
        tasa_es_actual = True
        avisos.append("Esta venta no tiene tasa guardada ni pagos en bolívares: se usa la tasa de hoy.")
    else:
        moneda_fiscal = tasa = operacion = None
        avisos.append("No hay moneda fiscal (bolívares) configurada: los montos se muestran solo en la moneda principal.")
    conv = _Conversor(tasa, operacion)

    # ---- líneas: platos iguales (mismo nombre, precio y alícuota) se agrupan
    grupos: dict[tuple, int] = defaultdict(int)
    for item in comanda.items:
        if item.estado == EstadoItem.entregado and not item.cortesia:  # la cortesía no se factura
            grupos[(item.nombre_producto, item.precio_unitario, item.alicuota_iva)] += 1

    lineas = []
    por_alicuota: dict[Decimal, list[Decimal | None]] = defaultdict(lambda: [CERO, CERO])
    for (nombre, precio, alicuota), cantidad in sorted(grupos.items(), key=lambda g: g[0][0]):
        unit_f = conv(precio)
        total_p = precio * cantidad
        total_f = None if unit_f is None else unit_f * cantidad
        lineas.append(
            {
                "descripcion": nombre,
                "cantidad": cantidad,
                "precio_unitario": _par(precio, unit_f),
                "alicuota_iva": alicuota,
                "exento": alicuota == 0,
                "total": _par(total_p, total_f),
            }
        )
        acum = por_alicuota[alicuota]
        acum[0] += total_p
        acum[1] = None if total_f is None or acum[1] is None else acum[1] + total_f

    # ---- descuento: se reparte en proporción entre las alícuotas
    descuento_p = venta.descuento or CERO
    descuento_f = None if tasa is None else CERO
    if descuento_p > 0:
        bruto_p = sum((v[0] for v in por_alicuota.values()), CERO)
        factor = (bruto_p - descuento_p) / bruto_p if bruto_p else Decimal(1)
        bruto_f = None if tasa is None else sum((v[1] for v in por_alicuota.values()), CERO)
        for v in por_alicuota.values():
            v[0] = q2(v[0] * factor)
            if v[1] is not None:
                v[1] = q2(v[1] * factor)
        # El redondeo de cada grupo no debe mover el total: lo absorbe el grupo mayor
        mayor = max(por_alicuota.values(), key=lambda v: v[0])
        mayor[0] += (bruto_p - descuento_p) - sum((v[0] for v in por_alicuota.values()), CERO)
        if bruto_f is not None:
            descuento_f = bruto_f - sum((v[1] for v in por_alicuota.values()), CERO)

    # ---- resumen por alícuota (base imponible + IVA en cada moneda)
    resumen = []
    subtotal_p = iva_p = exento_p = CERO
    subtotal_f = iva_f = exento_f = None if tasa is None else CERO
    for alicuota in sorted(por_alicuota, reverse=True):
        total_p, total_f = por_alicuota[alicuota]
        base_p, iva_a_p = _base_e_iva(total_p, alicuota)
        base_f, iva_a_f = _base_e_iva(total_f, alicuota) if total_f is not None else (None, None)
        resumen.append(
            {
                "alicuota_iva": alicuota,
                "etiqueta": etiqueta_alicuota(alicuota),
                "base_imponible": _par(base_p, base_f),
                "iva": _par(iva_a_p, iva_a_f),
                "total": _par(total_p, total_f),
            }
        )
        if alicuota == 0:
            exento_p += total_p
            exento_f = None if exento_f is None else exento_f + total_f
        else:
            subtotal_p += base_p
            iva_p += iva_a_p
            if subtotal_f is not None:
                subtotal_f += base_f
                iva_f += iva_a_f

    total_p = subtotal_p + iva_p + exento_p
    total_f = None if subtotal_f is None else subtotal_f + iva_f + exento_f

    # ---- IGTF: el que se cobró en caja dentro de cada pago en divisas. En ventas anteriores a
    # que caja lo cobrara, se calcula como referencia sobre lo pagado en divisas.
    igtf = None
    total_pagar_p, total_pagar_f = total_p, total_f
    if sucursal.cobra_igtf:
        pct = config.get("igtf_porcentaje")
        cobrado = venta.igtf or CERO
        if cobrado > 0:
            base_igtf_p = sum((p.monto_principal - p.igtf for p in comanda.pagos if p.igtf), CERO)
            monto_p = cobrado
        else:
            base_igtf_p = min(sum((p.monto_principal for p in comanda.pagos if p.moneda.es_divisa), CERO), total_p)
            monto_p = q2(base_igtf_p * pct / CIEN)
            if monto_p > 0:
                avisos.append("Venta anterior al cobro de IGTF en caja: el IGTF se muestra como referencia.")
        base_igtf_f = conv(base_igtf_p)
        monto_f = None if base_igtf_f is None else q2(base_igtf_f * pct / CIEN)
        igtf = {"porcentaje": pct, "base": _par(base_igtf_p, base_igtf_f), "monto": _par(monto_p, monto_f)}
        total_pagar_p += monto_p
        total_pagar_f = None if total_f is None or monto_f is None else total_f + monto_f

    # ---- receptor: el registrado en la factura, o el cliente de la comanda
    if venta.numero_factura:
        tipo, doc = venta.receptor_tipo_documento, venta.receptor_documento
        razon, domicilio = venta.receptor_razon_social, venta.receptor_domicilio
    elif comanda.cliente:
        c = comanda.cliente
        tipo, doc, razon, domicilio = c.tipo_documento, c.documento, c.nombre, c.direccion
    else:
        tipo = doc = domicilio = None
        razon = comanda.nombre_cliente
    consumidor_final = not doc
    if consumidor_final:
        avisos.append("Sin documento del cliente: se factura como consumidor final.")
    if not sucursal.rif or not sucursal.razon_social:
        avisos.append("Faltan los datos fiscales de la sucursal (RIF y razón social). Cárgalos en Sucursales.")

    return {
        "venta_id": venta.id,
        "comanda_id": comanda.id,
        "fecha": venta.created_at,
        "mesa": comanda.mesa.nombre if comanda.mesa else None,
        "emisor": emisor_de(sucursal),
        "receptor": {
            "tipo_documento": tipo,
            "documento": doc,
            "rif": formato_rif(tipo, doc),
            "razon_social": razon,
            "domicilio": domicilio,
            "consumidor_final": consumidor_final,
        },
        "moneda_principal": principal.codigo,
        "moneda_fiscal": moneda_fiscal,
        "tasa_fiscal": tasa,
        "operacion_fiscal": operacion,
        "tasa_es_actual": tasa_es_actual,
        "lineas": lineas,
        "resumen_iva": resumen,
        "subtotal": _par(subtotal_p, subtotal_f),
        "descuento": _par(descuento_p, descuento_f),
        "exento": _par(exento_p, exento_f),
        "iva": _par(iva_p, iva_f),
        "total": _par(total_p, total_f),
        "igtf": igtf,
        "total_a_pagar": _par(total_pagar_p, total_pagar_f),
        "pagos": [
            {
                "metodo": p.metodo.value,
                "moneda": p.moneda.codigo,
                "monto": p.monto,
                "monto_principal": p.monto_principal,
                "es_divisa": p.moneda.es_divisa,
                "referencia": p.referencia,
            }
            for p in comanda.pagos
        ],
        "cliente_id": venta.cliente_id,
        "numero_factura": venta.numero_factura,
        "numero_control": venta.numero_control,
        "facturada_en": venta.facturada_en,
        "anulada_en": venta.anulada_en,
        "motivo_anulacion": venta.motivo_anulacion,
        "nota_credito_numero": venta.nota_credito_numero,
        "nota_credito_control": venta.nota_credito_control,
        "avisos": avisos,
        "leyenda": LEYENDA,
    }


def _num(v: Decimal | None) -> str:
    """Formato de Excel en español: coma decimal, sin separador de miles."""
    return "" if v is None else f"{v:.2f}".replace(".", ",")


def _clave(d: dict) -> str:
    return "fiscal" if d["moneda_fiscal"] else "principal"


def _filas_libro(filas: list[dict]) -> list[dict]:
    """Una fila por factura y, si fue anulada, otra por su nota de crédito con los montos en negativo."""
    tz = ZoneInfo(config.get("timezone"))
    salida = []
    for d in filas:
        clave = _clave(d)
        por = {r["alicuota_iva"]: r for r in d["resumen_iva"]}

        def campo(alicuota, nombre, signo=1):
            r = por.get(Decimal(alicuota))
            return (r[nombre][clave] if r else CERO) * signo

        def fila(tipo, fecha, numero, control, afectada, signo):
            return {
                "fecha": fecha.astimezone(tz).strftime("%d/%m/%Y"),
                "tipo": tipo,
                "numero": numero,
                "control": control,
                "afectada": afectada,
                "rif": d["receptor"]["rif"] or "Consumidor final",
                "razon": d["receptor"]["razon_social"] or "",
                "total": d["total"][clave] * signo,
                "exento": d["exento"][clave] * signo,
                "base16": campo(16, "base_imponible", signo),
                "iva16": campo(16, "iva", signo),
                "base8": campo(8, "base_imponible", signo),
                "iva8": campo(8, "iva", signo),
                "igtf": (d["igtf"]["monto"][clave] if d["igtf"] else CERO) * signo,
                "venta": d["venta_id"],
            }

        salida.append(fila("Factura", d["fecha"], d["numero_factura"], d["numero_control"], "", 1))
        if d.get("anulada_en"):
            salida.append(
                fila("Nota de crédito", d["anulada_en"], d["nota_credito_numero"], d["nota_credito_control"], d["numero_factura"], -1)
            )
    return salida


def libro_ventas_csv(filas: list[dict], moneda: str, periodo: str = "") -> str:
    """Libro de ventas para el contador: facturas y notas de crédito, con encabezado y totales.

    Es una ayuda para llevar el libro; el contador es quien responde por él ante el SENIAT.
    """
    buf = io.StringIO()
    buf.write("﻿")  # BOM: Excel abre el UTF-8 con tildes correctas
    w = csv.writer(buf, delimiter=";")
    emisor = filas[0]["emisor"] if filas else {}
    w.writerow(["LIBRO DE VENTAS"])
    w.writerow([emisor.get("razon_social") or emisor.get("nombre_comercial") or "", f"RIF {emisor.get('rif') or '—'}"])
    w.writerow([f"Período: {periodo}", f"Montos en {moneda}"])
    w.writerow([])
    w.writerow(
        [
            "Fecha",
            "Tipo",
            "N° documento",
            "N° control",
            "N° factura afectada",
            "RIF / C.I. receptor",
            "Razón social",
            f"Total con IVA ({moneda})",
            "Ventas exentas",
            "Base 16 %",
            "IVA 16 %",
            "Base 8 %",
            "IVA 8 %",
            "IGTF",
            "Venta #",
        ]
    )
    campos = ["total", "exento", "base16", "iva16", "base8", "iva8", "igtf"]
    totales = dict.fromkeys(campos, CERO)
    for f in _filas_libro(filas):
        for c in campos:
            totales[c] += f[c]
        w.writerow(
            [f["fecha"], f["tipo"], f["numero"], f["control"], f["afectada"], f["rif"], f["razon"], *(_num(f[c]) for c in campos), f["venta"]]
        )
    w.writerow(["TOTALES", "", "", "", "", "", "", *(_num(totales[c]) for c in campos)])
    return buf.getvalue()


def cierre_dia(filas: list[dict], ventas: list[Venta], dia, sucursal: str | None, emisor: dict, moneda_principal: str) -> dict:
    """Resumen administrativo de las ventas de un día: lo que se cuenta al cerrar la caja."""
    moneda = next((f["moneda_fiscal"] for f in filas if f["moneda_fiscal"]), moneda_principal)
    iva: dict[Decimal, dict] = {}
    metodos: dict[str, Decimal] = defaultdict(Decimal)
    total = exento = igtf = descuentos = propinas = anuladas_total = CERO
    cortesias = facturadas = anuladas = 0
    for d, v in zip(filas, ventas):
        clave = _clave(d)
        if v.anulada_en:
            anuladas += 1
            anuladas_total += d["total"][clave]
            continue  # una venta anulada no cuenta como venta del día
        total += d["total"][clave]
        exento += d["exento"][clave]
        if d["igtf"]:
            igtf += d["igtf"]["monto"][clave]
        descuentos += d["descuento"][clave]
        propinas += v.propina if clave == "principal" else (_a_fiscal(v.propina, d) or CERO)
        facturadas += 1 if v.numero_factura else 0
        for r in d["resumen_iva"]:
            if r["alicuota_iva"] == 0:
                continue
            fila = iva.setdefault(r["alicuota_iva"], {"alicuota_iva": r["alicuota_iva"], "etiqueta": r["etiqueta"], "base_imponible": CERO, "iva": CERO})
            fila["base_imponible"] += r["base_imponible"][clave]
            fila["iva"] += r["iva"][clave]
        for p in d["pagos"]:
            metodos[p["metodo"]] += _a_fiscal(p["monto_principal"], d) or CERO
        cortesias += sum(1 for i in v.comanda.items if i.cortesia and i.estado in (EstadoItem.listo, EstadoItem.entregado))
    vigentes = len(filas) - anuladas
    return {
        "dia": dia,
        "sucursal": sucursal,
        "emisor": emisor,
        "moneda": moneda,
        "ventas": vigentes,
        "total": q2(total),
        "exento": q2(exento),
        "iva": [{**f, "base_imponible": q2(f["base_imponible"]), "iva": q2(f["iva"])} for _, f in sorted(iva.items())],
        "igtf": q2(igtf),
        "descuentos": q2(descuentos),
        "propinas": q2(propinas),
        "por_metodo": [{"metodo": m, "monto": q2(x)} for m, x in sorted(metodos.items())],
        "cortesias": cortesias,
        "facturadas": facturadas,
        "pendientes_facturar": vigentes - facturadas,
        "anuladas": anuladas,
        "anuladas_total": q2(anuladas_total),
        "leyenda": "REPORTE ADMINISTRATIVO · No sustituye el Reporte Z de la máquina fiscal ni el libro de ventas",
    }


def _a_fiscal(monto_principal: Decimal, d: dict) -> Decimal | None:
    """Monto de la moneda principal expresado en la moneda del documento (la fiscal si la hay)."""
    if not d["moneda_fiscal"] or d["tasa_fiscal"] is None:
        return monto_principal
    return desde_principal(monto_principal, d["tasa_fiscal"], d.get("operacion_fiscal") or Operacion.multiplicar)
