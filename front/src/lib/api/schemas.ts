import { z } from "zod";

/**
 * Contratos de la API (backend/app/schemas/*.py). El dinero y las cantidades son
 * Decimal en Python y llegan como string: se validan como string y nunca se
 * convierten a number.
 */
export const Decimal = z.string().regex(/^-?\d+(\.\d+)?$/, "decimal");
export const IsoDate = z.string();

export const MODULOS = [
  "usuarios",
  "roles",
  "sucursales",
  "monedas",
  "insumos",
  "inventario",
  "recetas",
  "categorias",
  "productos",
  "clientes",
  "mesas",
  "comandas",
  "caja",
  "cocina",
  "ventas",
  "bitacora",
  "compras",
] as const;
export const ACCIONES = ["crear", "leer", "editar", "eliminar"] as const;
export type Modulo = (typeof MODULOS)[number];
export type Accion = (typeof ACCIONES)[number];

export const Pagina = <T extends z.ZodType>(item: T) =>
  z.object({ total: z.number(), limite: z.number(), offset: z.number(), items: z.array(item) });

// ---------- Usuarios y auth
export const SucursalResumen = z.object({ id: z.number(), nombre: z.string() });
export const RolResumen = z.object({ id: z.number(), nombre: z.string() });

export const UsuarioOut = z.object({
  id: z.number(),
  email: z.string(),
  nombre: z.string(),
  es_superadmin: z.boolean(),
  activo: z.boolean(),
  rol: RolResumen.nullable(),
  sucursales: z.array(SucursalResumen),
  ultimo_login: IsoDate.nullable(),
  created_at: IsoDate,
});

export const Permisos = z.record(z.string(), z.record(z.string(), z.boolean()));
export const MeOut = UsuarioOut.extend({ permisos: Permisos });
export type Me = z.infer<typeof MeOut>;

export const WsTicketOut = z.object({ ticket: z.string(), expira_en_seg: z.number() });

export const SucursalOut = z.object({
  id: z.number(),
  nombre: z.string(),
  direccion: z.string().nullable(),
  telefono: z.string().nullable(),
  activa: z.boolean(),
  rif: z.string().nullable(),
  razon_social: z.string().nullable(),
  domicilio_fiscal: z.string().nullable(),
  cobra_igtf: z.boolean(),
  precios_incluyen_iva: z.boolean(),
});
export type Sucursal = z.infer<typeof SucursalOut>;

// ---------- Tiempo real
export const StockAlertaEvento = z.object({
  inventario_id: z.number(),
  insumo_id: z.number(),
  insumo: z.string(),
  unidad: z.string(),
  cantidad: Decimal,
  stock_minimo: Decimal,
  mensaje: z.string(),
});

// ---------- Monedas y menú
export const Operacion = z.enum(["multiplicar", "dividir"]);
export const MonedaOut = z.object({
  id: z.number(),
  codigo: z.string(),
  nombre: z.string(),
  simbolo: z.string(),
  es_principal: z.boolean(),
  tasa: Decimal,
  operacion: Operacion,
  activa: z.boolean(),
  es_divisa: z.boolean(),
  es_fiscal: z.boolean(),
  updated_at: IsoDate,
});
export type Moneda = z.infer<typeof MonedaOut>;

export const MontoMoneda = z.object({ moneda: z.string(), simbolo: z.string(), monto: Decimal });
export type MontoMoneda = z.infer<typeof MontoMoneda>;

export const MedioOut = z.object({
  id: z.number(),
  tipo: z.enum(["imagen", "video"]),
  url: z.string(),
  mime: z.string().nullable(),
  tamano_bytes: z.number().nullable(),
  orden: z.number(),
  es_portada: z.boolean(),
  texto_alt: z.string().nullable(),
});

