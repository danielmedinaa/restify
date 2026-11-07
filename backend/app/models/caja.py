from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Dinero, str_enum
from app.models.monedas import Moneda
from app.models.usuarios import Sucursal


class EstadoTurno(StrEnum):
    abierto = "abierto"
    cerrado = "cerrado"


class TurnoCaja(Base):
    """Turno de caja: se abre con un fondo en efectivo y se cierra contando la gaveta (arqueo)."""

    __tablename__ = "turnos_caja"
    __table_args__ = (
        # Un solo turno abierto por sucursal
        Index("uq_turnos_caja_abierto", "sucursal_id", unique=True, postgresql_where=text("estado = 'abierto'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    estado: Mapped[EstadoTurno] = mapped_column(str_enum(EstadoTurno), default=EstadoTurno.abierto)
    abierto_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    abierto_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    cerrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # [{"moneda_id": 1, "monto": "50.00"}] efectivo con el que arranca la gaveta
    fondo: Mapped[list] = mapped_column(JSONB, default=list)
    # Arqueo al cerrar: [{"moneda_id", "esperado", "contado", "diferencia"}] (solo efectivo)
    arqueo: Mapped[list | None] = mapped_column(JSONB)
    notas: Mapped[str | None] = mapped_column(Text)

    sucursal: Mapped[Sucursal] = relationship(lazy="joined")
    movimientos: Mapped[list["MovimientoCaja"]] = relationship(
        back_populates="turno", lazy="selectin", order_by="MovimientoCaja.id"
    )


class TipoMovimientoCaja(StrEnum):
    ingreso = "ingreso"  # p. ej. cambio que se trae del banco
    retiro = "retiro"  # p. ej. pago a un proveedor con efectivo de la gaveta


class MovimientoCaja(Base):
    __tablename__ = "movimientos_caja"
    __table_args__ = (CheckConstraint("monto > 0", name="monto_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos_caja.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[TipoMovimientoCaja] = mapped_column(str_enum(TipoMovimientoCaja))
    moneda_id: Mapped[int] = mapped_column(ForeignKey("monedas.id", ondelete="RESTRICT"))
    monto: Mapped[Decimal] = mapped_column(Dinero)
    motivo: Mapped[str] = mapped_column(String(255))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    turno: Mapped[TurnoCaja] = relationship(back_populates="movimientos")
    moneda: Mapped[Moneda] = relationship(lazy="joined")
