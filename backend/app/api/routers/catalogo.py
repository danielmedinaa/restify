import io
from decimal import Decimal
from typing import Annotated, Literal

import segno
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy import exists, func, or_, select, update

from app.api.deps import SessionDep, UsuarioActual, requiere, sucursales_visibles, verificar_sucursal
from app.api.utils import Limite, Offset, aplicar_cambios, guardar, insertar, obtener_o_404, paginar
from app.core.errors import Conflicto, Invalido, NoEncontrado, Prohibido
from app.core.realtime import canal_sucursal, emitir
from app.models import (
    Accion,
    AlertaStock,
    Categoria,
    Estacion,
    EstadoAlerta,
    Insumo,
    Inventario,
    Modulo,
    Moneda,
    MovimientoStock,
    Operacion,
    Producto,
    ProductoMedio,
    ProductoSucursal,
    Presentacion,
    Receta,
    RecetaInsumo,
    Sucursal,
    UnidadMedida,
    Usuario,
)
from app.schemas.base import Pagina
from app.schemas.catalogo import (
    AjusteIn,
    AlertaOut,
    CategoriaIn,
    CategoriaOut,
    CategoriaUpdate,
    EstacionIn,
    EstacionOut,
    EstacionUpdate,
    IngredienteIn,
    InsumoIn,
    InsumoEncontradoOut,
    InsumoOut,
    InsumoUpdate,
    InventarioIn,
    InventarioOut,
    InventarioUpdate,
    MedioOut,
    MedioUpdate,
    MedioUrlIn,
    MenuOut,
    MonedaIn,
    MonedaOut,
    MonedaUpdate,
    MovimientoIn,
    MovimientoOut,
    ProductoIn,
    ProductoOut,
    ProductoSucursalIn,
    ProductoSucursalOut,
    PresentacionesIn,
    ProductoUpdate,
    RecetaIn,
    RecetaOut,
    RecetaUpdate,
    UnidadIn,
    UnidadOut,
    UnidadUpdate,
)
from app.services import bitacora, licencia, unidades as unidades_srv
from app.services import medios as medios_srv
from app.services import stock
from app.services.menu import construir_menu
from app.services.monedas import q2

router = APIRouter()


def _perm(modulo: Modulo, accion: Accion):
    return Depends(requiere(modulo, accion))


# ============================================================ Monedas
@router.get("/monedas", response_model=list[MonedaOut], tags=["Monedas"], dependencies=[_perm(Modulo.monedas, Accion.leer)])
async def listar_monedas(session: SessionDep):
    return (await session.scalars(select(Moneda).order_by(Moneda.es_principal.desc(), Moneda.codigo))).all()


@router.post(
    "/monedas",
    response_model=MonedaOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Monedas"],
    dependencies=[_perm(Modulo.monedas, Accion.crear)],
)
async def crear_moneda(datos: MonedaIn, session: SessionDep):
    hay_principal = await session.scalar(select(exists().where(Moneda.es_principal.is_(True))))
    if datos.es_principal and hay_principal:
        raise Conflicto("Ya existe una moneda principal; usa POST /monedas/{id}/principal para cambiarla")
    if not datos.es_principal and not hay_principal:
        raise Conflicto("La primera moneda debe ser la principal")
    if datos.es_fiscal:
        await _quitar_fiscal(session)
    moneda = Moneda(**datos.model_dump())
    if moneda.es_principal:
        moneda.tasa, moneda.operacion, moneda.activa = 1, Operacion.multiplicar, True
    session.add(moneda)
    await guardar(session, "Ya existe una moneda con ese código")
    return moneda


@router.patch("/monedas/{moneda_id}", response_model=MonedaOut, tags=["Monedas"], dependencies=[_perm(Modulo.monedas, Accion.editar)])
async def editar_moneda(moneda_id: int, datos: MonedaUpdate, session: SessionDep, usuario: UsuarioActual):
    moneda = await obtener_o_404(session, Moneda, moneda_id, "Moneda")
    tasa_antes = moneda.tasa
    if moneda.es_principal and (datos.tasa is not None or datos.operacion is not None or datos.activa is False):
        raise Conflicto("La moneda principal siempre tiene tasa 1 y no se puede desactivar")
    if datos.es_fiscal and not moneda.es_fiscal:
        await _quitar_fiscal(session)
    aplicar_cambios(moneda, datos)
    if datos.tasa is not None and datos.tasa != tasa_antes:
        bitacora.registrar(
            session, usuario, "monedas", "tasa",
            f"Cambió la tasa de {moneda.codigo}: {tasa_antes.normalize():f} → {moneda.tasa.normalize():f}",
            entidad="moneda", entidad_id=moneda.id, datos={"antes": tasa_antes, "despues": moneda.tasa},
        )
    else:
        bitacora.registrar(session, usuario, "monedas", "editar", f"Editó la moneda {moneda.codigo}", entidad="moneda", entidad_id=moneda.id)
    await guardar(session)
    return moneda


async def _quitar_fiscal(session) -> None:
    """Solo una moneda puede ser la fiscal: al marcar otra, la anterior deja de serlo."""
    await session.execute(update(Moneda).where(Moneda.es_fiscal.is_(True)).values(es_fiscal=False))
    await session.flush()


@router.post(
    "/monedas/{moneda_id}/principal",
    response_model=MonedaOut,
    tags=["Monedas"],
    dependencies=[_perm(Modulo.monedas, Accion.editar)],
)
async def hacer_principal(moneda_id: int, session: SessionDep):
    """Cambia la moneda principal. Recuerda actualizar las tasas de las demás monedas."""
    moneda = await obtener_o_404(session, Moneda, moneda_id, "Moneda")
    await session.execute(update(Moneda).where(Moneda.es_principal.is_(True)).values(es_principal=False))
    await session.flush()
    moneda.es_principal, moneda.tasa, moneda.operacion, moneda.activa = True, 1, Operacion.multiplicar, True
    await guardar(session)
    return moneda


