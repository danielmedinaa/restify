from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Numeric, func, text
from sqlalchemy.orm import Mapped, mapped_column

# Dinero en moneda principal / secundaria
Dinero = Numeric(14, 2)
# Cantidades de insumos (g, ml, unidades)
Cantidad = Numeric(14, 3)
# Tasas de cambio
Tasa = Numeric(18, 6)
# Porcentajes de impuesto (IVA)
Alicuota = Numeric(5, 2)


def codigo_auto(secuencia: str, prefijo: str):
    """Código interno legible ("INS-0007") generado por la BD si no se escribe uno."""
    return text(f"'{prefijo}-' || lpad(nextval('{secuencia}')::text, 4, '0')")


def str_enum(enum_cls: type[StrEnum], length: int = 20) -> Enum:
    """Enum guardado como VARCHAR + CHECK (más fácil de migrar que un ENUM nativo)."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
        create_constraint=True,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


__all__ = ["Alicuota", "Cantidad", "codigo_auto", "Decimal", "Dinero", "Tasa", "TimestampMixin", "str_enum"]
