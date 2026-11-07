from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, AnyHttpUrl, Field

from app.models import EstadoAlerta, Operacion, TipoMedio, TipoMovimiento
from app.schemas.base import (
    CantidadNoNegativa,
    CantidadPositiva,
    MontoNoNegativo,
    Nombre,
    Schema,
    TextoCorto,
)
from app.schemas.fiscal import AlicuotaIva, CodigoBarras, CodigoInterno


# ---------- Monedas ----------
class MonedaIn(Schema):
    codigo: str = Field(min_length=2, max_length=10, pattern=r"^[A-Z0-9]+$")
    nombre: str = Field(min_length=1, max_length=60)
    simbolo: str = Field(min_length=1, max_length=8)
    es_principal: bool = False
    tasa: Decimal = Field(gt=0, max_digits=18, decimal_places=6, default=Decimal(1))
    operacion: Operacion = Operacion.multiplicar
    activa: bool = True
    es_divisa: bool = False
    es_fiscal: bool = False


class MonedaUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    simbolo: str | None = Field(default=None, min_length=1, max_length=8)
    tasa: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    operacion: Operacion | None = None
    activa: bool | None = None
    es_divisa: bool | None = None
    es_fiscal: bool | None = None


class MonedaOut(Schema):
    id: int
    codigo: str
    nombre: str
    simbolo: str
    es_principal: bool
    tasa: Decimal
    operacion: Operacion
    activa: bool
    es_divisa: bool
    es_fiscal: bool
    updated_at: datetime


class MontoMoneda(Schema):
    moneda: str
    simbolo: str
    monto: Decimal


# ---------- Unidades de medida ----------
Codigo = Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[a-z0-9_]+$", description="Minúsculas, números o _")]


class UnidadIn(Schema):
    codigo: Codigo
    nombre: Nombre
    abreviatura: str = Field(min_length=1, max_length=12)
    permite_decimales: bool = True
    subunidad_abreviatura: str | None = Field(default=None, min_length=1, max_length=12)
    factor_subunidad: Decimal | None = Field(default=None, gt=1, max_digits=14, decimal_places=3)
    activa: bool = True


class UnidadUpdate(Schema):
    nombre: Nombre | None = None
    abreviatura: str | None = Field(default=None, min_length=1, max_length=12)
    permite_decimales: bool | None = None
    subunidad_abreviatura: str | None = Field(default=None, min_length=1, max_length=12)
    factor_subunidad: Decimal | None = Field(default=None, gt=1, max_digits=14, decimal_places=3)
    activa: bool | None = None


class UnidadOut(Schema):
    id: int
    codigo: str
    nombre: str
    abreviatura: str
    permite_decimales: bool
    subunidad_abreviatura: str | None
    factor_subunidad: Decimal | None
    es_base: bool
    activa: bool
    en_uso: int = Field(default=0, description="Insumos que la usan")


class PresentacionIn(Schema):
    nombre: Nombre
    cantidad: CantidadPositiva = Field(description="Cuánto trae, en la unidad del insumo (caja x24 = 24)")


class PresentacionesIn(Schema):
    presentaciones: list[PresentacionIn] = Field(max_length=20)


class PresentacionOut(Schema):
    id: int
    nombre: str
    cantidad: Decimal


# ---------- Insumos ----------
Costo = Annotated[Decimal | None, Field(ge=0, max_digits=16, decimal_places=6)]


class InsumoIn(Schema):
    nombre: Nombre
    unidad: Codigo
    activo: bool = True
    codigo: CodigoInterno = Field(default=None, description="Vacío = se genera (INS-0001)")
    codigo_barras: CodigoBarras = None
    costo_unitario: Costo = None


class InsumoUpdate(Schema):
    nombre: Nombre | None = None
    unidad: Codigo | None = None
    activo: bool | None = None
    codigo: CodigoInterno = None
    codigo_barras: CodigoBarras = None
    costo_unitario: Costo = None


class InsumoOut(Schema):
    id: int
    codigo: str
    codigo_barras: str | None
    nombre: str
    unidad: str
    activo: bool
    costo_unitario: Decimal | None = Field(default=None, description="Por unidad del insumo, en moneda principal")
    unidad_abreviatura: str
    permite_decimales: bool
    presentaciones: list[PresentacionOut] = []