@router.delete("/monedas/{moneda_id}", status_code=204, tags=["Monedas"], dependencies=[_perm(Modulo.monedas, Accion.eliminar)])
async def desactivar_moneda(moneda_id: int, session: SessionDep):
    moneda = await obtener_o_404(session, Moneda, moneda_id, "Moneda")
    if moneda.es_principal:
        raise Conflicto("No se puede desactivar la moneda principal")
    moneda.activa = False
    await guardar(session)


# ============================================================ Unidades de medida
def _unidad_out(u: UnidadMedida, en_uso: int) -> dict:
    return {**{c: getattr(u, c) for c in UnidadOut.model_fields if c != "en_uso"}, "en_uso": en_uso}


def _validar_subunidad(abreviatura, factor) -> None:
    if (abreviatura is None) != (factor is None):
        raise Invalido("La subunidad necesita nombre y equivalencia (1 kg = 1000 g), o ninguno de los dos")


async def _usos_unidad(session, unidad_id: int) -> int:
    return await session.scalar(
        select(func.count(Insumo.id)).join(UnidadMedida, Insumo.unidad == UnidadMedida.codigo).where(UnidadMedida.id == unidad_id)
    ) or 0


@router.get("/unidades", response_model=list[UnidadOut], tags=["Unidades"])
async def listar_unidades(session: SessionDep, _usuario: UsuarioActual):
    """Catálogo de unidades: lo ve cualquier usuario (el personal lo necesita para leer cantidades)."""
    await unidades_srv.asegurar_base(session)
    await session.commit()
    usos = dict((await session.execute(select(Insumo.unidad, func.count()).group_by(Insumo.unidad))).all())
    filas = await session.scalars(select(UnidadMedida).order_by(UnidadMedida.es_base.desc(), UnidadMedida.nombre))
    return [_unidad_out(u, usos.get(u.codigo, 0)) for u in filas]


@router.post(
    "/unidades",
    response_model=UnidadOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Unidades"],
    dependencies=[_perm(Modulo.insumos, Accion.crear)],
)
async def crear_unidad(datos: UnidadIn, session: SessionDep, usuario: UsuarioActual):
    _validar_subunidad(datos.subunidad_abreviatura, datos.factor_subunidad)
    await unidades_srv.asegurar_base(session)
    unidad = UnidadMedida(**datos.model_dump())
    session.add(unidad)
    await insertar(session, "Ya existe una unidad con ese código o nombre")
    bitacora.registrar(session, usuario, "insumos", "crear", f"Creó la unidad de medida {unidad.nombre} ({unidad.abreviatura})", entidad="unidad", entidad_id=unidad.id)
    await guardar(session, "Ya existe una unidad con ese código o nombre")
    return _unidad_out(unidad, 0)


@router.patch("/unidades/{unidad_id}", response_model=UnidadOut, tags=["Unidades"], dependencies=[_perm(Modulo.insumos, Accion.editar)])
async def editar_unidad(unidad_id: int, datos: UnidadUpdate, session: SessionDep, usuario: UsuarioActual):
    unidad = await obtener_o_404(session, UnidadMedida, unidad_id, "Unidad")
    usos = await _usos_unidad(session, unidad.id)
    if datos.permite_decimales is False and unidad.permite_decimales and usos:
        raise Conflicto("No se puede exigir enteros: hay insumos que usan esta unidad con cantidades decimales")
    enviados = datos.model_dump(exclude_unset=True)
    _validar_subunidad(
        enviados.get("subunidad_abreviatura", unidad.subunidad_abreviatura),
        enviados.get("factor_subunidad", unidad.factor_subunidad),
    )
    if datos.activa is False and usos:
        raise Conflicto(f"{usos} insumo(s) usan esta unidad; cámbialos de unidad antes de desactivarla")
    cambios = aplicar_cambios(unidad, datos)
    if cambios:
        bitacora.registrar(session, usuario, "insumos", "editar", f"Editó la unidad {unidad.nombre}: {', '.join(cambios)}", entidad="unidad", entidad_id=unidad.id, datos=cambios)
    await guardar(session, "Ya existe una unidad con ese nombre")
    return _unidad_out(unidad, usos)


@router.delete("/unidades/{unidad_id}", status_code=204, tags=["Unidades"], dependencies=[_perm(Modulo.insumos, Accion.eliminar)])
async def eliminar_unidad(unidad_id: int, session: SessionDep, usuario: UsuarioActual):
    unidad = await obtener_o_404(session, UnidadMedida, unidad_id, "Unidad")
    if unidad.es_base:
        raise Conflicto("Las unidades de fábrica no se eliminan; puedes desactivarlas")
    if await _usos_unidad(session, unidad.id):
        raise Conflicto("Hay insumos que usan esta unidad")
    bitacora.registrar(session, usuario, "insumos", "eliminar", f"Eliminó la unidad de medida {unidad.nombre}", entidad="unidad", entidad_id=unidad.id)
    await session.delete(unidad)
    await guardar(session)


# ============================================================ Insumos
@router.get("/insumos", response_model=list[InsumoOut], tags=["Insumos"], dependencies=[_perm(Modulo.insumos, Accion.leer)])
async def listar_insumos(session: SessionDep, activo: bool | None = None):
    stmt = select(Insumo).order_by(Insumo.nombre)
    if activo is not None:
        stmt = stmt.where(Insumo.activo.is_(activo))
    return (await session.scalars(stmt)).all()


@router.post(
    "/insumos",
    response_model=InsumoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Insumos"],
    dependencies=[_perm(Modulo.insumos, Accion.crear)],
)
async def crear_insumo(datos: InsumoIn, session: SessionDep, usuario: UsuarioActual):
    # Sin código: lo genera la BD (INS-0001)
    unidad = await unidades_srv.unidad_activa(session, datos.unidad)
    insumo = Insumo(**datos.model_dump(exclude={"codigo"} if datos.codigo is None else set()), unidad_ref=unidad, presentaciones=[])
    session.add(insumo)
    await insertar(session, "Ya existe un insumo con ese nombre, código o código de barras")
    bitacora.registrar(
        session, usuario, "insumos", "crear", f"Creó el insumo {insumo.nombre} ({insumo.codigo})",
        entidad="insumo", entidad_id=insumo.id,
    )
    await guardar(session, "Ya existe un insumo con ese nombre, código o código de barras")
    return insumo


