import io
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import exists, extract, func, or_, select

from app.api.deps import SessionDep, UsuarioActual, requiere, sucursales_visibles, verificar_sucursal
from app.api.utils import Limite, Offset, aplicar_cambios, guardar, insertar, obtener_o_404, paginar
from app.core.errors import Conflicto, Invalido, NoEncontrado
from app.core.security import new_public_token
from app.models import (
    Producto,
    Zona,
    Accion,
    AutorMensaje,
    Cliente,
    Comanda,
    ComandaItem,
    EstadoComanda,
    EstadoItem,
    Mesa,
    Modulo,
    Moneda,
    OrigenComanda,
    Sucursal,
    TipoDescuento,
    Usuario,
    Venta,
)
from app.models.comandas import ESTADOS_ACTIVOS_COCINA
from app.schemas.catalogo import MenuIngrediente
from app.schemas.base import Pagina
from app.schemas.comandas import (
    AgregarItemsIn,
    CancelarIn,
    ClienteIn,
    ClienteOut,
    ConsultaCedulaOut,
    ClienteUpdate,
    CocinaComandaOut,
    ComandaCajaIn,
    ComandaOut,
    ComandaResumenOut,
    ComandaUpdate,
    CortesiaIn,
    DescuentoIn,
    DivisionItemsIn,
    DivisionOut,
    EnviarCocinaIn,
    EstadoItemCocinaIn,
    MensajeIn,
    MensajeOut,
    SinInsumosIn,
    MesaIn,
    MesaOut,
    MesaQrOut,
    MesaUpdate,
    UnirMesasIn,
    ZonaIn,
    ZonaOut,
    ZonaUpdate,
    PagoIn,
    PropinaIn,
    ResumenVentasOut,
    VentaDetalleOut,
    VentaOut,
)
from app.schemas.fiscal import AnularFacturaIn, CierreDiaOut, DatosFiscalesOut, FacturaIn
from app.core.ratelimit import check_rate_limit
from app.services import bitacora, cedulas
from app.services import comandas as srv
from app.services import fiscal as fiscal_srv
from app.services.monedas import moneda_principal, monedas_activas
from app.services import config, licencia

router = APIRouter()


def _perm(modulo: Modulo, accion: Accion):
    return Depends(requiere(modulo, accion))


# ============================================================ Clientes
@router.get("/clientes", response_model=Pagina[ClienteOut], tags=["Clientes"], dependencies=[_perm(Modulo.clientes, Accion.leer)])
async def listar_clientes(
    session: SessionDep,
    q: str | None = Query(default=None, max_length=100, description="Busca por nombre, documento, teléfono o email"),
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Cliente).order_by(Cliente.nombre)
    if q:
        patron = f"%{q}%"
        stmt = stmt.where(
            or_(
                Cliente.nombre.ilike(patron),
                Cliente.documento.ilike(patron),
                Cliente.telefono.ilike(patron),
                Cliente.email.ilike(patron),
            )
        )
    return await paginar(session, stmt, limite, offset)


@router.get("/clientes/consulta-externa", response_model=ConsultaCedulaOut | None, tags=["Clientes"])
async def consulta_externa_cedula(
    tipo: Literal["V", "E"],
    numero: Annotated[str, Query(pattern=r"^\d{5,10}$")],
    usuario: Usuario = _perm(Modulo.clientes, Accion.leer),
):
    """Autocompleta el nombre de una persona por su cédula (servicio externo opcional).

    503 si no está configurado. Devuelve null si la cédula no aparece.
    """
    await check_rate_limit(f"cedula:{usuario.id}", 30, 60)
    try:
        return await cedulas.consultar(tipo, numero)
    except cedulas.ConsultaNoDisponible as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.get("/clientes/{cliente_id}", response_model=ClienteOut, tags=["Clientes"], dependencies=[_perm(Modulo.clientes, Accion.leer)])
async def obtener_cliente(cliente_id: int, session: SessionDep):
    return await obtener_o_404(session, Cliente, cliente_id, "Cliente")


@router.post(
    "/clientes",
    response_model=ClienteOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Clientes"],
    dependencies=[_perm(Modulo.clientes, Accion.crear)],
)
async def crear_cliente(datos: ClienteIn, session: SessionDep, usuario: UsuarioActual):
    cliente = Cliente(**datos.model_dump())
    session.add(cliente)
    await insertar(session, "Ya existe un cliente con ese documento")
    bitacora.registrar(session, usuario, "clientes", "crear", f"Registró al cliente {cliente.nombre}", entidad="cliente", entidad_id=cliente.id)
    await guardar(session, "Ya existe un cliente con ese documento")
    return cliente


@router.patch("/clientes/{cliente_id}", response_model=ClienteOut, tags=["Clientes"], dependencies=[_perm(Modulo.clientes, Accion.editar)])
async def editar_cliente(cliente_id: int, datos: ClienteUpdate, session: SessionDep, usuario: UsuarioActual):
    cliente = await obtener_o_404(session, Cliente, cliente_id, "Cliente")
    cambios = aplicar_cambios(cliente, datos)
    if cambios:
        bitacora.registrar(
            session, usuario, "clientes", "editar", f"Editó al cliente {cliente.nombre}: {', '.join(cambios)}",
            entidad="cliente", entidad_id=cliente.id,
        )
    if cliente.documento and not cliente.tipo_documento:
        raise Invalido("Indica el tipo de documento (V, E, J, G o P)")
    await guardar(session, "Ya existe un cliente con ese documento")
    return cliente


@router.delete("/clientes/{cliente_id}", status_code=204, tags=["Clientes"], dependencies=[_perm(Modulo.clientes, Accion.eliminar)])
async def eliminar_cliente(cliente_id: int, session: SessionDep, usuario: UsuarioActual):
    cliente = await obtener_o_404(session, Cliente, cliente_id, "Cliente")
    bitacora.registrar(session, usuario, "clientes", "eliminar", f"Eliminó al cliente {cliente.nombre}", entidad="cliente", entidad_id=cliente.id)
    await session.delete(cliente)  # comandas y ventas conservan el histórico (cliente_id -> NULL)
    await guardar(session)


