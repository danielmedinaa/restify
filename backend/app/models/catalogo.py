from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Alicuota, Cantidad, Dinero, TimestampMixin, codigo_auto, str_enum
from app.models.inventario import Insumo


class Receta(TimestampMixin, Base):
    __tablename__ = "recetas"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, server_default=codigo_auto("recetas_codigo_seq", "REC"))
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    ingredientes: Mapped[list["RecetaInsumo"]] = relationship(
        back_populates="receta", cascade="all, delete-orphan", lazy="selectin"
    )


class RecetaInsumo(Base):
    __tablename__ = "receta_insumos"
    __table_args__ = (
        UniqueConstraint("receta_id", "insumo_id"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receta_id: Mapped[int] = mapped_column(ForeignKey("recetas.id", ondelete="CASCADE"), index=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id", ondelete="RESTRICT"))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    # El cliente puede pedir el plato sin este ingrediente (sin cebolla): ahí no se descuenta
    removible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    receta: Mapped[Receta] = relationship(back_populates="ingredientes")
    insumo: Mapped[Insumo] = relationship(lazy="joined")


class Categoria(TimestampMixin, Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Estación que heredan los productos nuevos de esta categoría (Bebidas -> Barra)
    estacion_id: Mapped[int | None] = mapped_column(ForeignKey("estaciones.id", ondelete="SET NULL"))


class Estacion(TimestampMixin, Base):
    """Lugar de preparación (Cocina, Barra, Parrilla…). Cada producto se asigna a una."""

    __tablename__ = "estaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Producto(TimestampMixin, Base):
    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint("precio_base >= 0", name="precio_no_negativo"),
        CheckConstraint("alicuota_iva >= 0 AND alicuota_iva <= 100", name="alicuota_valida"),
        CheckConstraint("receta_id IS NULL OR insumo_id IS NULL", name="receta_o_insumo"),
        CheckConstraint("cantidad_por_venta > 0", name="cantidad_por_venta_positiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, server_default=codigo_auto("productos_codigo_seq", "PRD"))
    codigo_barras: Mapped[str | None] = mapped_column(String(64), unique=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias.id", ondelete="SET NULL"), index=True)
    receta_id: Mapped[int | None] = mapped_column(ForeignKey("recetas.id", ondelete="RESTRICT"), index=True)
    # Producto de reventa (Pepsi, agua): sin receta, descuenta directo de un insumo por cada venta
    insumo_id: Mapped[int | None] = mapped_column(ForeignKey("insumos.id", ondelete="RESTRICT"), index=True)
    cantidad_por_venta: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(1), server_default="1")
    # Dónde se prepara; NULL = aparece en todas las pantallas de preparación
    estacion_id: Mapped[int | None] = mapped_column(ForeignKey("estaciones.id", ondelete="SET NULL"), index=True)
    # Precio en moneda principal; cada sucursal puede sobrescribirlo
    precio_base: Mapped[Decimal] = mapped_column(Dinero)
    # Alícuota de IVA en % (0 = sin IVA). Según la sucursal, el precio la incluye o se suma encima.
    alicuota_iva: Mapped[Decimal] = mapped_column(Alicuota, default=Decimal(16), server_default="16")
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    categoria: Mapped[Categoria | None] = relationship(lazy="joined")
    estacion: Mapped[Estacion | None] = relationship(lazy="joined")
    receta: Mapped[Receta | None] = relationship(lazy="selectin")
    insumo: Mapped["Insumo | None"] = relationship(lazy="joined")
    sucursales: Mapped[list["ProductoSucursal"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def control_stock(self) -> str:
        """receta: descuenta los ingredientes · directo: descuenta su propio insumo · ninguno: no toca el inventario."""
        if self.receta_id is not None:
            return "receta"
        return "directo" if self.insumo_id is not None else "ninguno"

    def consumo(self, omitidos: set[int] | frozenset[int] = frozenset()) -> list[tuple[int, Decimal]]:
        """Qué insumos descuenta una venta de este producto: [(insumo_id, cantidad)]."""
        if self.receta is not None:
            return [(ri.insumo_id, ri.cantidad) for ri in self.receta.ingredientes if ri.insumo_id not in omitidos]
        if self.insumo_id is not None:
            return [(self.insumo_id, self.cantidad_por_venta)]
        return []

    medios: Mapped[list["ProductoMedio"]] = relationship(
        back_populates="producto",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductoMedio.orden",
    )


class ProductoSucursal(Base):
    """Configuración del producto por sucursal: precio propio y/o disponibilidad."""

    __tablename__ = "producto_sucursal"
    __table_args__ = (
        UniqueConstraint("producto_id", "sucursal_id"),
        CheckConstraint("precio IS NULL OR precio >= 0", name="precio_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="CASCADE"), index=True)
    precio: Mapped[Decimal | None] = mapped_column(Dinero)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    producto: Mapped[Producto] = relationship(back_populates="sucursales")


class TipoMedio(StrEnum):
    imagen = "imagen"
    video = "video"


class ProductoMedio(TimestampMixin, Base):
    """Fotos y videos del producto (archivo subido o URL externa)."""

    __tablename__ = "producto_medios"

    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[TipoMedio] = mapped_column(str_enum(TipoMedio))
    url: Mapped[str] = mapped_column(String(500))
    # Nombre del archivo en disco si fue subido (None si es URL externa)
    archivo: Mapped[str | None] = mapped_column(String(120))
    mime: Mapped[str | None] = mapped_column(String(60))
    tamano_bytes: Mapped[int | None] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    es_portada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    texto_alt: Mapped[str | None] = mapped_column(String(255))

    producto: Mapped[Producto] = relationship(back_populates="medios")


def precio_en_sucursal(producto: Producto, sucursal_id: int) -> Decimal:
    for ps in producto.sucursales:
        if ps.sucursal_id == sucursal_id and ps.precio is not None:
            return ps.precio
    return producto.precio_base


def precio_final(producto: Producto, sucursal) -> Decimal:
    """Lo que paga el cliente: el precio de la sucursal, más el IVA si allí no viene incluido."""
    precio = precio_en_sucursal(producto, sucursal.id)
    if sucursal.precios_incluyen_iva or not producto.alicuota_iva:
        return precio
    return (precio * (1 + producto.alicuota_iva / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def disponible_en_sucursal(producto: Producto, sucursal_id: int) -> bool:
    for ps in producto.sucursales:
        if ps.sucursal_id == sucursal_id:
            return ps.disponible
    return True
