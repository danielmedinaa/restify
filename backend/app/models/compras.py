from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Cantidad, Dinero, Tasa, TimestampMixin
from app.models.inventario import Insumo
from app.models.monedas import Moneda
from app.models.usuarios import Sucursal


class Proveedor(TimestampMixin, Base):
    __tablename__ = "proveedores"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(160), unique=True)
    rif: Mapped[str | None] = mapped_column(String(20))
    telefono: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    contacto: Mapped[str | None] = mapped_column(String(120))
    notas: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Compra(Base):
    """Compra recibida: suma el stock de cada insumo y actualiza su costo (último costo)."""

    __tablename__ = "compras"

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id", ondelete="SET NULL"), index=True)
    numero_documento: Mapped[str | None] = mapped_column(String(60))
    fecha: Mapped[date] = mapped_column(Date)
    # Moneda en que se pagó, con su tasa congelada; el total se guarda también en principal
    moneda_id: Mapped[int] = mapped_column(ForeignKey("monedas.id", ondelete="RESTRICT"))
    tasa: Mapped[Decimal] = mapped_column(Tasa)
    total: Mapped[Decimal] = mapped_column(Dinero)
    total_principal: Mapped[Decimal] = mapped_column(Dinero)
    notas: Mapped[str | None] = mapped_column(Text)
    registrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    sucursal: Mapped[Sucursal] = relationship(lazy="joined")
    proveedor: Mapped[Proveedor | None] = relationship(lazy="joined")
    moneda: Mapped[Moneda] = relationship(lazy="joined")
    items: Mapped[list["CompraItem"]] = relationship(back_populates="compra", lazy="selectin", order_by="CompraItem.id")


class CompraItem(Base):
    __tablename__ = "compra_items"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("subtotal >= 0", name="subtotal_no_negativo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    compra_id: Mapped[int] = mapped_column(ForeignKey("compras.id", ondelete="CASCADE"), index=True)
    insumo_id: Mapped[int] = mapped_column(ForeignKey("insumos.id", ondelete="RESTRICT"))
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)  # en la unidad base del insumo
    subtotal: Mapped[Decimal] = mapped_column(Dinero)  # en la moneda de la compra

    compra: Mapped[Compra] = relationship(back_populates="items")
    insumo: Mapped[Insumo] = relationship(lazy="joined")