@router.patch("/insumos/{insumo_id}", response_model=InsumoOut, tags=["Insumos"], dependencies=[_perm(Modulo.insumos, Accion.editar)])
async def editar_insumo(insumo_id: int, datos: InsumoUpdate, session: SessionDep, usuario: UsuarioActual):
    insumo = await obtener_o_404(session, Insumo, insumo_id, "Insumo")
    if datos.unidad is not None and datos.unidad != insumo.unidad:
        en_uso = await session.scalar(
            select(
                exists().where(Inventario.insumo_id == insumo.id)
                | exists().where(RecetaInsumo.insumo_id == insumo.id)
                | exists().where(Producto.insumo_id == insumo.id)
            )
        )
        if en_uso:
            raise Conflicto("No se puede cambiar la unidad de un insumo con inventario, recetas o productos")
        insumo.unidad_ref = await unidades_srv.unidad_activa(session, datos.unidad)
    cambios = aplicar_cambios(insumo, datos, excluir={"codigo"} if datos.codigo is None else None)
    if cambios:
        bitacora.registrar(
            session, usuario, "insumos", "editar", f"Editó el insumo {insumo.nombre} ({insumo.codigo}): {', '.join(cambios)}",
            entidad="insumo", entidad_id=insumo.id, datos=cambios,
        )
    await guardar(session, "Ya existe un insumo con ese nombre, código o código de barras")
    return insumo


@router.put("/insumos/{insumo_id}/presentaciones", response_model=InsumoOut, tags=["Insumos"], dependencies=[_perm(Modulo.insumos, Accion.editar)])
async def definir_presentaciones(insumo_id: int, datos: PresentacionesIn, session: SessionDep, usuario: UsuarioActual):
    """Cómo llega el insumo al reponerlo o comprarlo (caja x24, saco de 50 kg). Reemplaza la lista completa."""
    insumo = await obtener_o_404(session, Insumo, insumo_id, "Insumo")
    if len({p.nombre.strip().lower() for p in datos.presentaciones}) != len(datos.presentaciones):
        raise Invalido("Hay presentaciones con el mismo nombre")
    for p in datos.presentaciones:
        stock.validar_cantidad_unidad(p.cantidad, insumo)
    insumo.presentaciones.clear()
    await session.flush()
    insumo.presentaciones = [Presentacion(nombre=p.nombre, cantidad=p.cantidad) for p in datos.presentaciones]
    bitacora.registrar(
        session, usuario, "insumos", "editar",
        f"Presentaciones de {insumo.nombre}: " + (", ".join(f"{p.nombre} ({bitacora.cant(p.cantidad, insumo.unidad_abreviatura)})" for p in datos.presentaciones) or "ninguna"),
        entidad="insumo", entidad_id=insumo.id,
    )
    await guardar(session)
    await session.refresh(insumo)
    return insumo


@router.delete("/insumos/{insumo_id}", status_code=204, tags=["Insumos"], dependencies=[_perm(Modulo.insumos, Accion.eliminar)])
async def desactivar_insumo(insumo_id: int, session: SessionDep, usuario: UsuarioActual):
    insumo = await obtener_o_404(session, Insumo, insumo_id, "Insumo")
    insumo.activo = False
    bitacora.registrar(session, usuario, "insumos", "desactivar", f"Desactivó el insumo {insumo.nombre} ({insumo.codigo})", entidad="insumo", entidad_id=insumo.id)
    await guardar(session)


@router.get(
    "/insumos/{insumo_id}/etiqueta",
    tags=["Insumos"],
    response_class=Response,
    responses={200: {"content": {"image/svg+xml": {}, "image/png": {}}}},
    dependencies=[_perm(Modulo.insumos, Accion.leer)],
)
async def etiqueta_insumo(
    insumo_id: int,
    session: SessionDep,
    formato: Literal["svg", "png"] = "svg",
    escala: Annotated[int, Query(ge=2, le=30)] = 8,
):
    """QR con el código interno, para pegar en el envase o el estante y escanearlo al reponer."""
    insumo = await obtener_o_404(session, Insumo, insumo_id, "Insumo")
    buf = io.BytesIO()
    segno.make(insumo.codigo, error="m").save(buf, kind=formato, scale=escala, border=2)
    return Response(
        buf.getvalue(),
        media_type="image/svg+xml" if formato == "svg" else "image/png",
        headers={"Content-Disposition": f'inline; filename="{insumo.codigo}.{formato}"', "Cache-Control": "no-store"},
    )


# ============================================================ Inventario
async def _inventario_accesible(session, inventario_id: int, usuario: Usuario) -> Inventario:
    inv = await obtener_o_404(session, Inventario, inventario_id, "Inventario")
    verificar_sucursal(usuario, inv.sucursal_id)
    return inv


@router.get("/inventario", response_model=Pagina[InventarioOut], tags=["Inventario"])
async def listar_inventario(
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.inventario, Accion.leer),
    sucursal_id: int | None = None,
    bajo_minimo: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    limite: Limite = 100,
    offset: Offset = 0,
):
    stmt = select(Inventario).join(Insumo, Inventario.insumo_id == Insumo.id).order_by(Insumo.nombre)
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(Inventario.sucursal_id.in_(ids))
    if bajo_minimo is not None:
        cond = Inventario.cantidad <= Inventario.stock_minimo
        stmt = stmt.where(cond if bajo_minimo else ~cond)
    if q:
        stmt = stmt.where(Insumo.nombre.ilike(f"%{q}%"))
    return await paginar(session, stmt, limite, offset)


