"""El AprovisionadorAgente del panel habla con el agente real (con Docker simulado) por el socket firmado."""

import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "infra"))
import agente  # noqa: E402

from app import create_app, sembrar  # noqa: E402
from app.config import ConfigTest  # noqa: E402
from app.extensions import db  # noqa: E402
from app.modelos import Cliente, Plan  # noqa: E402
from app.servicios import suscripciones as svc  # noqa: E402

SECRETO = "k" * 48


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    import subprocess

    llamadas = []

    def docker(args, cwd=None, timeout=300):
        llamadas.append(args)
        if "crear-api-key" in args:
            return subprocess.CompletedProcess(args, 0, f"  rk_{'z' * 30}{len(llamadas)}\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(agente, "docker", docker)
    monkeypatch.setattr(agente, "BASE", tmp_path / "inst")
    monkeypatch.setattr(agente.time, "sleep", lambda s: None)
    agente.Manejador.secreto = SECRETO
    sock = tmp_path / "a.sock"
    srv = agente.Servidor(str(sock), agente.Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class Cfg(ConfigTest):
        APROVISIONADOR = "agente"
        AGENTE_SOCKET = str(sock)
        AGENTE_SECRETO = SECRETO

    app = create_app(Cfg)
    with app.app_context():
        db.create_all()
        sembrar()
        yield app, llamadas
        db.session.remove()
        db.drop_all()
    srv.shutdown()
    srv.server_close()


def test_ciclo_completo_por_el_agente(entorno):
    app, llamadas = entorno
    c = Cliente(nombre="Resto")
    db.session.add(c)
    s, token = svc.crear(c, db.session.query(Plan).first(), "resto1")
    db.session.commit()
    assert s.instancia.estado_infra == "en_linea"
    assert any("up" in a and "front" in a for a in llamadas)

    svc.cambiar_estado(s, "pausada")
    assert s.instancia.estado_infra == "detenida"
    svc.cambiar_estado(s, "suspendida", "Impago")  # suspendida queda encendida para mostrar el mensaje
    assert s.instancia.estado_infra == "en_linea"
    svc.cambiar_estado(s, "cancelada", "Baja")
    svc.eliminar_instancia(s)
    assert s.instancia.estado_infra == "eliminada"
    assert any("down" in a for a in llamadas)


def test_agente_apagado_deja_error_y_se_puede_reintentar(entorno):
    app, _ = entorno
    real = app.config["AGENTE_SOCKET"]
    app.config["AGENTE_SOCKET"] = "/tmp/no-existe.sock"
    c = Cliente(nombre="Resto")
    db.session.add(c)
    s, _ = svc.crear(c, db.session.query(Plan).first(), "resto2")
    db.session.commit()
    assert s.instancia.estado_infra == "error" and "agente" in s.instancia.error_infra
    assert s.estado == "activa"  # la suscripción existe aunque la instancia falló
    app.config["AGENTE_SOCKET"] = real  # se enciende el agente
    svc.reintentar_creacion(s)
    assert s.instancia.estado_infra == "en_linea" and s.instancia.error_infra is None
    with pytest.raises(svc.ReglaError):
        svc.reintentar_creacion(s)  # ya está creada


def test_secreto_incorrecto_es_rechazado(entorno):
    app, llamadas = entorno
    app.config["AGENTE_SECRETO"] = "x" * 48
    c = Cliente(nombre="Resto")
    db.session.add(c)
    s, _ = svc.crear(c, db.session.query(Plan).first(), "resto3")
    assert s.instancia.estado_infra == "error" and "Firma" in s.instancia.error_infra
    assert llamadas == []


def test_si_el_agente_falla_al_eliminar_no_se_suelta_la_instancia(entorno):
    app, _ = entorno
    real = app.config["AGENTE_SOCKET"]
    c = Cliente(nombre="Resto")
    db.session.add(c)
    s, _ = svc.crear(c, db.session.query(Plan).first(), "resto4")
    svc.cambiar_estado(s, "cancelada", "Baja")
    db.session.commit()
    app.config["AGENTE_SOCKET"] = "/tmp/no-existe.sock"
    with pytest.raises(svc.ReglaError, match="se conserva"):
        svc.eliminar_instancia(s)
    assert s.instancia.subdominio == "resto4"  # el subdominio sigue ocupado
    app.config["AGENTE_SOCKET"] = real
    svc.eliminar_instancia(s)  # y al volver el agente se puede borrar bien
    assert s.instancia.estado_infra == "eliminada" and s.instancia.subdominio != "resto4"


def test_contenedores_y_logs_por_el_agente(entorno, monkeypatch):
    import json
    import subprocess

    from app.infra import aprovisionador

    app, llamadas = entorno
    c = Cliente(nombre="Resto")
    db.session.add(c)
    s, _ = svc.crear(c, db.session.query(Plan).first(), "resto1")
    db.session.commit()

    ps = json.dumps({"Service": "api", "Name": "restify-resto1-api-1", "State": "running", "Status": "Up 1 minute", "Image": "restify-api"})
    base = agente.docker

    def docker(args, cwd=None, timeout=300):
        if "ps" in args:
            return subprocess.CompletedProcess(args, 0, ps + "\n", "")
        if "logs" in args:
            return subprocess.CompletedProcess(args, 0, "linea 1\nlinea 2\n", "")
        return base(args, cwd, timeout)

    monkeypatch.setattr(agente, "docker", docker)
    apr = aprovisionador.AprovisionadorAgente()
    lista, error = apr.contenedores(s.instancia)
    assert error is None and lista[0]["servicio"] == "api" and lista[0]["estado"] == "running"
    texto, error = apr.logs(s.instancia, "api", 50)
    assert error is None and "linea 2" in texto
    _, error = apr.logs(s.instancia, "../etc", 50)
    assert error and "no válido" in error
