"""Plugins: solo firmados por RESTIFY, con permisos que aprueba el administrador."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.core.database import SessionLocal
from app.services import plugins as srv

API = "/api/v1"
MANIFIESTO = {
    "slug": "cobros-demo",
    "nombre": "Cobros demo",
    "version": "1.0.0",
    "autor": "RESTIFY",
    "descripcion": "Plugin de prueba",
    "permisos": ["comandas:leer", "cobros:crear"],
    "eventos": ["comanda.creada"],
    "capacidades": ["cobro"],
}


@pytest.fixture
def clave(monkeypatch):
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    monkeypatch.setattr(settings, "plugin_claves_publicas", [pub])
    return k


def firmar(k, manifiesto=None):
    m = manifiesto or MANIFIESTO
    return {"manifiesto": m, "firma": base64.b64encode(k.sign(srv.canonico(m))).decode()}


async def test_instala_firmado_y_el_token_solo_se_muestra_una_vez(admin, clave):
    paquete = firmar(clave)
    r = await admin.post(f"{API}/plugins/inspeccionar", json=paquete)
    assert r.status_code == 200 and r.json()["firmado"] is True and not r.json()["ya_instalado"]
    assert [p["permiso"] for p in r.json()["permisos"]] == ["comandas:leer", "cobros:crear"]

    r = await admin.post(f"{API}/plugins", json={**paquete, "permisos_aprobados": ["comandas:leer"]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["token"].startswith("rsp_") and d["permisos_aprobados"] == ["comandas:leer"]
    assert "token" not in (await admin.get(f"{API}/plugins")).json()[0]

    async with SessionLocal() as s:
        p = await srv.autenticar(s, d["token"])
        assert p is not None and srv.permisos_de(p) == ["comandas:leer"]  # solo lo aprobado
        assert await srv.autenticar(s, d["token"] + "x") is None

    # Rotar: el token viejo deja de servir
    nuevo = (await admin.post(f"{API}/plugins/{d['id']}/token")).json()["token"]
    async with SessionLocal() as s:
        assert await srv.autenticar(s, d["token"]) is None and await srv.autenticar(s, nuevo) is not None

    # Pausar y desinstalar también cortan el acceso
    await admin.put(f"{API}/plugins/{d['id']}/activo", params={"activo": False})
    async with SessionLocal() as s:
        assert await srv.autenticar(s, nuevo) is None
    assert (await admin.delete(f"{API}/plugins/{d['id']}")).status_code == 204
    assert (await admin.get(f"{API}/plugins")).json() == []


async def test_rechaza_firmas_malas_y_cambios(admin, clave):
    ok = firmar(clave)
    # Cambiar un permiso después de firmar invalida la firma
    manipulado = {"manifiesto": {**MANIFIESTO, "permisos": ["comandas:leer", "ventas:leer"]}, "firma": ok["firma"]}
    assert (await admin.post(f"{API}/plugins/inspeccionar", json=manipulado)).status_code == 422
    # Firmado con otra clave
    assert (await admin.post(f"{API}/plugins/inspeccionar", json=firmar(Ed25519PrivateKey.generate()))).status_code == 422
    # Firma con basura
    assert (await admin.post(f"{API}/plugins/inspeccionar", json={"manifiesto": MANIFIESTO, "firma": "no-es-base64!!"})).status_code == 422


async def test_sin_firma_solo_en_desarrollo_con_la_opcion_encendida(admin, clave, monkeypatch):
    sin = {"manifiesto": MANIFIESTO}
    assert (await admin.post(f"{API}/plugins/inspeccionar", json=sin)).status_code == 422
    monkeypatch.setattr(settings, "plugins_permitir_sin_firma", True)
    r = await admin.post(f"{API}/plugins/inspeccionar", json=sin)
    assert r.status_code == 200 and r.json()["firmado"] is False
    # En producción nunca, aunque la opción esté encendida
    monkeypatch.setattr(settings, "environment", "production")
    assert (await admin.post(f"{API}/plugins/inspeccionar", json=sin)).status_code == 422


async def test_permisos(admin, clave):
    # Usuarios, roles y bitácora no se pueden pedir; tampoco permisos inventados
    for malo in ("usuarios:leer", "roles:editar", "bitacora:leer", "todo:todo"):
        p = firmar(clave, {**MANIFIESTO, "permisos": [malo]})
        assert (await admin.post(f"{API}/plugins/inspeccionar", json=p)).status_code == 422, malo
    # No se puede aprobar más de lo que el plugin pidió
    paquete = firmar(clave)
    r = await admin.post(f"{API}/plugins", json={**paquete, "permisos_aprobados": ["comandas:leer", "ventas:leer"]})
    assert r.status_code == 422
    # Los sensibles salen marcados
    sens = firmar(clave, {**MANIFIESTO, "slug": "otro-plugin", "permisos": ["ventas:leer", "comandas:leer"]})
    r = await admin.post(f"{API}/plugins/inspeccionar", json=sens)
    assert {p["permiso"]: p["sensible"] for p in r.json()["permisos"]} == {"ventas:leer": True, "comandas:leer": False}
    # Se pueden cambiar los permisos después, siempre dentro de lo pedido
    d = (await admin.post(f"{API}/plugins", json={**paquete, "permisos_aprobados": ["comandas:leer"]})).json()
    r = await admin.put(f"{API}/plugins/{d['id']}/permisos", json={"permisos_aprobados": ["comandas:leer", "cobros:crear"]})
    assert r.json()["permisos_aprobados"] == ["cobros:crear", "comandas:leer"]
    assert (await admin.put(f"{API}/plugins/{d['id']}/permisos", json={"permisos_aprobados": ["cocina:leer"]})).status_code == 422
    # Duplicado
    assert (await admin.post(f"{API}/plugins", json=paquete)).status_code == 409


async def test_revocados_no_se_instalan_ni_se_usan(admin, clave, monkeypatch):
    paquete = firmar(clave)
    d = (await admin.post(f"{API}/plugins", json=paquete)).json()
    monkeypatch.setattr(settings, "plugins_revocados", ["cobros-demo@1.0.0"])
    async with SessionLocal() as s:
        assert await srv.autenticar(s, d["token"]) is None  # ya instalado: deja de servir
    await admin.delete(f"{API}/plugins/{d['id']}")
    assert (await admin.post(f"{API}/plugins/inspeccionar", json=paquete)).status_code == 422