@router.get("/inventario/buscar", response_model=list[InsumoEncontradoOut], tags=["Inventario"])
async def buscar_insumo(
    session: SessionDep,
    sucursal_id: int,
    q: Annotated[str, Query(min_length=1, max_length=100)],
    usuario: Usuario = _perm(Modulo.inventario, Accion.leer),
):
    """Lo que escanea o escribe el personal: código interno, código de barras o nombre.

    Un código exacto devuelve un solo insumo; si no, se busca por nombre (máx. 20).
    """
    verificar_sucursal(usuario, sucursal_id)
    texto = q.strip()
    exacto = await session.scalar(
        select(Insumo).where(or_(func.upper(Insumo.codigo) == texto.upper(), Insumo.codigo_barras == texto))
    )
    if exacto:
        encontrados = [(exacto, "codigo" if exacto.codigo.upper() == texto.upper() else "codigo_barras")]
    else:
        patron = f"%{texto}%"
        filas = await session.scalars(
            select(Insumo)
            .where(or_(Insumo.nombre.ilike(patron), Insumo.codigo.ilike(patron)))
            .order_by(Insumo.activo.desc(), Insumo.nombre)
            .limit(20)
        )
        encontrados = [(i, "nombre") for i in filas]
    if not encontrados:
        return []
    inventarios = {
        inv.insumo_id: inv
        for inv in await session.scalars(
            select(Inventario).where(
                Inventario.sucursal_id == sucursal_id, Inventario.insumo_id.in_([i.id for i, _ in encontrados])
            )
        )
    }
    return [{"insumo": i, "inventario": inventarios.get(i.id), "coincidencia": c} for i, c in encontrados]


@router.post("/inventario", response_model=InventarioOut, status_code=status.HTTP_201_CREATED, tags=["Inventario"])
async def crear_inventario(
    datos: InventarioIn, session: SessionDep, usuario: Usuario = _perm(Modulo.inventario, Accion.crear)
):
    """Registra un insumo en el inventario de una sucursal con su stock inicial y mínimo."""
    verificar_sucursal(usuario, datos.sucursal_id)
    insumo = await obtener_o_404(session, Insumo, datos.insumo_id, "Insumo")
    sucursal = await obtener_o_404(session, Sucursal, datos.sucursal_id, "Sucursal")
    stock.validar_cantidad_unidad(datos.cantidad, insumo)
    inv = Inventario(
        sucursal=sucursal,
        sucursal_id=datos.sucursal_id,
        insumo_id=insumo.id,
        insumo=insumo,
        cantidad=Decimal(0),
        reservado=Decimal(0),
        stock_minimo=datos.stock_minimo,
    )
    session.add(inv)
    await guardar(session, "Ese insumo ya está en el inventario de la sucursal")
    if datos.cantidad > 0:
        await stock.registrar_entrada(session, inv.id, datos.cantidad, "Stock inicial", usuario.id)
    else:
        await stock.revisar_alerta(session, inv)
    u = insumo.unidad_abreviatura
    bitacora.registrar(
        session, usuario, "inventario", "registrar",
        f"Registró {insumo.nombre} en el inventario de {inv.sucursal.nombre} con {bitacora.cant(datos.cantidad, u)} (mínimo {bitacora.cant(datos.stock_minimo, u)})",
        sucursal_id=inv.sucursal_id, entidad="inventario", entidad_id=inv.id,
    )
    await guardar(session)
    await session.refresh(inv)
    return inv


@router.patch("/inventario/{inventario_id}", response_model=InventarioOut, tags=["Inventario"])
async def editar_inventario(
    inventario_id: int,
    datos: InventarioUpdate,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.inventario, Accion.editar),
):
    await _inventario_accesible(session, inventario_id, usuario)
    [inv] = await stock.bloquear_inventarios(session, inventario_ids=[inventario_id])
    antes = inv.stock_minimo
    inv.stock_minimo = datos.stock_minimo
    await stock.revisar_alerta(session, inv)
    u = inv.insumo.unidad_abreviatura
    bitacora.registrar(
        session, usuario, "inventario", "minimo",
        f"Cambió el mínimo de {inv.insumo.nombre} en {inv.sucursal.nombre}: {bitacora.cant(antes, u)} → {bitacora.cant(inv.stock_minimo, u)}",
        sucursal_id=inv.sucursal_id, entidad="inventario", entidad_id=inv.id,
    )
    await guardar(session)
    return inv


@router.post("/inventario/{inventario_id}/entrada", response_model=InventarioOut, tags=["Inventario"])
async def entrada_stock(
    inventario_id: int, datos: MovimientoIn, session: SessionDep, usuario: Usuario = _perm(Modulo.inventario, Accion.editar)
):
    inv = await _inventario_accesible(session, inventario_id, usuario)
    cant = stock.resolver_cantidad(inv.insumo, datos.cantidad, datos.presentacion_id)
    stock.validar_cantidad_unidad(cant, inv.insumo)
    antes, u = inv.cantidad, inv.insumo.unidad_abreviatura
    inv = await stock.registrar_entrada(session, inventario_id, cant, datos.motivo or "Entrada", usuario.id)
    bitacora.registrar(
        session, usuario, "inventario", "entrada",
        f"Repuso {bitacora.cant(cant, u)} de {inv.insumo.nombre} en {inv.sucursal.nombre} ({bitacora.cant(antes, u)} → {bitacora.cant(inv.cantidad, u)})" + (f" · {datos.motivo}" if datos.motivo else ""),
        sucursal_id=inv.sucursal_id, entidad="inventario", entidad_id=inv.id,
    )
    await guardar(session)
    return inv


@router.post("/inventario/{inventario_id}/merma", response_model=InventarioOut, tags=["Inventario"])
async def merma_stock(
    inventario_id: int, datos: MovimientoIn, session: SessionDep, usuario: Usuario = _perm(Modulo.inventario, Accion.editar)
):
    inv = await _inventario_accesible(session, inventario_id, usuario)
    stock.validar_cantidad_unidad(datos.cantidad, inv.insumo)
    antes, u = inv.cantidad, inv.insumo.unidad_abreviatura
    inv = await stock.registrar_merma(session, inventario_id, datos.cantidad, datos.motivo or "Merma", usuario.id)
    bitacora.registrar(
        session, usuario, "inventario", "merma",
        f"Registró merma de {bitacora.cant(datos.cantidad, u)} de {inv.insumo.nombre} en {inv.sucursal.nombre} ({bitacora.cant(antes, u)} → {bitacora.cant(inv.cantidad, u)})" + (f" · {datos.motivo}" if datos.motivo else ""),
        sucursal_id=inv.sucursal_id, entidad="inventario", entidad_id=inv.id,
    )
    await guardar(session)
    return inv