export const MenuProducto = z.object({
  id: z.number(),
  nombre: z.string(),
  descripcion: z.string().nullable(),
  /** Lo que paga el cliente, con IVA. */
  precio: Decimal,
  precios: z.array(MontoMoneda),
  precio_sin_iva: Decimal,
  alicuota_iva: Decimal,
  medios: z.array(MedioOut),
  porciones_disponibles: z.number().nullable(),
  /** Ingredientes que el cliente puede quitar. */
  ingredientes: z.array(z.object({ insumo_id: z.number(), nombre: z.string() })).default([]),
});
export type MenuProducto = z.infer<typeof MenuProducto>;

export const MenuOut = z.object({
  sucursal_id: z.number(),
  sucursal: z.string(),
  moneda_principal: z.string(),
  precios_incluyen_iva: z.boolean(),
  monedas: z.array(MonedaOut),
  categorias: z.array(z.object({ id: z.number().nullable(), nombre: z.string(), productos: z.array(MenuProducto) })),
});
export type Menu = z.infer<typeof MenuOut>;

// ---------- Mesas
export const MesaOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  nombre: z.string(),
  capacidad: z.number().nullable(),
  qr_habilitado: z.boolean(),
  activa: z.boolean(),
  pos_x: z.number().nullable(),
  pos_y: z.number().nullable(),
  zona_id: z.number().nullable().default(null),
  forma: z.enum(["cuadrada", "redonda", "rectangular"]).default("cuadrada"),
  ancho: z.number().default(3),
  alto: z.number().default(2),
  unida_a_id: z.number().nullable().default(null),
  ocupada: z.boolean(),
  comanda_abierta_id: z.number().nullable(),
});
export type Mesa = z.infer<typeof MesaOut>;
export const ZonaOut = z.object({ id: z.number(), sucursal_id: z.number(), nombre: z.string(), orden: z.number(), activa: z.boolean() });
export type Zona = z.infer<typeof ZonaOut>;

// ---------- Comandas
export const EstadoComanda = z.enum(["abierta", "cerrada", "cancelada"]);
export const EstadoItem = z.enum(["pendiente", "en_cocina", "preparando", "listo", "entregado", "cancelado"]);
export type EstadoItem = z.infer<typeof EstadoItem>;
export const Origen = z.enum(["qr", "caja"]);
export const MetodoPago = z.enum(["efectivo", "tarjeta", "transferencia", "pago_movil", "otro"]);
export type MetodoPago = z.infer<typeof MetodoPago>;

export const ComandaResumenOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  mesa_id: z.number().nullable(),
  mesa: z.string().nullable(),
  nombre_cliente: z.string().nullable(),
  origen: Origen,
  estado: EstadoComanda,
  total: Decimal,
  items_pendientes: z.number(),
  items_en_cocina: z.number(),
  items_listos: z.number(),
  items_por_servir: z.number(),
  created_at: IsoDate,
});
export type ComandaResumen = z.infer<typeof ComandaResumenOut>;

export const ItemOut = z.object({
  id: z.number(),
  producto_id: z.number(),
  nombre: z.string(),
  nombre_producto: z.string(),
  numero: z.number(),
  precio_unitario: Decimal,
  estado: EstadoItem,
  notas: z.string().nullable(),
  sin_insumo_ids: z.array(z.number()).default([]),
  estacion_id: z.number().nullable().default(null),
  agregado_por_cliente: z.boolean(),
  cortesia: z.boolean().default(false),
  cortesia_motivo: z.string().nullable().default(null),
  enviado_en: IsoDate.nullable(),
  listo_en: IsoDate.nullable(),
  entregado_en: IsoDate.nullable(),
});
export type Item = z.infer<typeof ItemOut>;

export const PagoOut = z.object({
  id: z.number(),
  moneda: z.string(),
  monto: Decimal,
  tasa: Decimal,
  operacion: z.string(),
  monto_principal: Decimal,
  metodo: MetodoPago,
  referencia: z.string().nullable(),
  etiqueta: z.string().nullable(),
  igtf: Decimal.default("0"),
  created_at: IsoDate,
});
export type Pago = z.infer<typeof PagoOut>;