# ---------- Inventario ----------
class InventarioIn(Schema):
    sucursal_id: int
    insumo_id: int
    cantidad: CantidadNoNegativa = Decimal(0)
    stock_minimo: CantidadNoNegativa = Decimal(0)


class InventarioUpdate(Schema):
    stock_minimo: CantidadNoNegativa


class MovimientoIn(Schema):
    cantidad: CantidadPositiva = Field(description="En la unidad del insumo; con presentacion_id, cantidad de envases")
    presentacion_id: int | None = None
    motivo: TextoCorto | None = None


class AjusteIn(Schema):
    """Conteo físico: fija el stock real."""

    cantidad_real: CantidadNoNegativa
    motivo: TextoCorto = Field(min_length=3)


class InventarioOut(Schema):
    id: int
    sucursal_id: int
    insumo: InsumoOut
    cantidad: Decimal
    reservado: Decimal
    disponible: Decimal
    stock_minimo: Decimal
    bajo_minimo: bool
    updated_at: datetime


class MovimientoOut(Schema):
    id: int
    tipo: TipoMovimiento
    cantidad: Decimal
    saldo: Decimal
    motivo: str | None
    usuario_id: int | None
    comanda_item_id: int | None
    created_at: datetime


class AlertaOut(Schema):
    id: int
    sucursal_id: int
    inventario_id: int
    insumo: str
    unidad: str
    cantidad: Decimal
    stock_minimo: Decimal
    mensaje: str
    estado: EstadoAlerta
    created_at: datetime
    resuelta_en: datetime | None


# ---------- Recetas ----------
class IngredienteIn(Schema):
    insumo_id: int
    cantidad: CantidadPositiva
    removible: bool = Field(default=True, description="El cliente puede pedirlo sin este ingrediente")


def _ingredientes_unicos(v: list[IngredienteIn] | None) -> list[IngredienteIn] | None:
    if v is not None and len({i.insumo_id for i in v}) != len(v):
        raise ValueError("Insumo repetido en la receta")
    return v


class RecetaIn(Schema):
    nombre: Nombre
    codigo: CodigoInterno = Field(default=None, description="Vacío = se genera (REC-0001)")
    descripcion: str | None = Field(default=None, max_length=2000)
    activa: bool = True
    ingredientes: Annotated[list[IngredienteIn], AfterValidator(_ingredientes_unicos)] = Field(min_length=1)


class RecetaUpdate(Schema):
    nombre: Nombre | None = None
    codigo: CodigoInterno = None
    descripcion: str | None = Field(default=None, max_length=2000)
    activa: bool | None = None
    ingredientes: Annotated[list[IngredienteIn] | None, AfterValidator(_ingredientes_unicos)] = Field(
        default=None, min_length=1
    )


class IngredienteOut(Schema):
    insumo_id: int
    insumo: str
    unidad: str
    cantidad: Decimal
    removible: bool = True
    costo: Decimal | None = None


class RecetaOut(Schema):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None
    activa: bool
    ingredientes: list[IngredienteOut]
    costo: Decimal | None = Field(default=None, description="null = algún insumo sin costo cargado")


# ---------- Categorías ----------
class CategoriaIn(Schema):
    nombre: str = Field(min_length=1, max_length=80)
    orden: int = 0
    activa: bool = True
    estacion_id: int | None = Field(default=None, description="Estación por defecto de sus productos nuevos")


class CategoriaUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    orden: int | None = None
    activa: bool | None = None
    estacion_id: int | None = None


class CategoriaOut(Schema):
    id: int
    nombre: str
    orden: int
    activa: bool
    estacion_id: int | None = None


# ---------- Estaciones de preparación ----------
class EstacionIn(Schema):
    nombre: str = Field(min_length=1, max_length=60)
    orden: int = 0
    activa: bool = True


class EstacionUpdate(Schema):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    orden: int | None = None
    activa: bool | None = None


class EstacionOut(Schema):
    id: int
    nombre: str
    orden: int
    activa: bool