@router.post("/inventario/{inventario_id}/ajuste", response_model=InventarioOut, tags=["Inventario"])
async def ajuste_stock(
    inventario_id: int, datos: AjusteIn, session: SessionDep, usuario: Usuario = _perm(Modulo.inventario, Accion.editar)
):
    inv = await _inventario_accesible(session, inventario_id, usuario)
    stock.validar_cantidad_unidad(datos.cantidad_real, inv.insumo)
    antes, u = inv.cantidad, inv.insumo.unidad_abreviatura
    inv = await stock.registrar_ajuste(session, inventario_id, datos.cantidad_real, datos.motivo, usuario.id)
    bitacora.registrar(
        session, usuario, "inventario", "ajuste",
        f"Ajustó el conteo de {inv.insumo.nombre} en {inv.sucursal.nombre}: {bitacora.cant(antes, u)} → {bitacora.cant(inv.cantidad, u)}" + (f" · {datos.motivo}" if datos.motivo else ""),
        sucursal_id=inv.sucursal_id, entidad="inventario", entidad_id=inv.id,
    )
    await guardar(session)
    return inv


@router.get("/inventario/{inventario_id}/movimientos", response_model=Pagina[MovimientoOut], tags=["Inventario"])
async def movimientos_stock(
    inventario_id: int,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.inventario, Accion.leer),
    limite: Limite = 50,
    offset: Offset = 0,
):
    await _inventario_accesible(session, inventario_id, usuario)
    stmt = (
        select(MovimientoStock)
        .where(MovimientoStock.inventario_id == inventario_id)
        .order_by(MovimientoStock.id.desc())
    )
    return await paginar(session, stmt, limite, offset)


@router.get("/alertas", response_model=Pagina[AlertaOut], tags=["Inventario"])
async def listar_alertas(
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.inventario, Accion.leer),
    sucursal_id: int | None = None,
    estado: EstadoAlerta | None = EstadoAlerta.activa,
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(AlertaStock).order_by(AlertaStock.id.desc())
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(AlertaStock.sucursal_id.in_(ids))
    if estado is not None:
        stmt = stmt.where(AlertaStock.estado == estado)
    pagina = await paginar(session, stmt, limite, offset)
    pagina["items"] = [
        {
            "id": a.id,
            "sucursal_id": a.sucursal_id,
            "inventario_id": a.inventario_id,
            "insumo": a.inventario.insumo.nombre,
            "unidad": a.inventario.insumo.unidad,
            "cantidad": a.cantidad,
            "stock_minimo": a.stock_minimo,
            "mensaje": a.mensaje,
            "estado": a.estado,
            "created_at": a.created_at,
            "resuelta_en": a.resuelta_en,
        }
        for a in pagina["items"]
    ]
    return pagina


# ============================================================ Recetas
def _receta_out(receta: Receta) -> dict:
    return {
        "id": receta.id,
        "codigo": receta.codigo,
        "nombre": receta.nombre,
        "descripcion": receta.descripcion,
        "activa": receta.activa,
        "ingredientes": [
            {
                "insumo_id": ri.insumo_id,
                "insumo": ri.insumo.nombre,
                "unidad": ri.insumo.unidad,
                "cantidad": ri.cantidad,
                "removible": ri.removible,
                "costo": None if ri.insumo.costo_unitario is None else q2(ri.cantidad * ri.insumo.costo_unitario),
            }
            for ri in receta.ingredientes
        ],
        "costo": (
            None
            if any(ri.insumo.costo_unitario is None for ri in receta.ingredientes)
            else q2(sum((ri.cantidad * ri.insumo.costo_unitario for ri in receta.ingredientes), Decimal(0)))
        ),
    }


async def _armar_ingredientes(session, ingredientes: list[IngredienteIn]) -> list[RecetaInsumo]:
    insumos = {
        i.id: i
        for i in await session.scalars(select(Insumo).where(Insumo.id.in_([x.insumo_id for x in ingredientes])))
    }
    resultado = []
    for x in ingredientes:
        insumo = insumos.get(x.insumo_id)
        if not insumo:
            raise NoEncontrado(f"Insumo {x.insumo_id}")
        stock.validar_cantidad_unidad(x.cantidad, insumo)
        resultado.append(RecetaInsumo(insumo_id=insumo.id, insumo=insumo, cantidad=x.cantidad, removible=x.removible))
    return resultado


@router.get("/recetas", response_model=list[RecetaOut], tags=["Recetas"], dependencies=[_perm(Modulo.recetas, Accion.leer)])
async def listar_recetas(session: SessionDep):
    return [_receta_out(r) for r in await session.scalars(select(Receta).order_by(Receta.nombre))]


@router.get("/recetas/{receta_id}", response_model=RecetaOut, tags=["Recetas"], dependencies=[_perm(Modulo.recetas, Accion.leer)])
async def obtener_receta(receta_id: int, session: SessionDep):
    return _receta_out(await obtener_o_404(session, Receta, receta_id, "Receta"))


@router.post(
    "/recetas",
    response_model=RecetaOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Recetas"],
    dependencies=[_perm(Modulo.recetas, Accion.crear)],
)
async def crear_receta(datos: RecetaIn, session: SessionDep, usuario: UsuarioActual):
    receta = Receta(nombre=datos.nombre, descripcion=datos.descripcion, activa=datos.activa)
    if datos.codigo:
        receta.codigo = datos.codigo
    receta.ingredientes = await _armar_ingredientes(session, datos.ingredientes)
    session.add(receta)
    await insertar(session, "Ya existe una receta con ese nombre o código")
    bitacora.registrar(session, usuario, "recetas", "crear", f"Creó la receta {receta.nombre} ({receta.codigo})", entidad="receta", entidad_id=receta.id)
    await guardar(session, "Ya existe una receta con ese nombre o código")
    return _receta_out(receta)


