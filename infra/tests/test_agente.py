import json
import subprocess
import threading
import time

import httpx
import pytest

import agente

SECRETO = "s" * 48
CREAR = {"sub": "resto1", "dominio_base": "restify.localhost", "esquema": "http", "puerto": "8080",
         "panel_url": "http://panel:8000/api/v1/estado", "zona_horaria": "America/Caracas"}


class DockerFalso:
    """Registra los comandos en vez de ejecutarlos."""

    def __init__(self):
        self.llamadas: list[list[str]] = []
        self.fallar_en: str | None = None

    def __call__(self, args, cwd=None, timeout=300):
        self.llamadas.append(args)
        if self.fallar_en and self.fallar_en in args:
            return subprocess.CompletedProcess(args, 1, "", "boom: sin memoria")
        if "crear-api-key" in args:
            return subprocess.CompletedProcess(args, 0, f"API key creada.\n\n  rk_{'x' * 30}{len(self.llamadas)}\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    falso = DockerFalso()
    monkeypatch.setattr(agente, "docker", falso)
    monkeypatch.setattr(agente, "BASE", tmp_path / "instancias")
    monkeypatch.setattr(agente.time, "sleep", lambda s: None)
    agente.Manejador.secreto = SECRETO
    sock = tmp_path / "a.sock"
    srv = agente.Servidor(str(sock), agente.Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield sock, falso
    srv.shutdown()
    srv.server_close()


def llamar(sock, ruta, datos, secreto=SECRETO, ts=None, firma=None):
    cuerpo = json.dumps(datos).encode()
    ts = ts or str(int(time.time()))
    firma = firma or agente.firma(secreto, ts, cuerpo)
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://a") as c:
        return c.post(ruta, content=cuerpo, headers={"X-Ts": ts, "X-Firma": firma})


def test_sin_firma_o_firma_mala_o_vieja_se_rechaza(servidor):
    sock, falso = servidor
    assert llamar(sock, "/crear", CREAR, secreto="otro" * 12).status_code == 401
    assert llamar(sock, "/crear", CREAR, firma="0" * 64).status_code == 401
    viejo = str(int(time.time()) - 600)
    assert llamar(sock, "/crear", CREAR, ts=viejo).status_code == 401
    with httpx.Client(transport=httpx.HTTPTransport(uds=str(sock)), base_url="http://a") as c:
        assert c.post("/crear", content=b"{}").status_code == 401
    assert falso.llamadas == []  # nada se ejecutó


def test_subdominios_peligrosos_o_reservados(servidor):
    sock, falso = servidor
    for malo in ["../etc", "a b", "UP", "panel", "x;rm -rf /", "a--b", "ab", "$(id)", "a" * 40, None, 5]:
        assert llamar(sock, "/eliminar", {"sub": malo}).status_code == 400, malo
    assert falso.llamadas == []


def test_datos_de_crear_se_validan(servidor):
    sock, falso = servidor
    for cambio in ({"esquema": "ftp"}, {"puerto": "80;ls"}, {"dominio_base": "a b"}, {"panel_url": "file:///etc/passwd"},
                   {"zona_horaria": "../../x"}):
        assert llamar(sock, "/crear", {**CREAR, **cambio}).status_code == 400, cambio
    assert falso.llamadas == []


def test_crear_levanta_en_orden_y_genera_secretos_privados(servidor, tmp_path):
    sock, falso = servidor
    r = llamar(sock, "/crear", CREAR)
    assert r.status_code == 200 and r.json() == {"estado": "en_linea"}
    d = tmp_path / "instancias" / "resto1"
    for archivo in ("api.env", "db.env", "front.env", ".env"):
        assert oct((d / archivo).stat().st_mode & 0o777) == "0o600", archivo
    api = (d / "api.env").read_text()
    assert "INSTANCIA_SUBDOMINIO=resto1" in api and "PANEL_URL=http://panel:8000/api/v1/estado" in api
    assert 'CORS_ORIGINS=["http://resto1.restify.localhost:8080"]' in api and "ENVIRONMENT=production" in api
    assert "PANEL_TOKEN" not in api  # el token lo escribe el cliente en el asistente
    front = (d / "front.env").read_text()
    assert front.count("_API_KEY=rk_") == 2 and "COOKIE_SECURE=false" in front
    # Orden: base+redis+api, luego claves, luego front
    cmds = [" ".join(c) for c in falso.llamadas]
    i_api = next(i for i, c in enumerate(cmds) if "up -d db redis api" in c)
    i_front = next(i for i, c in enumerate(cmds) if "up -d front" in c)
    assert i_api < i_front and all("-p restify-resto1" in c for c in cmds)


def test_crear_dos_veces_no_cambia_los_secretos(servidor, tmp_path):
    sock, falso = servidor
    llamar(sock, "/crear", CREAR)
    antes = {a: (tmp_path / "instancias" / "resto1" / a).read_text() for a in ("api.env", "front.env", "db.env")}
    assert llamar(sock, "/crear", CREAR).status_code == 200
    assert antes == {a: (tmp_path / "instancias" / "resto1" / a).read_text() for a in antes}


def test_si_docker_falla_el_error_llega_sin_trazas(servidor):
    sock, falso = servidor
    falso.fallar_en = "up"
    r = llamar(sock, "/crear", CREAR)
    assert r.status_code == 500 and "sin memoria" in r.json()["error"] and "Traceback" not in r.text


def test_detener_reanudar_eliminar(servidor, tmp_path):
    sock, falso = servidor
    assert llamar(sock, "/reanudar", {"sub": "resto1"}).status_code == 404  # no existe
    assert llamar(sock, "/detener", {"sub": "resto1"}).json() == {"estado": "detenida"}  # no falla si no existe
    llamar(sock, "/crear", CREAR)
    falso.llamadas.clear()
    assert llamar(sock, "/detener", {"sub": "resto1"}).status_code == 200
    assert llamar(sock, "/reanudar", {"sub": "resto1"}).status_code == 200
    assert llamar(sock, "/eliminar", {"sub": "resto1"}).json() == {"estado": "eliminada"}
    cmds = [" ".join(c) for c in falso.llamadas]
    assert any(c.endswith("stop") for c in cmds) and any(c.endswith("start") for c in cmds)
    assert any("down -v --remove-orphans" in c for c in cmds)
    assert not (tmp_path / "instancias" / "resto1").exists()


def test_rutas_desconocidas(servidor):
    sock, _ = servidor
    assert llamar(sock, "/ejecutar", {"cmd": "ls"}).status_code == 404
