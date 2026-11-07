from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

# ---------------------------------------------------------------- permisos (igual que Restify)

MODULOS = {
    "clientes": "Clientes",
    "suscripciones": "Suscripciones",
    "instancias": "Instancias y dominios",
    "planes": "Planes",
    "usuarios": "Administradores",
    "roles": "Roles",
    "auditoria": "Auditoría",
}
ACCIONES = ("crear", "leer", "editar", "eliminar")

# Estados de la suscripción y qué significa cada uno para la instancia
ESTADOS = {
    "pendiente": "Pendiente",
    "activa": "Activa",
    "pausada": "Pausada",  # a pedido del cliente: instancia detenida, datos intactos
    "suspendida": "Suspendida",  # por impago o abuso: acceso bloqueado, datos intactos
    "cancelada": "Cancelada",  # baja: la instancia se elimina tras el período de retención
}
ESTADOS_CON_ACCESO = {"activa"}
TRANSICIONES = {
    "pendiente": {"activa", "cancelada"},
    "activa": {"pausada", "suspendida", "cancelada"},
    "pausada": {"activa", "suspendida", "cancelada"},
    "suspendida": {"activa", "cancelada"},
    "cancelada": set(),
}

ESTADOS_INFRA = ("sin_crear", "creando", "en_linea", "detenida", "error", "eliminada")

# Límites que controla un plan. None = ilimitado
LIMITES = {
    "max_sucursales": "Sucursales",
    "max_salas": "Salas",
    "max_mesas": "Mesas",
    "max_productos": "Productos",
    "max_usuarios": "Usuarios",
}


def ahora() -> datetime:
    return datetime.now(UTC)


