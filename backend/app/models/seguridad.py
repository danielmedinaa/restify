from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.common import TimestampMixin


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # Todos los tokens de una misma sesión comparten familia: si se reutiliza uno ya rotado
    # se revoca la familia completa (detección de robo de refresh token).
    familia: Mapped[str] = mapped_column(String(32), index=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApiKey(TimestampMixin, Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    prefijo: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    ultimo_uso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"))
    metodo: Mapped[str] = mapped_column(String(10))
    ruta: Mapped[str] = mapped_column(String(255))
    status_code: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Bitacora(Base):
    """Historial legible de lo que hizo cada persona: "Ana repuso 500 g de Carne molida".

    A diferencia de la auditoría técnica (método/ruta/estado), cada entrada se escribe
    en la misma transacción que el cambio: si el cambio falla, no queda registro.
    """

    __tablename__ = "bitacora"
    __table_args__ = (Index("ix_bitacora_modulo_fecha", "modulo", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    # Nombre congelado: el registro se sigue leyendo aunque el usuario cambie de nombre o se borre
    usuario_nombre: Mapped[str] = mapped_column(String(120))
    sucursal_id: Mapped[int | None] = mapped_column(ForeignKey("sucursales.id", ondelete="SET NULL"), index=True)
    modulo: Mapped[str] = mapped_column(String(30))
    accion: Mapped[str] = mapped_column(String(40))
    descripcion: Mapped[str] = mapped_column(String(500))
    entidad: Mapped[str | None] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    datos: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))


class AlertaSeguridad(Base):
    """Comportamiento sospechoso detectado: fuerza bruta, robo de sesión, API keys falsas…"""

    __tablename__ = "alertas_seguridad"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    severidad: Mapped[str] = mapped_column(String(10))  # media | alta | critica
    titulo: Mapped[str] = mapped_column(String(160))
    detalle: Mapped[str] = mapped_column(String(500))
    ip: Mapped[str | None] = mapped_column(String(64))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    datos: Mapped[dict | None] = mapped_column(JSONB)
    revisada: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)
    revisada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
