from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import TimestampMixin


class Modulo(StrEnum):
    usuarios = "usuarios"
    roles = "roles"
    sucursales = "sucursales"
    monedas = "monedas"
    insumos = "insumos"
    inventario = "inventario"
    recetas = "recetas"
    categorias = "categorias"
    productos = "productos"
    clientes = "clientes"
    mesas = "mesas"
    comandas = "comandas"
    caja = "caja"
    cocina = "cocina"
    ventas = "ventas"
    bitacora = "bitacora"
    compras = "compras"


class Accion(StrEnum):
    crear = "crear"
    leer = "leer"
    editar = "editar"
    eliminar = "eliminar"


usuario_sucursal = Table(
    "usuario_sucursal",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("sucursal_id", ForeignKey("sucursales.id", ondelete="CASCADE"), primary_key=True),
)


class Sucursal(TimestampMixin, Base):
    __tablename__ = "sucursales"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    direccion: Mapped[str | None] = mapped_column(String(255))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Datos fiscales del emisor (aparecen en el documento para facturar)
    rif: Mapped[str | None] = mapped_column(String(20))
    razon_social: Mapped[str | None] = mapped_column(String(160))
    domicilio_fiscal: Mapped[str | None] = mapped_column(String(255))
    # Agente de percepción del IGTF: cobra el impuesto sobre los pagos en divisas
    cobra_igtf: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # True: el precio cargado ya trae el IVA. False: el IVA se suma encima al vender.
    precios_incluyen_iva: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Rol(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))

    permisos: Mapped[list["RolPermiso"]] = relationship(
        back_populates="rol", cascade="all, delete-orphan", lazy="selectin"
    )


class RolPermiso(Base):
    __tablename__ = "rol_permisos"
    __table_args__ = (UniqueConstraint("rol_id", "modulo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), index=True)
    modulo: Mapped[str] = mapped_column(String(40))
    crear: Mapped[bool] = mapped_column(Boolean, default=False)
    leer: Mapped[bool] = mapped_column(Boolean, default=False)
    editar: Mapped[bool] = mapped_column(Boolean, default=False)
    eliminar: Mapped[bool] = mapped_column(Boolean, default=False)

    rol: Mapped[Rol] = relationship(back_populates="permisos")


class Usuario(TimestampMixin, Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    rol_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"))
    es_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Se incrementa al cambiar contraseña/desactivar: invalida todos los access tokens emitidos
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rol: Mapped[Rol | None] = relationship(lazy="selectin")
    sucursales: Mapped[list[Sucursal]] = relationship(secondary=usuario_sucursal, lazy="selectin")

    def puede(self, modulo: Modulo | str, accion: Accion | str) -> bool:
        if self.es_superadmin:
            return True
        if not self.rol:
            return False
        for p in self.rol.permisos:
            if p.modulo == modulo:
                return bool(getattr(p, str(accion)))
        return False

    def sucursal_ids(self) -> set[int]:
        return {s.id for s in self.sucursales}

    def accede_sucursal(self, sucursal_id: int) -> bool:
        return self.es_superadmin or sucursal_id in self.sucursal_ids()