class FechaUTC(TypeDecorator):
    """DateTime que siempre vuelve con zona UTC (SQLite la pierde al guardar)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valor, dialecto):
        return valor.astimezone(UTC) if valor is not None else None

    def process_result_value(self, valor, dialecto):
        if valor is None:
            return None
        return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


class Marcas:
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora, onupdate=ahora)


class Rol(Marcas, db.Model):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(200))
    permisos: Mapped[dict] = mapped_column(JSON, default=dict)  # {"clientes": ["leer", "editar"], ...}
    # El rol de sistema (superadmin) no se edita ni se borra desde el panel
    es_sistema: Mapped[bool] = mapped_column(Boolean, default=False)

    usuarios = relationship("Admin", back_populates="rol")

    def puede(self, modulo: str, accion: str) -> bool:
        return self.es_sistema or accion in (self.permisos or {}).get(modulo, [])


class Admin(Marcas, db.Model):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # 2FA obligatorio. El secreto va cifrado; ultimo_paso evita reusar un código ya usado.
    totp_secreto: Mapped[str | None] = mapped_column(String(255))
    totp_confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_ultimo_paso: Mapped[int] = mapped_column(Integer, default=0)
    codigos_recuperacion: Mapped[list] = mapped_column(JSON, default=list)  # hashes sha256

    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(FechaUTC())
    # Subirlo invalida al instante todas las sesiones (cambio de clave, rol o desactivación)
    version_sesion: Mapped[int] = mapped_column(Integer, default=1)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=False)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(FechaUTC())

    rol = relationship("Rol", back_populates="usuarios")

    def puede(self, modulo: str, accion: str) -> bool:
        return self.activo and self.rol.puede(modulo, accion)


class Plan(Marcas, db.Model):
    __tablename__ = "planes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    precio_mensual: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)  # archivado = no se ofrece a nuevos clientes

    max_sucursales: Mapped[int | None] = mapped_column(Integer)
    max_salas: Mapped[int | None] = mapped_column(Integer)
    max_mesas: Mapped[int | None] = mapped_column(Integer)
    max_productos: Mapped[int | None] = mapped_column(Integer)
    max_usuarios: Mapped[int | None] = mapped_column(Integer)

    suscripciones = relationship("Suscripcion", back_populates="plan")

    __table_args__ = tuple(
        CheckConstraint(f"{c} IS NULL OR {c} >= 0", name=f"ck_planes_{c}") for c in LIMITES
    ) + (CheckConstraint("precio_mensual >= 0", name="ck_planes_precio"),)


class Cliente(Marcas, db.Model):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))  # nombre comercial
    razon_social: Mapped[str | None] = mapped_column(String(160))
    rif: Mapped[str | None] = mapped_column(String(20), unique=True)
    contacto: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    telefono: Mapped[str | None] = mapped_column(String(30))
    notas: Mapped[str | None] = mapped_column(Text)

    suscripciones = relationship("Suscripcion", back_populates="cliente", order_by="Suscripcion.id")


class Suscripcion(Marcas, db.Model):
    __tablename__ = "suscripciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="RESTRICT"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("planes.id", ondelete="RESTRICT"))
    estado: Mapped[str] = mapped_column(String(12), default="pendiente")
    motivo_estado: Mapped[str | None] = mapped_column(String(300))
    estado_desde: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    vence_en: Mapped[datetime | None] = mapped_column(FechaUTC())  # fin del período pagado

    # Ajustes a la medida que reemplazan al límite del plan. NULL = usar el del plan
    # (para dar "ilimitado" a un cliente en particular pon un valor muy alto o usa un plan aparte)
    ajuste_max_sucursales: Mapped[int | None] = mapped_column(Integer)
    ajuste_max_salas: Mapped[int | None] = mapped_column(Integer)
    ajuste_max_mesas: Mapped[int | None] = mapped_column(Integer)
    ajuste_max_productos: Mapped[int | None] = mapped_column(Integer)
    ajuste_max_usuarios: Mapped[int | None] = mapped_column(Integer)

    cliente = relationship("Cliente", back_populates="suscripciones")
    plan = relationship("Plan", back_populates="suscripciones")
    instancia = relationship("Instancia", back_populates="suscripcion", uselist=False, cascade="all, delete-orphan")

    def limite(self, nombre: str) -> int | None:
        ajuste = getattr(self, f"ajuste_{nombre}")
        return ajuste if ajuste is not None else getattr(self.plan, nombre)

    def limites(self) -> dict:
        return {n: self.limite(n) for n in LIMITES}


class Instancia(Marcas, db.Model):
    __tablename__ = "instancias"

    id: Mapped[int] = mapped_column(primary_key=True)
    suscripcion_id: Mapped[int] = mapped_column(ForeignKey("suscripciones.id", ondelete="CASCADE"), unique=True)
    subdominio: Mapped[str] = mapped_column(String(32), unique=True)
    estado_infra: Mapped[str] = mapped_column(String(12), default="sin_crear")
    error_infra: Mapped[str | None] = mapped_column(String(500))

    dominio_propio: Mapped[str | None] = mapped_column(String(253), unique=True)
    dominio_token: Mapped[str | None] = mapped_column(String(64))
    dominio_verificado: Mapped[bool] = mapped_column(Boolean, default=False)

    # La instancia consulta su estado y límites con este token (solo se guarda el hash)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_prefijo: Mapped[str] = mapped_column(String(10))
    ultima_consulta: Mapped[datetime | None] = mapped_column(FechaUTC())

    suscripcion = relationship("Suscripcion", back_populates="instancia")


class Evento(db.Model):
    """Auditoría encadenada: cada fila incluye el hash de la anterior, así que borrar o
    editar una se nota al verificar la cadena."""

    __tablename__ = "eventos"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id", ondelete="SET NULL"))
    admin_email: Mapped[str | None] = mapped_column(String(254))
    accion: Mapped[str] = mapped_column(String(60), index=True)
    entidad: Mapped[str | None] = mapped_column(String(30))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    hash_prev: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Intento(db.Model):
    """Registro para limitar peticiones por IP/cuenta (sirve con varios workers)."""

    __tablename__ = "intentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(80), index=True)
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora, index=True)
