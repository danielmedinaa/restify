from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select

from app.api.deps import SessionDep, requiere, sucursales_visibles, verificar_sucursal
from app.api.utils import Limite, Offset, aplicar_cambios, guardar, insertar, obtener_o_404, paginar
from app.core.errors import NoEncontrado
from app.models import Accion, Compra, CompraItem, Insumo, Inventario, Modulo, Moneda, Producto, Proveedor, Sucursal, Usuario
from app.models.catalogo import precio_final
from app.schemas.base import Pagina
from app.schemas.compras import CompraIn, CompraOut, ProveedorIn, ProveedorOut, ProveedorUpdate, RentabilidadOut
from app.services import bitacora, stock
from app.services.menu import _sin_iva
from app.services.monedas import a_principal, q2

router = APIRouter()

SEIS = Decimal("0.000001")


def _perm(modulo: Modulo, accion: Accion):
    return Depends(requiere(modulo, accion))


# ============================================================ Proveedores
@router.get("/proveedores", response_model=list[ProveedorOut], tags=["Compras"], dependencies=[_perm(Modulo.compras, Accion.leer)])
async def listar_proveedores(session: SessionDep, activo: bool | None = None):
    stmt = select(Proveedor).order_by(Proveedor.nombre)
    if activo is not None:
        stmt = stmt.where(Proveedor.activo.is_(activo))
    return (await session.scalars(stmt)).all()


@router.post("/proveedores", response_model=ProveedorOut, status_code=status.HTTP_201_CREATED, tags=["Compras"])
async def crear_proveedor(datos: ProveedorIn, session: SessionDep, usuario: Usuario = _perm(Modulo.compras, Accion.crear)):
    proveedor = Proveedor(**datos.model_dump())
    session.add(proveedor)
    await insertar(session, "Ya existe un proveedor con ese nombre")
    bitacora.registrar(session, usuario, "compras", "crear_proveedor", f"Registró al proveedor {proveedor.nombre}", entidad="proveedor", entidad_id=proveedor.id)
    await guardar(session, "Ya existe un proveedor con ese nombre")
    return proveedor


@router.patch("/proveedores/{proveedor_id}", response_model=ProveedorOut, tags=["Compras"])
async def editar_proveedor(
    proveedor_id: int, datos: ProveedorUpdate, session: SessionDep, usuario: Usuario = _perm(Modulo.compras, Accion.editar)
):
    proveedor = await obtener_o_404(session, Proveedor, proveedor_id, "Proveedor")
    if cambios := aplicar_cambios(proveedor, datos):
        bitacora.registrar(
            session, usuario, "compras", "editar_proveedor", f"Editó al proveedor {proveedor.nombre}: {', '.join(cambios)}",
            entidad="proveedor", entidad_id=proveedor.id,
        )
    await guardar(session, "Ya existe un proveedor con ese nombre")
    return proveedor


# ============================================================ Compras
def _compra_out(c: Compra) -> dict:
    return {
        "id": c.id,
        "sucursal_id": c.sucursal_id,
        "sucursal": c.sucursal.nombre,
        "proveedor_id": c.proveedor_id,
        "proveedor": c.proveedor.nombre if c.proveedor else None,
        "numero_documento": c.numero_documento,
        "fecha": c.fecha,
        "moneda": c.moneda.codigo,
        "simbolo": c.moneda.simbolo,
        "tasa": c.tasa,
        "total": c.total,
        "total_principal": c.total_principal,
        "notas": c.notas,
        "items": [
            {
                "insumo_id": i.insumo_id,
                "insumo": i.insumo.nombre,
                "codigo": i.insumo.codigo,
                "unidad": i.insumo.unidad,
                "cantidad": i.cantidad,
                "subtotal": i.subtotal,
                "costo_unitario": (a_principal(i.subtotal, c.tasa, c.moneda.operacion) / i.cantidad).quantize(SEIS),
            }
            for i in c.items
        ],
        "created_at": c.created_at,
    }


@router.get("/compras", response_model=Pagina[CompraOut], tags=["Compras"])
async def listar_compras(
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.compras, Accion.leer),
    sucursal_id: int | None = None,
    proveedor_id: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Compra).order_by(Compra.fecha.desc(), Compra.id.desc())
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(Compra.sucursal_id.in_(ids))
    if proveedor_id is not None:
        stmt = stmt.where(Compra.proveedor_id == proveedor_id)
    if desde:
        stmt = stmt.where(Compra.fecha >= desde)
    if hasta:
        stmt = stmt.where(Compra.fecha <= hasta)
    pagina = await paginar(session, stmt, limite, offset)
    pagina["items"] = [_compra_out(c) for c in pagina["items"]]
    return pagina


@router.get("/compras/{compra_id}", response_model=CompraOut, tags=["Compras"])
async def obtener_compra(compra_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.compras, Accion.leer)):
    compra = await obtener_o_404(session, Compra, compra_id, "Compra")
    verificar_sucursal(usuario, compra.sucursal_id)
    return _compra_out(compra)