export const ComandaOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  mesa_id: z.number().nullable(),
  mesa: z.string().nullable(),
  cliente_id: z.number().nullable(),
  nombre_cliente: z.string().nullable(),
  telefono_cliente: z.string().nullable(),
  origen: Origen,
  estado: EstadoComanda,
  notas: z.string().nullable(),
  seguimiento_url: z.string(),
  items: z.array(ItemOut),
  venta_id: z.number().nullable().default(null),
  /** % de IGTF que se suma al pagar en divisas (null = la sucursal no lo cobra). */
  igtf_porcentaje: Decimal.nullable().default(null),
  descuento: z.object({ tipo: z.enum(["porcentaje", "monto"]), valor: Decimal, motivo: z.string().nullable() }).nullable().default(null),
  pagos: z.array(PagoOut),
  totales: z.object({
    subtotal: Decimal,
    descuento: Decimal,
    facturable: Decimal,
    propina: Decimal,
    igtf: Decimal,
    /** Lo que paga el cliente: facturable + propina. */
    total: Decimal,
    pagado: Decimal,
    pendiente: Decimal,
    vuelto: Decimal,
    total_monedas: z.array(MontoMoneda),
    pendiente_monedas: z.array(MontoMoneda),
  }),
  created_at: IsoDate,
  cerrada_en: IsoDate.nullable(),
  motivo_cancelacion: z.string().nullable(),
});
export type Comanda = z.infer<typeof ComandaOut>;

export const DivisionOut = z.object({
  total: Decimal,
  pendiente: Decimal,
  partes: z.array(
    z.object({
      etiqueta: z.string(),
      monto: Decimal,
      montos_monedas: z.array(MontoMoneda),
      pagado: Decimal,
      item_ids: z.array(z.number()).default([]),
    }),
  ),
  sin_asignar: Decimal.default("0"),
});
export type Division = z.infer<typeof DivisionOut>;

// ---------- Clientes
export const TIPOS_DOCUMENTO = ["V", "E", "J", "G", "P"] as const;
export const TipoDocumento = z.enum(TIPOS_DOCUMENTO);
export type TipoDocumento = z.infer<typeof TipoDocumento>;

export const ClienteOut = z.object({
  id: z.number(),
  nombre: z.string(),
  tipo_documento: TipoDocumento.nullable(),
  documento: z.string().nullable(),
  telefono: z.string().nullable(),
  email: z.string().nullable(),
  direccion: z.string().nullable(),
  notas: z.string().nullable(),
  created_at: IsoDate,
});
export type Cliente = z.infer<typeof ClienteOut>;

// ---------- Cocina
export const CocinaComandaOut = z.object({
  comanda_id: z.number(),
  mesa: z.string().nullable(),
  nombre_cliente: z.string().nullable(),
  notas: z.string().nullable(),
  items: z.array(
    z.object({
      id: z.number(),
      nombre: z.string(),
      estado: EstadoItem,
      notas: z.string().nullable(),
      enviado_en: IsoDate.nullable(),
    }),
  ),
});
export type CocinaComanda = z.infer<typeof CocinaComandaOut>;

// ---------- Público (menú QR y seguimiento)
export const PedidoPublicoOut = z.object({
  sucursal_id: z.number(),
  sucursal: z.string(),
  mesa: z.string().nullable(),
  estado: EstadoComanda,
  items: z.array(z.object({ id: z.number(), nombre: z.string(), estado: EstadoItem, precio_unitario: Decimal, notas: z.string().nullable() })),
  total: Decimal,
  total_monedas: z.array(MontoMoneda),
  progreso: z.record(z.string(), z.number()),
  created_at: IsoDate,
});
export type PedidoPublico = z.infer<typeof PedidoPublicoOut>;

export const MesaPublicaOut = z.object({ mesa: z.string(), sucursal: z.string(), ocupada: z.boolean(), menu: MenuOut });
export type MesaPublica = z.infer<typeof MesaPublicaOut>;

export const PedidoCreadoOut = z.object({ tracking_token: z.string(), seguimiento_url: z.string(), pedido: PedidoPublicoOut });

