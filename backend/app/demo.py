"""Instancia de demostración completa: un restaurante venezolano listo para enseñar.

Carga, de forma idempotente (se puede repetir sin duplicar nada):
  sucursal · monedas (USD principal + Bs a tasa BCV) · proveedores · insumos con presentaciones ·
  compras reales a cada proveedor (que dejan el stock y el último costo) · menú con recetas y bebidas
  de reventa · zonas y mesas con QR · roles (Mesero, Cocina, Cajero) y un usuario de cada uno.

Todos los nombres de proveedores, RIF y teléfonos son FICTICIOS (correos @*.example).
Uso:  docker compose exec -T api python -m app.cli preparar-demo --email admin@... --password-stdin
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from pydantic import TypeAdapter
from sqlalchemy import exists, select

from app.core.security import hash_password, new_public_token
from app.models import (
    Accion,
    Categoria,
    Compra,
    CompraItem,
    Estacion,
    FormaMesa,
    Insumo,
    Inventario,
    Mesa,
    Modulo,
    Moneda,
    Operacion,
    Presentacion,
    Producto,
    ProductoMedio,
    Proveedor,
    Receta,
    RecetaInsumo,
    Rol,
    RolPermiso,
    Sucursal,
    TipoMedio,
    UnidadMedida,
    Usuario,
    Zona,
)
from app.schemas.usuarios import Password
from app.services import config, stock
from app.services import unidades as unidades_srv

SEIS = Decimal("0.000001")

PROVEEDORES = {
    "esperanza": dict(nombre="Distribuidora La Esperanza C.A.", rif="J-31245678-0", telefono="0212-555-0101",
                      email="ventas@laesperanza.example", contacto="Carlos Méndez",
                      notas="Abarrotes, lácteos y despensa. Entrega martes y viernes."),
    "carnes": dict(nombre="Carnes y Embutidos El Corral C.A.", rif="J-29876543-2", telefono="0212-555-0102",
                   email="pedidos@elcorral.example", contacto="María Fernández",
                   notas="Carne, pollo y tocineta. Pedidos antes de las 4 pm para entrega al día siguiente."),
    "mercado": dict(nombre="Frutas y Verduras Mercado Mayor", rif="J-40123456-7", telefono="0414-555-0103",
                    email="mercadomayor@correo.example", contacto="José Ramírez",
                    notas="Verduras y frutas frescas. Entrega diaria en la mañana."),
    "marta": dict(nombre="Panadería y Pastelería Doña Marta", rif="J-41234567-1", telefono="0416-555-0105",
                  email="donamarta@correo.example", contacto="Marta Rodríguez",
                  notas="Panes, tequeños, postres y helados. Pago de contado."),
    "bebidas": dict(nombre="Bebidas y Refrescos del Centro C.A.", rif="J-30998877-5", telefono="0212-555-0104",
                    email="despachos@bebidascentro.example", contacto="Luis Herrera",
                    notas="Refrescos, agua, malta y cerveza. Entrega los jueves; crédito a 7 días."),
}

# nombre, unidad base, proveedor, presentación, cantidad de la presentación (en unidad base), precio por presentación (USD),
# cuántas presentaciones se compran al abrir, stock mínimo (en unidad base)
INSUMOS = [
    ("Carne molida", "g", "carnes", "Bolsa 1 kg", 1000, "6.50", 15, 3000),
    ("Carne mechada", "g", "carnes", "Bolsa 1 kg", 1000, "7.80", 6, 1500),
    ("Pechuga de pollo", "g", "carnes", "Bandeja 1 kg", 1000, "4.20", 10, 2000),
    ("Tocineta", "g", "carnes", "Paquete 500 g", 500, "4.50", 6, 600),
    ("Queso amarillo", "g", "esperanza", "Bloque 1 kg", 1000, "7.00", 4, 800),
    ("Queso blanco", "g", "esperanza", "Bloque 1 kg", 1000, "6.00", 6, 1500),
    ("Harina de maíz precocida", "g", "esperanza", "Paquete 1 kg", 1000, "1.60", 12, 2000),
    ("Caraotas negras", "g", "esperanza", "Bolsa 1 kg", 1000, "2.20", 6, 1500),
    ("Arroz", "g", "esperanza", "Bolsa 1 kg", 1000, "1.40", 10, 2000),
    ("Aceite", "ml", "esperanza", "Botella 1 L", 1000, "3.20", 8, 2000),
    ("Salsa de ajo", "ml", "esperanza", "Pote 1 L", 1000, "3.50", 3, 600),
    ("Azúcar", "g", "esperanza", "Bolsa 1 kg", 1000, "1.30", 6, 1000),
    ("Café molido", "g", "esperanza", "Paquete 500 g", 500, "6.50", 4, 500),
    ("Aguacate", "g", "mercado", "Kilo", 1000, "3.00", 6, 1000),
    ("Plátano maduro", "g", "mercado", "Kilo", 1000, "1.50", 10, 2000),
    ("Tomate", "g", "mercado", "Kilo", 1000, "2.00", 5, 800),
    ("Lechuga", "g", "mercado", "Kilo", 1000, "2.50", 3, 500),
    ("Cebolla", "g", "mercado", "Kilo", 1000, "1.80", 5, 800),
    ("Papas", "g", "mercado", "Saco 10 kg", 10000, "9.00", 3, 4000),
    ("Lechosa", "g", "mercado", "Kilo", 1000, "1.20", 8, 1500),
    ("Parchita", "g", "mercado", "Kilo", 1000, "4.00", 3, 600),
    ("Limón", "unidad", "mercado", "Bolsa x25", 25, "2.50", 4, 15),
    ("Pan de hamburguesa", "unidad", "marta", "Paquete x8", 8, "2.40", 12, 16),
    ("Tequeño", "unidad", "marta", "Caja x50", 50, "15.00", 3, 24),
    ("Brownie", "unidad", "marta", "Caja x12", 12, "9.00", 3, 6),
    ("Helado de vainilla", "g", "marta", "Pote 2 kg", 2000, "9.00", 3, 1000),
    ("Quesillo (porción)", "unidad", "marta", "Bandeja x8", 8, "12.00", 3, 4),
    ("Torta tres leches (porción)", "unidad", "marta", "Torta x12", 12, "14.40", 2, 4),
    ("Pepsi lata", "unidad", "bebidas", "Caja x24", 24, "15.00", 4, 24),
    ("Agua mineral", "unidad", "bebidas", "Caja x24", 24, "9.60", 3, 24),
    ("Malta lata", "unidad", "bebidas", "Caja x24", 24, "21.00", 3, 24),
    ("Cerveza nacional (botellín)", "unidad", "bebidas", "Caja x36", 36, "28.00", 3, 36),
]

# Productos de reventa: sin receta, descuentan directo su propio insumo
REVENTA = {
    "Pepsi": "Pepsi lata",
    "Agua mineral": "Agua mineral",
    "Malta": "Malta lata",
    "Cerveza nacional": "Cerveza nacional (botellín)",
    "Quesillo": "Quesillo (porción)",
    "Torta tres leches": "Torta tres leches (porción)",
}

_IMG = "https://images.unsplash.com/{}?w=1200&q=80&fit=crop"
FOTOS = {
    "Hamburguesa clásica": _IMG.format("photo-1568901346375-23c9450c58cd"),
    "Hamburguesa doble": _IMG.format("photo-1572802419224-296b0aeee0d9"),
    "Hamburguesa de pollo": _IMG.format("photo-1550547660-d9450f859349"),
    "Papas fritas": _IMG.format("photo-1573080496219-bb080dd4f877"),
    "Pepsi": _IMG.format("photo-1556679343-c7306c1976bc"),
    "Agua mineral": _IMG.format("photo-1523362628745-0c100150b504"),
    "Limonada": _IMG.format("photo-1556881286-fc6915169721"),
    "Café": _IMG.format("photo-1514432324607-a09d9b4aefdd"),
    "Brownie con helado": _IMG.format("photo-1551024506-0bccd828d307"),
}

# categoría, estación, nombre, precio USD (IVA incluido), ingredientes [(insumo, cantidad, quitable)]
MENU = [
    ("Arepas", "Cocina", "Arepa reina pepiada", "4.50", [("Harina de maíz precocida", 120, False), ("Pechuga de pollo", 100, False), ("Aguacate", 60, True)]),
    ("Arepas", "Cocina", "Arepa pelúa", "5.00", [("Harina de maíz precocida", 120, False), ("Carne mechada", 100, False), ("Queso amarillo", 40, True)]),
    ("Arepas", "Cocina", "Arepa de queso", "3.50", [("Harina de maíz precocida", 120, False), ("Queso blanco", 60, True)]),
    ("Arepas", "Cocina", "Arepa pabellón", "5.50", [("Harina de maíz precocida", 120, False), ("Carne mechada", 80, False), ("Caraotas negras", 60, False), ("Plátano maduro", 40, True), ("Queso blanco", 30, True)]),
    ("Platos fuertes", "Cocina", "Pabellón criollo", "9.50", [("Carne mechada", 150, False), ("Arroz", 150, False), ("Caraotas negras", 120, False), ("Plátano maduro", 100, True)]),
    ("Platos fuertes", "Cocina", "Pollo a la plancha", "8.50", [("Pechuga de pollo", 250, False), ("Arroz", 120, False), ("Lechuga", 40, True), ("Tomate", 40, True)]),
    ("Platos fuertes", "Cocina", "Cachapa con queso", "7.00", [("Harina de maíz precocida", 150, False), ("Queso blanco", 120, False)]),
    ("Hamburguesas", "Cocina", "Hamburguesa clásica", "6.50", [("Pan de hamburguesa", 1, False), ("Carne molida", 150, False), ("Queso amarillo", 30, True), ("Lechuga", 20, True), ("Tomate", 30, True), ("Cebolla", 20, True), ("Salsa de ajo", 20, True)]),
    ("Hamburguesas", "Cocina", "Hamburguesa doble", "8.50", [("Pan de hamburguesa", 1, False), ("Carne molida", 300, False), ("Queso amarillo", 60, True), ("Tocineta", 40, True), ("Cebolla", 20, True), ("Salsa de ajo", 20, True)]),
    ("Hamburguesas", "Cocina", "Hamburguesa de pollo", "7.00", [("Pan de hamburguesa", 1, False), ("Pechuga de pollo", 150, False), ("Lechuga", 20, True), ("Tomate", 30, True), ("Salsa de ajo", 20, True)]),
    ("Entradas", "Cocina", "Tequeños (6)", "4.50", [("Tequeño", 6, False)]),
    ("Entradas", "Cocina", "Papas fritas", "3.00", [("Papas", 250, False), ("Aceite", 30, False)]),
    ("Bebidas", "Barra", "Pepsi", "1.50", []),
    ("Bebidas", "Barra", "Agua mineral", "1.00", []),
    ("Bebidas", "Barra", "Malta", "1.50", []),
    ("Bebidas", "Barra", "Cerveza nacional", "2.00", []),
    ("Bebidas", "Barra", "Jugo de lechosa", "2.50", [("Lechosa", 250, False), ("Azúcar", 20, True)]),
    ("Bebidas", "Barra", "Jugo de parchita", "3.00", [("Parchita", 120, False), ("Azúcar", 25, True)]),
    ("Bebidas", "Barra", "Limonada", "2.50", [("Limón", 3, False), ("Azúcar", 30, True)]),
    ("Bebidas", "Barra", "Café", "1.50", [("Café molido", 12, False), ("Azúcar", 10, True)]),
    ("Postres", "Cocina", "Quesillo", "3.50", []),
    ("Postres", "Cocina", "Torta tres leches", "4.00", []),
    ("Postres", "Cocina", "Brownie con helado", "4.50", [("Brownie", 1, False), ("Helado de vainilla", 100, True)]),
]
CATEGORIAS = ["Arepas", "Platos fuertes", "Hamburguesas", "Entradas", "Bebidas", "Postres"]

ZONAS = [("Salón", "Mesa", 10, FormaMesa.cuadrada), ("Terraza", "Terraza", 6, FormaMesa.redonda)]

_TODOS = {m: (True, True, True, True) for m in Modulo}
# rol -> descripción, {módulo: (crear, leer, editar, eliminar)}
ROLES = {
    "Mesero": ("Toma pedidos en sala y consulta el menú.", {
        Modulo.comandas: (True, True, True, False), Modulo.mesas: (False, True, False, False),
        Modulo.productos: (False, True, False, False), Modulo.categorias: (False, True, False, False),
        Modulo.clientes: (True, True, True, False)}),
    "Cocina": ("Ve y despacha los platos de su estación.", {
        Modulo.cocina: (False, True, True, False), Modulo.comandas: (False, True, False, False),
        Modulo.productos: (False, True, False, False), Modulo.inventario: (False, True, False, False)}),
    "Cajero": ("Cobra, abre y cierra la caja.", {
        Modulo.caja: (True, True, True, False), Modulo.comandas: (True, True, True, False),
        Modulo.ventas: (False, True, False, False), Modulo.clientes: (True, True, True, False),
        Modulo.mesas: (False, True, False, False), Modulo.productos: (False, True, False, False)}),
}


@dataclass
class Resumen:
    creado: dict[str, int] = field(default_factory=dict)
    usuarios: list[tuple[str, str]] = field(default_factory=list)  # (rol, correo)

    def sumar(self, que: str, n: int = 1) -> None:
        if n:
            self.creado[que] = self.creado.get(que, 0) + n


def correo_demo(rol: str, dominio: str) -> str:
    return f"{rol.lower()}@{dominio}"


async def preparar(
    session,
    *,
    email: str,
    nombre: str,
    password: str,
    tasa_bcv: Decimal = Decimal("36.50"),
    zona_horaria: str = "America/Caracas",
    token: str | None = None,
    dominio_correos: str = "demo.turestify.com",
) -> Resumen:
    """Deja la instancia lista. Si ya hay datos, solo agrega lo que falte."""
    TypeAdapter(Password).validate_python(password)
    r = Resumen()
    email = email.lower()

    # --- administrador, sucursal y monedas (lo que hace el asistente de configuración)
    admin = await session.scalar(select(Usuario).where(Usuario.es_superadmin.is_(True)).order_by(Usuario.id))
    if admin is None:
        admin = Usuario(email=email, nombre=nombre, password_hash=hash_password(password), es_superadmin=True)
        session.add(admin)
        r.sumar("administradores")
    sucursal = await session.scalar(select(Sucursal).where(Sucursal.activa.is_(True)).order_by(Sucursal.id))
    if sucursal is None:
        sucursal = Sucursal(
            nombre="Sucursal Centro", direccion="Av. Principal, Centro", telefono="0212-555-0100",
            rif="J-12345678-9", razon_social="Restaurante Demo C.A.", domicilio_fiscal="Av. Principal, Centro",
            precios_incluyen_iva=True, cobra_igtf=False,
        )
        session.add(sucursal)
        r.sumar("sucursales")
    await session.flush()

    if not await session.scalar(select(exists().where(Moneda.es_principal.is_(True)))):
        session.add(Moneda(codigo="USD", nombre="Dólar", simbolo="$", es_principal=True, tasa=Decimal(1),
                           operacion=Operacion.multiplicar, es_divisa=True))
        r.sumar("monedas")
    if not await session.scalar(select(Moneda).where(Moneda.codigo == "VES")):
        session.add(Moneda(codigo="VES", nombre="Bolívar", simbolo="Bs", tasa=tasa_bcv,
                           operacion=Operacion.multiplicar, es_fiscal=True))
        r.sumar("monedas")
    await session.flush()
    principal = await session.scalar(select(Moneda).where(Moneda.es_principal.is_(True)))
    if principal.codigo != "USD":
        # Los precios del menú están en dólares: con otra moneda principal quedarían mal sin avisar
        raise ValueError(
            f"La moneda principal de esta instancia es {principal.codigo} y la demo usa precios en USD. "
            "Elimina el cliente y créalo de nuevo desde el panel."
        )

    cambios = {"timezone": zona_horaria}
    if token:
        cambios["panel_token"] = token.strip()
    await config.guardar(session, cambios, admin.id)

    # --- estaciones y unidades de fábrica (por si la base se vació)
    estaciones = {e.nombre: e for e in await session.scalars(select(Estacion))}
    for orden, nom in enumerate(["Cocina", "Barra"]):
        if nom not in estaciones:
            estaciones[nom] = Estacion(nombre=nom, orden=orden)
            session.add(estaciones[nom])
            r.sumar("estaciones")
    await unidades_srv.asegurar_base(session)
    await session.flush()
    unidades = {u.codigo: u for u in await session.scalars(select(UnidadMedida))}

    # --- proveedores
    proveedores = {p.nombre: p for p in await session.scalars(select(Proveedor))}
    prov = {}
    for clave, datos in PROVEEDORES.items():
        if datos["nombre"] not in proveedores:
            proveedores[datos["nombre"]] = Proveedor(**datos)
            session.add(proveedores[datos["nombre"]])
            r.sumar("proveedores")
        prov[clave] = proveedores[datos["nombre"]]
    await session.flush()

    # --- insumos (con presentaciones) y su compra inicial: deja el stock y el último costo
    existentes = {i.nombre: i for i in await session.scalars(select(Insumo))}
    nuevos: dict[str, tuple] = {}
    for fila in INSUMOS:
        nom, unidad, clave, pres, cant_pres, precio, n_comprado, minimo = fila
        if nom in existentes:
            continue
        ins = Insumo(nombre=nom, unidad=unidad, unidad_ref=unidades[unidad],
                     presentaciones=[Presentacion(nombre=pres, cantidad=Decimal(cant_pres))])
        session.add(ins)
        existentes[nom] = ins
        nuevos[nom] = (clave, Decimal(cant_pres) * n_comprado, Decimal(precio) * n_comprado, Decimal(minimo))
        r.sumar("insumos")
    await session.flush()

    por_proveedor: dict[str, list[str]] = {}
    for nom, (clave, *_rest) in nuevos.items():
        por_proveedor.setdefault(clave, []).append(nom)
    for n, (clave, nombres) in enumerate(sorted(por_proveedor.items())):
        total = sum((nuevos[x][2] for x in nombres), Decimal(0))
        compra = Compra(
            sucursal_id=sucursal.id, proveedor_id=prov[clave].id, numero_documento=f"FAC-{1001 + n:06d}",
            fecha=date.today() - timedelta(days=2 + n), moneda_id=principal.id, tasa=Decimal(1), total=total,
            total_principal=total, notas="Compra inicial de la demostración", registrada_por_id=admin.id,
            items=[CompraItem(insumo_id=existentes[x].id, insumo=existentes[x], cantidad=nuevos[x][1], subtotal=nuevos[x][2]) for x in nombres],
        )
        session.add(compra)
        await session.flush()
        for x in nombres:
            ins = existentes[x]
            inv = Inventario(sucursal_id=sucursal.id, insumo_id=ins.id, insumo=ins, cantidad=0, reservado=0, stock_minimo=nuevos[x][3])
            session.add(inv)
            await session.flush()
            await stock.registrar_entrada(session, inv.id, nuevos[x][1], f"Compra #{compra.id} · {prov[clave].nombre}", admin.id)
            ins.costo_unitario = (nuevos[x][2] / nuevos[x][1]).quantize(SEIS)
        r.sumar("compras")

    # --- menú
    categorias = {c.nombre: c for c in await session.scalars(select(Categoria))}
    for orden, nom in enumerate(CATEGORIAS):
        if nom not in categorias:
            est = estaciones["Barra" if nom == "Bebidas" else "Cocina"]
            categorias[nom] = Categoria(nombre=nom, orden=orden, estacion_id=est.id)
            session.add(categorias[nom])
            r.sumar("categorías")
    await session.flush()

    productos = set(await session.scalars(select(Producto.nombre)))
    for orden, (cat, est, nom, precio, ingredientes) in enumerate(MENU):
        if nom in productos:
            continue
        directo = existentes[REVENTA[nom]].id if nom in REVENTA else None
        receta = None
        if directo is None:
            receta = Receta(nombre=nom, ingredientes=[
                RecetaInsumo(insumo_id=existentes[i].id, cantidad=Decimal(c), removible=q) for i, c, q in ingredientes])
            session.add(receta)
            await session.flush()
        foto = FOTOS.get(nom)
        session.add(Producto(
            nombre=nom, categoria_id=categorias[cat].id, estacion_id=estaciones[est].id,
            receta_id=receta.id if receta else None, insumo_id=directo, precio_base=Decimal(precio), orden=orden,
            sucursales=[],
            medios=[ProductoMedio(tipo=TipoMedio.imagen, url=foto, orden=0, es_portada=True, texto_alt=nom)] if foto else [],
        ))
        r.sumar("productos")

    # --- zonas y mesas (con su QR)
    zonas = {z.nombre: z for z in await session.scalars(select(Zona).where(Zona.sucursal_id == sucursal.id))}
    mesas = set(await session.scalars(select(Mesa.nombre).where(Mesa.sucursal_id == sucursal.id)))
    for orden, (zona_nom, prefijo, cuantas, forma) in enumerate(ZONAS):
        if zona_nom not in zonas:
            zonas[zona_nom] = Zona(sucursal_id=sucursal.id, nombre=zona_nom, orden=orden)
            session.add(zonas[zona_nom])
            r.sumar("zonas")
            await session.flush()
        for i in range(cuantas):
            nombre_mesa = f"{prefijo} {i + 1}"
            if nombre_mesa in mesas:
                continue
            session.add(Mesa(
                sucursal_id=sucursal.id, zona_id=zonas[zona_nom].id, nombre=nombre_mesa,
                capacidad=6 if (zona_nom == "Salón" and i >= 8) else 4, qr_token=new_public_token(),
                forma=FormaMesa.rectangular if (zona_nom == "Salón" and i >= 8) else forma,
                pos_x=(i % 4) * 3, pos_y=(i // 4) * 2,
            ))
            r.sumar("mesas")

    # --- roles y un usuario de cada uno (misma contraseña que el administrador)
    roles = {x.nombre: x for x in await session.scalars(select(Rol))}
    for nom, (desc, permisos) in ROLES.items():
        if nom not in roles:
            roles[nom] = Rol(nombre=nom, descripcion=desc, permisos=[
                RolPermiso(modulo=str(m), crear=c, leer=le, editar=e, eliminar=d) for m, (c, le, e, d) in permisos.items()])
            session.add(roles[nom])
            r.sumar("roles")
    await session.flush()
    for nom in ROLES:
        correo = correo_demo(nom, dominio_correos)
        r.usuarios.append((nom, correo))
        if not await session.scalar(select(exists().where(Usuario.email == correo))):
            session.add(Usuario(email=correo, nombre=f"{nom} Demo", password_hash=hash_password(password),
                                rol_id=roles[nom].id, sucursales=[sucursal]))
            r.sumar("usuarios")

    await session.commit()
    config.invalidar()
    return r
