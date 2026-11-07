"""Bitácora: quién hizo qué y cuándo, escrito para leerse ("Ana repuso 500 g de Carne molida").

La entrada se agrega a la sesión del cambio, así se guarda en el mismo commit: si el cambio
falla, tampoco queda registro. La IP se toma de la petición en curso (contextvar).
"""

from contextvars import ContextVar
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bitacora, Usuario

ip_actual: ContextVar[str | None] = ContextVar("ip_actual", default=None)


def registrar(
    session: AsyncSession,
    usuario: Usuario,
    modulo: str,
    accion: str,
    descripcion: str,
    *,
    sucursal_id: int | None = None,
    entidad: str | None = None,
    entidad_id: int | None = None,
    datos: dict | None = None,
) -> None:
    session.add(
        Bitacora(
            usuario_id=usuario.id,
            usuario_nombre=usuario.nombre,
            sucursal_id=sucursal_id,
            modulo=modulo,
            accion=accion,
            descripcion=descripcion[:500],
            entidad=entidad,
            entidad_id=entidad_id,
            datos=_json(datos) if datos else None,
            ip=ip_actual.get(),
        )
    )


def cant(valor: Decimal, unidad: str) -> str:
    """Decimal(500.000), "g" -> "500 g"."""
    n = f"{valor.normalize():f}"
    return f"{n} {'u' if unidad == 'unidad' else unidad}"


def dinero(valor: Decimal, simbolo: str = "$") -> str:
    entero, _, dec = f"{valor:.2f}".partition(".")
    signo = "-" if entero.startswith("-") else ""
    entero = entero.lstrip("-")
    miles = f"{int(entero):,}".replace(",", ".")
    return f"{simbolo} {signo}{miles},{dec}"


def _json(datos: dict) -> dict:
    """Los Decimal se guardan como texto para no perder precisión en el JSONB."""
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in datos.items()}