// ---------- Inventario y catálogo
export const Unidad = z.string();
export const UnidadMedidaOut = z.object({
  id: z.number(),
  codigo: z.string(),
  nombre: z.string(),
  abreviatura: z.string(),
  permite_decimales: z.boolean(),
  subunidad_abreviatura: z.string().nullable(),
  factor_subunidad: Decimal.nullable(),
  es_base: z.boolean(),
  activa: z.boolean(),
  en_uso: z.number().default(0),
});
export type UnidadMedida = z.infer<typeof UnidadMedidaOut>;
export const PresentacionOut = z.object({ id: z.number(), nombre: z.string(), cantidad: Decimal });
export type Presentacion = z.infer<typeof PresentacionOut>;
export const InsumoOut = z.object({
  id: z.number(),
  codigo: z.string(),
  codigo_barras: z.string().nullable(),
  nombre: z.string(),
  unidad: Unidad,
  activo: z.boolean(),
  /** Por unidad del insumo, en moneda principal (lo actualiza cada compra). */
  costo_unitario: Decimal.nullable().default(null),
  unidad_abreviatura: z.string().default(""),
  permite_decimales: z.boolean().default(true),
  presentaciones: z.array(PresentacionOut).default([]),
});
export type Insumo = z.infer<typeof InsumoOut>;

export const InventarioOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  insumo: InsumoOut,
  cantidad: Decimal,
  reservado: Decimal,
  disponible: Decimal,
  stock_minimo: Decimal,
  bajo_minimo: z.boolean(),
  updated_at: IsoDate,
});
export type Inventario = z.infer<typeof InventarioOut>;

/** Resultado de buscar un insumo por código interno, código de barras o nombre. */
export const InsumoEncontradoOut = z.object({
  insumo: InsumoOut,
  inventario: InventarioOut.nullable(),
  coincidencia: z.enum(["codigo", "codigo_barras", "nombre"]),
});
export type InsumoEncontrado = z.infer<typeof InsumoEncontradoOut>;

export const BitacoraOut = z.object({
  id: z.number(),
  created_at: IsoDate,
  usuario_id: z.number().nullable(),
  usuario_nombre: z.string(),
  sucursal_id: z.number().nullable(),
  sucursal: z.string().nullable(),
  modulo: z.string(),
  accion: z.string(),
  descripcion: z.string(),
  entidad: z.string().nullable(),
  entidad_id: z.number().nullable(),
  datos: z.record(z.string(), z.unknown()).nullable(),
  ip: z.string().nullable(),
});
export type EntradaBitacora = z.infer<typeof BitacoraOut>;

export const MovimientoOut = z.object({
  id: z.number(),
  tipo: z.enum(["entrada", "ajuste", "merma", "consumo"]),
  cantidad: Decimal,
  saldo: Decimal,
  motivo: z.string().nullable(),
  usuario_id: z.number().nullable(),
  comanda_item_id: z.number().nullable(),
  created_at: IsoDate,
});

export const AlertaOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  inventario_id: z.number(),
  insumo: z.string(),
  unidad: Unidad,
  cantidad: Decimal,
  stock_minimo: Decimal,
  mensaje: z.string(),
  estado: z.enum(["activa", "resuelta"]),
  created_at: IsoDate,
  resuelta_en: IsoDate.nullable(),
});

export const RecetaOut = z.object({
  id: z.number(),
  codigo: z.string(),
  nombre: z.string(),
  descripcion: z.string().nullable(),
  activa: z.boolean(),
  ingredientes: z.array(z.object({ insumo_id: z.number(), insumo: z.string(), unidad: Unidad, cantidad: Decimal, removible: z.boolean().default(true), costo: Decimal.nullable().default(null) })),
  costo: Decimal.nullable().default(null),
});
export type Receta = z.infer<typeof RecetaOut>;

export const CategoriaOut = z.object({ id: z.number(), nombre: z.string(), orden: z.number(), activa: z.boolean(), estacion_id: z.number().nullable().default(null) });
export type Categoria = z.infer<typeof CategoriaOut>;

