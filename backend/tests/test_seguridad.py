from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import PASSWORD, crear_usuario, login

API = "/api/v1"

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


async def test_sin_api_key_rechaza(datos):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as anon:
        assert (await anon.get(f"{API}/public/sucursales/1/menu")).status_code == 401
        r = await anon.get(f"{API}/public/sucursales/1/menu", headers={"X-API-Key": "rk_deadbeef_falsa"})
        assert r.status_code == 401


async def test_api_key_revocada(admin):
    r = await admin.post(f"{API}/api-keys", json={"nombre": "Tablet cocina"})
    assert r.status_code == 201
    clave = r.json()["clave"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost", headers={"X-API-Key": clave}) as c:
        assert (await c.post(f"{API}/auth/login", json={"email": "x@x.com", "password": "x"})).status_code == 401
        await admin.delete(f"{API}/api-keys/{r.json()['id']}")
        r2 = await c.post(f"{API}/auth/login", json={"email": "x@x.com", "password": "x"})
        assert r2.json()["detail"] == "API key requerida o inválida"


async def test_sin_token_y_token_invalido(client):
    assert (await client.get(f"{API}/comandas")).status_code == 401
    r = await client.get(f"{API}/comandas", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


async def test_headers_de_seguridad(client):
    r = await client.get(f"{API}/auth/me")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]


async def test_bloqueo_por_intentos_fallidos(client):
    await crear_usuario("cajero@restify.com")
    for _ in range(5):
        r = await client.post(f"{API}/auth/login", json={"email": "cajero@restify.com", "password": "MalaClave123"})
        assert r.status_code == 401
    # Bloqueada: ni la contraseña correcta entra, y el mensaje no lo revela
    r = await client.post(f"{API}/auth/login", json={"email": "cajero@restify.com", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "Credenciales inválidas"


async def test_rate_limit_login(client):
    codigos = [
        (await client.post(f"{API}/auth/login", json={"email": f"u{i}@x.com", "password": "x"})).status_code for i in range(11)
    ]
    assert codigos[-1] == 429


async def test_refresh_rota_y_detecta_reutilizacion(client):
    await crear_usuario("mesero@restify.com")
    t1 = await login(client, "mesero@restify.com")
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": t1["refresh_token"]})
    assert r.status_code == 200
    t2 = r.json()
    # Reusar el token viejo revoca toda la sesión, incluido el nuevo
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": t1["refresh_token"]})).status_code == 401
    assert (await client.post(f"{API}/auth/refresh", json={"refresh_token": t2["refresh_token"]})).status_code == 401


async def test_cambio_password_invalida_tokens(client):
    await crear_usuario("chef@restify.com")
    t = await login(client, "chef@restify.com")
    h = {"Authorization": f"Bearer {t['access_token']}"}
    r = await client.post(
        f"{API}/auth/cambiar-password", json={"password_actual": PASSWORD, "password_nueva": "NuevaClave4567"}, headers=h
    )
    assert r.status_code == 204
    assert (await client.get(f"{API}/auth/me", headers=h)).status_code == 401


async def test_password_debil_rechazada(admin):
    r = await admin.post(f"{API}/usuarios", json={"email": "a@b.com", "nombre": "A", "password": "123456"})
    assert r.status_code == 422


async def _usuario_con_rol(admin, email, permisos, sucursal_ids=()) -> AsyncClient:
    rol = (await admin.post(f"{API}/roles", json={"nombre": f"rol-{email}", "permisos": permisos})).json()
    r = await admin.post(
        f"{API}/usuarios",
        json={"email": email, "nombre": "X", "password": PASSWORD, "rol_id": rol["id"], "sucursal_ids": list(sucursal_ids)},
    )
    assert r.status_code == 201, r.text
    tokens = await login(admin, email)
    c = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://localhost",
        headers={"X-API-Key": admin.headers["X-API-Key"], "Authorization": f"Bearer {tokens['access_token']}"},
    )
    return c


async def test_permisos_crud_por_modulo(admin, datos):
    cocinero = await _usuario_con_rol(
        admin, "cocina@restify.com", [{"modulo": "cocina", "leer": True, "editar": True}], [datos["sucursal"]["id"]]
    )
    async with cocinero:
        assert (await cocinero.get(f"{API}/cocina", params={"sucursal_id": datos["sucursal"]["id"]})).status_code == 200
        assert (await cocinero.get(f"{API}/ventas")).status_code == 403
        assert (await cocinero.post(f"{API}/insumos", json={"nombre": "Sal", "unidad": "g"})).status_code == 403
        me = (await cocinero.get(f"{API}/auth/me")).json()
        assert me["permisos"]["cocina"] == {"crear": False, "leer": True, "editar": True, "eliminar": False}


async def test_aislamiento_por_sucursal(admin, datos):
    otra = (await admin.post(f"{API}/sucursales", json={"nombre": "Norte"})).json()
    cajero = await _usuario_con_rol(
        admin, "norte@restify.com", [{"modulo": "comandas", "leer": True, "crear": True}], [otra["id"]]
    )
    async with cajero:
        r = await cajero.post(f"{API}/comandas", json={"sucursal_id": datos["sucursal"]["id"]})
        assert r.status_code == 403
        assert (await cajero.post(f"{API}/comandas", json={"sucursal_id": otra["id"]})).status_code == 201


async def test_no_escalar_privilegios(admin):
    gerente = await _usuario_con_rol(
        admin,
        "gerente@restify.com",
        [{"modulo": "roles", "leer": True, "crear": True, "editar": True}, {"modulo": "usuarios", "crear": True}],
    )
    async with gerente:
        # No puede crear un rol con permisos que él no tiene
        r = await gerente.post(f"{API}/roles", json={"nombre": "Dios", "permisos": [{"modulo": "ventas", "leer": True}]})
        assert r.status_code == 403
        # No puede editar su propio rol
        me = (await gerente.get(f"{API}/auth/me")).json()
        r = await gerente.patch(f"{API}/roles/{me['rol']['id']}", json={"permisos": []})
        assert r.status_code == 403
        # No puede crear superadmins
        r = await gerente.post(
            f"{API}/usuarios", json={"email": "s@s.com", "nombre": "S", "password": PASSWORD, "es_superadmin": True}
        )
        assert r.status_code == 403


async def test_subida_medios_valida_contenido(admin, datos):
    url = f"{API}/productos/{datos['hamburguesa']['id']}/medios/archivo"
    r = await admin.post(url, files={"archivo": ("foto.png", PNG_1PX, "image/png")}, data={"es_portada": "true"})
    assert r.status_code == 201, r.text
    medio = r.json()
    assert medio["tipo"] == "imagen" and medio["mime"] == "image/png" and medio["url"].startswith("/media/")
    assert "foto" not in medio["url"]  # nombre aleatorio, nunca el del cliente

    # Un script disfrazado de imagen es rechazado
    r = await admin.post(url, files={"archivo": ("x.png", b"<script>alert(1)</script>", "image/png")})
    assert r.status_code == 422

    # Video por URL externa + varias fotos por producto
    r = await admin.post(
        f"{API}/productos/{datos['hamburguesa']['id']}/medios/url",
        json={"tipo": "video", "url": "https://cdn.ejemplo.com/hamburguesa.mp4", "orden": 1},
    )
    assert r.status_code == 201
    producto = (await admin.get(f"{API}/productos/{datos['hamburguesa']['id']}")).json()
    assert [m["tipo"] for m in producto["medios"]] == ["imagen", "video"]

    r = await admin.get(medio["url"])
    assert r.status_code == 200 and r.content == PNG_1PX


async def test_auditoria_registra_escrituras(admin, datos):
    r = await admin.get(f"{API}/auditoria", params={"limite": 100})
    assert r.status_code == 200
    rutas = {a["ruta"] for a in r.json()["items"]}
    assert f"{API}/productos" in rutas