@router.patch("/recetas/{receta_id}", response_model=RecetaOut, tags=["Recetas"], dependencies=[_perm(Modulo.recetas, Accion.editar)])
async def editar_receta(receta_id: int, datos: RecetaUpdate, session: SessionDep, usuario: UsuarioActual):
    """Los platos ya enviados a cocina conservan la reserva calculada con la receta anterior."""
    receta = await obtener_o_404(session, Receta, receta_id, "Receta")
    if datos.ingredientes is not None:
        nuevos = await _armar_ingredientes(session, datos.ingredientes)
        # Borrar antes de insertar para no chocar con UNIQUE(receta_id, insumo_id)
        receta.ingredientes.clear()
        await session.flush()
        receta.ingredientes = nuevos
    cambios = aplicar_cambios(receta, datos, excluir={"ingredientes"} | ({"codigo"} if datos.codigo is None else set()))
    detalle = [*cambios, *(["ingredientes"] if datos.ingredientes is not None else [])]
    bitacora.registrar(
        session, usuario, "recetas", "editar", f"Editó la receta {receta.nombre} ({receta.codigo}): {', '.join(detalle) or 'sin cambios'}",
        entidad="receta", entidad_id=receta.id,
    )
    await guardar(session, "Ya existe una receta con ese nombre o código")
    return _receta_out(receta)


@router.delete("/recetas/{receta_id}", status_code=204, tags=["Recetas"], dependencies=[_perm(Modulo.recetas, Accion.eliminar)])
async def eliminar_receta(receta_id: int, session: SessionDep, usuario: UsuarioActual):
    receta = await obtener_o_404(session, Receta, receta_id, "Receta")
    if await session.scalar(select(exists().where(Producto.receta_id == receta.id))):
        raise Conflicto("La receta está asociada a productos; desactívala o cambia los productos primero")
    bitacora.registrar(session, usuario, "recetas", "eliminar", f"Eliminó la receta {receta.nombre} ({receta.codigo})", entidad="receta", entidad_id=receta.id)
    await session.delete(receta)
    await guardar(session)


# ============================================================ Categorías
@router.get("/categorias", response_model=list[CategoriaOut], tags=["Categorías"], dependencies=[_perm(Modulo.categorias, Accion.leer)])
async def listar_categorias(session: SessionDep):
    return (await session.scalars(select(Categoria).order_by(Categoria.orden, Categoria.nombre))).all()


@router.post(
    "/categorias",
    response_model=CategoriaOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Categorías"],
    dependencies=[_perm(Modulo.categorias, Accion.crear)],
)
async def crear_categoria(datos: CategoriaIn, session: SessionDep):
    if datos.estacion_id is not None:
        await obtener_o_404(session, Estacion, datos.estacion_id, "Estación")
    campos = datos.model_dump()
    campos["estacion_id"] = datos.estacion_id or await _estacion_por_defecto(session)
    categoria = Categoria(**campos)
    session.add(categoria)
    await guardar(session, "Ya existe una categoría con ese nombre")
    return categoria


@router.patch(
    "/categorias/{categoria_id}",
    response_model=CategoriaOut,
    tags=["Categorías"],
    dependencies=[_perm(Modulo.categorias, Accion.editar)],
)
async def editar_categoria(categoria_id: int, datos: CategoriaUpdate, session: SessionDep):
    categoria = await obtener_o_404(session, Categoria, categoria_id, "Categoría")
    if datos.estacion_id is not None:
        await obtener_o_404(session, Estacion, datos.estacion_id, "Estación")
    aplicar_cambios(categoria, datos)
    await guardar(session, "Ya existe una categoría con ese nombre")
    return categoria


@router.delete(
    "/categorias/{categoria_id}", status_code=204, tags=["Categorías"], dependencies=[_perm(Modulo.categorias, Accion.eliminar)]
)
async def eliminar_categoria(categoria_id: int, session: SessionDep):
    categoria = await obtener_o_404(session, Categoria, categoria_id, "Categoría")
    await session.delete(categoria)  # los productos quedan sin categoría ("Otros")
    await guardar(session)


# ============================================================ Estaciones
async def _estacion_por_defecto(session) -> int | None:
    """Cocina (o, si no existe, la primera estación activa): a donde va todo lo que no se asigna a otra."""
    cocina = await session.scalar(select(Estacion.id).where(func.lower(Estacion.nombre) == "cocina"))
    return cocina or await session.scalar(
        select(Estacion.id).where(Estacion.activa.is_(True)).order_by(Estacion.orden, Estacion.id).limit(1)
    )


@router.get("/estaciones", response_model=list[EstacionOut], tags=["Estaciones"])
async def listar_estaciones(session: SessionDep, usuario: UsuarioActual):
    """Las ve quien administra el catálogo o quien trabaja en una pantalla de preparación."""
    if not (usuario.puede(Modulo.categorias, Accion.leer) or usuario.puede(Modulo.cocina, Accion.leer)):
        raise Prohibido("Sin permiso para leer estaciones")
    return (await session.scalars(select(Estacion).order_by(Estacion.orden, Estacion.nombre))).all()


@router.post(
    "/estaciones",
    response_model=EstacionOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Estaciones"],
    dependencies=[_perm(Modulo.categorias, Accion.crear)],
)
async def crear_estacion(datos: EstacionIn, session: SessionDep):
    estacion = Estacion(**datos.model_dump())
    session.add(estacion)
    await guardar(session, "Ya existe una estación con ese nombre")
    return estacion


@router.patch("/estaciones/{estacion_id}", response_model=EstacionOut, tags=["Estaciones"], dependencies=[_perm(Modulo.categorias, Accion.editar)])
async def editar_estacion(estacion_id: int, datos: EstacionUpdate, session: SessionDep):
    estacion = await obtener_o_404(session, Estacion, estacion_id, "Estación")
    aplicar_cambios(estacion, datos)
    await guardar(session, "Ya existe una estación con ese nombre")
    return estacion


