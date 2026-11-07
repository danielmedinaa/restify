from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from app.api.deps import SessionDep, requiere, verificar_sucursal
from app.api.utils import Limite, guardar, insertar, obtener_o_404
from app.core.errors import Conflicto, NoEncontrado
from app.core.realtime import canal_sucursal, emitir
from app.models import Accion, EstadoTurno, Modulo, Moneda, MovimientoCaja, Sucursal, TurnoCaja, Usuario
from app.schemas.caja import AbrirTurnoIn, CerrarTurnoIn, MovimientoCajaIn, TurnoOut
from app.services import bitacora
from app.services import caja as srv

router = APIRouter(prefix="/caja", tags=["Turnos de caja"])


def _perm(accion: Accion):
    return Depends(requiere(Modulo.caja, accion))


async def _turno(session, turno_id: int, usuario: Usuario) -> TurnoCaja:
    turno = await obtener_o_404(session, TurnoCaja, turno_id, "Turno")
    verificar_sucursal(usuario, turno.sucursal_id)
    return turno


async def _monedas_validas(session, ids: list[int]) -> dict[int, Moneda]:
    monedas = {m.id: m for m in await session.scalars(select(Moneda).where(Moneda.id.in_(ids)))}
    if faltan := set(ids) - monedas.keys():
        raise NoEncontrado(f"Moneda {sorted(faltan)}")
    return monedas


@router.get("/turno-actual", response_model=TurnoOut | None)
async def turno_actual(sucursal_id: int, session: SessionDep, usuario: Usuario = _perm(Accion.leer)):
    """El turno abierto de la sucursal, con su resumen en vivo (null si la caja está cerrada)."""
    verificar_sucursal(usuario, sucursal_id)
    turno = await srv.turno_abierto(session, sucursal_id)
    return await srv.serializar_turno(session, turno) if turno else None


@router.get("/turnos", response_model=list[TurnoOut])
async def listar_turnos(sucursal_id: int, session: SessionDep, usuario: Usuario = _perm(Accion.leer), limite: Limite = 20):
    verificar_sucursal(usuario, sucursal_id)
    turnos = await session.scalars(
        select(TurnoCaja).where(TurnoCaja.sucursal_id == sucursal_id).order_by(TurnoCaja.id.desc()).limit(limite)
    )
    return [await srv.serializar_turno(session, t) for t in turnos]


@router.get("/turnos/{turno_id}", response_model=TurnoOut)
async def obtener_turno(turno_id: int, session: SessionDep, usuario: Usuario = _perm(Accion.leer)):
    return await srv.serializar_turno(session, await _turno(session, turno_id, usuario))


@router.post("/turnos", response_model=TurnoOut, status_code=status.HTTP_201_CREATED)
async def abrir_turno(datos: AbrirTurnoIn, session: SessionDep, usuario: Usuario = _perm(Accion.crear)):
    """Abre la caja con el efectivo inicial. Desde ahí, cada pago queda en este turno."""
    verificar_sucursal(usuario, datos.sucursal_id)
    sucursal = await obtener_o_404(session, Sucursal, datos.sucursal_id, "Sucursal")
    if await srv.turno_abierto(session, datos.sucursal_id):
        raise Conflicto("Ya hay un turno de caja abierto en esta sucursal")
    monedas = await _monedas_validas(session, [f.moneda_id for f in datos.fondo])
    turno = TurnoCaja(
        sucursal_id=sucursal.id,
        abierto_por_id=usuario.id,
        fondo=[{"moneda_id": f.moneda_id, "monto": str(f.monto)} for f in datos.fondo if f.monto > 0],
        notas=datos.notas,
        movimientos=[],
    )
    session.add(turno)
    await insertar(session, "Ya hay un turno de caja abierto en esta sucursal")
    fondo_txt = ", ".join(bitacora.dinero(f.monto, monedas[f.moneda_id].simbolo) for f in datos.fondo if f.monto > 0) or "sin fondo"
    bitacora.registrar(
        session, usuario, "caja", "abrir_turno", f"Abrió la caja de {sucursal.nombre} con {fondo_txt}",
        sucursal_id=sucursal.id, entidad="turno", entidad_id=turno.id,
    )
    emitir(session, canal_sucursal(sucursal.id), "caja.turno", {"turno_id": turno.id, "estado": "abierto"})
    await guardar(session)
    await session.refresh(turno)
    return await srv.serializar_turno(session, turno)