# ============================================================ Mesas
async def _mesa_accesible(session, mesa_id: int, usuario: Usuario) -> Mesa:
    mesa = await obtener_o_404(session, Mesa, mesa_id, "Mesa")
    verificar_sucursal(usuario, mesa.sucursal_id)
    return mesa


async def _mesa_out(session, mesa: Mesa) -> dict:
    comanda_id = await srv.mesa_ocupada(session, mesa.id)
    return {**MesaOut.model_validate(mesa).model_dump(), "ocupada": comanda_id is not None, "comanda_abierta_id": comanda_id}


def _qr_url(mesa: Mesa) -> str:
    return f"{config.get("public_menu_base_url").rstrip('/')}/{mesa.qr_token}"


@router.get("/mesas", response_model=list[MesaOut], tags=["Mesas"])
async def listar_mesas(
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.mesas, Accion.leer),
    sucursal_id: int | None = None,
    activa: bool | None = None,
):
    stmt = select(Mesa).order_by(Mesa.sucursal_id, Mesa.nombre)
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(Mesa.sucursal_id.in_(ids))
    if activa is not None:
        stmt = stmt.where(Mesa.activa.is_(activa))
    mesas = (await session.scalars(stmt)).all()
    abiertas = dict(
        (
            await session.execute(
                select(Comanda.mesa_id, Comanda.id).where(
                    Comanda.estado == EstadoComanda.abierta,
                    Comanda.mesa_id.in_([m.unida_a_id or m.id for m in mesas]),
                )
            )
        ).all()
    )
    # Una mesa unida se ve ocupada con la comanda de su principal
    def comanda_de(m: Mesa) -> int | None:
        return abiertas.get(m.unida_a_id or m.id)

    return [
        {**MesaOut.model_validate(m).model_dump(), "ocupada": comanda_de(m) is not None, "comanda_abierta_id": comanda_de(m)}
        for m in mesas
    ]


async def _validar_zona(session, zona_id: int | None, sucursal_id: int) -> None:
    if zona_id is not None:
        zona = await obtener_o_404(session, Zona, zona_id, "Zona")
        if zona.sucursal_id != sucursal_id:
            raise Conflicto("La zona es de otra sucursal")


@router.get("/zonas", response_model=list[ZonaOut], tags=["Mesas"])
async def listar_zonas(session: SessionDep, sucursal_id: int, usuario: Usuario = _perm(Modulo.mesas, Accion.leer)):
    verificar_sucursal(usuario, sucursal_id)
    return (
        await session.scalars(select(Zona).where(Zona.sucursal_id == sucursal_id).order_by(Zona.orden, Zona.nombre))
    ).all()


@router.post("/zonas", response_model=ZonaOut, status_code=status.HTTP_201_CREATED, tags=["Mesas"])
async def crear_zona(datos: ZonaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.crear)):
    verificar_sucursal(usuario, datos.sucursal_id)
    await licencia.exigir_cupo(session, "max_salas", select(Zona.id).where(Zona.activa.is_(True)))
    zona = Zona(**datos.model_dump())
    session.add(zona)
    await guardar(session, "Ya existe una zona con ese nombre en la sucursal")
    await session.refresh(zona)
    return zona


@router.patch("/zonas/{zona_id}", response_model=ZonaOut, tags=["Mesas"])
async def editar_zona(zona_id: int, datos: ZonaUpdate, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.editar)):
    zona = await obtener_o_404(session, Zona, zona_id, "Zona")
    verificar_sucursal(usuario, zona.sucursal_id)
    aplicar_cambios(zona, datos)
    await guardar(session, "Ya existe una zona con ese nombre en la sucursal")
    await session.refresh(zona)
    return zona


@router.delete("/zonas/{zona_id}", status_code=204, tags=["Mesas"])
async def eliminar_zona(zona_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.eliminar)):
    zona = await obtener_o_404(session, Zona, zona_id, "Zona")
    verificar_sucursal(usuario, zona.sucursal_id)
    await session.delete(zona)  # sus mesas quedan sin zona
    await guardar(session)


@router.post("/mesas/{mesa_id}/unir", response_model=list[MesaOut], tags=["Mesas"])
async def unir_mesas(mesa_id: int, datos: UnirMesasIn, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.editar)):
    """Une otras mesas a esta (grupo grande): una sola comanda y un solo QR activo."""
    principal = await _mesa_accesible(session, mesa_id, usuario)
    otras = [await _mesa_accesible(session, i, usuario) for i in dict.fromkeys(datos.mesa_ids)]
    await srv.unir_mesas(session, principal, otras)
    await guardar(session)
    return [await _mesa_out(session, m) for m in [principal, *otras]]


@router.post("/mesas/{mesa_id}/separar", response_model=MesaOut, tags=["Mesas"])
async def separar_mesas(mesa_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.editar)):
    """Deshace la unión: si es la principal, separa todo el grupo."""
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    await srv.separar_mesas(session, mesa.id)
    await guardar(session)
    await session.refresh(mesa)
    return await _mesa_out(session, mesa)


@router.get("/mesas/{mesa_id}", response_model=MesaOut, tags=["Mesas"])
async def obtener_mesa(mesa_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.leer)):
    return await _mesa_out(session, await _mesa_accesible(session, mesa_id, usuario))


@router.post("/mesas", response_model=MesaOut, status_code=status.HTTP_201_CREATED, tags=["Mesas"])
async def crear_mesa(datos: MesaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.crear)):
    verificar_sucursal(usuario, datos.sucursal_id)
    await licencia.exigir_cupo(session, "max_mesas", select(Mesa.id).where(Mesa.activa.is_(True)))
    await obtener_o_404(session, Sucursal, datos.sucursal_id, "Sucursal")
    await _validar_zona(session, datos.zona_id, datos.sucursal_id)
    mesa = Mesa(**datos.model_dump(), qr_token=new_public_token())
    session.add(mesa)
    await guardar(session, "Ya existe una mesa con ese nombre en la sucursal")
    return await _mesa_out(session, mesa)


