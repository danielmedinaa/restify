import pyotp
import pytest

from app import auditoria
from app.extensions import db
from app.modelos import Admin, Cliente, Evento, Plan, Suscripcion
from app.servicios import suscripciones as svc
from tests.conftest import PASSWORD, crear_admin


def test_login_exige_2fa_y_entra(app, cliente):
    a, secreto = crear_admin()
    cliente.csrf()
    r = cliente.post("/login", {"email": a.email, "password": PASSWORD})
    assert r.status_code == 302 and "/login/2fa" in r.location
    assert cliente.c.get("/").status_code == 302  # aún sin sesión
    assert cliente.post("/login/2fa", {"codigo": "000000"}).status_code == 401
    r = cliente.post("/login/2fa", {"codigo": pyotp.TOTP(secreto).now()})
    assert r.status_code == 302
    assert cliente.c.get("/").status_code == 200


def test_totp_no_se_reutiliza(app, cliente):
    a, secreto = crear_admin()
    cliente.csrf()
    cliente.post("/login", {"email": a.email, "password": PASSWORD})
    codigo = pyotp.TOTP(secreto).now()
    assert cliente.post("/login/2fa", {"codigo": codigo}).status_code == 302
    otro = type(cliente)(app)
    otro.csrf()
    otro.post("/login", {"email": a.email, "password": PASSWORD})
    assert otro.post("/login/2fa", {"codigo": codigo}).status_code == 401


def test_bloqueo_tras_fallos_y_sin_enumeracion(app, cliente):
    a, _ = crear_admin()
    cliente.csrf()
    msg_malo = cliente.post("/login", {"email": a.email, "password": "mala"}).get_data(as_text=True)
    msg_inexistente = cliente.post("/login", {"email": "no@x.com", "password": "mala"}).get_data(as_text=True)
    assert "incorrectos" in msg_malo and "incorrectos" in msg_inexistente
    for _ in range(5):
        cliente.post("/login", {"email": a.email, "password": "mala"})
    r = cliente.post("/login", {"email": a.email, "password": PASSWORD})  # ni la correcta entra
    assert r.status_code in (401, 429)


def test_csrf_obligatorio(app, sesion):
    assert sesion.c.post("/clientes/nuevo", data={"nombre": "X"}).status_code == 400


def test_sin_login_redirige_y_cabeceras(app, cliente):
    assert cliente.c.get("/clientes").status_code == 302
    r = cliente.c.get("/login")
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_redireccion_abierta_bloqueada(app, cliente):
    from app.rutas.auth import _destino_seguro
    with app.test_request_context():
        assert _destino_seguro("//evil.com") == "/"
        assert _destino_seguro("https://evil.com") == "/"
        assert _destino_seguro("/clientes") == "/clientes"


def test_flujo_cliente_suscripcion_estados(app, sesion):
    r = sesion.post("/clientes/nuevo", {"nombre": "Pizzería Don Luigi", "email": "l@x.com"})
    assert r.status_code == 302
    c = db.session.query(Cliente).one()
    plan = db.session.query(Plan).filter_by(nombre="Pro").one()
    r = sesion.post(f"/clientes/{c.id}/suscripcion", {"plan_id": plan.id, "subdominio": "luigi"})
    assert r.status_code == 200 and "rst_" in r.get_data(as_text=True)
    s = db.session.query(Suscripcion).one()
    assert s.estado == "activa" and s.instancia.estado_infra == "en_linea"
    assert (app.config["DIR_INSTANCIAS"] / "luigi" / "docker-compose.yml").exists()
    env = app.config["DIR_INSTANCIAS"] / "luigi" / ".env"
    assert oct(env.stat().st_mode & 0o777) == "0o600"
    assert "INSTANCIA_SUBDOMINIO=luigi" in env.read_text() and "PANEL_TOKEN" not in env.read_text()

    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "pausada"})
    assert s.estado == "pausada" and s.instancia.estado_infra == "detenida"
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "suspendida"})  # sin motivo
    assert s.estado == "pausada"
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "suspendida", "motivo": "Impago"})
    assert s.estado == "suspendida"
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "activa"})
    assert s.estado == "activa" and s.instancia.estado_infra == "en_linea"
    # cancelar exige contraseña
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "cancelada", "motivo": "Baja"})
    assert s.estado == "activa"
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "cancelada", "motivo": "Baja", "confirmar_password": PASSWORD})
    assert s.estado == "cancelada"
    sesion.post(f"/suscripciones/{s.id}/estado", {"estado": "activa"})  # cancelada es final
    assert s.estado == "cancelada"


