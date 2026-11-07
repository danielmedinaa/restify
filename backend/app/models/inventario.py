from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Cantidad, TimestampMixin, codigo_auto, str_enum
from app.models.usuarios import Sucursal


class Unidad(StrEnum):
    g = "g"
    kg = "kg"
    ml = "ml"
    l = "l"
    unidad = "unidad"


# Unidades que vienen de fábrica: (código, nombre, abreviatura, decimales, subunidad, factor)
UNIDADES_BASE = [
    ("g", "gramos", "g", True, None, None),
    ("kg", "kilos", "kg", True, "g", 1000),
    ("ml", "mililitros", "ml", True, None, None),
    ("l", "litros", "L", True, "ml", 1000),
    ("unidad", "unidades", "u", False, None, None),
]


class UnidadMedida(TimestampMixin, Base):
    """Unidad en la que se mide un insumo. Las de fábrica ya existen; el administrador agrega las suyas.

    permite_decimales=False obliga a cantidades enteras (unidades, cajas, latas).
    subunidad_*: unidad menor para escribir cantidades chicas (1 kg = 1000 g) en las recetas.
    """

    __tablename__ = "unidades_medida"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    abreviatura: Mapped[str] = mapped_column(String(12))
    permite_decimales: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    subunidad_abreviatura: Mapped[str | None] = mapped_column(String(12))
    factor_subunidad: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    es_base: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Insumo(TimestampMixin, Base):
    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Código interno (se imprime como QR en la etiqueta) y código de barras del fabricante
    codigo: Mapped[str] = mapped_column(String(30), unique=True, server_default=codigo_auto("insumos_codigo_seq", "INS"))
    codigo_barras: Mapped[str | None] = mapped_column(String(64), unique=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    unidad: Mapped[str] = mapped_column(String(20), ForeignKey("unidades_medida.codigo", onupdate="CASCADE", ondelete="RESTRICT"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Costo por unidad base (por g, ml o unidad) en moneda principal: lo actualiza cada compra
    costo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))

    unidad_ref: Mapped[UnidadMedida] = relationship(lazy="joined")
    presentaciones: Mapped[list["Presentacion"]] = relationship(
        back_populates="insumo", cascade="all, delete-orphan", lazy="selectin", order_by="Presentacion.id"
    )

    @property
    def permite_decimales(self) -> bool:
        return self.unidad_ref.permite_decimales

    @property
    def unidad_abreviatura(self) -> str:
        return self.unidad_ref.abreviatura


class Presentacion(Base):
    """Cómo llega el insumo al comprarlo o reponerlo: "Caja x24" = 24 unidades, "Saco 50 kg" = 50 kg."""

    __tablename__ = "insumo_presentaciones"
    __table_args__ = (
        UniqueConstraint("insumo_id", "nombre"),
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)  # en la unidad del insumo

    insumo: Mapped[Insumo] = relationship(back_populates="presentaciones")


class Inventario(TimestampMixin, Base):
    """Stock de un insumo en una sucursal.

    cantidad: stock físico.  reservado: comprometido por platos enviados a cocina
    que aún no están listos.  disponible = cantidad - reservado.
    """

    __tablename__ = "inventario"
    __table_args__ = (
        UniqueConstraint("sucursal_id", "insumo_id"),
        CheckConstraint("cantidad >= 0", name="cantidad_no_negativa"),
        CheckConstraint("reservado >= 0", name="reservado_no_negativo"),
        CheckConstraint("cantidad >= reservado", name="reservado_menor_cantidad"),
        CheckConstraint("stock_minimo >= 0", name="minimo_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id", ondelete="RESTRICT"), index=True)
    cantidad: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(0))
    reservado: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(0))
    stock_minimo: Mapped[Decimal] = mapped_column(Cantidad, default=Decimal(0))

    insumo: Mapped[Insumo] = relationship(lazy="joined")
    sucursal: Mapped[Sucursal] = relationship(lazy="joined")

    @property
    def disponible(self) -> Decimal:
        return self.cantidad - self.reservado

    @property
    def bajo_minimo(self) -> bool:
        return self.cantidad <= self.stock_minimo


class TipoMovimiento(StrEnum):
    entrada = "entrada"
    ajuste = "ajuste"
    merma = "merma"
    consumo = "consumo"


class MovimientoStock(Base):
    """Kárdex: cada cambio del stock físico queda registrado."""

    __tablename__ = "movimientos_stock"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventario_id: Mapped[int] = mapped_column(ForeignKey("inventario.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[TipoMovimiento] = mapped_column(str_enum(TipoMovimiento))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)  # con signo
    saldo: Mapped[Decimal] = mapped_column(Cantidad)
    motivo: Mapped[str | None] = mapped_column(String(255))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    comanda_item_id: Mapped[int | None] = mapped_column(ForeignKey("comanda_items.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class EstadoAlerta(StrEnum):
    activa = "activa"
    resuelta = "resuelta"


class AlertaStock(Base):
    __tablename__ = "alertas_stock"
    __table_args__ = (
        # Una sola alerta activa por inventario
        Index(
            "uq_alertas_stock_activa",
            "inventario_id",
            unique=True,
            postgresql_where=text("estado = 'activa'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventario_id: Mapped[int] = mapped_column(ForeignKey("inventario.id", ondelete="CASCADE"), index=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="CASCADE"), index=True)
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    stock_minimo: Mapped[Decimal] = mapped_column(Cantidad)
    mensaje: Mapped[str] = mapped_column(String(255))
    estado: Mapped[EstadoAlerta] = mapped_column(str_enum(EstadoAlerta), default=EstadoAlerta.activa)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resuelta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inventario: Mapped[Inventario] = relationship(lazy="joined")