@router.patch("/mesas/{mesa_id}", response_model=MesaOut, tags=["Mesas"])
async def editar_mesa(
    mesa_id: int, datos: MesaUpdate, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.editar)
):
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    if "zona_id" in datos.model_fields_set:
        await _validar_zona(session, datos.zona_id, mesa.sucursal_id)
    aplicar_cambios(mesa, datos)
    await guardar(session, "Ya existe una mesa con ese nombre en la sucursal")
    return await _mesa_out(session, mesa)


@router.delete("/mesas/{mesa_id}", status_code=204, tags=["Mesas"])
async def desactivar_mesa(mesa_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.eliminar)):
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    if await srv.mesa_ocupada(session, mesa.id):
        raise Conflicto("La mesa tiene una comanda abierta")
    mesa.activa = False
    await guardar(session)


@router.get("/mesas/{mesa_id}/qr-url", response_model=MesaQrOut, tags=["Mesas"])
async def qr_url(mesa_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.leer)):
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    return {"mesa_id": mesa.id, "url": _qr_url(mesa)}


@router.get(
    "/mesas/{mesa_id}/qr",
    tags=["Mesas"],
    response_class=Response,
    responses={200: {"content": {"image/png": {}, "image/svg+xml": {}}}},
)
async def qr_imagen(
    mesa_id: int,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.mesas, Accion.leer),
    formato: Literal["png", "svg"] = "png",
    escala: Annotated[int, Query(ge=2, le=40)] = 10,
):
    """Imagen del QR lista para imprimir."""
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    buf = io.BytesIO()
    segno.make(_qr_url(mesa), error="m").save(buf, kind=formato, scale=escala, border=2)
    media = "image/png" if formato == "png" else "image/svg+xml"
    return Response(
        buf.getvalue(),
        media_type=media,
        headers={"Content-Disposition": f'inline; filename="mesa-{mesa.id}.{formato}"', "Cache-Control": "no-store"},
    )


@router.post("/mesas/{mesa_id}/regenerar-qr", response_model=MesaQrOut, tags=["Mesas"])
async def regenerar_qr(mesa_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.mesas, Accion.editar)):
    """Invalida el QR anterior (por ejemplo, si alguien lo fotografió y hace pedidos falsos)."""
    mesa = await _mesa_accesible(session, mesa_id, usuario)
    mesa.qr_token = new_public_token()
    bitacora.registrar(
        session, usuario, "mesas", "regenerar_qr", f"Regeneró el QR de {_nombre_mesa(mesa.nombre)}",
        sucursal_id=mesa.sucursal_id, entidad="mesa", entidad_id=mesa.id,
    )
    await guardar(session)
    return {"mesa_id": mesa.id, "url": _qr_url(mesa)}


# ============================================================ Comandas
async def _comanda_accesible(session, comanda_id: int, usuario: Usuario, *, bloquear: bool = True) -> Comanda:
    comanda = await srv.obtener_comanda(session, comanda_id, bloquear=bloquear)
    verificar_sucursal(usuario, comanda.sucursal_id)
    return comanda


async def _guardar_y_responder(session, comanda_id: int, tipo: str = "comanda.actualizada") -> dict:
    await guardar(session)
    comanda, monedas = await srv.notificar(session, comanda_id, tipo)
    return srv.serializar_comanda(comanda, monedas)


@router.get("/comandas", response_model=Pagina[ComandaResumenOut], tags=["Comandas"])
async def listar_comandas(
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.comandas, Accion.leer),
    sucursal_id: int | None = None,
    estado: EstadoComanda | None = EstadoComanda.abierta,
    mesa_id: int | None = None,
    limite: Limite = 50,
    offset: Offset = 0,
):
    stmt = select(Comanda).order_by(Comanda.id.desc())
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(Comanda.sucursal_id.in_(ids))
    if estado is not None:
        stmt = stmt.where(Comanda.estado == estado)
    if mesa_id is not None:
        stmt = stmt.where(Comanda.mesa_id == mesa_id)
    pagina = await paginar(session, stmt, limite, offset)
    pagina["items"] = [srv.resumen_comanda(c) for c in pagina["items"]]
    return pagina


@router.post("/comandas", response_model=ComandaOut, status_code=status.HTTP_201_CREATED, tags=["Comandas"])
async def crear_comanda(
    datos: ComandaCajaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.crear)
):
    """Caja abre una comanda manualmente. La mesa es opcional (para llevar / barra)."""
    verificar_sucursal(usuario, datos.sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, datos.sucursal_id, "Sucursal")
    if not sucursal.activa:
        raise Conflicto("La sucursal está inactiva")
    comanda = await srv.crear_comanda(
        session,
        sucursal_id=datos.sucursal_id,
        origen=OrigenComanda.caja,
        items=datos.items,
        mesa_id=datos.mesa_id,
        cliente_id=datos.cliente_id,
        nombre_cliente=datos.nombre_cliente,
        telefono_cliente=datos.telefono_cliente,
        notas=datos.notas,
        usuario=usuario,
    )
    if datos.enviar_a_cocina and datos.items:
        await srv.enviar_a_cocina(session, comanda)
    await session.refresh(comanda, ["mesa"])
    _log_comanda(session, usuario, comanda, "abrir", f"Abrió la comanda {_ref(comanda)}")
    return await _guardar_y_responder(session, comanda.id, "comanda.creada")


@router.get("/comandas/{comanda_id}", response_model=ComandaOut, tags=["Comandas"])
async def obtener_comanda(comanda_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.leer)):
    comanda = await _comanda_accesible(session, comanda_id, usuario, bloquear=False)
    return srv.serializar_comanda(comanda, await monedas_activas(session))


