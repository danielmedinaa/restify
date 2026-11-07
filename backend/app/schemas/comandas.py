from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import EmailStr, Field, model_validator

from app.models import EstadoComanda, EstadoItem, FormaMesa, MetodoPago, OrigenComanda, TipoDescuento, TipoDocumento
from app.schemas.base import MontoNoNegativo, MontoPositivo, Nombre, Schema, TextoCorto
from app.schemas.catalogo import MontoMoneda
from app.schemas.fiscal import Documento, NombrePersonaObligatorio, Telefono, TelefonoObligatorio, exigir_tipo_con_documento


# ---------- Clientes ----------
class ClienteIn(Schema):
    nombre: Nombre = Field(description="Nombre o razón social")
    tipo_documento: TipoDocumento | None = None
    documento: Documento = None
    telefono: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    direccion: TextoCorto | None = Field(default=None, description="Domicilio fiscal")
    notas: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _tipo(self):
        exigir_tipo_con_documento(self.tipo_documento, self.documento)
        return self


class ClienteUpdate(Schema):
    nombre: Nombre | None = None
    tipo_documento: TipoDocumento | None = None
    documento: Documento = None
    telefono: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    direccion: TextoCorto | None = None
    notas: str | None = Field(default=None, max_length=2000)


class ClienteOut(Schema):
    id: int
    nombre: str
    tipo_documento: TipoDocumento | None
    documento: str | None
    telefono: str | None
    email: str | None
    direccion: str | None
    notas: str | None
    created_at: datetime


class ConsultaCedulaOut(Schema):
    nombre: str
    rif: str | None
    zona: str | None = Field(description="Parroquia, municipio y estado del centro electoral (no es el domicilio)")


# ---------- Mesas ----------
PosicionPlano = Annotated[int | None, Field(ge=0, le=99, description="Celda en el plano de la sala")]


class MesaIn(Schema):
    sucursal_id: int
    nombre: str = Field(min_length=1, max_length=40)
    capacidad: int | None = Field(default=None, ge=1, le=100)
    qr_habilitado: bool = True
    activa: bool = True
    pos_x: PosicionPlano = None
    pos_y: PosicionPlano = None
    zona_id: int | None = None
    forma: FormaMesa = FormaMesa.cuadrada
    ancho: int = Field(default=3, ge=1, le=8)
    alto: int = Field(default=2, ge=1, le=8)


class MesaUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=40)
    capacidad: int | None = Field(default=None, ge=1, le=100)
    qr_habilitado: bool | None = None
    activa: bool | None = None
    pos_x: PosicionPlano = None
    pos_y: PosicionPlano = None
    zona_id: int | None = None
    forma: FormaMesa | None = None
    ancho: int | None = Field(default=None, ge=1, le=8)
    alto: int | None = Field(default=None, ge=1, le=8)


class ZonaIn(Schema):
    sucursal_id: int
    nombre: str = Field(min_length=1, max_length=60)
    orden: int = 0
    activa: bool = True


class ZonaUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    orden: int | None = None
    activa: bool | None = None


class ZonaOut(Schema):
    id: int
    sucursal_id: int
    nombre: str
    orden: int
    activa: bool


class UnirMesasIn(Schema):
    mesa_ids: list[int] = Field(min_length=1, max_length=20, description="Mesas que se suman a la principal")


class MesaOut(Schema):
    id: int
    sucursal_id: int
    nombre: str
    capacidad: int | None
    qr_habilitado: bool
    activa: bool
    pos_x: int | None = None
    pos_y: int | None = None
    zona_id: int | None = None
    forma: FormaMesa = FormaMesa.cuadrada
    ancho: int = 3
    alto: int = 2
    unida_a_id: int | None = None
    ocupada: bool = False
    comanda_abierta_id: int | None = None


class MesaQrOut(Schema):
    mesa_id: int
    url: str


# ---------- Comandas ----------

class ItemIn(Schema):
    producto_id: int
    cantidad: int = Field(default=1, ge=1, le=50)
    notas: TextoCorto | None = None
    sin_insumo_ids: list[int] = Field(default=[], max_length=30, description="Ingredientes que se quitan del plato")