export const EstacionOut = z.object({ id: z.number(), nombre: z.string(), orden: z.number(), activa: z.boolean() });
export type Estacion = z.infer<typeof EstacionOut>;

export const ProductoOut = z.object({
  id: z.number(),
  codigo: z.string(),
  codigo_barras: z.string().nullable(),
  nombre: z.string(),
  descripcion: z.string().nullable(),
  categoria: CategoriaOut.nullable(),
  receta_id: z.number().nullable(),
  insumo_id: z.number().nullable().default(null),
  cantidad_por_venta: Decimal.default("1"),
  control_stock: z.enum(["receta", "directo", "ninguno"]).default("ninguno"),
  estacion: EstacionOut.nullable().default(null),
  precio_base: Decimal,
  alicuota_iva: Decimal,
  orden: z.number(),
  activo: z.boolean(),
  sucursales: z.array(z.object({ sucursal_id: z.number(), precio: Decimal.nullable(), disponible: z.boolean() })),
  medios: z.array(MedioOut),
});
export type Producto = z.infer<typeof ProductoOut>;

// ---------- Ventas
export const VentaOut = z.object({
  id: z.number(),
  comanda_id: z.number(),
  sucursal_id: z.number(),
  sucursal: z.string(),
  mesa: z.string().nullable(),
  cliente_id: z.number().nullable(),
  nombre_cliente: z.string().nullable(),
  total: Decimal,
  pagado: Decimal,
  vuelto: Decimal,
  cantidad_items: z.number(),
  created_at: IsoDate,
  numero_factura: z.string().nullable(),
  numero_control: z.string().nullable(),
  facturada_en: IsoDate.nullable(),
  anulada_en: IsoDate.nullable().default(null),
  descuento: Decimal.default("0"),
  propina: Decimal.default("0"),
  igtf: Decimal.default("0"),
});
export const VentaDetalleOut = VentaOut.extend({ comanda: ComandaOut });

// ---------- Facturación manual (documento para facturar)
const MontoFiscal = z.object({ principal: Decimal, fiscal: Decimal.nullable() });
export type MontoFiscal = z.infer<typeof MontoFiscal>;
export const DatosFiscalesOut = z.object({
  venta_id: z.number(),
  comanda_id: z.number(),
  cliente_id: z.number().nullable(),
  fecha: IsoDate,
  mesa: z.string().nullable(),
  emisor: z.object({
    nombre_comercial: z.string(),
    razon_social: z.string().nullable(),
    rif: z.string().nullable(),
    domicilio_fiscal: z.string().nullable(),
    telefono: z.string().nullable(),
  }),
  receptor: z.object({
    tipo_documento: TipoDocumento.nullable(),
    documento: z.string().nullable(),
    rif: z.string().nullable(),
    razon_social: z.string().nullable(),
    domicilio: z.string().nullable(),
    consumidor_final: z.boolean(),
  }),
  moneda_principal: z.string(),
  moneda_fiscal: z.string().nullable(),
  tasa_fiscal: Decimal.nullable(),
  tasa_es_actual: z.boolean(),
  lineas: z.array(
    z.object({ descripcion: z.string(), cantidad: z.number(), precio_unitario: MontoFiscal, alicuota_iva: Decimal, exento: z.boolean(), total: MontoFiscal }),
  ),
  resumen_iva: z.array(z.object({ alicuota_iva: Decimal, etiqueta: z.string(), base_imponible: MontoFiscal, iva: MontoFiscal, total: MontoFiscal })),
  subtotal: MontoFiscal,
  exento: MontoFiscal,
  iva: MontoFiscal,
  total: MontoFiscal,
  igtf: z.object({ porcentaje: Decimal, base: MontoFiscal, monto: MontoFiscal }).nullable(),
  total_a_pagar: MontoFiscal,
  pagos: z.array(z.object({ metodo: z.string(), moneda: z.string(), monto: Decimal, monto_principal: Decimal, es_divisa: z.boolean(), referencia: z.string().nullable() })),
  numero_factura: z.string().nullable(),
  numero_control: z.string().nullable(),
  facturada_en: IsoDate.nullable(),
  anulada_en: IsoDate.nullable().default(null),
  motivo_anulacion: z.string().nullable().default(null),
  nota_credito_numero: z.string().nullable().default(null),
  nota_credito_control: z.string().nullable().default(null),
  avisos: z.array(z.string()),
  leyenda: z.string(),
});
export type DatosFiscales = z.infer<typeof DatosFiscalesOut>;