@router.delete("/estaciones/{estacion_id}", status_code=204, tags=["Estaciones"], dependencies=[_perm(Modulo.categorias, Accion.eliminar)])
async def eliminar_estacion(estacion_id: int, session: SessionDep):
    estacion = await obtener_o_404(session, Estacion, estacion_id, "Estación")
    await session.delete(estacion)  # los productos quedan sin estación (se ven en todas las pantallas)
    await guardar(session)


# ============================================================ Productos
async def _validar_refs_producto(session, categoria_id, receta_id, estacion_id=None, insumo_id=None, cantidad_por_venta=None) -> None:
    if receta_id is not None and insumo_id is not None:
        raise Invalido("Un producto descuenta stock por receta o por un insumo directo, no por ambos")
    if insumo_id is not None:
        insumo = await obtener_o_404(session, Insumo, insumo_id, "Insumo")
        if cantidad_por_venta is not None:
            stock.validar_cantidad_unidad(cantidad_por_venta, insumo)
    if estacion_id is not None:
        await obtener_o_404(session, Estacion, estacion_id, "Estación")
    if categoria_id is not None:
        await obtener_o_404(session, Categoria, categoria_id, "Categoría")
    if receta_id is not None:
        await obtener_o_404(session, Receta, receta_id, "Receta")


async def _producto(session, producto_id: int) -> Producto:
    return await obtener_o_404(session, Producto, producto_id, "Producto")


@router.get("/productos", response_model=Pagina[ProductoOut], tags=["Productos"], dependencies=[_perm(Modulo.productos, Accion.leer)])
async def listar_productos(
    session: SessionDep,
    categoria_id: int | None = None,
    activo: bool | None = None,
    q: str | None = Query(default=None, max_length=100),
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Producto).order_by(Producto.orden, Producto.nombre)
    if categoria_id is not None:
        stmt = stmt.where(Producto.categoria_id == categoria_id)
    if activo is not None:
        stmt = stmt.where(Producto.activo.is_(activo))
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(or_(Producto.nombre.ilike(patron), Producto.codigo.ilike(patron), Producto.codigo_barras == q))
    return await paginar(session, stmt, limite, offset)


@router.get("/productos/{producto_id}", response_model=ProductoOut, tags=["Productos"], dependencies=[_perm(Modulo.productos, Accion.leer)])
async def obtener_producto(producto_id: int, session: SessionDep):
    return await _producto(session, producto_id)


@router.post(
    "/productos",
    response_model=ProductoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Productos"],
    dependencies=[_perm(Modulo.productos, Accion.crear)],
)
async def crear_producto(datos: ProductoIn, session: SessionDep, usuario: UsuarioActual):
    await licencia.exigir_cupo(session, "max_productos", select(Producto.id).where(Producto.activo.is_(True)))
    await _validar_refs_producto(session, datos.categoria_id, datos.receta_id, datos.estacion_id, datos.insumo_id, datos.cantidad_por_venta)
    campos = datos.model_dump(exclude={"codigo"} if datos.codigo is None else set())
    if datos.estacion_id is None:
        # Sin estación elegida: la de su categoría (Bebidas -> Barra) y, si no tiene, Cocina
        categoria = await session.get(Categoria, datos.categoria_id) if datos.categoria_id is not None else None
        campos["estacion_id"] = (categoria.estacion_id if categoria else None) or await _estacion_por_defecto(session)
    producto = Producto(**campos, sucursales=[], medios=[])
    session.add(producto)
    await insertar(session, "Ya existe un producto con ese nombre, código o código de barras")
    bitacora.registrar(
        session, usuario, "productos", "crear",
        f"Creó el producto {producto.nombre} ({producto.codigo}) a {bitacora.dinero(producto.precio_base)}",
        entidad="producto", entidad_id=producto.id,
    )
    await guardar(session, "Ya existe un producto con ese nombre, código o código de barras")
    await session.refresh(producto)
    return producto


@router.patch("/productos/{producto_id}", response_model=ProductoOut, tags=["Productos"], dependencies=[_perm(Modulo.productos, Accion.editar)])
async def editar_producto(producto_id: int, datos: ProductoUpdate, session: SessionDep, usuario: UsuarioActual):
    producto = await _producto(session, producto_id)
    cambios = datos.model_dump(exclude_unset=True)
    receta_final = cambios.get("receta_id", producto.receta_id)
    insumo_final = cambios.get("insumo_id", producto.insumo_id)
    # Al pasar a una forma de control, la otra se suelta sola
    if cambios.get("receta_id") is not None and "insumo_id" not in cambios:
        datos.insumo_id, insumo_final = None, None
    elif cambios.get("insumo_id") is not None and "receta_id" not in cambios:
        datos.receta_id, receta_final = None, None
    await _validar_refs_producto(
        session, cambios.get("categoria_id"), receta_final, cambios.get("estacion_id"), insumo_final,
        cambios.get("cantidad_por_venta", producto.cantidad_por_venta) if insumo_final is not None else None,
    )
    precio_antes = producto.precio_base
    hechos = aplicar_cambios(producto, datos, excluir={"codigo"} if datos.codigo is None else None)
    if hechos:
        texto = f"Editó el producto {producto.nombre} ({producto.codigo}): {', '.join(hechos)}"
        if "precio_base" in hechos:
            texto += f" · precio {bitacora.dinero(precio_antes)} → {bitacora.dinero(producto.precio_base)}"
        bitacora.registrar(session, usuario, "productos", "editar", texto, entidad="producto", entidad_id=producto.id, datos=hechos)
    await guardar(session, "Ya existe un producto con ese nombre, código o código de barras")
    await session.refresh(producto)
    return producto