def test_subdominios_invalidos(app, sesion):
    from app.servicios.validacion import validar_subdominio
    for malo in ["ab", "www", "-x-", "UP", "a--b", "a.b", "a" * 40, "panel"]:
        assert validar_subdominio(malo), malo
    assert validar_subdominio("mi-cliente1") is None


def test_dominio_propio_no_robable(app):
    from app.servicios.validacion import validar_dominio_propio
    assert validar_dominio_propio("x.restify.localhost")
    assert validar_dominio_propio("restify.localhost")
    assert validar_dominio_propio("miweb.local")
    assert validar_dominio_propio("menu.turestaurante.com") is None


def test_limites_plan_y_ajuste_y_api(app, sesion):
    c = Cliente(nombre="A")
    db.session.add(c)
    db.session.commit()
    plan = db.session.query(Plan).filter_by(nombre="Básico").one()
    s, token = svc.crear(c, plan, "acme")
    db.session.commit()
    assert s.limites()["max_sucursales"] == 1
    sesion.post(f"/suscripciones/{s.id}/limites", {"max_sucursales": "5", "max_productos": ""})
    assert s.limite("max_sucursales") == 5 and s.limite("max_productos") == 100
    plan.max_productos = 250  # editar el plan se refleja
    db.session.commit()
    assert s.limite("max_productos") == 250

    api = app.test_client()
    assert api.get("/api/v1/estado").status_code == 401
    assert api.get("/api/v1/estado", headers={"Authorization": "Bearer rst_mal"}).status_code == 401
    r = api.get("/api/v1/estado", headers={"Authorization": f"Bearer {token}"})
    j = r.get_json()
    assert j["subdominio"] == "acme"
    assert j["acceso"] is True and j["limites"]["max_sucursales"] == 5 and j["estado"] == "activa"
    svc.cambiar_estado(s, "suspendida", "Impago")
    db.session.commit()
    j = api.get("/api/v1/estado", headers={"Authorization": f"Bearer {token}"}).get_json()
    assert j["acceso"] is False and j["motivo"] == "Impago"
    nuevo = svc.rotar_token(s.instancia)
    db.session.commit()
    assert api.get("/api/v1/estado", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert api.get("/api/v1/estado", headers={"Authorization": f"Bearer {nuevo}"}).status_code == 200
    assert token not in s.instancia.token_hash  # solo se guarda el hash


def test_permisos_por_rol(app, cliente):
    a, secreto = crear_admin("lector@x.com", rol="Solo lectura")
    cliente.login(a.email, secreto)
    assert cliente.c.get("/clientes").status_code == 200
    assert cliente.c.get("/clientes/nuevo").status_code == 403
    assert cliente.c.get("/usuarios").status_code == 403
    assert cliente.post("/planes/nuevo", {"nombre": "x"}).status_code == 403


def test_no_se_otorgan_permisos_ajenos(app, cliente):
    from app.modelos import Rol
    rol = db.session.query(Rol).filter_by(nombre="Soporte").one()
    rol.permisos = {**rol.permisos, "roles": ["crear", "leer", "editar"]}
    db.session.commit()
    a, secreto = crear_admin("s@x.com", rol="Soporte")
    cliente.login(a.email, secreto)
    r = cliente.post("/roles/nuevo", {"nombre": "Trampa", "usuarios.crear": "1", "usuarios.eliminar": "1"})
    assert r.status_code == 200 and "No puedes otorgar" in r.get_data(as_text=True)
    assert db.session.query(Rol).filter_by(nombre="Trampa").first() is None


def test_cadena_de_auditoria_detecta_manipulacion(app, sesion):
    sesion.post("/clientes/nuevo", {"nombre": "Uno"})
    sesion.post("/clientes/nuevo", {"nombre": "Dos"})
    assert auditoria.verificar_cadena() == (True, None)
    e = db.session.query(Evento).filter_by(accion="cliente.crear").first()
    e.detalle = {"nombre": "otro"}
    db.session.commit()
    ok, roto = auditoria.verificar_cadena()
    assert not ok and roto == e.id


def test_password_politica(app):
    from app.seguridad import validar_password
    assert validar_password("corta1A")
    assert validar_password("todominusculas123")
    assert validar_password("Admin-Segura-2026", "admin@x.com")  # contiene el usuario
    assert validar_password("Hola-Mundo-Seguro-2026", "x@y.com") is None


def test_eliminar_instancia_libera_subdominio(app, sesion):
    c = Cliente(nombre="B")
    db.session.add(c)
    db.session.commit()
    s, _ = svc.crear(c, db.session.query(Plan).first(), "borrame")
    with pytest.raises(svc.ReglaError):
        svc.eliminar_instancia(s)  # no cancelada
    svc.cambiar_estado(s, "cancelada", "Baja")
    svc.eliminar_instancia(s)
    db.session.commit()
    assert not (app.config["DIR_INSTANCIAS"] / "borrame").exists()
    from app.servicios.validacion import validar_subdominio
    assert validar_subdominio("borrame") is None


def test_todas_las_paginas_renderizan(app, sesion):
    c = Cliente(nombre="Render")
    db.session.add(c)
    db.session.commit()
    s, _ = svc.crear(c, db.session.query(Plan).first(), "render")
    svc.asignar_dominio(s.instancia, "menu.render.com")
    db.session.commit()
    rutas = ["/", "/clientes", "/clientes?q=ren", "/clientes/nuevo", f"/clientes/{c.id}", f"/clientes/{c.id}/editar",
             f"/clientes/{c.id}/suscripcion", "/planes", "/planes/nuevo", "/planes/1", "/suscripciones",
             "/suscripciones?estado=activa", f"/suscripciones/{s.id}", "/usuarios", "/usuarios/nuevo", "/roles",
             "/roles/nuevo", "/roles/2", "/auditoria?verificar=1", "/cuenta/password", "/cuenta/codigos", "/nada"]
    for r in rutas:
        resp = sesion.c.get(r)
        assert resp.status_code == (404 if r == "/nada" else 200), (r, resp.status_code)
    assert "restify-verificacion=" in sesion.c.get(f"/suscripciones/{s.id}").get_data(as_text=True)


def test_configurar_2fa_primer_ingreso(app, cliente):
    a, _ = crear_admin("nuevo@x.com", totp=False)
    cliente.csrf()
    r = cliente.post("/login", {"email": a.email, "password": PASSWORD})
    assert "configurar" in r.location
    html = cliente.c.get("/login/2fa/configurar").get_data(as_text=True)
    assert "data:image/svg+xml" in html
    with cliente.c.session_transaction() as s:
        secreto = s["totp_pendiente"]
    r = cliente.post("/login/2fa/configurar", {"codigo": pyotp.TOTP(secreto).now()})
    assert r.status_code == 302
    assert "recuperación" in cliente.c.get("/login/codigos").get_data(as_text=True)
    assert cliente.post("/login/codigos").status_code == 302
    assert cliente.c.get("/").status_code == 200