export const CierreDiaOut = z.object({
  dia: z.string(),
  sucursal: z.string().nullable(),
  emisor: z.object({ nombre_comercial: z.string(), razon_social: z.string().nullable(), rif: z.string().nullable(), domicilio_fiscal: z.string().nullable(), telefono: z.string().nullable() }),
  moneda: z.string(),
  ventas: z.number(),
  total: Decimal,
  exento: Decimal,
  iva: z.array(z.object({ alicuota_iva: Decimal, etiqueta: z.string(), base_imponible: Decimal, iva: Decimal })),
  igtf: Decimal,
  descuentos: Decimal,
  propinas: Decimal,
  por_metodo: z.array(z.object({ metodo: z.string(), monto: Decimal })),
  cortesias: z.number(),
  facturadas: z.number(),
  pendientes_facturar: z.number(),
  anuladas: z.number(),
  anuladas_total: Decimal,
  leyenda: z.string(),
});
export type CierreDia = z.infer<typeof CierreDiaOut>;
export const ResumenVentasOut = z.object({
  cantidad_ventas: z.number(),
  total: Decimal,
  ticket_promedio: Decimal,
  por_periodo: z.array(z.object({ periodo: z.string(), cantidad_ventas: z.number(), total: Decimal })),
  productos_top: z.array(z.object({ producto: z.string(), cantidad: z.number(), total: Decimal })),
});

// ---------- Administración
export const RolOut = z.object({
  id: z.number(),
  nombre: z.string(),
  descripcion: z.string().nullable(),
  permisos: z.array(z.object({ modulo: z.string(), crear: z.boolean(), leer: z.boolean(), editar: z.boolean(), eliminar: z.boolean() })),
});
export type Rol = z.infer<typeof RolOut>;
export type Usuario = z.infer<typeof UsuarioOut>;

export const ApiKeyOut = z.object({ id: z.number(), nombre: z.string(), prefijo: z.string(), activa: z.boolean(), ultimo_uso: IsoDate.nullable(), created_at: IsoDate });
export const ApiKeyCreadaOut = ApiKeyOut.extend({ clave: z.string() });
export const AuditoriaOut = z.object({
  id: z.number(),
  usuario_id: z.number().nullable(),
  api_key_id: z.number().nullable(),
  metodo: z.string(),
  ruta: z.string(),
  status_code: z.number(),
  ip: z.string().nullable(),
  created_at: IsoDate,
});
export const MesaQrOut = z.object({ mesa_id: z.number(), url: z.string() });

// ---------- Turnos de caja
const MontoMonedaId = z.object({ moneda_id: z.number(), moneda: z.string(), simbolo: z.string(), monto: Decimal });
export const TurnoOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  sucursal: z.string(),
  estado: z.enum(["abierto", "cerrado"]),
  abierto_por: z.string().nullable(),
  abierto_en: IsoDate,
  cerrado_por: z.string().nullable(),
  cerrado_en: IsoDate.nullable(),
  fondo: z.array(MontoMonedaId),
  movimientos: z.array(
    z.object({
      id: z.number(),
      tipo: z.enum(["ingreso", "retiro"]),
      moneda: z.string(),
      simbolo: z.string(),
      monto: Decimal,
      motivo: z.string(),
      usuario: z.string().nullable(),
      created_at: IsoDate,
    }),
  ),
  resumen: z.object({
    ventas: z.number(),
    facturado: Decimal,
    descuentos: Decimal,
    propinas: Decimal,
    igtf: Decimal,
    vueltos: Decimal,
    por_metodo: z.array(z.object({ metodo: MetodoPago, moneda: z.string(), simbolo: z.string(), monto: Decimal, cantidad: z.number() })),
    efectivo: z.array(
      z.object({
        moneda_id: z.number(),
        moneda: z.string(),
        simbolo: z.string(),
        fondo: Decimal,
        cobrado: Decimal,
        ingresos: Decimal,
        retiros: Decimal,
        vueltos: Decimal,
        esperado: Decimal,
      }),
    ),
  }),
  arqueo: z
    .array(z.object({ moneda_id: z.number(), moneda: z.string(), simbolo: z.string(), esperado: Decimal, contado: Decimal, diferencia: Decimal }))
    .nullable(),
  notas: z.string().nullable(),
});
export type Turno = z.infer<typeof TurnoOut>;

