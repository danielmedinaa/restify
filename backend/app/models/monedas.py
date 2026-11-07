from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import Tasa, TimestampMixin, str_enum


class Operacion(StrEnum):
    """Cómo se obtiene el monto en esta moneda a partir de la moneda principal.

    multiplicar: monto_moneda = monto_principal * tasa   (ej. principal USD, VES tasa 36.5)
    dividir:     monto_moneda = monto_principal / tasa   (ej. principal VES, USD tasa 36.5)
    """

    multiplicar = "multiplicar"
    dividir = "dividir"


class Moneda(TimestampMixin, Base):
    __tablename__ = "monedas"
    __table_args__ = (
        CheckConstraint("tasa > 0", name="tasa_positiva"),
        # Solo una moneda principal
        Index("uq_monedas_principal", "es_principal", unique=True, postgresql_where=text("es_principal")),
        # Solo una moneda fiscal (en la que se expresa la factura: bolívares)
        Index("uq_monedas_fiscal", "es_fiscal", unique=True, postgresql_where=text("es_fiscal")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(60))
    simbolo: Mapped[str] = mapped_column(String(8))
    es_principal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    tasa: Mapped[Decimal] = mapped_column(Tasa, default=Decimal(1))
    operacion: Mapped[Operacion] = mapped_column(str_enum(Operacion), default=Operacion.multiplicar)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Moneda extranjera: los pagos en ella generan IGTF (si la sucursal lo cobra)
    es_divisa: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Moneda en la que se emite la factura ante el SENIAT (bolívares)
    es_fiscal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