class ComandaCajaIn(Schema):
    """Caja abre comanda manualmente: con mesa, o sin mesa (para llevar / barra)."""

    sucursal_id: int
    mesa_id: int | None = None
    cliente_id: int | None = None
    nombre_cliente: Nombre | None = None
    telefono_cliente: Telefono = None
    notas: str | None = Field(default=None, max_length=1000)
    items: list[ItemIn] = Field(default=[], max_length=50)
    enviar_a_cocina: bool = False


class ComandaQrIn(Schema):
    """Pedido desde el QR: nombre y teléfono reales son obligatorios para poder confirmarlo."""

    nombre_cliente: NombrePersonaObligatorio
    telefono_cliente: TelefonoObligatorio
    notas: str | None = Field(default=None, max_length=500)
    items: list[ItemIn] = Field(min_length=1, max_length=30)


class AgregarItemsIn(Schema):
    items: list[ItemIn] = Field(min_length=1, max_length=50)
    enviar_a_cocina: bool = False


class AgregarItemsPublicoIn(Schema):
    items: list[ItemIn] = Field(min_length=1, max_length=30)


class ComandaUpdate(Schema):
    mesa_id: int | None = None
    cliente_id: int | None = None
    nombre_cliente: Nombre | None = None
    telefono_cliente: Telefono = None
    notas: str | None = Field(default=None, max_length=1000)


class EnviarCocinaIn(Schema):
    item_ids: list[int] | None = Field(default=None, description="null = todos los pendientes")


class CancelarIn(Schema):
    motivo: TextoCorto = Field(min_length=3)


class SinInsumosIn(Schema):
    sin_insumo_ids: list[int] = Field(max_length=30)


class EstadoItemCocinaIn(Schema):
    estado: Literal[EstadoItem.preparando, EstadoItem.listo]


class DescuentoIn(Schema):
    """tipo null = quitar el descuento."""

    tipo: TipoDescuento | None
    valor: MontoNoNegativo | None = None
    motivo: TextoCorto | None = Field(default=None, min_length=3)

    @model_validator(mode="after")
    def _valor(self):
        if self.tipo and (self.valor is None or self.valor <= 0):
            raise ValueError("Indica el valor del descuento")
        if self.tipo and not self.motivo:
            raise ValueError("Indica el motivo del descuento")
        return self


class DescuentoOut(Schema):
    tipo: TipoDescuento
    valor: Decimal
    motivo: str | None


class PropinaIn(Schema):
    """Monto en moneda principal, o un % sobre lo facturable."""

    monto: MontoNoNegativo | None = None
    porcentaje: Decimal | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _uno(self):
        if (self.monto is None) == (self.porcentaje is None):
            raise ValueError("Indica el monto o el porcentaje de la propina")
        return self


class CortesiaIn(Schema):
    cortesia: bool = True
    motivo: TextoCorto | None = Field(default=None, min_length=3)

    @model_validator(mode="after")
    def _motivo(self):
        if self.cortesia and not self.motivo:
            raise ValueError("Indica el motivo de la cortesía")
        return self


class PagoIn(Schema):
    moneda_id: int
    monto: MontoPositivo
    metodo: MetodoPago
    referencia: str | None = Field(default=None, max_length=120)
    etiqueta: str | None = Field(default=None, max_length=60, description="Para cuentas divididas")


class PagoOut(Schema):
    id: int
    moneda: str
    monto: Decimal
    tasa: Decimal
    operacion: str
    monto_principal: Decimal
    metodo: MetodoPago
    referencia: str | None
    etiqueta: str | None
    igtf: Decimal = Field(description="IGTF incluido en este pago (moneda principal)")
    created_at: datetime


class ItemOut(Schema):
    id: int
    producto_id: int
    nombre: str = Field(description="Ej: 'Hamburguesa #2'")
    nombre_producto: str
    numero: int
    precio_unitario: Decimal
    estado: EstadoItem
    notas: str | None
    sin_insumo_ids: list[int] = []
    estacion_id: int | None = None
    agregado_por_cliente: bool
    cortesia: bool
    cortesia_motivo: str | None
    enviado_en: datetime | None
    listo_en: datetime | None
    entregado_en: datetime | None


class Totales(Schema):
    subtotal: Decimal = Field(description="Platos que se cobran (sin cortesías)")
    descuento: Decimal
    facturable: Decimal = Field(description="Subtotal - descuento: lo que se vende")
    propina: Decimal
    igtf: Decimal = Field(description="IGTF cobrado dentro de los pagos en divisas")
    total: Decimal = Field(description="Lo que paga el cliente: facturable + propina")
    pagado: Decimal
    pendiente: Decimal
    vuelto: Decimal
    total_monedas: list[MontoMoneda]
    pendiente_monedas: list[MontoMoneda]


