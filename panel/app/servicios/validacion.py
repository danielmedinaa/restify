import re

from flask import current_app

from app.extensions import db
from app.modelos import LIMITES, Instancia

RESERVADOS = {
    "www", "panel", "admin", "api", "app", "demo", "mail", "smtp", "ftp", "ns1", "ns2", "soporte",
    "support", "status", "docs", "blog", "landing", "static", "cdn", "dev", "test", "staging", "root",
    "login", "billing", "pagos", "restify",
}
_SUB = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])$")
_DOMINIO = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
_TEL = re.compile(r"^\+?[0-9 ()-]{7,20}$")
_RIF = re.compile(r"^[VEJPGC]-?\d{6,9}-?\d?$", re.I)


def texto(valor, maximo: int) -> str:
    return " ".join(str(valor or "").split())[:maximo] if maximo < 400 else str(valor or "").strip()[:maximo]


def validar_subdominio(sub: str, excepto_id: int | None = None) -> str | None:
    if not _SUB.match(sub):
        return "El subdominio usa 3 a 32 letras minúsculas, números o guiones (sin empezar ni terminar en guion)."
    if "--" in sub:
        return "El subdominio no puede llevar dos guiones seguidos."
    if sub in RESERVADOS:
        return "Ese subdominio está reservado."
    q = db.session.query(Instancia.id).filter(Instancia.subdominio == sub)
    if excepto_id:
        q = q.filter(Instancia.id != excepto_id)
    if q.first():
        return "Ese subdominio ya está en uso."
    return None


def validar_dominio_propio(dominio: str, excepto_id: int | None = None) -> str | None:
    base = current_app.config["DOMINIO_BASE"]
    if not _DOMINIO.match(dominio):
        return "Dominio no válido (ej: menu.turestaurante.com)."
    if dominio == base or dominio.endswith("." + base):
        return f"Ese dominio ya es de RESTIFY; usa el subdominio. (.{base})"
    if dominio.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")):
        return "Ese dominio no es público."
    q = db.session.query(Instancia.id).filter(Instancia.dominio_propio == dominio)
    if excepto_id:
        q = q.filter(Instancia.id != excepto_id)
    if q.first():
        return "Ese dominio ya está asignado a otra instancia."
    return None


def validar_cliente(form) -> tuple[dict, dict]:
    d = {
        "nombre": texto(form.get("nombre"), 120),
        "razon_social": texto(form.get("razon_social"), 160) or None,
        "rif": texto(form.get("rif"), 20).upper() or None,
        "contacto": texto(form.get("contacto"), 120) or None,
        "email": texto(form.get("email"), 254).lower() or None,
        "telefono": texto(form.get("telefono"), 30) or None,
        "notas": texto(form.get("notas"), 2000) or None,
    }
    e = {}
    if len(d["nombre"]) < 2:
        e["nombre"] = "Escribe el nombre del cliente."
    if d["email"] and not _EMAIL.match(d["email"]):
        e["email"] = "Correo no válido."
    if d["telefono"] and not _TEL.match(d["telefono"]):
        e["telefono"] = "Teléfono no válido."
    if d["rif"] and not _RIF.match(d["rif"]):
        e["rif"] = "RIF no válido (ej: J-12345678-9)."
    return d, e


def entero_o_none(valor, nombre: str, errores: dict, maximo: int = 10_000_000) -> int | None:
    """Campo de límite: vacío = ilimitado (plan) o sin ajuste (suscripción)."""
    v = str(valor or "").strip()
    if not v:
        return None
    if not v.isdigit() or int(v) > maximo:
        errores[nombre] = f"Debe ser un número entero entre 0 y {maximo}."
        return None
    return int(v)


def validar_plan(form) -> tuple[dict, dict]:
    e: dict = {}
    d = {
        "nombre": texto(form.get("nombre"), 60),
        "descripcion": texto(form.get("descripcion"), 300) or None,
    }
    if len(d["nombre"]) < 2:
        e["nombre"] = "Escribe el nombre del plan."
    try:
        from decimal import Decimal, InvalidOperation

        precio = Decimal(str(form.get("precio_mensual") or "0").replace(",", "."))
        if precio < 0 or precio > 1_000_000:
            raise InvalidOperation
        d["precio_mensual"] = precio.quantize(Decimal("0.01"))
    except Exception:
        e["precio_mensual"] = "Precio no válido."
    for n in LIMITES:
        d[n] = entero_o_none(form.get(n), n, e)
    return d, e
