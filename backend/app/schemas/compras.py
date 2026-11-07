from datetime import date, datetime
from decimal import Decimal

from pydantic import EmailStr, Field

from app.schemas.base import CantidadPositiva, MontoNoNegativo, Schema, TextoCorto
from app.schemas.fiscal import Rif


class ProveedorIn(Schema):
    nombre: str = Field(min_length=1, max_length=160)
    rif: Rif = None
    telefono: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    contacto: str | None = Field(default=None, max_length=120)
    notas: str | None = Field(default=None, max_length=2000)
    activo: bool = True


class ProveedorUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=160)
    rif: Rif = None
    telefono: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    contacto: str | None = Field(default=None, max_length=120)
    notas: str | None = Field(default=None, max_length=2000)
    activo: bool | None = None


class ProveedorOut(Schema):
    id: int
    nombre: str
    rif: str | None
    telefono: str | None
    email: str | None
    contacto: str | None
    notas: str | None
    activo: bool


class CompraItemIn(Schema):
    insumo_id: int
    cantidad: CantidadPositiva = Field(description="En la unidad del insumo; con presentacion_id, cantidad de envases")
    presentacion_id: int | None = None
    subtotal: MontoNoNegativo = Field(description="Lo que costó esa línea, en la moneda de la compra")


class CompraIn(Schema):
    sucursal_id: int
    proveedor_id: int | None = None
    numero_documento: TextoCorto | None = None
    fecha: date | None = None
    moneda_id: int
    items: list[CompraItemIn] = Field(min_length=1, max_length=100)
    notas: str | None = Field(default=None, max_length=2000)


class CompraItemOut(Schema):
    insumo_id: int
    insumo: str
    codigo: str
    unidad: str
    cantidad: Decimal
    subtotal: Decimal
    costo_unitario: Decimal = Field(description="Por unidad base, en moneda principal")


class CompraOut(Schema):
    id: int
    sucursal_id: int
    sucursal: str
    proveedor_id: int | None
    proveedor: str | None
    numero_documento: str | None
    fecha: date
    moneda: str
    simbolo: str
    tasa: Decimal
    total: Decimal
    total_principal: Decimal
    notas: str | None
    items: list[CompraItemOut]
    created_at: datetime


class RentabilidadOut(Schema):
    producto_id: int
    producto: str
    codigo: str
    categoria: str | None
    precio: Decimal = Field(description="Lo que paga el cliente, con IVA")
    precio_sin_iva: Decimal
    costo: Decimal | None = Field(description="null = la receta tiene insumos sin costo cargado")
    margen: Decimal | None
    margen_pct: Decimal | None
    costo_pct: Decimal | None = Field(description="Food cost: costo / precio sin IVA")
    sin_receta: bool
    insumos_sin_costo: list[str]
