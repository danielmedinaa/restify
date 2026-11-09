"""Instancia de demostración completa (app/demo.py): se carga entera, se puede repetir y se puede usar."""

from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app import demo
from app.core.database import SessionLocal
from app.models import Compra, Insumo, Inventario, Mesa, Moneda, Producto, Proveedor, Rol, Usuario, Zona
from tests.conftest import PASSWORD, crear_usuario

API = "/api/v1"
ADMIN = "admin@demo.turestify.com"


async def _preparar(**extra):
    async with SessionLocal() as s:
        return await demo.preparar(s, email=ADMIN, nombre="Admin Demo", password=PASSWORD, **extra)


async def _contar(modelo) -> int:
    async with SessionLocal() as s:
        return await s.scalar(select(func.count()).select_from(modelo))


async def test_carga_completa():
    r = await _preparar()
    assert await _contar(Proveedor) == len(demo.PROVEEDORES) == 5
    assert await _contar(Insumo) == len(demo.INSUMOS)
    assert await _contar(Producto) == len(demo.MENU)
    assert await _contar(Compra) == 5  # una por proveedor
    assert await _contar(Moneda) == 2
    assert await _contar(Zona) == 2 and await _contar(Mesa) == 16
    assert await _contar(Rol) == 3 and await _contar(Usuario) == 4  # administrador + mesero, cocina y cajero
    assert r.creado["administradores"] == 1 and r.creado["productos"] == len(demo.MENU)


async def test_se_puede_repetir_sin_duplicar():
    await _preparar()
    antes = [await _contar(m) for m in (Proveedor, Insumo, Producto, Compra, Mesa, Usuario, Inventario)]
    r = await _preparar()
    assert r.creado == {}  # nada nuevo
    assert antes == [await _contar(m) for m in (Proveedor, Insumo, Producto, Compra, Mesa, Usuario, Inventario)]


async def test_las_compras_dejan_stock_y_ultimo_costo():
    await _preparar()
    async with SessionLocal() as s:
        carne = await s.scalar(select(Insumo).where(Insumo.nombre == "Carne molida"))
        inv = await s.scalar(select(Inventario).where(Inventario.insumo_id == carne.id))
    assert inv.cantidad == Decimal(15000) and inv.stock_minimo == Decimal(3000)  # 15 bolsas de 1 kg
    assert carne.costo_unitario == Decimal("0.006500")  # $6.50 el kilo
    # todo lo que se vende tiene su insumo con costo (la rentabilidad no queda en blanco)
    async with SessionLocal() as s:
        sin_costo = (await s.scalars(select(Insumo.nombre).where(Insumo.costo_unitario.is_(None)))).all()
    assert sin_costo == []


async def test_el_menu_usa_receta_o_reventa_segun_corresponda():
    await _preparar()
    async with SessionLocal() as s:
        prods = {p.nombre: p for p in await s.scalars(select(Producto))}
    assert prods["Hamburguesa clásica"].control_stock == "receta"
    assert prods["Pepsi"].control_stock == "directo" and prods["Quesillo"].control_stock == "directo"
    assert all(p.precio_base > 0 for p in prods.values())
    assert all(p.control_stock != "ninguno" for p in prods.values())  # todo descuenta inventario


async def test_la_demo_trae_bolivares_a_tasa_bcv():
    await _preparar(tasa_bcv=Decimal("40.25"))
    async with SessionLocal() as s:
        monedas = {m.codigo: m for m in await s.scalars(select(Moneda))}
    assert monedas["USD"].es_principal and monedas["VES"].tasa == Decimal("40.25") and monedas["VES"].es_fiscal


async def test_los_usuarios_demo_entran_y_cada_rol_ve_solo_lo_suyo(client):
    await _preparar()
    for rol in ("Mesero", "Cocina", "Cajero"):
        r = await client.post(f"{API}/auth/login", json={"email": demo.correo_demo(rol, "demo.turestify.com"), "password": PASSWORD})
        assert r.status_code == 200, (rol, r.text)
    mesero = (await client.post(f"{API}/auth/login", json={"email": "mesero@demo.turestify.com", "password": PASSWORD})).json()
    cab = {"Authorization": f"Bearer {mesero['access_token']}"}
    assert (await client.get(f"{API}/productos", headers=cab)).status_code == 200
    assert (await client.get(f"{API}/usuarios", headers=cab)).status_code == 403  # un mesero no administra usuarios


async def test_si_el_administrador_ya_existe_no_se_crea_otro():
    await crear_usuario("dueno@restify.com", superadmin=True)
    r = await _preparar()
    assert "administradores" not in r.creado
    assert await _contar(Usuario) == 1 + 3


async def test_clave_debil_se_rechaza_antes_de_crear_nada():
    async with SessionLocal() as s:
        with pytest.raises(ValidationError):
            await demo.preparar(s, email=ADMIN, nombre="x", password="corta")
    assert await _contar(Usuario) == 0


async def test_si_la_moneda_principal_no_es_dolar_no_toca_nada():
    async with SessionLocal() as s:
        s.add(Moneda(codigo="VES", nombre="Bolívar", simbolo="Bs", es_principal=True, tasa=Decimal(1)))
        await s.commit()
    with pytest.raises(ValueError, match="USD"):
        await _preparar()
    assert await _contar(Producto) == 0 and await _contar(Proveedor) == 0  # nada quedó a medias


async def test_los_usuarios_demo_pueden_tener_otra_clave_que_el_administrador(client):
    clave_usuarios = "OtraClave2026Demo"
    await _preparar(password_usuarios=clave_usuarios)
    entra = lambda email, clave: client.post(f"{API}/auth/login", json={"email": email, "password": clave})
    assert (await entra("mesero@demo.turestify.com", clave_usuarios)).status_code == 200
    assert (await entra(ADMIN, PASSWORD)).status_code == 200
    # la clave de los prospectos NO abre el administrador, ni la del administrador abre a los usuarios demo
    assert (await entra(ADMIN, clave_usuarios)).status_code == 401
    assert (await entra("mesero@demo.turestify.com", PASSWORD)).status_code == 401