class ComandaOut(Schema):
    id: int
    sucursal_id: int
    mesa_id: int | None
    mesa: str | None
    cliente_id: int | None
    nombre_cliente: str | None
    telefono_cliente: str | None
    origen: OrigenComanda
    estado: EstadoComanda
    notas: str | None
    seguimiento_url: str
    items: list[ItemOut]
    venta_id: int | None = None
    igtf_porcentaje: Decimal | None = None
    descuento: "DescuentoOut | None" = None
    pagos: list[PagoOut]
    totales: Totales
    created_at: datetime
    cerrada_en: datetime | None
    motivo_cancelacion: str | None


class ComandaResumenOut(Schema):
    id: int
    sucursal_id: int
    mesa_id: int | None
    mesa: str | None
    nombre_cliente: str | None
    origen: OrigenComanda
    estado: EstadoComanda
    total: Decimal
    items_pendientes: int
    items_en_cocina: int
    items_listos: int = Field(description="listos + entregados")
    items_por_servir: int = Field(description="listos que aún no se entregan")
    created_at: datetime


# ---------- Público (seguimiento del cliente) ----------
class ItemPublicoOut(Schema):
    id: int
    nombre: str
    estado: EstadoItem
    precio_unitario: Decimal
    notas: str | None


class PedidoPublicoOut(Schema):
    sucursal_id: int
    sucursal: str
    mesa: str | None
    estado: EstadoComanda
    items: list[ItemPublicoOut]
    total: Decimal
    total_monedas: list[MontoMoneda]
    progreso: dict[str, int]
    created_at: datetime


class PedidoCreadoOut(Schema):
    tracking_token: str
    seguimiento_url: str
    pedido: PedidoPublicoOut


# ---------- Cocina ----------
class CocinaItemOut(Schema):
    id: int
    nombre: str
    estado: EstadoItem
    notas: str | None
    enviado_en: datetime | None


class CocinaComandaOut(Schema):
    comanda_id: int
    mesa: str | None
    nombre_cliente: str | None
    notas: str | None
    items: list[CocinaItemOut]


# ---------- División de cuenta ----------
class GrupoDivisionIn(Schema):
    etiqueta: str = Field(min_length=1, max_length=60)
    item_ids: list[int] = Field(min_length=1)


class DivisionItemsIn(Schema):
    grupos: list[GrupoDivisionIn] = Field(min_length=1, max_length=50)


class ParteDivision(Schema):
    etiqueta: str
    monto: Decimal
    montos_monedas: list[MontoMoneda]
    pagado: Decimal
    item_ids: list[int] = []


class DivisionOut(Schema):
    total: Decimal
    pendiente: Decimal
    partes: list[ParteDivision]
    sin_asignar: Decimal = Decimal(0)


# ---------- Ventas ----------
class VentaOut(Schema):
    id: int
    comanda_id: int
    sucursal_id: int
    sucursal: str
    mesa: str | None
    cliente_id: int | None
    nombre_cliente: str | None
    total: Decimal
    pagado: Decimal
    vuelto: Decimal
    cantidad_items: int
    descuento: Decimal = Decimal(0)
    propina: Decimal = Decimal(0)
    igtf: Decimal = Decimal(0)
    created_at: datetime
    numero_factura: str | None
    numero_control: str | None
    facturada_en: datetime | None
    anulada_en: datetime | None = None


class VentaDetalleOut(VentaOut):
    comanda: ComandaOut


class ResumenPeriodo(Schema):
    periodo: str
    cantidad_ventas: int
    total: Decimal


class ResumenVentasOut(Schema):
    cantidad_ventas: int
    total: Decimal
    ticket_promedio: Decimal
    por_periodo: list[ResumenPeriodo]
    productos_top: list[dict]


# ---------- Chat mesa <-> caja ----------
class MensajeIn(Schema):
    texto: str = Field(min_length=1, max_length=500)


class MensajeOut(Schema):
    id: int
    autor: Literal["cliente", "personal"]
    autor_nombre: str | None
    texto: str
    created_at: datetime
