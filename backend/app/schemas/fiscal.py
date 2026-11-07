"""Tipos y respuestas de la facturación manual (el restaurante factura con talonario o
máquina fiscal; el sistema arma los datos y guarda los números que se usaron)."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from app.models import Operacion, TipoDocumento
from app.schemas.base import Schema, TextoCorto


def _normalizar_rif(v: str | None) -> str | None:
    """'j-12345678-9', 'J 12.345.678 9' -> 'J123456789'."""
    if v is None:
        return None
    limpio = re.sub(r"[\s.\-]", "", str(v)).upper()
    if limpio == "":
        return None
    if not re.fullmatch(r"[VEJGP]\d{6,10}", limpio):
        raise ValueError("RIF inválido. Ejemplo: J-12345678-9")
    return limpio


def _normalizar_documento(v: str | None) -> str | None:
    """Solo los dígitos de la cédula o el RIF, sin la letra ni separadores."""
    if v is None:
        return None
    limpio = re.sub(r"[\s.\-]", "", str(v)).upper()
    if limpio == "":
        return None
    # Si viene con la letra (V12345678) se quita: el tipo va en su propio campo
    limpio = re.sub(r"^[VEJGP]", "", limpio)
    if not re.fullmatch(r"\d{5,10}", limpio):
        raise ValueError("Documento inválido: escribe solo los números de la cédula o el RIF")
    return limpio


def _normalizar_telefono(v: str | None) -> str | None:
    """Celular venezolano en cualquier formato (0412-1234567, 412 123 4567, +58 412…) -> +584121234567.
    Un número extranjero se acepta si viene con +código de país."""
    if v is None:
        return None
    crudo = str(v).strip()
    if crudo == "":
        return None
    digitos = re.sub(r"[\s().\-]", "", crudo)
    ve = re.fullmatch(r"(?:\+?58)?0?(4(?:12|14|16|22|24|26)\d{7})", digitos)
    if ve:
        return f"+58{ve.group(1)}"
    if re.fullmatch(r"\+[1-9]\d{7,14}", digitos):
        return digitos
    raise ValueError("Teléfono inválido. Ejemplo: 0412 123 4567")


def _validar_nombre_persona(v: str | None) -> str | None:
    """Nombre real: letras (con tildes), espacios, apóstrofes, puntos o guiones; al menos 2 letras."""
    if v is None:
        return None
    limpio = re.sub(r"\s+", " ", str(v)).strip()
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .\-]{2,60}", limpio) or len(re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", limpio)) < 2:
        raise ValueError("Escribe un nombre válido (solo letras)")
    return limpio


def _normalizar_codigo(v: str | None) -> str | None:
    """Código interno: 'ins-12 ' -> 'INS-12'. Vacío = que lo genere el sistema."""
    if v is None:
        return None
    limpio = str(v).strip().upper()
    if limpio == "":
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._\-]{0,29}", limpio):
        raise ValueError("Código inválido: usa letras, números, punto, guion o guion bajo (máx. 30)")
    return limpio


def _normalizar_barras(v: str | None) -> str | None:
    if v is None:
        return None
    limpio = str(v).strip()
    if limpio == "":
        return None
    if not re.fullmatch(r"[A-Za-z0-9.\-]{4,64}", limpio):
        raise ValueError("Código de barras inválido")
    return limpio


Rif = Annotated[str | None, BeforeValidator(_normalizar_rif)]
CodigoInterno = Annotated[str | None, BeforeValidator(_normalizar_codigo)]
CodigoBarras = Annotated[str | None, BeforeValidator(_normalizar_barras)]
def _obligatorio(fn, mensaje: str):
    def validar(v):
        r = fn(v)
        if not r:
            raise ValueError(mensaje)
        return r

    return validar


Telefono = Annotated[str | None, BeforeValidator(_normalizar_telefono)]
TelefonoObligatorio = Annotated[str, BeforeValidator(_obligatorio(_normalizar_telefono, "Escribe tu teléfono"))]
NombrePersonaObligatorio = Annotated[str, BeforeValidator(_obligatorio(_validar_nombre_persona, "Escribe tu nombre"))]
Documento = Annotated[str | None, BeforeValidator(_normalizar_documento)]
AlicuotaIva = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


def formato_rif(tipo: str | None, numero: str | None) -> str | None:
    """'J', '123456789' -> 'J-12345678-9'  ·  'V', '12345678' -> 'V-12345678'."""
    if not numero:
        return None
    if tipo in ("J", "G") and len(numero) >= 9:
        return f"{tipo}-{numero[:-1]}-{numero[-1]}"
    return f"{tipo}-{numero}" if tipo else numero


def exigir_tipo_con_documento(tipo, documento) -> None:
    if documento and not tipo:
        raise ValueError("Indica el tipo de documento (V, E, J, G o P)")


# ---------- Registrar la factura hecha a mano ----------
NumeroFactura = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9\-/ ]+$")]


class FacturaIn(Schema):
    numero_factura: NumeroFactura
    numero_control: NumeroFactura
    # Receptor tal como se escribió en la factura. Vacío = consumidor final.
    receptor_tipo_documento: TipoDocumento | None = None
    receptor_documento: Documento = None
    receptor_razon_social: Annotated[str | None, Field(max_length=160)] = None
    receptor_domicilio: TextoCorto | None = None
    # Registrar (o actualizar) al receptor como cliente y asociarlo a la venta
    guardar_cliente: bool = False

    @model_validator(mode="after")
    def _tipo(self):
        exigir_tipo_con_documento(self.receptor_tipo_documento, self.receptor_documento)
        if self.guardar_cliente and not self.receptor_documento:
            raise ValueError("Para registrar al cliente hace falta su cédula o RIF")
        if self.receptor_documento and not self.receptor_razon_social:
            raise ValueError("Falta la razón social o el nombre del receptor")
        return self


class AnularFacturaIn(Schema):
    """Nota de crédito emitida a mano que anula la factura."""

    nota_credito_numero: NumeroFactura
    nota_credito_control: NumeroFactura
    motivo: Annotated[str, Field(min_length=3, max_length=255)]


# ---------- Documento para facturar ----------
class MontoFiscal(Schema):
    """Un mismo monto en la moneda principal y en la moneda fiscal (Bs)."""

    principal: Decimal
    fiscal: Decimal | None


class EmisorOut(Schema):
    nombre_comercial: str
    razon_social: str | None
    rif: str | None
    domicilio_fiscal: str | None
    telefono: str | None


class ReceptorOut(Schema):
    tipo_documento: TipoDocumento | None
    documento: str | None
    rif: str | None = Field(description="Documento con formato, p. ej. J-12345678-9")
    razon_social: str | None
    domicilio: str | None
    consumidor_final: bool


class LineaFiscalOut(Schema):
    descripcion: str
    cantidad: int
    precio_unitario: MontoFiscal
    alicuota_iva: Decimal
    exento: bool
    total: MontoFiscal


class ResumenIvaOut(Schema):
    alicuota_iva: Decimal
    etiqueta: str
    base_imponible: MontoFiscal
    iva: MontoFiscal
    total: MontoFiscal


class PagoFiscalOut(Schema):
    metodo: str
    moneda: str
    monto: Decimal
    monto_principal: Decimal
    es_divisa: bool
    referencia: str | None


class IgtfOut(Schema):
    porcentaje: Decimal
    base: MontoFiscal
    monto: MontoFiscal


class DatosFiscalesOut(Schema):
    venta_id: int
    comanda_id: int
    cliente_id: int | None = Field(description="Cliente registrado asociado a la venta")
    fecha: datetime
    mesa: str | None
    emisor: EmisorOut
    receptor: ReceptorOut
    moneda_principal: str
    moneda_fiscal: str | None
    tasa_fiscal: Decimal | None
    operacion_fiscal: Operacion | None = None
    tasa_es_actual: bool = Field(description="True si la venta es anterior a este módulo y se usa la tasa de hoy")
    lineas: list[LineaFiscalOut]
    resumen_iva: list[ResumenIvaOut]
    subtotal: MontoFiscal
    descuento: MontoFiscal
    exento: MontoFiscal
    iva: MontoFiscal
    total: MontoFiscal
    igtf: IgtfOut | None
    total_a_pagar: MontoFiscal
    pagos: list[PagoFiscalOut]
    numero_factura: str | None
    numero_control: str | None
    facturada_en: datetime | None
    anulada_en: datetime | None = None
    motivo_anulacion: str | None = None
    nota_credito_numero: str | None = None
    nota_credito_control: str | None = None
    avisos: list[str]
    leyenda: str


# ---------- Cierre del día ----------
class CierreIvaOut(Schema):
    alicuota_iva: Decimal
    etiqueta: str
    base_imponible: Decimal
    iva: Decimal


class CierreMetodoOut(Schema):
    metodo: str
    monto: Decimal


class CierreDiaOut(Schema):
    dia: date
    sucursal: str | None
    emisor: EmisorOut
    moneda: str = Field(description="Moneda en la que están los montos (la fiscal si hay tasa; si no, la principal)")
    ventas: int
    total: Decimal = Field(description="Total facturable con IVA, sin propinas")
    exento: Decimal
    iva: list[CierreIvaOut]
    igtf: Decimal
    descuentos: Decimal
    propinas: Decimal
    por_metodo: list[CierreMetodoOut]
    cortesias: int
    facturadas: int
    pendientes_facturar: int
    anuladas: int
    anuladas_total: Decimal
    leyenda: str
