from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Categoria, Inventario, Producto, Sucursal
from app.models.catalogo import disponible_en_sucursal, precio_en_sucursal, precio_final
from app.services.monedas import moneda_principal, monedas_activas, montos_en_monedas


async def disponibles_por_insumo(session: AsyncSession, sucursal_id: int) -> dict[int, Decimal]:
    rows = await session.execute(
        select(Inventario.insumo_id, Inventario.cantidad - Inventario.reservado).where(
            Inventario.sucursal_id == sucursal_id
        )
    )
    return {insumo_id: disponible for insumo_id, disponible in rows.all()}


def porciones(producto: Producto, disponibles: dict[int, Decimal]) -> int | None:
    """Cuántas porciones completas se pueden vender. None = no controla stock (sin límite)."""
    receta = producto.receta
    if receta is not None and not receta.activa:
        return 0
    consumo = producto.consumo()
    if not consumo:
        return None
    return min(int(disponibles.get(insumo_id, Decimal(0)) // cantidad) for insumo_id, cantidad in consumo)


async def productos_vendibles(session: AsyncSession, sucursal_id: int) -> list[tuple[Producto, int | None]]:
    productos = await session.scalars(
        select(Producto)
        .outerjoin(Categoria, Producto.categoria_id == Categoria.id)
        .where(Producto.activo.is_(True), (Categoria.id.is_(None)) | (Categoria.activa.is_(True)))
        .order_by(Producto.orden, Producto.nombre)
    )
    disponibles = await disponibles_por_insumo(session, sucursal_id)
    resultado = []
    for p in productos.unique():
        if not disponible_en_sucursal(p, sucursal_id):
            continue
        n = porciones(p, disponibles)
        if n is None or n > 0:
            resultado.append((p, n))
    return resultado


async def construir_menu(session: AsyncSession, sucursal: Sucursal) -> dict:
    monedas = await monedas_activas(session)
    principal = await moneda_principal(session)
    vendibles = await productos_vendibles(session, sucursal.id)

    categorias: dict[int | None, dict] = {}
    orden_cat: dict[int | None, tuple] = {}
    for p, n in vendibles:
        cat_id = p.categoria.id if p.categoria else None
        if cat_id not in categorias:
            categorias[cat_id] = {
                "id": cat_id,
                "nombre": p.categoria.nombre if p.categoria else "Otros",
                "productos": [],
            }
            orden_cat[cat_id] = (p.categoria.orden, p.categoria.nombre) if p.categoria else (10**9, "")
        precio = precio_final(p, sucursal)
        categorias[cat_id]["productos"].append(
            {
                "id": p.id,
                "nombre": p.nombre,
                "descripcion": p.descripcion,
                "precio": precio,
                "precios": montos_en_monedas(precio, monedas),
                "precio_sin_iva": _sin_iva(precio_en_sucursal(p, sucursal.id), p.alicuota_iva, sucursal.precios_incluyen_iva),
                "alicuota_iva": p.alicuota_iva,
                "medios": p.medios,
                "porciones_disponibles": n,
                "ingredientes": [
                    {"insumo_id": ri.insumo_id, "nombre": ri.insumo.nombre}
                    for ri in (p.receta.ingredientes if p.receta and p.receta.activa else [])
                    if ri.removible
                ],
            }
        )

    return {
        "sucursal_id": sucursal.id,
        "sucursal": sucursal.nombre,
        "moneda_principal": principal.codigo,
        "precios_incluyen_iva": sucursal.precios_incluyen_iva,
        "monedas": monedas,
        "categorias": [categorias[k] for k in sorted(categorias, key=lambda k: orden_cat[k])],
    }


def _sin_iva(precio: Decimal, alicuota: Decimal, incluido: bool) -> Decimal:
    """Precio antes de IVA (para mostrar "Bs 10 + IVA" o el desglose)."""
    if not incluido or not alicuota:
        return precio
    return (precio / (1 + alicuota / 100)).quantize(Decimal("0.01"))
