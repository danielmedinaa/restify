"""Puntos de cobro (POS): manuales o conectados por API a cualquier proveedor (solo superadmin)."""

import json
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field, field_validator
from sqlalchemy import select

from app.api.deps import SessionDep, UsuarioActual, requiere_superadmin
from app.api.utils import guardar, obtener_o_404
from app.core.errors import Invalido
from app.models import PosDispositivo, Sucursal
from app.schemas.base import MontoPositivo, Schema
from app.services import bitacora
from app.services import pos as srv

router = APIRouter(prefix="/pos", tags=["Puntos de cobro (POS)"], dependencies=[Depends(requiere_superadmin)])

Nombre = Annotated[str, Field(min_length=2, max_length=80)]
NombreSecreto = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")]
Ruta = Annotated[str, Field(max_length=300, pattern=r"^/[^\s]*$")]
PathJson = Annotated[str, Field(max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")]


class OperacionIn(Schema):
    metodo: Literal["GET", "POST", "PUT", "PATCH"] = "POST"
    ruta: Ruta
    cabeceras: dict[str, str] = Field(default_factory=dict, max_length=10)
    cuerpo: dict | list | None = None


class CrearIn(OperacionIn):
    id_path: PathJson | None = None  # dónde viene el id del cobro en la respuesta
    url_path: PathJson | None = None  # dónde viene el enlace/QR de pago


class ConsultarIn(OperacionIn):
    metodo: Literal["GET", "POST"] = "GET"
    estado_path: PathJson | None = None
    pagado: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=10)  # valores que significan "pagado"


class ConfigApi(Schema):
    base_url: Annotated[str, Field(max_length=200, pattern=r"^https://[^\s/]+(/[^\s]*)?$")]
    cabeceras: dict[str, str] = Field(default_factory=dict, max_length=10)
    crear: CrearIn
    consultar: ConsultarIn | None = None

    @field_validator("cabeceras")
    @classmethod
    def _cab(cls, v: dict[str, str]) -> dict[str, str]:
        for k, val in v.items():
            if len(k) > 60 or len(val) > 500 or "\n" in k + val or "\r" in k + val:
                raise ValueError("Cabecera no válida")
        return v


class PosIn(Schema):
    nombre: Nombre
    sucursal_id: int | None = None
    tipo: Literal["manual", "api"] = "manual"
    activo: bool = True
    config: ConfigApi | None = None
    # Valor = reemplaza, null = borra, no enviado = se conserva
    secretos: dict[NombreSecreto, Annotated[str, Field(max_length=500)] | None] = Field(default_factory=dict, max_length=20)


class PosOut(Schema):
    id: int
    nombre: str
    sucursal_id: int | None
    tipo: str
    activo: bool
    config: dict | None
    secretos_configurados: list[str]


class CobroPruebaIn(Schema):
    monto: MontoPositivo = Decimal("14")
    moneda: Annotated[str, Field(pattern=r"^[A-Z]{3,4}$")] = "VES"


def _out(d: PosDispositivo) -> dict:
    return {
        "id": d.id,
        "nombre": d.nombre,
        "sucursal_id": d.sucursal_id,
        "tipo": d.tipo,
        "activo": d.activo,
        "config": srv.leer_config(d) or None,
        "secretos_configurados": sorted(srv.leer_secretos(d)),
    }


async def _aplicar(session, d: PosDispositivo, datos: PosIn) -> None:
    if datos.sucursal_id is not None and not await session.get(Sucursal, datos.sucursal_id):
        raise Invalido("La sucursal no existe")
    if datos.tipo == "api":
        if datos.config is None:
            raise Invalido("Un punto de cobro por API necesita su configuración")
        await srv.verificar_url(datos.config.base_url)
    d.nombre, d.sucursal_id, d.tipo, d.activo = datos.nombre, datos.sucursal_id, datos.tipo, datos.activo
    d.config = json.dumps(datos.config.model_dump(exclude_none=True), ensure_ascii=False) if datos.tipo == "api" and datos.config else None
    srv.guardar_secretos(d, dict(datos.secretos))


@router.get("", response_model=list[PosOut])
async def listar(session: SessionDep):
    filas = (await session.scalars(select(PosDispositivo).order_by(PosDispositivo.nombre))).all()
    return [_out(d) for d in filas]


@router.post("", response_model=PosOut, status_code=201)
async def crear(datos: PosIn, session: SessionDep, actor: UsuarioActual):
    d = PosDispositivo()
    await _aplicar(session, d, datos)
    session.add(d)
    await session.flush()
    bitacora.registrar(session, actor, "pos", "crear", f"Creó el punto de cobro {d.nombre}", entidad="pos", entidad_id=d.id)
    await guardar(session)
    return _out(d)


@router.put("/{pos_id}", response_model=PosOut)
async def editar(pos_id: int, datos: PosIn, session: SessionDep, actor: UsuarioActual):
    d = await obtener_o_404(session, PosDispositivo, pos_id, "Punto de cobro")
    await _aplicar(session, d, datos)
    bitacora.registrar(session, actor, "pos", "editar", f"Editó el punto de cobro {d.nombre}", entidad="pos", entidad_id=d.id)
    await guardar(session)
    return _out(d)


@router.delete("/{pos_id}", status_code=204)
async def eliminar(pos_id: int, session: SessionDep, actor: UsuarioActual):
    d = await obtener_o_404(session, PosDispositivo, pos_id, "Punto de cobro")
    bitacora.registrar(session, actor, "pos", "eliminar", f"Eliminó el punto de cobro {d.nombre}", entidad="pos", entidad_id=d.id)
    await session.delete(d)
    await guardar(session)


@router.post("/{pos_id}/cobro-prueba")
async def cobro_de_prueba(pos_id: int, datos: CobroPruebaIn, session: SessionDep, actor: UsuarioActual):
    """Crea un cobro real en el proveedor (usa su sandbox) para comprobar que la configuración funciona."""
    d = await obtener_o_404(session, PosDispositivo, pos_id, "Punto de cobro")
    r = await srv.crear_cobro(d, monto=str(datos.monto), moneda=datos.moneda, referencia=f"prueba-{d.id}", nombre="Prueba RESTIFY", descripcion="Cobro de prueba")
    bitacora.registrar(session, actor, "pos", "probar", f"Probó el punto de cobro {d.nombre}", entidad="pos", entidad_id=d.id)
    await guardar(session)
    return r


@router.get("/{pos_id}/cobro/{id_externo}")
async def estado_del_cobro(pos_id: int, id_externo: Annotated[str, Field(max_length=200, pattern=r"^[A-Za-z0-9_.:-]+$")], session: SessionDep):
    d = await obtener_o_404(session, PosDispositivo, pos_id, "Punto de cobro")
    return await srv.consultar_cobro(d, id_externo)