@router.delete("/productos/{producto_id}", status_code=204, tags=["Productos"], dependencies=[_perm(Modulo.productos, Accion.eliminar)])
async def desactivar_producto(producto_id: int, session: SessionDep, usuario: UsuarioActual):
    """Desactiva (no borra): las comandas y ventas históricas lo referencian."""
    producto = await _producto(session, producto_id)
    producto.activo = False
    bitacora.registrar(session, usuario, "productos", "desactivar", f"Desactivó el producto {producto.nombre} ({producto.codigo})", entidad="producto", entidad_id=producto.id)
    await guardar(session)


@router.put(
    "/productos/{producto_id}/sucursales/{sucursal_id}",
    response_model=ProductoSucursalOut,
    tags=["Productos"],
)
async def configurar_producto_sucursal(
    producto_id: int,
    sucursal_id: int,
    datos: ProductoSucursalIn,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.productos, Accion.editar),
):
    """Precio propio de la sucursal (null = precio base) y si se vende en ella."""
    verificar_sucursal(usuario, sucursal_id)
    producto = await _producto(session, producto_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    config = await session.scalar(
        select(ProductoSucursal).where(
            ProductoSucursal.producto_id == producto_id, ProductoSucursal.sucursal_id == sucursal_id
        )
    )
    if not config:
        config = ProductoSucursal(producto_id=producto_id, sucursal_id=sucursal_id)
        session.add(config)
    config.precio, config.disponible = datos.precio, datos.disponible
    bitacora.registrar(
        session, usuario, "productos", "precio_sucursal",
        f"{producto.nombre} en {sucursal.nombre}: "
        + (f"precio {bitacora.dinero(datos.precio)}" if datos.precio is not None else "precio base")
        + ("" if datos.disponible else " · no disponible"),
        sucursal_id=sucursal_id, entidad="producto", entidad_id=producto_id,
    )
    emitir(session, canal_sucursal(sucursal_id), "menu.actualizado", {"producto_id": producto_id})
    await guardar(session)
    return config


@router.delete("/productos/{producto_id}/sucursales/{sucursal_id}", status_code=204, tags=["Productos"])
async def quitar_config_sucursal(
    producto_id: int, sucursal_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.productos, Accion.editar)
):
    verificar_sucursal(usuario, sucursal_id)
    config = await session.scalar(
        select(ProductoSucursal).where(
            ProductoSucursal.producto_id == producto_id, ProductoSucursal.sucursal_id == sucursal_id
        )
    )
    if not config:
        raise NoEncontrado("Configuración de sucursal")
    await session.delete(config)
    await guardar(session)


# ---------- Medios (fotos y videos)
async def _desmarcar_portadas(session, producto_id: int, excepto: int | None = None) -> None:
    stmt = update(ProductoMedio).where(ProductoMedio.producto_id == producto_id).values(es_portada=False)
    if excepto is not None:
        stmt = stmt.where(ProductoMedio.id != excepto)
    await session.execute(stmt)


@router.post(
    "/productos/{producto_id}/medios/archivo",
    response_model=MedioOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Productos"],
    dependencies=[_perm(Modulo.productos, Accion.editar)],
)
async def subir_medio(
    producto_id: int,
    session: SessionDep,
    archivo: Annotated[UploadFile, File(description="JPG, PNG, WEBP, AVIF, MP4, MOV o WEBM")],
    orden: Annotated[int, Form()] = 0,
    es_portada: Annotated[bool, Form()] = False,
    texto_alt: Annotated[str | None, Form(max_length=255)] = None,
):
    await _producto(session, producto_id)
    info = await medios_srv.guardar_archivo(archivo)
    if es_portada:
        await _desmarcar_portadas(session, producto_id)
    medio = ProductoMedio(producto_id=producto_id, orden=orden, es_portada=es_portada, texto_alt=texto_alt, **info)
    session.add(medio)
    try:
        await guardar(session)
    except Exception:
        medios_srv.borrar_archivo(info["archivo"])
        raise
    return medio


@router.post(
    "/productos/{producto_id}/medios/url",
    response_model=MedioOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Productos"],
    dependencies=[_perm(Modulo.productos, Accion.editar)],
)
async def agregar_medio_url(producto_id: int, datos: MedioUrlIn, session: SessionDep):
    """Foto o video alojado afuera (CDN, YouTube, Vimeo...)."""
    await _producto(session, producto_id)
    if datos.es_portada:
        await _desmarcar_portadas(session, producto_id)
    medio = ProductoMedio(producto_id=producto_id, **datos.model_dump(mode="json"))
    session.add(medio)
    await guardar(session)
    return medio


async def _medio(session, producto_id: int, medio_id: int) -> ProductoMedio:
    medio = await session.get(ProductoMedio, medio_id)
    if not medio or medio.producto_id != producto_id:
        raise NoEncontrado("Medio")
    return medio


@router.patch(
    "/productos/{producto_id}/medios/{medio_id}",
    response_model=MedioOut,
    tags=["Productos"],
    dependencies=[_perm(Modulo.productos, Accion.editar)],
)
async def editar_medio(producto_id: int, medio_id: int, datos: MedioUpdate, session: SessionDep):
    medio = await _medio(session, producto_id, medio_id)
    if datos.es_portada:
        await _desmarcar_portadas(session, producto_id, excepto=medio.id)
    aplicar_cambios(medio, datos)
    await guardar(session)
    return medio


@router.delete(
    "/productos/{producto_id}/medios/{medio_id}",
    status_code=204,
    tags=["Productos"],
    dependencies=[_perm(Modulo.productos, Accion.editar)],
)
async def eliminar_medio(producto_id: int, medio_id: int, session: SessionDep):
    medio = await _medio(session, producto_id, medio_id)
    archivo = medio.archivo
    await session.delete(medio)
    await guardar(session)
    medios_srv.borrar_archivo(archivo)


# ============================================================ Menú (vista interna del personal)
@router.get("/menu/{sucursal_id}", response_model=MenuOut, tags=["Menú"])
async def menu_sucursal(
    sucursal_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.productos, Accion.leer)
):
    verificar_sucursal(usuario, sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    return await construir_menu(session, sucursal)