@router.patch("/comandas/{comanda_id}", response_model=ComandaOut, tags=["Comandas"])
async def editar_comanda(
    comanda_id: int, datos: ComandaUpdate, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.editar)
):
    """Asignar/cambiar mesa manualmente, cliente, nombre o notas."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    await srv.actualizar_comanda(session, comanda, datos.model_dump(exclude_unset=True))
    return await _guardar_y_responder(session, comanda_id)


@router.post("/comandas/{comanda_id}/items", response_model=ComandaOut, tags=["Comandas"])
async def agregar_items(
    comanda_id: int, datos: AgregarItemsIn, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.editar)
):
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    nuevos = await srv.agregar_items(session, comanda, datos.items, por_cliente=False)
    if datos.enviar_a_cocina:
        await srv.enviar_a_cocina(session, comanda, [i.id for i in nuevos])
    return await _guardar_y_responder(session, comanda_id)


@router.post("/comandas/{comanda_id}/enviar-cocina", response_model=ComandaOut, tags=["Comandas"])
async def enviar_a_cocina(
    comanda_id: int,
    session: SessionDep,
    datos: EnviarCocinaIn | None = None,
    usuario: Usuario = _perm(Modulo.comandas, Accion.editar),
):
    """Caja aprueba los platos pendientes y los manda a cocina (reserva stock)."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    await srv.enviar_a_cocina(session, comanda, datos.item_ids if datos else None)
    return await _guardar_y_responder(session, comanda_id, "cocina.nuevos")


@router.post("/comandas/{comanda_id}/items/{item_id}/entregar", response_model=ComandaOut, tags=["Comandas"])
async def entregar_item(
    comanda_id: int, item_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.editar)
):
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    await srv.entregar_item(session, comanda, _item(comanda, item_id))
    return await _guardar_y_responder(session, comanda_id)


@router.get("/comandas/{comanda_id}/mensajes", response_model=list[MensajeOut], tags=["Chat"])
async def ver_mensajes(comanda_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.leer)):
    comanda = await _comanda_accesible(session, comanda_id, usuario, bloquear=False)
    return await srv.listar_mensajes(session, comanda.id)


@router.post("/comandas/{comanda_id}/mensajes", response_model=MensajeOut, status_code=201, tags=["Chat"])
async def escribir_mensaje(
    comanda_id: int, datos: MensajeIn, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.editar)
):
    """Caja le escribe a la mesa; el cliente lo ve al instante en su link de seguimiento."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    msg = await srv.enviar_mensaje(session, comanda, AutorMensaje.personal, datos.texto, usuario.nombre)
    await guardar(session)
    await session.refresh(msg)
    return msg


@router.get("/comandas/{comanda_id}/items/{item_id}/ingredientes", response_model=list[MenuIngrediente], tags=["Comandas"])
async def ingredientes_quitables(
    comanda_id: int, item_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.leer)
):
    """Ingredientes del plato que se pueden quitar (para que caja arme el 'sin cebolla')."""
    comanda = await _comanda_accesible(session, comanda_id, usuario, bloquear=False)
    producto = await session.get(Producto, _item(comanda, item_id).producto_id)
    receta = producto.receta if producto else None
    return [
        {"insumo_id": ri.insumo_id, "nombre": ri.insumo.nombre}
        for ri in (receta.ingredientes if receta else [])
        if ri.removible
    ]


@router.put("/comandas/{comanda_id}/items/{item_id}/sin-ingredientes", response_model=ComandaOut, tags=["Comandas"])
async def cambiar_ingredientes_item(
    comanda_id: int,
    item_id: int,
    datos: SinInsumosIn,
    session: SessionDep,
    usuario: Usuario = _perm(Modulo.comandas, Accion.editar),
):
    """Quita o repone ingredientes de un plato pendiente, para que el stock no descuente lo que no se usa."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    item = _item(comanda, item_id)
    await srv.cambiar_sin_insumos(session, comanda, item, datos.sin_insumo_ids)
    return await _guardar_y_responder(session, comanda_id)


@router.post("/comandas/{comanda_id}/items/{item_id}/cancelar", response_model=ComandaOut, tags=["Comandas"])
async def cancelar_item(
    comanda_id: int, item_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.editar)
):
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    item = _item(comanda, item_id)
    await srv.cancelar_item(session, comanda, item)
    _log_comanda(session, usuario, comanda, "cancelar_plato", f"Canceló {item.nombre_producto} de la comanda {_ref(comanda)}")
    return await _guardar_y_responder(session, comanda_id)


@router.post("/comandas/{comanda_id}/cancelar", response_model=ComandaOut, tags=["Comandas"])
async def cancelar_comanda(
    comanda_id: int, datos: CancelarIn, session: SessionDep, usuario: Usuario = _perm(Modulo.comandas, Accion.eliminar)
):
    """Cancela la comanda, libera el stock reservado y desbloquea la mesa."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    await srv.cancelar_comanda(session, comanda, datos.motivo, usuario)
    _log_comanda(session, usuario, comanda, "cancelar", f"Canceló la comanda {_ref(comanda)} · {datos.motivo}")
    return await _guardar_y_responder(session, comanda_id, "comanda.cancelada")


def _nombre_mesa(nombre: str) -> str:
    return f"Mesa {nombre}" if nombre.isdigit() else nombre


def _ref(comanda: Comanda) -> str:
    """'#12 (Mesa 1)' o '#13 (para llevar)'."""
    return f"#{comanda.id} ({_nombre_mesa(comanda.mesa.nombre) if comanda.mesa else 'para llevar'})"


def _log_comanda(session, usuario: Usuario, comanda: Comanda, accion: str, texto: str, modulo: str = "comandas") -> None:
    bitacora.registrar(session, usuario, modulo, accion, texto, sucursal_id=comanda.sucursal_id, entidad="comanda", entidad_id=comanda.id)


def _item(comanda: Comanda, item_id: int) -> ComandaItem:
    item = next((i for i in comanda.items if i.id == item_id), None)
    if not item:
        raise NoEncontrado("Plato")
    return item


# ============================================================ Caja
@router.post("/comandas/{comanda_id}/pagos", response_model=ComandaOut, status_code=status.HTTP_201_CREATED, tags=["Caja"])
async def registrar_pago(
    comanda_id: int, datos: PagoIn, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.crear)
):
    """Registra un pago en cualquier moneda activa. Se pueden combinar monedas y métodos."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    pago = await srv.registrar_pago(session, comanda, usuario=usuario, **datos.model_dump())
    _log_comanda(
        session, usuario, comanda, "pago",
        f"Registró un pago de {bitacora.dinero(pago.monto, pago.moneda.simbolo)} ({pago.metodo.value.replace('_', ' ')}) en la comanda {_ref(comanda)}",
        modulo="caja",
    )
    return await _guardar_y_responder(session, comanda_id)


