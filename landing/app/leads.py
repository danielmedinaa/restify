"""Solicitudes de demo del formulario de contacto, guardadas en SQLite."""

import csv
import hashlib
import io
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    restaurante TEXT,
    telefono TEXT NOT NULL,
    email TEXT,
    sucursales TEXT,
    mensaje TEXT,
    ip_hash TEXT NOT NULL,
    creado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_leads_ip ON leads (ip_hash, creado_en);
"""

SUCURSALES = ["1", "2-3", "4 o más"]
_TELEFONO = re.compile(r"^\+?[0-9 ()-]{7,20}$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")


def conectar(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db, timeout=5)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(ESQUEMA)
    return con


def hash_ip(ip: str, secreto: str) -> str:
    """No se guarda la IP: solo un hash con sal para limitar envíos repetidos."""
    return hashlib.sha256(f"{secreto}:{ip}".encode()).hexdigest()


def validar(datos: dict) -> tuple[dict, dict]:
    """Devuelve (lead limpio, errores por campo)."""

    def campo(nombre, maximo):
        return str(datos.get(nombre) or "").strip()[:maximo]

    lead = {
        "nombre": campo("nombre", 80),
        "restaurante": campo("restaurante", 120),
        "telefono": campo("telefono", 20),
        "email": campo("email", 254).lower(),
        "sucursales": campo("sucursales", 10),
        "mensaje": campo("mensaje", 1000),
    }
    errores = {}
    if len(lead["nombre"]) < 2:
        errores["nombre"] = "Escribe tu nombre."
    if not _TELEFONO.match(lead["telefono"]):
        errores["telefono"] = "Escribe un teléfono válido, por ejemplo +58 412 000 0000."
    if lead["email"] and not _EMAIL.match(lead["email"]):
        errores["email"] = "Ese correo no parece válido."
    if lead["sucursales"] and lead["sucursales"] not in SUCURSALES:
        errores["sucursales"] = "Elige una opción."
    return lead, errores


def demasiados(db: Path, ip_hash: str, maximo: int, ventana_min: int) -> bool:
    desde = (datetime.now(UTC) - timedelta(minutes=ventana_min)).isoformat()
    with closing(conectar(db)) as con:
        (n,) = con.execute("SELECT count(*) FROM leads WHERE ip_hash = ? AND creado_en >= ?", (ip_hash, desde)).fetchone()
    return n >= maximo


def guardar(db: Path, lead: dict, ip_hash: str) -> int:
    with closing(conectar(db)) as con, con:
        cur = con.execute(
            "INSERT INTO leads (nombre, restaurante, telefono, email, sucursales, mensaje, ip_hash, creado_en) "
            "VALUES (:nombre, :restaurante, :telefono, :email, :sucursales, :mensaje, :ip_hash, :creado_en)",
            {**lead, "ip_hash": ip_hash, "creado_en": datetime.now(UTC).isoformat()},
        )
        return cur.lastrowid


def exportar_csv(db: Path) -> str:
    with closing(conectar(db)) as con:
        filas = con.execute(
            "SELECT creado_en, nombre, restaurante, telefono, email, sucursales, mensaje FROM leads ORDER BY id DESC"
        ).fetchall()
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Fecha", "Nombre", "Restaurante", "Teléfono", "Correo", "Sucursales", "Mensaje"])
    w.writerows(filas)
    return buf.getvalue()
