from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class PosDispositivo(TimestampMixin, Base):
    """Un punto de cobro: manual (el cajero registra el pago) o conectado por API a un proveedor.

    `config` es JSON sin secretos (URL, rutas, plantillas). `secretos` es un JSON cifrado con
    las llaves y claves del proveedor: nunca se devuelve por la API, solo sus nombres.
    """

    __tablename__ = "pos_dispositivos"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL = disponible en todas las sucursales
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(10), default="manual")  # manual | api
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    config: Mapped[str | None] = mapped_column(Text)
    secretos: Mapped[str | None] = mapped_column(Text)