@router.post("/compras", response_model=CompraOut, status_code=status.HTTP_201_CREATED, tags=["Compras"])
async def registrar_compra(datos: CompraIn, session: SessionDep, usuario: Usuario = _perm(Modulo.compras, Accion.crear)):
    """Compra recibida: suma el stock de cada insumo en la sucursal y actualiza su costo (último costo)."""
    verificar_sucursal(usuario, datos.sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, datos.sucursal_id, "Sucursal")
    moneda = await obtener_o_404(session, Moneda, datos.moneda_id, "Moneda")
    proveedor = await obtener_o_404(session, Proveedor, datos.proveedor_id, "Proveedor") if datos.proveedor_id else None
    insumos = {i.id: i for i in await session.scalars(select(Insumo).where(Insumo.id.in_([x.insumo_id for x in datos.items])))}
    if faltan := {x.insumo_id for x in datos.items} - insumos.keys():
        raise NoEncontrado(f"Insumo {sorted(faltan)}")
    # En la compra la cantidad puede venir en envases (3 cajas x24); el stock siempre se lleva en la unidad del insumo
    cantidades = {}
    for n, x in enumerate(datos.items):
        cantidades[n] = stock.resolver_cantidad(insumos[x.insumo_id], x.cantidad, x.presentacion_id)
        stock.validar_cantidad_unidad(cantidades[n], insumos[x.insumo_id])

    total = q2(sum((x.subtotal for x in datos.items), Decimal(0)))
    compra = Compra(
        sucursal_id=sucursal.id,
        proveedor_id=proveedor.id if proveedor else None,
        numero_documento=datos.numero_documento,
        fecha=datos.fecha or date.today(),
        moneda_id=moneda.id,
        tasa=Decimal(1) if moneda.es_principal else moneda.tasa,
        total=total,
        total_principal=a_principal(total, Decimal(1) if moneda.es_principal else moneda.tasa, moneda.operacion),
        notas=datos.notas,
        registrada_por_id=usuario.id,
        items=[CompraItem(insumo_id=x.insumo_id, insumo=insumos[x.insumo_id], cantidad=cantidades[n], subtotal=x.subtotal) for n, x in enumerate(datos.items)],
    )
    session.add(compra)
    await insertar(session)

    existentes = {
        inv.insumo_id: inv
        for inv in await session.scalars(
            select(Inventario).where(Inventario.sucursal_id == sucursal.id, Inventario.insumo_id.in_(insumos.keys()))
        )
    }
    origen = f"Compra #{compra.id}" + (f" · {proveedor.nombre}" if proveedor else "")
    for n, x in enumerate(datos.items):
        insumo = insumos[x.insumo_id]
        cant = cantidades[n]
        inv = existentes.get(insumo.id)
        if inv is None:
            inv = Inventario(sucursal_id=sucursal.id, insumo_id=insumo.id, insumo=insumo, cantidad=0, reservado=0, stock_minimo=0)
            session.add(inv)
            await session.flush()
            existentes[insumo.id] = inv
        await stock.registrar_entrada(session, inv.id, cant, origen, usuario.id)
        if x.subtotal > 0:
            insumo.costo_unitario = (a_principal(x.subtotal, compra.tasa, moneda.operacion) / cant).quantize(SEIS)

    bitacora.registrar(
        session, usuario, "compras", "registrar",
        f"Registró la compra #{compra.id}{' a ' + proveedor.nombre if proveedor else ''} en {sucursal.nombre} por "
        f"{bitacora.dinero(total, moneda.simbolo)} ({len(datos.items)} insumos)",
        sucursal_id=sucursal.id, entidad="compra", entidad_id=compra.id,
    )
    await guardar(session)
    return _compra_out(await obtener_o_404(session, Compra, compra.id, "Compra"))


# ============================================================ Rentabilidad (costo de receta y margen)
@router.get("/rentabilidad", response_model=list[RentabilidadOut], tags=["Compras"])
async def rentabilidad(
    sucursal_id: int,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.ventas, Accion.leer),
    q: str | None = Query(default=None, max_length=100),
):
    """Costo de cada plato según su receta y el último costo de cada insumo, contra su precio sin IVA."""
    verificar_sucursal(usuario, sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    stmt = select(Producto).where(Producto.activo.is_(True)).order_by(Producto.nombre)
    if q:
        stmt = stmt.where(or_(Producto.nombre.ilike(f"%{q}%"), Producto.codigo.ilike(f"%{q}%")))
    filas = []
    for p in await session.scalars(stmt):
        precio = precio_final(p, sucursal)
        sin_iva = _sin_iva(precio, p.alicuota_iva, True)
        costo, faltan = None, []
        lineas = (
            [(ri.insumo, ri.cantidad) for ri in p.receta.ingredientes]
            if p.receta
            else [(p.insumo, p.cantidad_por_venta)] if p.insumo else []
        )
        if lineas:
            faltan = [ins.nombre for ins, _ in lineas if ins.costo_unitario is None]
            if not faltan:
                costo = q2(sum((cant * ins.costo_unitario for ins, cant in lineas), Decimal(0)))
        margen = None if costo is None else sin_iva - costo
        filas.append(
            {
                "producto_id": p.id,
                "producto": p.nombre,
                "codigo": p.codigo,
                "categoria": p.categoria.nombre if p.categoria else None,
                "precio": precio,
                "precio_sin_iva": sin_iva,
                "costo": costo,
                "margen": margen,
                "margen_pct": None if margen is None or not sin_iva else q2(margen / sin_iva * 100),
                "costo_pct": None if costo is None or not sin_iva else q2(costo / sin_iva * 100),
                "sin_receta": not lineas,
                "insumos_sin_costo": faltan,
            }
        )
    return filas

