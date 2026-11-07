from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.common import Alicuota, Cantidad, Dinero, Tasa, TimestampMixin, str_enum
from app.models.monedas import Moneda, Operacion
from app.models.usuarios import Sucursal


class TipoDocumento(StrEnum):
    """Prefijo de la cédula o el RIF venezolano."""

    V = "V"  # venezolano
    E = "E"  # extranjero residente
    J = "J"  # persona jurídica
    G = "G"  # gobierno
    P = "P"  # pasaporte


class Cliente(TimestampMixin, Base):
    __tablename__ = "clientes"
    __table_args__ = (
        # V-12345678 y J-12345678 son personas distintas. Los clientes sin documento no chocan
        # entre sí (NULL es distinto de NULL); la API exige el tipo cuando hay documento.
        UniqueConstraint("tipo_documento", "documento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nombre o razón social (es lo que va en la factura)
    nombre: Mapped[str] = mapped_column(String(120), index=True)
    tipo_documento: Mapped[TipoDocumento | None] = mapped_column(str_enum(TipoDocumento, length=1))
    documento: Mapped[str | None] = mapped_column(String(40))
    telefono: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    direccion: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)


class Zona(TimestampMixin, Base):
    """Área de la sala (Salón, Terraza, Piso 2…). Cada zona tiene su propio plano."""

    __tablename__ = "zonas"
    __table_args__ = (UniqueConstraint("sucursal_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(60))
    orden: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class FormaMesa(StrEnum):
    cuadrada = "cuadrada"
    redonda = "redonda"
    rectangular = "rectangular"


class Mesa(TimestampMixin, Base):
    __tablename__ = "mesas"
    __table_args__ = (UniqueConstraint("sucursal_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    nombre: Mapped[str] = mapped_column(String(40))
    capacidad: Mapped[int | None] = mapped_column(Integer)
    # Token opaco del QR. El QR es opcional: si qr_habilitado=False solo caja abre comandas.
    qr_token: Mapped[str] = mapped_column(String(64), unique=True)
    qr_habilitado: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Posición en el plano de la sala (celdas de una grilla). NULL = sin ubicar.
    pos_x: Mapped[int | None] = mapped_column(Integer)
    pos_y: Mapped[int | None] = mapped_column(Integer)
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zonas.id", ondelete="SET NULL"), index=True)
    forma: Mapped[FormaMesa] = mapped_column(str_enum(FormaMesa), default=FormaMesa.cuadrada, server_default="cuadrada")
    # Tamaño en celdas del plano (grilla de 12 columnas)
    ancho: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    alto: Mapped[int] = mapped_column(Integer, default=2, server_default="2")
    # Mesa unida a otra (grupo grande): la comanda vive en la principal
    unida_a_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id", ondelete="SET NULL"), index=True)

    sucursal: Mapped[Sucursal] = relationship(lazy="joined")


class TipoDescuento(StrEnum):
    porcentaje = "porcentaje"
    monto = "monto"


class OrigenComanda(StrEnum):
    qr = "qr"
    caja = "caja"


class EstadoComanda(StrEnum):
    abierta = "abierta"
    cerrada = "cerrada"
    cancelada = "cancelada"


class Comanda(TimestampMixin, Base):
    __tablename__ = "comandas"
    __table_args__ = (
        # Bloqueo de mesa garantizado por la BD: una sola comanda abierta por mesa
        Index(
            "uq_comandas_mesa_abierta",
            "mesa_id",
            unique=True,
            postgresql_where=text("estado = 'abierta' AND mesa_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    mesa_id: Mapped[int | None] = mapped_column(ForeignKey("mesas.id", ondelete="RESTRICT"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id", ondelete="SET NULL"), index=True)
    nombre_cliente: Mapped[str | None] = mapped_column(String(120))
    # Teléfono que deja el cliente al pedir por QR (para confirmar el pedido)
    telefono_cliente: Mapped[str | None] = mapped_column(String(20))
    origen: Mapped[OrigenComanda] = mapped_column(str_enum(OrigenComanda))
    estado: Mapped[EstadoComanda] = mapped_column(
        str_enum(EstadoComanda), default=EstadoComanda.abierta, index=True
    )
    tracking_token: Mapped[str] = mapped_column(String(64), unique=True)
    notas: Mapped[str | None] = mapped_column(Text)
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    cerrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    cerrada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelacion: Mapped[str | None] = mapped_column(String(255))
    # Descuento sobre el total: un % o un monto en moneda principal
    descuento_tipo: Mapped[TipoDescuento | None] = mapped_column(str_enum(TipoDescuento))
    descuento_valor: Mapped[Decimal | None] = mapped_column(Dinero)
    descuento_motivo: Mapped[str | None] = mapped_column(String(255))
    # Propina (moneda principal): se cobra aparte y no es venta del restaurante
    propina: Mapped[Decimal] = mapped_column(Dinero, default=Decimal(0), server_default="0")

    sucursal: Mapped[Sucursal] = relationship(lazy="joined")
    mesa: Mapped[Mesa | None] = relationship(lazy="joined")
    cliente: Mapped[Cliente | None] = relationship(lazy="joined")
    items: Mapped[list["ComandaItem"]] = relationship(
        back_populates="comanda", lazy="selectin", order_by="ComandaItem.id"
    )
    pagos: Mapped[list["Pago"]] = relationship(back_populates="comanda", lazy="selectin", order_by="Pago.id")
    # La venta que generó al cerrarse (la crea cerrar_comanda)
    venta: Mapped["Venta | None"] = relationship(back_populates="comanda", lazy="selectin")


class EstadoItem(StrEnum):
    pendiente = "pendiente"  # esperando aprobación de caja
    en_cocina = "en_cocina"  # enviado a cocina, stock reservado
    preparando = "preparando"
    listo = "listo"  # stock descontado
    entregado = "entregado"
    cancelado = "cancelado"


ESTADOS_ACTIVOS_COCINA = (EstadoItem.en_cocina, EstadoItem.preparando)
ESTADOS_FACTURABLES = (EstadoItem.listo, EstadoItem.entregado)


class ComandaItem(TimestampMixin, Base):
    """Una unidad de un producto (2 hamburguesas = 2 items), para seguir cada plato."""

    __tablename__ = "comanda_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id", ondelete="CASCADE"), index=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="RESTRICT"))
    # Snapshots: si luego cambia el producto/precio, la comanda conserva lo vendido
    nombre_producto: Mapped[str] = mapped_column(String(120))
    precio_unitario: Mapped[Decimal] = mapped_column(Dinero)
    alicuota_iva: Mapped[Decimal] = mapped_column(Alicuota, default=Decimal(16), server_default="16")
    estado: Mapped[EstadoItem] = mapped_column(str_enum(EstadoItem), default=EstadoItem.pendiente, index=True)
    notas: Mapped[str | None] = mapped_column(String(255))
    # Insumos que el cliente pidió quitar (ids): no se reservan ni se descuentan del stock
    sin_insumo_ids: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")
    # Snapshot de la estación del producto al pedirlo (NULL = todas las pantallas)
    estacion_id: Mapped[int | None] = mapped_column(ForeignKey("estaciones.id", ondelete="SET NULL"), index=True)
    agregado_por_cliente: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listo_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    listo_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    entregado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Cortesía: el plato se sirve pero no se cobra
    cortesia: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cortesia_motivo: Mapped[str | None] = mapped_column(String(255))

    comanda: Mapped[Comanda] = relationship(back_populates="items")
    reservas: Mapped[list["ReservaStock"]] = relationship(back_populates="item", lazy="selectin")


class EstadoReserva(StrEnum):
    reservada = "reservada"
    consumida = "consumida"
    liberada = "liberada"


class ReservaStock(Base):
    """Cantidad exacta comprometida por item. Se consume al estar listo o se libera al cancelar."""

    __tablename__ = "reservas_stock"
    __table_args__ = (CheckConstraint("cantidad > 0", name="cantidad_positiva"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comanda_item_id: Mapped[int] = mapped_column(ForeignKey("comanda_items.id", ondelete="CASCADE"), index=True)
    inventario_id: Mapped[int] = mapped_column(ForeignKey("inventario.id", ondelete="RESTRICT"), index=True)
    cantidad: Mapped[Decimal] = mapped_column(Cantidad)
    estado: Mapped[EstadoReserva] = mapped_column(str_enum(EstadoReserva), default=EstadoReserva.reservada)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    item: Mapped[ComandaItem] = relationship(back_populates="reservas")


class MetodoPago(StrEnum):
    efectivo = "efectivo"
    tarjeta = "tarjeta"
    transferencia = "transferencia"
    pago_movil = "pago_movil"
    otro = "otro"


class Pago(Base):
    __tablename__ = "pagos"
    __table_args__ = (CheckConstraint("monto > 0", name="monto_positivo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id", ondelete="CASCADE"), index=True)
    moneda_id: Mapped[int] = mapped_column(ForeignKey("monedas.id", ondelete="RESTRICT"))
    monto: Mapped[Decimal] = mapped_column(Dinero)  # en la moneda del pago
    # Snapshot de la tasa usada, para que la venta no cambie si luego cambia la tasa
    tasa: Mapped[Decimal] = mapped_column(Tasa)
    operacion: Mapped[Operacion] = mapped_column(str_enum(Operacion))
    monto_principal: Mapped[Decimal] = mapped_column(Dinero)
    metodo: Mapped[MetodoPago] = mapped_column(str_enum(MetodoPago))
    referencia: Mapped[str | None] = mapped_column(String(120))
    # Para dividir cuentas: "Persona 1", "Juan", etc.
    etiqueta: Mapped[str | None] = mapped_column(String(60))
    registrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # IGTF incluido en este pago (moneda principal). Lo que abona a la cuenta es monto_principal - igtf.
    igtf: Mapped[Decimal] = mapped_column(Dinero, default=Decimal(0), server_default="0")
    # Turno de caja en el que entró el dinero (para el arqueo)
    turno_id: Mapped[int | None] = mapped_column(ForeignKey("turnos_caja.id", ondelete="SET NULL"), index=True)

    comanda: Mapped[Comanda] = relationship(back_populates="pagos")
    moneda: Mapped[Moneda] = relationship(lazy="joined")


class Venta(Base):
    __tablename__ = "ventas"
    __table_args__ = (
        # El mismo número de factura no puede repetirse en una sucursal
        Index(
            "uq_ventas_numero_factura",
            "sucursal_id",
            "numero_factura",
            unique=True,
            postgresql_where=text("numero_factura IS NOT NULL"),
        ),
        Index(
            "uq_ventas_nota_credito",
            "sucursal_id",
            "nota_credito_numero",
            unique=True,
            postgresql_where=text("nota_credito_numero IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id", ondelete="RESTRICT"), unique=True)
    sucursal_id: Mapped[int] = mapped_column(ForeignKey("sucursales.id", ondelete="RESTRICT"), index=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id", ondelete="SET NULL"), index=True)
    total: Mapped[Decimal] = mapped_column(Dinero, index=True)  # facturable: con descuento, sin propina ni IGTF
    descuento: Mapped[Decimal] = mapped_column(Dinero, default=Decimal(0), server_default="0")
    propina: Mapped[Decimal] = mapped_column(Dinero, default=Decimal(0), server_default="0")
    igtf: Mapped[Decimal] = mapped_column(Dinero, default=Decimal(0), server_default="0")
    pagado: Mapped[Decimal] = mapped_column(Dinero)
    vuelto: Mapped[Decimal] = mapped_column(Dinero)
    cantidad_items: Mapped[int] = mapped_column(Integer)
    cerrada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Tasa de la moneda fiscal (Bs) al cerrar: la factura se expresa con ella
    moneda_fiscal: Mapped[str | None] = mapped_column(String(10))
    tasa_fiscal: Mapped[Decimal | None] = mapped_column(Tasa)
    operacion_fiscal: Mapped[Operacion | None] = mapped_column(str_enum(Operacion))

    # Factura emitida a mano (talonario o máquina fiscal) y registrada después en el sistema
    numero_factura: Mapped[str | None] = mapped_column(String(40))
    numero_control: Mapped[str | None] = mapped_column(String(40))
    facturada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facturada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    # Receptor tal como quedó en la factura (no cambia si luego se edita el cliente)
    receptor_tipo_documento: Mapped[TipoDocumento | None] = mapped_column(str_enum(TipoDocumento, length=1))
    receptor_documento: Mapped[str | None] = mapped_column(String(40))
    receptor_razon_social: Mapped[str | None] = mapped_column(String(160))
    receptor_domicilio: Mapped[str | None] = mapped_column(String(255))

    # Anulación de la factura con una nota de crédito (emitida a mano), que se registra aquí
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anulada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(255))
    nota_credito_numero: Mapped[str | None] = mapped_column(String(40))
    nota_credito_control: Mapped[str | None] = mapped_column(String(40))

    comanda: Mapped[Comanda] = relationship(back_populates="venta", lazy="joined")
    sucursal: Mapped[Sucursal] = relationship(lazy="joined")


class AutorMensaje(StrEnum):
    cliente = "cliente"
    personal = "personal"


class MensajeComanda(Base):
    """Chat entre la mesa (cliente) y caja, dentro de una comanda."""

    __tablename__ = "mensajes_comanda"

    id: Mapped[int] = mapped_column(primary_key=True)
    comanda_id: Mapped[int] = mapped_column(ForeignKey("comandas.id", ondelete="CASCADE"), index=True)
    autor: Mapped[AutorMensaje] = mapped_column(str_enum(AutorMensaje))
    autor_nombre: Mapped[str | None] = mapped_column(String(120))
    texto: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
