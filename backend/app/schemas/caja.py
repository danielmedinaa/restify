from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.models import EstadoTurno, MetodoPago, TipoMovimientoCaja
from app.schemas.base import MontoNoNegativo, MontoPositivo, Schema, TextoCorto


class MontoMonedaIn(Schema):
    moneda_id: int
    monto: MontoNoNegativo


class AbrirTurnoIn(Schema):
    sucursal_id: int
    fondo: list[MontoMonedaIn] = Field(default=[], max_length=10, description="Efectivo con el que arranca la gaveta")
    notas: str | None = Field(default=None, max_length=1000)


class MovimientoCajaIn(Schema):
    tipo: TipoMovimientoCaja
    moneda_id: int
    monto: MontoPositivo
    motivo: TextoCorto = Field(min_length=3)


class CerrarTurnoIn(Schema):
    contado: list[MontoMonedaIn] = Field(max_length=10, description="Efectivo contado en la gaveta, por moneda")
    notas: str | None = Field(default=None, max_length=1000)


class MontoMonedaOut(Schema):
    moneda_id: int
    moneda: str
    simbolo: str
    monto: Decimal


class MovimientoCajaOut(Schema):
    id: int
    tipo: TipoMovimientoCaja
    moneda: str
    simbolo: str
    monto: Decimal
    motivo: str
    usuario: str | None
    created_at: datetime


class CobroMetodoOut(Schema):
    metodo: MetodoPago
    moneda: str
    simbolo: str
    monto: Decimal
    cantidad: int


class EfectivoOut(Schema):
    moneda_id: int
    moneda: str
    simbolo: str
    fondo: Decimal
    cobrado: Decimal
    ingresos: Decimal
    retiros: Decimal
    vueltos: Decimal
    esperado: Decimal


class ArqueoLineaOut(Schema):
    moneda_id: int
    moneda: str
    simbolo: str
    esperado: Decimal
    contado: Decimal
    diferencia: Decimal = Field(description="contado - esperado: negativo = falta dinero")


class ResumenTurnoOut(Schema):
    ventas: int
    facturado: Decimal
    descuentos: Decimal
    propinas: Decimal
    igtf: Decimal
    vueltos: Decimal
    por_metodo: list[CobroMetodoOut]
    efectivo: list[EfectivoOut]


class TurnoOut(Schema):
    id: int
    sucursal_id: int
    sucursal: str
    estado: EstadoTurno
    abierto_por: str | None
    abierto_en: datetime
    cerrado_por: str | None
    cerrado_en: datetime | None
    fondo: list[MontoMonedaOut]
    movimientos: list[MovimientoCajaOut]
    resumen: ResumenTurnoOut
    arqueo: list[ArqueoLineaOut] | None
    notas: str | None
