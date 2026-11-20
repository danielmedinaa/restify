from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class Plugin(TimestampMixin, Base):
    """Un plugin instalado: su manifiesto firmado, los permisos que el administrador aprobó y su token."""

    __tablename__ = "plugins"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(20))
    autor: Mapped[str] = mapped_column(String(80))
    manifiesto: Mapped[str] = mapped_column(Text)  # JSON canónico tal como se firmó
    firma: Mapped[str | None] = mapped_column(Text)
    huella: Mapped[str] = mapped_column(String(64))  # sha256 del manifiesto canónico
    firmado: Mapped[bool] = mapped_column(Boolean, default=False)
    permisos_aprobados: Mapped[str] = mapped_column(Text, default="[]")  # JSON: lista de "modulo:accion"
    # El token se guarda solo como hash; el valor se muestra una vez al instalar o rotar
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_prefijo: Mapped[str] = mapped_column(String(12))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    instalado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
