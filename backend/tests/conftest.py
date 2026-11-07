import os
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

assert os.environ.get("ENVIRONMENT") == "test", "Los tests solo corren con ENVIRONMENT=test (docker compose run tests)"

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.core.security import hash_password, new_api_key  # noqa: E402
from app.main import app  # noqa: E402
from app.services import config  # noqa: E402
from app.models import ApiKey, Usuario  # noqa: E402

PASSWORD = "ClaveSegura123"


@pytest.fixture(scope="session", autouse=True)
def migrar_bd():
    """Esquema limpio y migraciones de Alembic (se prueban las migraciones reales)."""
    import asyncio

    async def reset():
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    subprocess.run(["alembic", "upgrade", "head"], check=True)


@pytest.fixture(autouse=True)
async def limpiar():
    tablas = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    await redis_client.flushdb()
    config.invalidar()  # la copia en memoria no debe sobrevivir al TRUNCATE entre tests
    yield


@pytest.fixture
async def api_key() -> str:
    clave, prefijo, key_hash = new_api_key()
    async with SessionLocal() as s:
        s.add(ApiKey(nombre="tests", prefijo=prefijo, key_hash=key_hash))
        await s.commit()
    return clave


@pytest.fixture
async def client(api_key):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost", headers={"X-API-Key": api_key}
    ) as c:
        yield c


async def crear_usuario(email: str, superadmin: bool = False) -> Usuario:
    async with SessionLocal() as s:
        u = Usuario(email=email, nombre=email.split("@")[0], password_hash=hash_password(PASSWORD), es_superadmin=superadmin)
        s.add(u)
        await s.commit()
        return u


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def admin(client) -> AsyncClient:
    """Cliente autenticado como superadmin."""
    await crear_usuario("admin@restify.com", superadmin=True)
    tokens = await login(client, "admin@restify.com")
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return client


@pytest.fixture
async def datos(admin) -> dict:
    """Escenario base: sucursal, USD principal + VES, carne 200 g (mínimo 60), pan, hamburguesa 150 g."""
    c = admin

    async def post(url, body):
        r = await c.post(url, json=body)
        assert r.status_code == 201, r.text
        return r.json()

    sucursal = await post("/api/v1/sucursales", {"nombre": "Centro"})
    usd = await post("/api/v1/monedas", {"codigo": "USD", "nombre": "Dólar", "simbolo": "$", "es_principal": True})
    ves = await post(
        "/api/v1/monedas", {"codigo": "VES", "nombre": "Bolívar", "simbolo": "Bs", "tasa": "36.5", "operacion": "multiplicar"}
    )
    carne = await post("/api/v1/insumos", {"nombre": "Carne molida", "unidad": "g"})
    pan = await post("/api/v1/insumos", {"nombre": "Pan de hamburguesa", "unidad": "unidad"})
    inv_carne = await post(
        "/api/v1/inventario", {"sucursal_id": sucursal["id"], "insumo_id": carne["id"], "cantidad": "200", "stock_minimo": "60"}
    )
    inv_pan = await post(
        "/api/v1/inventario", {"sucursal_id": sucursal["id"], "insumo_id": pan["id"], "cantidad": "20", "stock_minimo": "5"}
    )
    receta = await post(
        "/api/v1/recetas",
        {
            "nombre": "Hamburguesa clásica",
            "ingredientes": [{"insumo_id": carne["id"], "cantidad": "150"}, {"insumo_id": pan["id"], "cantidad": "1"}],
        },
    )
    categoria = await post("/api/v1/categorias", {"nombre": "Hamburguesas"})
    hamburguesa = await post(
        "/api/v1/productos",
        {"nombre": "Hamburguesa", "precio_base": "10.00", "receta_id": receta["id"], "categoria_id": categoria["id"]},
    )
    refresco = await post("/api/v1/productos", {"nombre": "Refresco", "precio_base": "2.00"})
    mesa = await post("/api/v1/mesas", {"sucursal_id": sucursal["id"], "nombre": "Mesa 1"})
    mesa2 = await post("/api/v1/mesas", {"sucursal_id": sucursal["id"], "nombre": "Mesa 2"})
    qr = (await c.get(f"/api/v1/mesas/{mesa['id']}/qr-url")).json()["url"].rsplit("/", 1)[1]
    return {
        "sucursal": sucursal,
        "usd": usd,
        "ves": ves,
        "carne": carne,
        "pan": pan,
        "inv_carne": inv_carne,
        "inv_pan": inv_pan,
        "receta": receta,
        "hamburguesa": hamburguesa,
        "refresco": refresco,
        "mesa": mesa,
        "mesa2": mesa2,
        "qr": qr,
    }
