#!/usr/bin/env python3
"""Arranca todo RESTIFY en local: backend, landing, panel, proxy, front y agente.

Uso:
    ./arrancar.py            prende todo y se queda en primer plano (Ctrl+C apaga front y agente)
    ./arrancar.py --apagar   baja también los contenedores (sin -v: no borra bases de datos)
    ./arrancar.py --sin-landing
    ./arrancar.py --construir   construye las imágenes de los clientes (primera vez)
"""
import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RED = "restify-net"

# (nombre, carpeta con docker-compose.yml)
SERVICIOS = [
    ("backend", RAIZ / "backend"),
    ("landing", RAIZ / "landing"),
    ("panel", RAIZ / "panel"),
    ("proxy", RAIZ / "infra" / "proxy"),
]

PUERTO_FRONT = 3001
COLORES = {"front": "36", "agente": "35"}


def log(msg):
    print(f"\033[1m[arrancar]\033[0m {msg}", flush=True)


def ejecutar(cmd, cwd=None, check=True, **kw):
    return subprocess.run(cmd, cwd=cwd, check=check, **kw)


def puerto_ocupado(puerto):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def asegurar_red():
    r = ejecutar(["docker", "network", "inspect", RED], check=False,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        log(f"creando red {RED}")
        ejecutar(["docker", "network", "create", RED])


def compose(carpeta, *args):
    return ejecutar(["docker", "compose", *args], cwd=carpeta)


def esperar_http(url, nombre, intentos=40):
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=2):
                log(f"{nombre} responde ✔  ({url})")
                return True
        except Exception:
            time.sleep(1.5)
    log(f"⚠ {nombre} no respondió en {url} (revisa: docker compose logs)")
    return False


def volcar(proceso, nombre):
    color = COLORES.get(nombre, "0")
    for linea in proceso.stdout:
        print(f"\033[{color}m[{nombre}]\033[0m {linea.rstrip()}", flush=True)


def lanzar(nombre, cmd, cwd, env=None):
    p = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True,
    )
    threading.Thread(target=volcar, args=(p, nombre), daemon=True).start()
    return p


def env_agente():
    """Replica infra/iniciar.sh: el secreto compartido sale de panel/.env."""
    archivo = RAIZ / "panel" / ".env"
    if not archivo.exists():
        sys.exit("Falta panel/.env")
    secreto = ""
    for linea in archivo.read_text().splitlines():
        if linea.startswith("AGENTE_SECRETO="):
            secreto = linea.split("=", 1)[1].strip()
    env = {**os.environ, "AGENTE_SECRETO": secreto, "PYTHONUNBUFFERED": "1"}
    (RAIZ / "panel" / "run").mkdir(exist_ok=True)
    return env


def apagar(servicios):
    for nombre, carpeta in reversed(servicios):
        log(f"bajando {nombre}")
        ejecutar(["docker", "compose", "down"], cwd=carpeta, check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--apagar", action="store_true", help="baja los contenedores y sale")
    ap.add_argument("--sin-landing", action="store_true", help="no prende la landing")
    ap.add_argument("--construir", action="store_true", help="construye imágenes de clientes antes")
    args = ap.parse_args()

    for herramienta in ("docker", "npm", "python3"):
        if not shutil.which(herramienta):
            sys.exit(f"Falta '{herramienta}' en el PATH")

    servicios = [s for s in SERVICIOS if not (args.sin_landing and s[0] == "landing")]

    if args.apagar:
        apagar(servicios)
        log("contenedores abajo. Si el front/agente siguen en otra terminal, Ctrl+C ahí.")
        return

    asegurar_red()

    if args.construir:
        log("construyendo imágenes de clientes (1-5 min)")
        ejecutar([str(RAIZ / "infra" / "construir_imagenes.sh")])

    for nombre, carpeta in servicios:
        log(f"prendiendo {nombre}")
        compose(carpeta, "up", "-d")

    esperar_http("http://localhost:8010/health", "backend")
    esperar_http("http://localhost:8030/login", "panel")

    procesos = []
    if puerto_ocupado(PUERTO_FRONT):
        log(f"puerto {PUERTO_FRONT} ya ocupado: asumo que el front ya corre, no lo lanzo")
    else:
        log("lanzando front (npm run dev)")
        procesos.append(("front", lanzar(
            "front", ["npm", "run", "dev"], RAIZ / "front",
            {**os.environ, "PORT": str(PUERTO_FRONT)})))

    sock = RAIZ / "panel" / "run" / "agente.sock"
    if sock.exists() and subprocess.run(["pgrep", "-f", "agente.py"], capture_output=True).returncode == 0:
        log("el agente ya parece estar corriendo, no lo lanzo")
    else:
        log("lanzando agente")
        procesos.append(("agente", lanzar(
            "agente", ["python3", "agente.py"], RAIZ / "infra", env_agente())))

    print(f"""
  Backend  http://localhost:8010
  Front    http://localhost:{PUERTO_FRONT}
  Landing  http://localhost:8020
  Panel    http://localhost:8030
  Clientes http://<cliente>.restify.localhost:8088

  Ctrl+C apaga front y agente (los contenedores siguen; usa ./arrancar.py --apagar).
""", flush=True)

    def salir(*_):
        log("deteniendo front y agente…")
        for _, p in procesos:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, salir)
    signal.signal(signal.SIGTERM, salir)

    if not procesos:
        return
    while True:
        for nombre, p in procesos:
            if p.poll() is not None:
                log(f"⚠ {nombre} terminó con código {p.returncode}")
                procesos.remove((nombre, p))
                break
        if not procesos:
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