@router.delete("/comandas/{comanda_id}/pagos/{pago_id}", response_model=ComandaOut, tags=["Caja"])
async def eliminar_pago(
    comanda_id: int, pago_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.eliminar)
):
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    pago = next((p for p in comanda.pagos if p.id == pago_id), None)
    await srv.eliminar_pago(session, comanda, pago_id)
    if pago:
        _log_comanda(
            session, usuario, comanda, "eliminar_pago",
            f"Eliminó un pago de {bitacora.dinero(pago.monto, pago.moneda.simbolo)} de la comanda {_ref(comanda)}",
            modulo="caja",
        )
    return await _guardar_y_responder(session, comanda_id)


@router.post("/comandas/{comanda_id}/cerrar", response_model=ComandaOut, tags=["Caja"])
async def cerrar_comanda(comanda_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.editar)):
    """Cierra la comanda pagada: genera la venta y desbloquea la mesa/QR."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    venta = await srv.cerrar_comanda(session, comanda, usuario)
    principal = await moneda_principal(session)
    _log_comanda(
        session, usuario, comanda, "cobrar",
        f"Cobró la comanda {_ref(comanda)} · venta #{venta.id} por {bitacora.dinero(venta.total, principal.simbolo)}",
        modulo="caja",
    )
    return await _guardar_y_responder(session, comanda_id, "comanda.cerrada")


@router.put("/comandas/{comanda_id}/descuento", response_model=ComandaOut, tags=["Caja"])
async def descuento_comanda(
    comanda_id: int, datos: DescuentoIn, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.editar)
):
    """Descuento en % o monto sobre la cuenta (tipo null lo quita). Queda en la bitácora."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    await srv.aplicar_descuento(session, comanda, datos.tipo, datos.valor, datos.motivo)
    principal = await moneda_principal(session)
    if datos.tipo is None:
        texto = f"Quitó el descuento de la comanda {_ref(comanda)}"
    else:
        cuanto = f"{datos.valor.normalize():f} %" if datos.tipo == TipoDescuento.porcentaje else bitacora.dinero(datos.valor, principal.simbolo)
        texto = f"Aplicó un descuento de {cuanto} a la comanda {_ref(comanda)} · {datos.motivo}"
    _log_comanda(session, usuario, comanda, "descuento", texto, modulo="caja")
    return await _guardar_y_responder(session, comanda_id)