# ---------- Productos ----------
class ProductoIn(Schema):
    nombre: Nombre
    codigo: CodigoInterno = Field(default=None, description="Vacío = se genera (PRD-0001)")
    codigo_barras: CodigoBarras = None
    descripcion: str | None = Field(default=None, max_length=2000)
    categoria_id: int | None = None
    receta_id: int | None = None
    insumo_id: int | None = Field(default=None, description="Producto de reventa: descuenta este insumo en cada venta")
    cantidad_por_venta: CantidadPositiva = Decimal(1)
    estacion_id: int | None = None
    precio_base: MontoNoNegativo
    alicuota_iva: AlicuotaIva = Decimal(16)
    orden: int = 0
    activo: bool = True


class ProductoUpdate(Schema):
    nombre: Nombre | None = None
    codigo: CodigoInterno = None
    codigo_barras: CodigoBarras = None
    descripcion: str | None = Field(default=None, max_length=2000)
    categoria_id: int | None = None
    receta_id: int | None = None
    insumo_id: int | None = None
    cantidad_por_venta: CantidadPositiva | None = None
    estacion_id: int | None = None
    precio_base: MontoNoNegativo | None = None
    alicuota_iva: AlicuotaIva | None = None
    orden: int | None = None
    activo: bool | None = None


class ProductoSucursalIn(Schema):
    precio: MontoNoNegativo | None = Field(default=None, description="null = usar precio base")
    disponible: bool = True


class ProductoSucursalOut(Schema):
    sucursal_id: int
    precio: Decimal | None
    disponible: bool


class MedioUrlIn(Schema):
    tipo: TipoMedio
    url: AnyHttpUrl
    orden: int = 0
    es_portada: bool = False
    texto_alt: TextoCorto | None = None


class MedioUpdate(Schema):
    orden: int | None = None
    es_portada: bool | None = None
    texto_alt: TextoCorto | None = None


class MedioOut(Schema):
    id: int
    tipo: TipoMedio
    url: str
    mime: str | None
    tamano_bytes: int | None
    orden: int
    es_portada: bool
    texto_alt: str | None


class ProductoOut(Schema):
    id: int
    codigo: str
    codigo_barras: str | None
    nombre: str
    descripcion: str | None
    categoria: CategoriaOut | None
    receta_id: int | None
    insumo_id: int | None
    cantidad_por_venta: Decimal
    control_stock: str = Field(description="receta | directo | ninguno")
    estacion: EstacionOut | None
    precio_base: Decimal
    alicuota_iva: Decimal
    orden: int
    activo: bool
    sucursales: list[ProductoSucursalOut]
    medios: list[MedioOut]


# ---------- Menú ----------
class MenuIngrediente(Schema):
    insumo_id: int
    nombre: str


class MenuProducto(Schema):
    id: int
    nombre: str
    descripcion: str | None
    precio: Decimal = Field(description="Lo que paga el cliente (con IVA)")
    precios: list[MontoMoneda]
    precio_sin_iva: Decimal
    alicuota_iva: Decimal
    medios: list[MedioOut]
    porciones_disponibles: int | None = Field(description="null = no controla stock (sin límite)")
    ingredientes: list[MenuIngrediente] = Field(default=[], description="Los que el cliente puede quitar")


class MenuCategoria(Schema):
    id: int | None
    nombre: str
    productos: list[MenuProducto]


class MenuOut(Schema):
    sucursal_id: int
    sucursal: str
    moneda_principal: str
    precios_incluyen_iva: bool
    monedas: list[MonedaOut]
    categorias: list[MenuCategoria]


# ---------- Búsqueda por código (reposición desde el teléfono) ----------
class InsumoEncontradoOut(Schema):
    insumo: InsumoOut
    inventario: InventarioOut | None = Field(description="null = el insumo no está en el inventario de esta sucursal")
    coincidencia: str = Field(description="codigo | codigo_barras | nombre")


class BitacoraOut(Schema):
    id: int
    created_at: datetime
    usuario_id: int | None
    usuario_nombre: str
    sucursal_id: int | None
    sucursal: str | None = None
    modulo: str
    accion: str
    descripcion: str
    entidad: str | None
    entidad_id: int | None
    datos: dict | None
    ip: str | None
