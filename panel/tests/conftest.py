import pyotp
import pytest

from app import create_app, sembrar
from app.config import ConfigTest
from app.extensions import db
from app.modelos import Admin, Rol
from app.seguridad import cifrar, hashear

PASSWORD = "Clave-Segura-2026"


@pytest.fixture()
def app(tmp_path):
    class Cfg(ConfigTest):
        DIR_INSTANCIAS = tmp_path / "instancias"

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        sembrar()
        yield app
        db.session.remove()
        db.drop_all()


def crear_admin(email="admin@x.com", rol="Superadmin", totp=True, password=PASSWORD):
    secreto = pyotp.random_base32()
    a = Admin(email=email, nombre="Test", password_hash=hashear(password), rol=db.session.query(Rol).filter_by(nombre=rol).one(),
              totp_secreto=cifrar(secreto) if totp else None, totp_confirmado=totp)
    db.session.add(a)
    db.session.commit()
    return a, secreto


class Cliente:
    def __init__(self, app):
        self.c = app.test_client()

    def csrf(self):
        import re
        html = self.c.get("/login").get_data(as_text=True)
        m = re.search(r'name="csrf" value="([^"]+)"', html)
        return m.group(1)

    def post(self, url, data=None, **kw):
        data = dict(data or {})
        with self.c.session_transaction() as s:
            data.setdefault("csrf", s.get("csrf", ""))
        return self.c.post(url, data=data, **kw)

    def login(self, email, secreto, password=PASSWORD):
        self.csrf()
        self.post("/login", {"email": email, "password": password})
        import time
        r = self.post("/login/2fa", {"codigo": pyotp.TOTP(secreto).now()})
        return r


@pytest.fixture()
def cliente(app):
    return Cliente(app)


@pytest.fixture()
def sesion(app, cliente):
    a, secreto = crear_admin()
    cliente.login(a.email, secreto)
    return cliente