@router.post("/turnos/{turno_id}/movimientos", response_model=TurnoOut, status_code=status.HTTP_201_CREATED)
async def movimiento_caja(turno_id: int, datos: MovimientoCajaIn, session: SessionDep, usuario: Usuario = _perm(Accion.crear)):
    """Ingreso o retiro de efectivo de la gaveta (cambio del banco, pago a un proveedor…)."""
    turno = await _turno(session, turno_id, usuario)
    if turno.estado != EstadoTurno.abierto:
        raise Conflicto("El turno ya está cerrado")
    moneda = (await _monedas_validas(session, [datos.moneda_id]))[datos.moneda_id]
    turno.movimientos.append(
        MovimientoCaja(tipo=datos.tipo, moneda_id=moneda.id, moneda=moneda, monto=datos.monto, motivo=datos.motivo, usuario_id=usuario.id)
    )
    verbo = "Ingresó" if datos.tipo == "ingreso" else "Retiró"
    bitacora.registrar(
        session, usuario, "caja", datos.tipo.value,
        f"{verbo} {bitacora.dinero(datos.monto, moneda.simbolo)} {'a' if datos.tipo == 'ingreso' else 'de'} la caja de {turno.sucursal.nombre} · {datos.motivo}",
        sucursal_id=turno.sucursal_id, entidad="turno", entidad_id=turno.id,
    )
    await guardar(session)
    await session.refresh(turno)
    return await srv.serializar_turno(session, turno)


@router.post("/turnos/{turno_id}/cerrar", response_model=TurnoOut)
async def cerrar_turno(turno_id: int, datos: CerrarTurnoIn, session: SessionDep, usuario: Usuario = _perm(Accion.editar)):
    """Arqueo: se cuenta el efectivo por moneda y se compara con lo esperado."""
    turno = await _turno(session, turno_id, usuario)
    if turno.estado != EstadoTurno.abierto:
        raise Conflicto("El turno ya está cerrado")
    contado = {c.moneda_id: srv.q2(c.monto) for c in datos.contado}
    resumen = await srv.resumen_turno(session, turno)
    arqueo = []
    ids = {e["moneda_id"] for e in resumen["efectivo"]} | set(contado)
    esperado = {e["moneda_id"]: e["esperado"] for e in resumen["efectivo"]}
    monedas = await _monedas_validas(session, list(ids))
    for mid in sorted(ids):
        e = esperado.get(mid, srv.CERO)
        c = contado.get(mid, srv.CERO)
        arqueo.append({"moneda_id": mid, "esperado": str(e), "contado": str(c), "diferencia": str(c - e)})
    turno.arqueo = arqueo
    turno.estado = EstadoTurno.cerrado
    turno.cerrado_en = datetime.now(UTC)
    turno.cerrado_por_id = usuario.id
    if datos.notas:
        turno.notas = "\n".join(filter(None, [turno.notas, datos.notas]))
    descuadres = [f"{bitacora.dinero(srv.q2(c - esperado.get(m, srv.CERO)), monedas[m].simbolo)}" for m, c in contado.items() if c != esperado.get(m, srv.CERO)]
    bitacora.registrar(
        session, usuario, "caja", "cerrar_turno",
        f"Cerró la caja de {turno.sucursal.nombre}: {resumen['ventas']} ventas"
        + (f" · descuadre {', '.join(descuadres)}" if descuadres else " · cuadró exacto"),
        sucursal_id=turno.sucursal_id, entidad="turno", entidad_id=turno.id, datos={"arqueo": arqueo},
    )
    emitir(session, canal_sucursal(turno.sucursal_id), "caja.turno", {"turno_id": turno.id, "estado": "cerrado"})
    await guardar(session)
    return await srv.serializar_turno(session, turno)