@router.put("/comandas/{comanda_id}/propina", response_model=ComandaOut, tags=["Caja"])
async def propina_comanda(
    comanda_id: int, datos: PropinaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.editar)
):
    """Propina en monto o % sobre lo facturable. 0 la quita. No es venta del restaurante."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    monto = datos.monto if datos.monto is not None else srv.total_comanda(comanda) * datos.porcentaje / 100
    await srv.fijar_propina(session, comanda, monto)
    principal = await moneda_principal(session)
    _log_comanda(session, usuario, comanda, "propina", f"Registró una propina de {bitacora.dinero(comanda.propina, principal.simbolo)} en la comanda {_ref(comanda)}", modulo="caja")
    return await _guardar_y_responder(session, comanda_id)


@router.put("/comandas/{comanda_id}/items/{item_id}/cortesia", response_model=ComandaOut, tags=["Caja"])
async def cortesia_item(
    comanda_id: int, item_id: int, datos: CortesiaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.editar)
):
    """Marca un plato como cortesía (no se cobra) o lo vuelve a cobrar."""
    comanda = await _comanda_accesible(session, comanda_id, usuario)
    item = _item(comanda, item_id)
    await srv.marcar_cortesia(session, comanda, item, datos.cortesia, datos.motivo)
    texto = (
        f"Dio de cortesía {item.nombre_producto} en la comanda {_ref(comanda)} · {datos.motivo}"
        if datos.cortesia
        else f"Volvió a cobrar {item.nombre_producto} en la comanda {_ref(comanda)}"
    )
    _log_comanda(session, usuario, comanda, "cortesia", texto, modulo="caja")
    return await _guardar_y_responder(session, comanda_id)


@router.get("/comandas/{comanda_id}/division", response_model=DivisionOut, tags=["Caja"])
async def division_partes_iguales(
    comanda_id: int,
    session: SessionDep,
    partes: Annotated[int, Query(ge=2, le=50)],
    usuario: Usuario = _perm(Modulo.caja, Accion.leer),
):
    """Divide la cuenta en N partes iguales. Registra cada pago con etiqueta 'Parte N'."""
    comanda = await _comanda_accesible(session, comanda_id, usuario, bloquear=False)
    return srv.dividir_partes_iguales(comanda, partes, await monedas_activas(session))


@router.post("/comandas/{comanda_id}/division", response_model=DivisionOut, tags=["Caja"])
async def division_por_items(
    comanda_id: int, datos: DivisionItemsIn, session: SessionDep, usuario: Usuario = _perm(Modulo.caja, Accion.leer)
):
    """Divide la cuenta por platos (cada quien paga lo suyo). Usa la etiqueta del grupo al registrar el pago."""
    comanda = await _comanda_accesible(session, comanda_id, usuario, bloquear=False)
    return srv.dividir_por_items(comanda, datos.grupos, await monedas_activas(session))


# ============================================================ Cocina
@router.get("/cocina", response_model=list[CocinaComandaOut], tags=["Cocina"])
async def tablero_cocina(
    session: SessionDep,
    sucursal_id: int,
    estacion_id: int | None = None,
    usuario: Usuario = _perm(Modulo.cocina, Accion.leer),
):
    """Platos enviados a preparar o en preparación, agrupados por comanda (más antiguos primero).

    estacion_id filtra por lugar de preparación (cocina, barra…); los platos sin estación salen en todas.
    """
    verificar_sucursal(usuario, sucursal_id)
    def de_la_estacion(i: ComandaItem) -> bool:
        return estacion_id is None or i.estacion_id in (None, estacion_id)

    comandas = (
        await session.scalars(
            select(Comanda)
            .where(
                Comanda.sucursal_id == sucursal_id,
                Comanda.estado == EstadoComanda.abierta,
                exists().where(
                    ComandaItem.comanda_id == Comanda.id,
                    ComandaItem.estado.in_(ESTADOS_ACTIVOS_COCINA),
                    *([ComandaItem.estacion_id.is_(None) | (ComandaItem.estacion_id == estacion_id)] if estacion_id is not None else []),
                ),
            )
            .order_by(Comanda.id)
        )
    ).unique()
    tablero = []
    for c in comandas:
        numeros = srv.numerar_items(c)
        items = sorted(
            (i for i in c.items if i.estado in ESTADOS_ACTIVOS_COCINA and de_la_estacion(i)), key=lambda i: (i.enviado_en, i.id)
        )
        tablero.append(
            {
                "comanda_id": c.id,
                "mesa": c.mesa.nombre if c.mesa else None,
                "nombre_cliente": c.nombre_cliente,
                "notas": c.notas,
                "items": [
                    {
                        "id": i.id,
                        "nombre": f"{i.nombre_producto} #{numeros[i.id]}",
                        "estado": i.estado,
                        "notas": i.notas,
                        "enviado_en": i.enviado_en,
                    }
                    for i in items
                ],
            }
        )
    tablero.sort(key=lambda t: t["items"][0]["enviado_en"])
    return tablero


@router.post("/cocina/items/{item_id}/estado", response_model=ComandaOut, tags=["Cocina"])
async def estado_item_cocina(
    item_id: int, datos: EstadoItemCocinaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.cocina, Accion.editar)
):
    """Marca un plato en preparación o listo. Al marcarlo LISTO se descuenta el stock."""
    comanda, item = await srv.obtener_item(session, item_id)
    verificar_sucursal(usuario, comanda.sucursal_id)
    await srv.cambiar_estado_cocina(session, comanda, item, EstadoItem(datos.estado), usuario)
    if datos.estado == EstadoItem.listo:
        _log_comanda(session, usuario, comanda, "plato_listo", f"Marcó listo {item.nombre_producto} de la comanda {_ref(comanda)}", modulo="cocina")
    return await _guardar_y_responder(session, comanda.id, "cocina.item_actualizado")


# ============================================================ Ventas
def _filtros_ventas(
    stmt,
    *,
    usuario: Usuario,
    sucursal_id,
    fecha_desde,
    fecha_hasta,
    dia,
    mes,
    anio,
    monto_min,
    monto_max,
    cliente_id,
    facturada=None,
):
    local = func.timezone(config.get("timezone"), Venta.created_at)
    ids = sucursales_visibles(usuario, sucursal_id)
    if ids is not None:
        stmt = stmt.where(Venta.sucursal_id.in_(ids))
    if dia:
        stmt = stmt.where(func.date(local) == dia)
    if fecha_desde:
        stmt = stmt.where(func.date(local) >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(func.date(local) <= fecha_hasta)
    if anio:
        stmt = stmt.where(extract("year", local) == anio)
    if mes:
        stmt = stmt.where(extract("month", local) == mes)
    if monto_min is not None:
        stmt = stmt.where(Venta.total >= monto_min)
    if monto_max is not None:
        stmt = stmt.where(Venta.total <= monto_max)
    if cliente_id is not None:
        stmt = stmt.where(Venta.cliente_id == cliente_id)
    if facturada is not None:
        stmt = stmt.where(Venta.numero_factura.is_not(None) if facturada else Venta.numero_factura.is_(None))
    return stmt


class FiltrosVentas:
    def __init__(
        self,
        sucursal_id: int | None = None,
        dia: date | None = Query(default=None, description="Ventas de un día (YYYY-MM-DD)"),
        mes: int | None = Query(default=None, ge=1, le=12),
        anio: int | None = Query(default=None, ge=2000, le=2100),
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        monto_min: Decimal | None = Query(default=None, ge=0),
        monto_max: Decimal | None = Query(default=None, ge=0),
        cliente_id: int | None = None,
        facturada: bool | None = Query(default=None, description="false = pendientes por facturar"),
    ):
        self.kwargs = dict(
            facturada=facturada,
            sucursal_id=sucursal_id,
            dia=dia,
            mes=mes,
            anio=anio,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            monto_min=monto_min,
            monto_max=monto_max,
            cliente_id=cliente_id,
        )


def _venta_out(v: Venta) -> dict:
    c = v.comanda
    return {
        "id": v.id,
        "comanda_id": v.comanda_id,
        "sucursal_id": v.sucursal_id,
        "sucursal": v.sucursal.nombre,
        "mesa": c.mesa.nombre if c.mesa else None,
        "cliente_id": v.cliente_id,
        "nombre_cliente": c.nombre_cliente or (c.cliente.nombre if c.cliente else None),
        "total": v.total,
        "pagado": v.pagado,
        "vuelto": v.vuelto,
        "cantidad_items": v.cantidad_items,
        "descuento": v.descuento,
        "propina": v.propina,
        "igtf": v.igtf,
        "created_at": v.created_at,
        "numero_factura": v.numero_factura,
        "numero_control": v.numero_control,
        "facturada_en": v.facturada_en,
        "anulada_en": v.anulada_en,
    }


@router.get("/ventas", response_model=Pagina[VentaOut], tags=["Ventas"])
async def listar_ventas(
    session: SessionDep,
    filtros: Annotated[FiltrosVentas, Depends()],
    usuario: Usuario = _perm(Modulo.ventas, Accion.leer),
    ordenar: Literal["fecha_desc", "fecha_asc", "monto_desc", "monto_asc"] = "fecha_desc",
    limite: Limite = 50,
    offset: Offset = 0,
):
    orden = {
        "fecha_desc": Venta.id.desc(),
        "fecha_asc": Venta.id.asc(),
        "monto_desc": Venta.total.desc(),
        "monto_asc": Venta.total.asc(),
    }[ordenar]
    stmt = _filtros_ventas(select(Venta).order_by(orden), usuario=usuario, **filtros.kwargs)
    pagina = await paginar(session, stmt, limite, offset)
    pagina["items"] = [_venta_out(v) for v in pagina["items"]]
    return pagina


@router.get("/ventas/resumen", response_model=ResumenVentasOut, tags=["Ventas"])
async def resumen_ventas(
    session: SessionDep,
    filtros: Annotated[FiltrosVentas, Depends()],
    usuario: Usuario = _perm(Modulo.ventas, Accion.leer),
    agrupar: Literal["dia", "mes", "anio"] = "dia",
):
    local = func.timezone(config.get("timezone"), Venta.created_at)
    formato = {"dia": "YYYY-MM-DD", "mes": "YYYY-MM", "anio": "YYYY"}[agrupar]
    periodo = func.to_char(local, formato).label("periodo")

    totales = (
        await session.execute(
            _filtros_ventas(
                select(func.count(Venta.id), func.coalesce(func.sum(Venta.total), 0)), usuario=usuario, **filtros.kwargs
            )
        )
    ).one()
    por_periodo = (
        await session.execute(
            _filtros_ventas(
                select(periodo, func.count(Venta.id), func.sum(Venta.total)).group_by(periodo).order_by(periodo),
                usuario=usuario,
                **filtros.kwargs,
            )
        )
    ).all()
    top = (
        await session.execute(
            _filtros_ventas(
                select(
                    ComandaItem.nombre_producto,
                    func.count(ComandaItem.id).label("cantidad"),
                    func.sum(ComandaItem.precio_unitario).label("total"),
                )
                .join(Venta, Venta.comanda_id == ComandaItem.comanda_id)
                .where(ComandaItem.estado == EstadoItem.entregado)
                .group_by(ComandaItem.nombre_producto)
                .order_by(func.count(ComandaItem.id).desc())
                .limit(10),
                usuario=usuario,
                **filtros.kwargs,
            )
        )
    ).all()

    cantidad, total = totales
    return {
        "cantidad_ventas": cantidad,
        "total": total,
        "ticket_promedio": (Decimal(total) / cantidad).quantize(Decimal("0.01")) if cantidad else Decimal(0),
        "por_periodo": [{"periodo": p, "cantidad_ventas": n, "total": t} for p, n, t in por_periodo],
        "productos_top": [{"producto": n, "cantidad": c, "total": t} for n, c, t in top],
    }


@router.get("/ventas/cierre-dia", response_model=CierreDiaOut, tags=["Facturación"])
async def cierre_del_dia(
    session: SessionDep,
    dia: date,
    sucursal_id: int,
    usuario: Usuario = _perm(Modulo.ventas, Accion.leer),
):
    """Resumen administrativo del día: ventas, IVA por alícuota, IGTF, métodos de pago, anuladas y pendientes por facturar."""
    verificar_sucursal(usuario, sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, sucursal_id, "Sucursal")
    ventas = (
        await session.scalars(
            _filtros_ventas(
                select(Venta).order_by(Venta.created_at, Venta.id), usuario=usuario, sucursal_id=sucursal_id, dia=dia,
                fecha_desde=None, fecha_hasta=None, mes=None, anio=None, monto_min=None, monto_max=None, cliente_id=None,
            )
        )
    ).unique().all()
    principal, fiscal = await _monedas_fiscales(session)
    filas = [fiscal_srv.datos_fiscales(v, v.comanda, principal, fiscal) for v in ventas]
    emisor = filas[0]["emisor"] if filas else fiscal_srv.emisor_de(sucursal)
    return fiscal_srv.cierre_dia(filas, list(ventas), dia, sucursal.nombre, emisor, principal.codigo)


@router.get(
    "/ventas/libro",
    tags=["Facturación"],
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def libro_ventas(
    session: SessionDep,
    filtros: Annotated[FiltrosVentas, Depends()],
    usuario: Usuario = _perm(Modulo.ventas, Accion.leer),
):
    """Libro de ventas en CSV (Excel) con las facturas registradas. Filtra con mes/anio o fechas."""
    kwargs = {**filtros.kwargs, "facturada": True}
    if not any(kwargs[k] for k in ("dia", "mes", "anio", "fecha_desde", "fecha_hasta")):
        raise Invalido("Indica el período del libro: mes y año, o un rango de fechas")
    ventas = (
        await session.scalars(_filtros_ventas(select(Venta).order_by(Venta.created_at, Venta.id), usuario=usuario, **kwargs))
    ).unique().all()
    principal, fiscal = await _monedas_fiscales(session)
    filas = [fiscal_srv.datos_fiscales(v, v.comanda, principal, fiscal) for v in ventas]
    moneda = next((f["moneda_fiscal"] for f in filas if f["moneda_fiscal"]), principal.codigo)
    periodo = f"{kwargs['anio'] or ''}-{kwargs['mes']:02d}" if kwargs["mes"] else date.today().isoformat()
    texto_periodo = (
        f"{kwargs['mes']:02d}/{kwargs['anio'] or ''}" if kwargs["mes"]
        else " a ".join(str(x) for x in (kwargs["fecha_desde"], kwargs["fecha_hasta"]) if x) or str(kwargs["dia"] or periodo)
    )
    return Response(
        fiscal_srv.libro_ventas_csv(filas, moneda, texto_periodo),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="libro-ventas-{periodo.strip("-")}.csv"'},
    )


async def _monedas_fiscales(session) -> tuple[Moneda, Moneda | None]:
    principal = await moneda_principal(session)
    fiscal = await session.scalar(select(Moneda).where(Moneda.es_fiscal.is_(True)))
    return principal, fiscal


async def _venta_accesible(session, venta_id: int, usuario: Usuario) -> Venta:
    venta = await obtener_o_404(session, Venta, venta_id, "Venta")
    verificar_sucursal(usuario, venta.sucursal_id)
    return venta


async def _datos_fiscales(session, venta: Venta) -> dict:
    principal, fiscal = await _monedas_fiscales(session)
    return fiscal_srv.datos_fiscales(venta, venta.comanda, principal, fiscal)


@router.get("/ventas/{venta_id}/fiscal", response_model=DatosFiscalesOut, tags=["Facturación"])
async def datos_para_facturar(venta_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.leer)):
    """Datos para copiar en la factura manual: emisor, receptor, líneas, IVA, IGTF y total en Bs."""
    return await _datos_fiscales(session, await _venta_accesible(session, venta_id, usuario))


@router.put("/ventas/{venta_id}/factura", response_model=DatosFiscalesOut, tags=["Facturación"])
async def registrar_factura(
    venta_id: int, datos: FacturaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.editar)
):
    """Guarda el número de factura y de control usados al facturar a mano, con el receptor tal como se escribió."""
    venta = await _venta_accesible(session, venta_id, usuario)
    for campo, valor in datos.model_dump(exclude={"guardar_cliente"}).items():
        setattr(venta, campo, valor)
    if datos.guardar_cliente:
        await _registrar_cliente_de_factura(session, venta, datos, usuario)
    venta.facturada_en = datetime.now(UTC)
    venta.facturada_por_id = usuario.id
    bitacora.registrar(
        session, usuario, "ventas", "factura",
        f"Registró la factura N° {datos.numero_factura} (control {datos.numero_control}) de la venta #{venta.id}",
        sucursal_id=venta.sucursal_id, entidad="venta", entidad_id=venta.id,
    )
    await guardar(session, "Ese número de factura ya está registrado en otra venta de la sucursal")
    return await _datos_fiscales(session, venta)


async def _registrar_cliente_de_factura(session, venta: Venta, datos: FacturaIn, usuario: Usuario) -> None:
    """Crea al cliente con los datos de la factura (o completa el existente con esa cédula/RIF)
    y lo asocia a la venta y a su comanda."""
    cliente = await session.scalar(
        select(Cliente).where(
            Cliente.tipo_documento == datos.receptor_tipo_documento, Cliente.documento == datos.receptor_documento
        )
    )
    if cliente:
        cliente.nombre = datos.receptor_razon_social or cliente.nombre
        cliente.direccion = datos.receptor_domicilio or cliente.direccion
        texto = f"Actualizó los datos del cliente {cliente.nombre} desde la factura de la venta #{venta.id}"
    else:
        cliente = Cliente(
            nombre=datos.receptor_razon_social,
            tipo_documento=datos.receptor_tipo_documento,
            documento=datos.receptor_documento,
            direccion=datos.receptor_domicilio,
        )
        session.add(cliente)
        await insertar(session, "Ya existe un cliente con ese documento")
        texto = f"Registró al cliente {cliente.nombre} desde la factura de la venta #{venta.id}"
    venta.cliente_id = cliente.id
    if venta.comanda.cliente_id is None:
        venta.comanda.cliente_id = cliente.id
    bitacora.registrar(session, usuario, "clientes", "crear", texto, sucursal_id=venta.sucursal_id, entidad="cliente", entidad_id=cliente.id)


@router.put("/ventas/{venta_id}/anulacion", response_model=DatosFiscalesOut, tags=["Facturación"])
async def anular_factura(
    venta_id: int, datos: AnularFacturaIn, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.eliminar)
):
    """Registra la nota de crédito (emitida a mano) que anula una factura. La factura queda en el libro junto a su nota."""
    venta = await _venta_accesible(session, venta_id, usuario)
    if not venta.numero_factura:
        raise Conflicto("La venta no tiene factura registrada; no hay nada que anular")
    if venta.anulada_en:
        raise Conflicto("La factura ya está anulada")
    venta.nota_credito_numero = datos.nota_credito_numero
    venta.nota_credito_control = datos.nota_credito_control
    venta.motivo_anulacion = datos.motivo
    venta.anulada_en = datetime.now(UTC)
    venta.anulada_por_id = usuario.id
    bitacora.registrar(
        session, usuario, "ventas", "anular_factura",
        f"Anuló la factura N° {venta.numero_factura} de la venta #{venta.id} con la nota de crédito N° {datos.nota_credito_numero} · {datos.motivo}",
        sucursal_id=venta.sucursal_id, entidad="venta", entidad_id=venta.id,
    )
    await guardar(session, "Ese número de nota de crédito ya está registrado en otra venta de la sucursal")
    return await _datos_fiscales(session, venta)


@router.delete("/ventas/{venta_id}/anulacion", response_model=DatosFiscalesOut, tags=["Facturación"])
async def deshacer_anulacion(venta_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.eliminar)):
    """Deshace el registro de la anulación (si se cargó por error)."""
    venta = await _venta_accesible(session, venta_id, usuario)
    if not venta.anulada_en:
        raise Conflicto("La factura no está anulada")
    bitacora.registrar(
        session, usuario, "ventas", "deshacer_anulacion",
        f"Deshizo la anulación (nota de crédito N° {venta.nota_credito_numero}) de la venta #{venta.id}",
        sucursal_id=venta.sucursal_id, entidad="venta", entidad_id=venta.id,
    )
    venta.anulada_en = venta.anulada_por_id = venta.motivo_anulacion = venta.nota_credito_numero = venta.nota_credito_control = None
    await guardar(session)
    return await _datos_fiscales(session, venta)


@router.delete("/ventas/{venta_id}/factura", response_model=DatosFiscalesOut, tags=["Facturación"])
async def quitar_factura(venta_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.eliminar)):
    """Deshace el registro (p. ej. si se cargó en la venta equivocada). La venta vuelve a pendientes."""
    venta = await _venta_accesible(session, venta_id, usuario)
    if venta.anulada_en:
        raise Conflicto("La factura está anulada con una nota de crédito; deshaz primero la anulación")
    bitacora.registrar(
        session, usuario, "ventas", "quitar_factura", f"Quitó la factura N° {venta.numero_factura} de la venta #{venta.id}",
        sucursal_id=venta.sucursal_id, entidad="venta", entidad_id=venta.id,
    )
    for campo in FacturaIn.model_fields.keys() - {"guardar_cliente"}:
        setattr(venta, campo, None)
    venta.facturada_en = venta.facturada_por_id = None
    await guardar(session)
    return await _datos_fiscales(session, venta)


@router.get("/ventas/{venta_id}", response_model=VentaDetalleOut, tags=["Ventas"])
async def obtener_venta(venta_id: int, session: SessionDep, usuario: Usuario = _perm(Modulo.ventas, Accion.leer)):
    """Detalle de la venta con la comanda completa: platos pedidos y pagos."""
    venta = await obtener_o_404(session, Venta, venta_id, "Venta")
    verificar_sucursal(usuario, venta.sucursal_id)
    comanda = await srv.obtener_comanda(session, venta.comanda_id)
    return {**_venta_out(venta), "comanda": srv.serializar_comanda(comanda, await monedas_activas(session))}