// ---------- Compras, proveedores y rentabilidad
export const ProveedorOut = z.object({
  id: z.number(),
  nombre: z.string(),
  rif: z.string().nullable(),
  telefono: z.string().nullable(),
  email: z.string().nullable(),
  contacto: z.string().nullable(),
  notas: z.string().nullable(),
  activo: z.boolean(),
});
export type Proveedor = z.infer<typeof ProveedorOut>;

export const CompraOut = z.object({
  id: z.number(),
  sucursal_id: z.number(),
  sucursal: z.string(),
  proveedor_id: z.number().nullable(),
  proveedor: z.string().nullable(),
  numero_documento: z.string().nullable(),
  fecha: z.string(),
  moneda: z.string(),
  simbolo: z.string(),
  tasa: Decimal,
  total: Decimal,
  total_principal: Decimal,
  notas: z.string().nullable(),
  items: z.array(
    z.object({ insumo_id: z.number(), insumo: z.string(), codigo: z.string(), unidad: Unidad, cantidad: Decimal, subtotal: Decimal, costo_unitario: Decimal }),
  ),
  created_at: IsoDate,
});
export type Compra = z.infer<typeof CompraOut>;

export const RentabilidadOut = z.object({
  producto_id: z.number(),
  producto: z.string(),
  codigo: z.string(),
  categoria: z.string().nullable(),
  precio: Decimal,
  precio_sin_iva: Decimal,
  costo: Decimal.nullable(),
  margen: Decimal.nullable(),
  margen_pct: Decimal.nullable(),
  costo_pct: Decimal.nullable(),
  sin_receta: z.boolean(),
  insumos_sin_costo: z.array(z.string()),
});
export type Rentabilidad = z.infer<typeof RentabilidadOut>;

// ---------- Seguridad
export const AlertaSeguridadOut = z.object({
  id: z.number(),
  created_at: IsoDate,
  tipo: z.string(),
  severidad: z.enum(["media", "alta", "critica"]),
  titulo: z.string(),
  detalle: z.string(),
  ip: z.string().nullable(),
  usuario_id: z.number().nullable(),
  revisada: z.boolean(),
  revisada_en: IsoDate.nullable(),
});
export type AlertaSeguridad = z.infer<typeof AlertaSeguridadOut>;

export const ConsultaCedulaOut = z.object({ nombre: z.string(), rif: z.string().nullable(), zona: z.string().nullable() });

// ---------- Configuración editable (superadmin)
export const OpcionConfigOut = z.object({
  clave: z.string(),
  grupo: z.string(),
  etiqueta: z.string(),
  descripcion: z.string(),
  tipo: z.enum(["entero", "decimal", "texto", "url", "zona_horaria", "secreto"]),
  minimo: Decimal.nullable(),
  maximo: Decimal.nullable(),
  valor: z.string().nullable(),
  por_defecto: z.string().nullable(),
  configurado: z.boolean(),
  origen: z.enum(["panel", "entorno"]),
});
export type OpcionConfig = z.infer<typeof OpcionConfigOut>;

// ---------- Chat mesa <-> caja
export const MensajeOut = z.object({
  id: z.number(),
  autor: z.enum(["cliente", "personal"]),
  autor_nombre: z.string().nullable(),
  texto: z.string(),
  created_at: IsoDate,
});
export type Mensaje = z.infer<typeof MensajeOut>;
