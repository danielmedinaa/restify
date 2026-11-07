"""Respaldos y actualizaciones de versión de las instancias (con Docker simulado)."""

import gzip
import subprocess

import pytest

import agente

CREAR = {"sub": "resto1", "dominio_base": "restify.localhost", "esquema": "http", "puerto": "8080",
         "panel_url": "http://panel:8000/api/v1/estado", "zona_horaria": "America/Caracas"}


class Docker:
    def __init__(self):
        self.llamadas: list[str] = []
        self.corriendo = True
        self.fallar_up_con: str | None = None  # texto de imagen que hace fallar el `up`

    def __call__(self, args, cwd=None, timeout=300):
        cmd = " ".join(args)
        self.llamadas.append(cmd)
        if "crear-api-key" in args:
            return subprocess.CompletedProcess(args, 0, f"  rk_{'x' * 30}{len(self.llamadas)}\n", "")
        if "ps --status running" in cmd:
            return subprocess.CompletedProcess(args, 0, "abc123\n" if self.corriendo else "", "")
        if " up -d api front" in cmd and self.fallar_up_con and self.fallar_up_con in (cwd / "docker-compose.yml").read_text():
            return subprocess.CompletedProcess(args, 1, "", "pull access denied")
        return subprocess.CompletedProcess(args, 0, "", "")

    def volcado(self, args, cwd, destino):
        self.llamadas.append("DUMP " + " ".join(args))
        with gzip.open(destino, "wb") as f:
            f.write(b"-- PostgreSQL dump\n" * 20)
        return 0


@pytest.fixture
def d(tmp_path, monkeypatch):
    falso = Docker()
    monkeypatch.setattr(agente, "docker", falso)
    monkeypatch.setattr(agente, "docker_a_archivo", falso.volcado)
    monkeypatch.setattr(agente, "BASE", tmp_path / "inst")
    monkeypatch.setattr(agente, "RESPALDOS", tmp_path / "resp")
    monkeypatch.setattr(agente.time, "sleep", lambda s: None)
    agente.crear(CREAR)
    falso.llamadas.clear()
    return falso


def compose_de(tmp_path, sub="resto1"):
    return (tmp_path / "inst" / sub / "docker-compose.yml").read_text()


def test_respaldar_guarda_y_conserva_solo_los_ultimos(d, tmp_path):
    for i in range(4):
        (tmp_path / "resp" / "resto1").mkdir(parents=True, exist_ok=True)
        (tmp_path / "resp" / "resto1" / f"2020010{i}-000000.sql.gz").write_bytes(b"x" * 200)
    nuevo = agente.respaldar_instancia("resto1", conservar=3)
    archivos = sorted((tmp_path / "resp" / "resto1").glob("*.sql.gz"))
    assert len(archivos) == 3 and nuevo in archivos
    assert oct(nuevo.stat().st_mode & 0o777) == "0o600"


def test_si_el_volcado_falla_no_queda_un_archivo_vacio(d, tmp_path, monkeypatch):
    monkeypatch.setattr(agente, "docker_a_archivo", lambda a, c, dest: (dest.write_bytes(b""), 1)[1])
    with pytest.raises(agente.ErrorAgente, match="No se pudo respaldar"):
        agente.respaldar_instancia("resto1")
    assert not list((tmp_path / "resp" / "resto1").glob("*.sql.gz"))


def test_actualizar_respalda_primero_y_cambia_solo_lo_pedido(d, tmp_path):
    r = agente.actualizar_instancia("resto1", imagen_api="ghcr.io/x/api:v2")
    assert r == {"estado": "actualizada"}
    cmds = d.llamadas
    assert cmds[[c.startswith("DUMP") for c in cmds].index(True)] and cmds.index(next(c for c in cmds if c.startswith("DUMP"))) < \
        cmds.index(next(c for c in cmds if " up -d api front" in c))
    txt = compose_de(tmp_path)
    assert "image: ghcr.io/x/api:v2" in txt and "image: restify-front:latest" in txt  # el front no cambió
    # Los secretos no se tocan
    assert (tmp_path / "inst" / "resto1" / "api.env").exists()


def test_actualizar_a_la_misma_version_no_hace_nada(d):
    agente.actualizar_instancia("resto1", imagen_api="restify-api:latest")
    assert not any("DUMP" in c or " up " in c for c in d.llamadas)


def test_si_la_nueva_version_falla_vuelve_a_la_anterior(d, tmp_path):
    d.fallar_up_con = "api:rota"
    with pytest.raises(agente.ErrorAgente, match="versión anterior"):
        agente.actualizar_instancia("resto1", imagen_api="ghcr.io/x/api:rota")
    assert "api:rota" not in compose_de(tmp_path) and "image: restify-api:latest" in compose_de(tmp_path)


def test_instancia_apagada_se_actualiza_sin_arrancarla(d, tmp_path):
    d.corriendo = False
    r = agente.actualizar_instancia("resto1", imagen_front="ghcr.io/x/front:v2")
    assert r["estado"] == "actualizada_apagada"
    assert "front:v2" in compose_de(tmp_path)
    assert not any("DUMP" in c or " up -d" in c for c in d.llamadas)  # una pausada sigue pausada


def test_imagen_peligrosa_o_instancia_inexistente(d):
    for mala in ["x; rm -rf /", "$(id)", "a b", "UP/CASE", ""]:
        if mala == "":
            continue
        with pytest.raises(agente.ErrorAgente, match="Imagen no válida"):
            agente.actualizar_instancia("resto1", imagen_api=mala)
    with pytest.raises(agente.ErrorAgente) as e:
        agente.actualizar_instancia("noexiste", imagen_api="a/b:1")
    assert e.value.codigo == 404


def test_cli_actualiza_todas_y_deja_la_version_para_las_nuevas(d, tmp_path, capsys):
    agente.crear({**CREAR, "sub": "resto2"})
    d.llamadas.clear()
    codigo = agente.cli(["actualizar", "--api", "ghcr.io/x/api:v3", "--front", "ghcr.io/x/front:v3"])
    assert codigo == 0
    out = capsys.readouterr().out
    assert "resto1: actualizada" in out and "resto2: actualizada" in out
    # Una instancia nueva nace ya con esa versión
    agente.crear({**CREAR, "sub": "resto3"})
    assert "image: ghcr.io/x/api:v3" in compose_de(tmp_path, "resto3")


def test_cli_se_detiene_en_la_primera_falla(d, tmp_path, capsys):
    agente.crear({**CREAR, "sub": "resto2"})
    d.fallar_up_con = "api:rota"
    codigo = agente.cli(["actualizar", "--api", "ghcr.io/x/api:rota"])
    cap = capsys.readouterr()
    assert codigo == 1 and "[ERROR] resto1" in cap.err and "resto2" not in cap.out  # resto2 ni se intentó
    assert "api:rota" not in compose_de(tmp_path, "resto2")


def test_prefijo_y_red_separan_los_entornos(tmp_path, monkeypatch):
    monkeypatch.setattr(agente, "PREFIJO", "restify-dev")
    monkeypatch.setattr(agente, "RED", "dev-net")
    txt = agente._compose("resto1", "a:1", "b:1")
    assert "name: restify-dev-resto1" in txt and "name: restify-dev-resto1-edge" in txt
