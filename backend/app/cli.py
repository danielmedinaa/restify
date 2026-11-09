"""Comandos de administración.

  docker compose exec api python -m app.cli crear-superadmin --email admin@restify.com --nombre "Admin"
  docker compose exec api python -m app.cli crear-api-key --nombre "Panel web"
  docker compose exec api python -m app.cli crear-moneda-principal --codigo USD --nombre Dólar --simbolo '$'
  docker compose exec api python -m app.cli sembrar-demo     # menú, insumos y stock de ejemplo (BD sin datos de negocio)
  printf '%s' "$CLAVE" | docker compose exec -T api python -m app.cli preparar-demo --email admin@... --password-stdin
      # instancia de demostración COMPLETA (proveedores, compras, menú, mesas, roles y usuarios); se puede repetir
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import exists, select

from app.core.database import SessionLocal, engine
from app.core.security import hash_password, new_api_key
from decimal import Decimal

from app.models import (
    ApiKey,
    Categoria,
    Estacion,
    Insumo,
    Inventario,
    Moneda,
    Operacion,
    Producto,
    ProductoMedio,
    Receta,
    RecetaInsumo,
    Sucursal,
    TipoMedio,
    Unidad,
    UnidadMedida,
    Usuario,
)
from app.schemas.usuarios import Password
from app.services import unidades as unidades_srv


async def crear_superadmin(email: str, nombre: str) -> None:
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Repite la contraseña: "):
        sys.exit("Las contraseñas no coinciden")
    try:
        TypeAdapter(Password).validate_python(password)
    except ValidationError as e:
        sys.exit(e.errors()[0]["msg"])

    async with SessionLocal() as session:
        if await session.scalar(select(exists().where(Usuario.email == email.lower()))):
            sys.exit("Ya existe un usuario con ese email")
        session.add(
            Usuario(email=email.lower(), nombre=nombre, password_hash=hash_password(password), es_superadmin=True)
        )
        await session.commit()
    print(f"Superadmin {email} creado.")


async def crear_api_key(nombre: str) -> None:
    clave, prefijo, key_hash = new_api_key()
    async with SessionLocal() as session:
        session.add(ApiKey(nombre=nombre, prefijo=prefijo, key_hash=key_hash))
        await session.commit()
    print("API key creada. Guárdala ahora, no se volverá a mostrar:\n")
    print(f"  {clave}\n")


async def crear_moneda_principal(codigo: str, nombre: str, simbolo: str) -> None:
    async with SessionLocal() as session:
        if await session.scalar(select(exists().where(Moneda.es_principal.is_(True)))):
            sys.exit("Ya existe una moneda principal")
        session.add(
            Moneda(
                codigo=codigo.upper(),
                nombre=nombre,
                simbolo=simbolo,
                es_principal=True,
                tasa=1,
                operacion=Operacion.multiplicar,
            )
        )
        await session.commit()
    print(f"Moneda principal {codigo.upper()} creada.")


# nombre -> (unidad, stock inicial, stock mínimo)
_INSUMOS = {
    "Pan de hamburguesa": (Unidad.unidad, 80, 15),
    "Carne molida": (Unidad.g, 15000, 3000),
    "Pechuga de pollo": (Unidad.g, 8000, 2000),
    "Queso amarillo": (Unidad.g, 4000, 800),
    "Tocineta": (Unidad.g, 3000, 600),
    "Lechuga": (Unidad.g, 2500, 500),
    "Tomate": (Unidad.g, 3000, 600),
    "Cebolla": (Unidad.g, 3000, 600),
    "Salsa de la casa": (Unidad.ml, 4000, 800),
    "Papas": (Unidad.g, 20000, 4000),
    "Aceite": (Unidad.ml, 10000, 2000),
    "Tequeño": (Unidad.unidad, 120, 24),
    "Pepsi lata": (Unidad.unidad, 96, 24),
    "Agua mineral": (Unidad.unidad, 60, 12),
    "Limón": (Unidad.unidad, 60, 15),
    "Azúcar": (Unidad.g, 5000, 1000),
    "Café molido": (Unidad.g, 3000, 500),
    "Brownie": (Unidad.unidad, 30, 6),
    "Helado de vainilla": (Unidad.g, 5000, 1000),
}

_REVENTA = {"Pepsi", "Agua mineral"}

# categoría, estación, nombre, precio (Bs, IVA incluido), receta [(insumo, cantidad, quitable)], foto (URL externa)
_MENU = [
    ("Hamburguesas", "Cocina", "Hamburguesa clásica", 4500, [("Pan de hamburguesa", 1, False), ("Carne molida", 150, False), ("Queso amarillo", 30, True), ("Lechuga", 20, True), ("Tomate", 30, True), ("Cebolla", 20, True), ("Salsa de la casa", 20, True)], "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=1200&q=80&fit=crop"),
    ("Hamburguesas", "Cocina", "Hamburguesa doble", 6500, [("Pan de hamburguesa", 1, False), ("Carne molida", 300, False), ("Queso amarillo", 60, True), ("Tocineta", 40, True), ("Cebolla", 20, True), ("Salsa de la casa", 20, True)], "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=1200&q=80&fit=crop"),
    ("Hamburguesas", "Cocina", "Hamburguesa de pollo", 5000, [("Pan de hamburguesa", 1, False), ("Pechuga de pollo", 150, False), ("Lechuga", 20, True), ("Tomate", 30, True), ("Salsa de la casa", 20, True)], "https://images.unsplash.com/photo-1550547660-d9450f859349?w=1200&q=80&fit=crop"),
    ("Entradas", "Cocina", "Papas fritas", 2500, [("Papas", 250, False), ("Aceite", 30, False)], "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?w=1200&q=80&fit=crop"),
    ("Entradas", "Cocina", "Tequeños (6)", 3000, [("Tequeño", 6, False)], None),
    ("Bebidas", "Barra", "Pepsi", 1500, [("Pepsi lata", 1, False)], "https://images.unsplash.com/photo-1556679343-c7306c1976bc?w=1200&q=80&fit=crop"),
    ("Bebidas", "Barra", "Agua mineral", 1000, [("Agua mineral", 1, False)], "https://images.unsplash.com/photo-1523362628745-0c100150b504?w=1200&q=80&fit=crop"),
    ("Bebidas", "Barra", "Limonada", 2000, [("Limón", 3, False), ("Azúcar", 30, False)], "https://images.unsplash.com/photo-1556881286-fc6915169721?w=1200&q=80&fit=crop"),
    ("Bebidas", "Barra", "Café", 1200, [("Café molido", 10, False), ("Azúcar", 10, True)], "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=1200&q=80&fit=crop"),
    ("Postres", "Cocina", "Brownie con helado", 3500, [("Brownie", 1, False), ("Helado de vainilla", 100, True)], "https://images.unsplash.com/photo-1551024506-0bccd828d307?w=1200&q=80&fit=crop"),
]


async def sembrar_demo() -> None:
    """Menú de ejemplo con insumos, recetas y stock. Solo corre si no hay productos ni insumos."""
    async with SessionLocal() as session:
        if await session.scalar(select(exists().where(Producto.id.is_not(None)))) or await session.scalar(
            select(exists().where(Insumo.id.is_not(None)))
        ):
            sys.exit("Ya hay productos o insumos; limpia los datos de negocio antes de sembrar.")
        sucursales = list((await session.scalars(select(Sucursal).where(Sucursal.activa.is_(True)))).all())
        estaciones = {e.nombre: e for e in await session.scalars(select(Estacion))}
        if not sucursales:
            sys.exit("Crea una sucursal primero.")

        await unidades_srv.asegurar_base(session)
        unidades = {u.codigo: u for u in await session.scalars(select(UnidadMedida))}
        insumos: dict[str, Insumo] = {}
        for nombre, (unidad, stock, minimo) in _INSUMOS.items():
            insumos[nombre] = Insumo(nombre=nombre, unidad=unidad.value, unidad_ref=unidades[unidad.value], presentaciones=[])
            session.add(insumos[nombre])
        await session.flush()
        for suc in sucursales:
            for nombre, (_, stock, minimo) in _INSUMOS.items():
                session.add(
                    Inventario(sucursal_id=suc.id, insumo_id=insumos[nombre].id, cantidad=Decimal(stock), reservado=Decimal(0), stock_minimo=Decimal(minimo))
                )

        categorias: dict[str, Categoria] = {}
        for orden, nombre in enumerate(["Hamburguesas", "Entradas", "Bebidas", "Postres"]):
            est = estaciones.get("Barra" if nombre == "Bebidas" else "Cocina")
            categorias[nombre] = Categoria(nombre=nombre, orden=orden, estacion_id=est.id if est else None)
            session.add(categorias[nombre])
        await session.flush()

        for orden, (cat, est, nombre, precio, ingredientes, foto) in enumerate(_MENU):
            # Bebidas embotelladas: sin receta, descuentan directo su propio insumo
            directo = insumos[ingredientes[0][0]].id if nombre in _REVENTA else None
            receta = None
            if directo is None:
                receta = Receta(
                    nombre=nombre,
                    ingredientes=[
                        RecetaInsumo(insumo_id=insumos[i].id, cantidad=Decimal(c), removible=q) for i, c, q in ingredientes
                    ],
                )
                session.add(receta)
                await session.flush()
            session.add(
                Producto(
                    nombre=nombre,
                    categoria_id=categorias[cat].id,
                    estacion_id=estaciones[est].id if est in estaciones else None,
                    receta_id=receta.id if receta else None,
                    insumo_id=directo,
                    precio_base=Decimal(precio),
                    orden=orden,
                    sucursales=[],
                    medios=[ProductoMedio(tipo=TipoMedio.imagen, url=foto, orden=0, es_portada=True, texto_alt=nombre)] if foto else [],
                )
            )
        await session.commit()
    print(f"Listo: {len(_INSUMOS)} insumos, {len(_MENU)} productos con receta y stock en {len(sucursales)} sucursal(es).")


async def preparar_demo(args) -> None:
    from decimal import Decimal

    from app import demo

    password_usuarios = None
    if args.password_stdin:
        # línea 1: contraseña del administrador · línea 2 (opcional): la de los usuarios demo; vacía = la misma
        lineas = sys.stdin.read().split("\n")
        password = lineas[0]
        password_usuarios = lineas[1] if len(lineas) > 1 and lineas[1] else None
    else:
        password = getpass.getpass("Contraseña del administrador y de los usuarios demo: ")
    try:
        async with SessionLocal() as session:
            r = await demo.preparar(
                session, email=args.email, nombre=args.nombre, password=password, password_usuarios=password_usuarios,
                tasa_bcv=Decimal(args.tasa_bcv),
                zona_horaria=args.zona_horaria, token=args.token, dominio_correos=args.dominio_correos,
            )
    except ValidationError as e:
        sys.exit(e.errors()[0]["msg"])
    except ValueError as e:
        sys.exit(str(e))
    if r.creado:
        print("Creado: " + ", ".join(f"{n} {k}" for k, n in r.creado.items()))
    else:
        print("Nada que crear: la instancia ya estaba completa.")
    print(f"Administrador: {args.email}")
    for rol, correo in r.usuarios:
        print(f"{rol}: {correo}")
    print("(el administrador con su contraseña; los usuarios demo con la suya)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("crear-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--nombre", required=True)

    p = sub.add_parser("crear-api-key")
    p.add_argument("--nombre", required=True)

    sub.add_parser("sembrar-demo")

    p = sub.add_parser("preparar-demo", help="Instancia de demostración completa (idempotente)")
    p.add_argument("--email", required=True)
    p.add_argument("--nombre", default="Administrador")
    p.add_argument("--password-stdin", action="store_true", help="Lee la contraseña de la entrada estándar")
    p.add_argument("--tasa-bcv", default="36.50", help="Bolívares por dólar (cámbiala a la tasa del día)")
    p.add_argument("--zona-horaria", default="America/Caracas")
    p.add_argument("--token", default=None, help="Token de la instancia en el panel de RESTIFY (opcional)")
    p.add_argument("--dominio-correos", default="demo.turestify.com", help="Dominio de los usuarios demo (mesero@...)")

    p = sub.add_parser("crear-moneda-principal")
    p.add_argument("--codigo", required=True)
    p.add_argument("--nombre", required=True)
    p.add_argument("--simbolo", required=True)

    args = parser.parse_args()

    async def run():
        try:
            if args.comando == "crear-superadmin":
                await crear_superadmin(args.email, args.nombre)
            elif args.comando == "crear-api-key":
                await crear_api_key(args.nombre)
            elif args.comando == "sembrar-demo":
                await sembrar_demo()
            elif args.comando == "preparar-demo":
                await preparar_demo(args)
            else:
                await crear_moneda_principal(args.codigo, args.nombre, args.simbolo)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
