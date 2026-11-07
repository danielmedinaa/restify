#!/usr/bin/env python3
"""Agente de instancias de RESTIFY. Corre en el servidor (tu laptop hoy, el VPS mañana), FUERA del panel.

El panel no toca Docker: le pide a este agente cuatro cosas fijas por un socket Unix y nada más.

    POST /crear      {sub, dominio_base, esquema, puerto, panel_url, zona_horaria}
    POST /detener    {sub}
    POST /reanudar   {sub}
    POST /eliminar   {sub}

Seguridad: sin dependencias (solo biblioteca estándar), escucha solo en un socket Unix (nunca en red),
cada petición lleva una firma HMAC con marca de tiempo, el subdominio se valida con una regla estricta
y los comandos se ejecutan sin shell, con argumentos fijos. Nunca ejecuta nada que venga del panel.

Cada instancia = 4 contenedores (db, redis, api, front) en el proyecto Docker `restify-<sub>`, con
sus propios secretos, su propia base y límites de memoria. Eliminarla borra todo (contenedores y datos).
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SOCKET = Path(os.environ.get("AGENTE_SOCKET", RAIZ / "panel" / "run" / "agente.sock"))
BASE = Path(os.environ.get("AGENTE_INSTANCIAS", Path.home() / ".restify-instancias"))
IMAGEN_API = os.environ.get("IMAGEN_API", "restify-api:latest")
IMAGEN_FRONT = os.environ.get("IMAGEN_FRONT", "restify-front:latest")
# Varios entornos en un mismo servidor (dev, pre) no pueden chocar: cada uno con su prefijo, su red y sus carpetas
PREFIJO = os.environ.get("AGENTE_PREFIJO", "restify")
RED = os.environ.get("AGENTE_RED", "restify-net")
RESPALDOS = Path(os.environ.get("AGENTE_RESPALDOS", Path.home() / ".restify-respaldos")) / PREFIJO
BANNER = os.environ.get("AGENTE_BANNER", "")  # "DESARROLLO" / "PRE PRODUCCION": el front de cada instancia muestra un banner fijo
PULL = os.environ.get("AGENTE_PULL", "0") == "1"  # en servidores: las imágenes vienen de un registro (ghcr.io)
VENTANA_SEG = 60

_SUB = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,30}[a-z0-9])$")
_DOMINIO = re.compile(r"^[a-z0-9]([a-z0-9.-]{1,98}[a-z0-9])$")
RESERVADOS = {
    "www", "panel", "admin", "api", "app", "demo", "mail", "smtp", "ftp", "ns1", "ns2", "soporte", "support",
    "status", "docs", "blog", "landing", "static", "cdn", "dev", "test", "staging", "root", "login", "billing",
    "pagos", "restify", "pre", "pro", "prod", "uat",
}


class ErrorAgente(Exception):
    def __init__(self, mensaje: str, codigo: int = 400):
        super().__init__(mensaje)
        self.codigo = codigo


# ---------------------------------------------------------------- docker

def docker(args: list[str], cwd: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    """Único punto que ejecuta procesos: lista de argumentos fija, sin shell."""
    return subprocess.run(["docker", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def compose(sub: str, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return docker(["compose", "-p", f"{PREFIJO}-{sub}", *args], cwd=BASE / sub, timeout=timeout)


def docker_a_archivo(args: list[str], cwd: Path, destino: Path) -> int:
    """Ejecuta docker y guarda su salida comprimida (volcados de la base). Devuelve el código de salida."""
    import gzip

    with subprocess.Popen(["docker", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
        with gzip.open(destino, "wb") as f:
            shutil.copyfileobj(proc.stdout, f)
        return proc.wait()


def _exigir(r: subprocess.CompletedProcess, que: str) -> str:
    if r.returncode != 0:
        detalle = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["sin detalle"]
        raise ErrorAgente(f"{que} falló: {detalle[0][:300]}", 500)
    return r.stdout


# ---------------------------------------------------------------- plantillas

COMPOSE = """\
# Generado por el agente de RESTIFY. No editar a mano.
name: {proyecto}

x-seguro: &seguro
  restart: unless-stopped
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]

# Sin tope los logs de Docker crecen hasta llenar el disco
x-logs: &logs
  driver: json-file
  options: {{max-size: "10m", max-file: "3"}}

services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    env_file: db.env
    mem_limit: 256m
    logging: *logs
    volumes: [pgdata:/var/lib/postgresql/data]
    networks: [interna]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 20
  redis:
    <<: *seguro
    image: redis:7-alpine
    command: ["redis-server", "--requirepass", "${{REDIS_PASSWORD}}", "--appendonly", "yes"]
    mem_limit: 64m
    logging: *logs
    user: redis   # directo como "redis": sin root, sin capacidades y sin tocar permisos al reiniciar
    volumes: [redisdata:/data]
    networks: [interna]
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a $${{REDIS_PASSWORD}} ping | grep PONG"]
      interval: 5s
      timeout: 5s
      retries: 20
    environment:
      REDIS_PASSWORD: ${{REDIS_PASSWORD}}
  api:
    <<: *seguro
    image: {imagen_api}
    env_file: api.env
    mem_limit: 384m
    logging: *logs
    volumes: [media:/app/media]
    networks: [interna, restify-net]
    depends_on:
      db: {{condition: service_healthy}}
      redis: {{condition: service_healthy}}
  front:
    <<: *seguro
    image: {imagen_front}
    env_file: front.env
    mem_limit: 256m
    logging: *logs
    networks: [interna, restify-net]

networks:
  # La base y redis solo se ven entre sí y con la api: sin salida a internet ni al resto de instancias
  interna: {{internal: true}}
  # Para llegar al proxy (Caddy) y al panel de RESTIFY
  restify-net: {{external: true, name: {red}}}

volumes:
  pgdata:
  redisdata:
  media:
"""


def _compose(sub: str, imagen_api: str, imagen_front: str) -> str:
    return COMPOSE.format(sub=sub, proyecto=f"{PREFIJO}-{sub}", red=RED, imagen_api=imagen_api, imagen_front=imagen_front)


def imagenes_por_defecto() -> tuple[str, str]:
    """Las que usan las instancias NUEVAS: las últimas desplegadas (imagenes.json) o las del entorno."""
    try:
        d = json.loads((BASE / "imagenes.json").read_text())
        return d["api"], d["front"]
    except (OSError, ValueError, KeyError):
        return IMAGEN_API, IMAGEN_FRONT


def _env(d: dict) -> str:
    return "".join(f"{k}={v}\n" for k, v in d.items())


def _escribir_secreto(ruta: Path, contenido: str) -> None:
    ruta.touch(mode=0o600)
    ruta.chmod(0o600)
    ruta.write_text(contenido)


def generar_archivos(sub: str, p: dict) -> None:
    """Escribe compose y .env de la instancia. Si ya existen no se pisan los secretos (crear es idempotente)."""
    d = BASE / sub
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    host = f"{sub}.{p['dominio_base']}"
    puerto = f":{p['puerto']}" if p["puerto"] else ""
    origen = f"{p['esquema']}://{host}{puerto}"
    api_img, front_img = imagenes_por_defecto()
    (d / "docker-compose.yml").write_text(_compose(sub, api_img, front_img))
    if (d / "api.env").exists():
        return
    pg, rd = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    _escribir_secreto(d / ".env", _env({"REDIS_PASSWORD": rd}))
    _escribir_secreto(d / "db.env", _env({"POSTGRES_DB": "restify", "POSTGRES_USER": "restify", "POSTGRES_PASSWORD": pg}))
    _escribir_secreto(d / "api.env", _env({
        "ENVIRONMENT": "production",
        "DATABASE_URL": f"postgresql+asyncpg://restify:{pg}@db:5432/restify",
        "REDIS_URL": f"redis://:{rd}@redis:6379/0",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "CORS_ORIGINS": json.dumps([origen]),
        "TRUSTED_HOSTS": json.dumps(["api", f"{PREFIJO}-{sub}-api-1", "localhost", host]),
        "PUBLIC_MENU_BASE_URL": f"{origen}/mesa",
        "PUBLIC_TRACKING_BASE_URL": f"{origen}/pedido",
        "TIMEZONE": p["zona_horaria"],
        # La api solo es alcanzable desde las redes de esta instancia y el proxy: se confía en X-Forwarded-For
        "FORWARDED_ALLOW_IPS": "*",
        "WEB_CONCURRENCY": "1",
        "PANEL_URL": p["panel_url"],
        "INSTANCIA_SUBDOMINIO": sub,
    }))


# ---------------------------------------------------------------- operaciones

_candados: dict[str, threading.Lock] = {}
_candados_lock = threading.Lock()


def _candado(sub: str) -> threading.Lock:
    with _candados_lock:
        return _candados.setdefault(sub, threading.Lock())


def validar_sub(sub: object) -> str:
    if not isinstance(sub, str) or not _SUB.match(sub) or "--" in sub or sub in RESERVADOS:
        raise ErrorAgente("Subdominio no válido")
    return sub


def validar_crear(d: dict) -> dict:
    sub = validar_sub(d.get("sub"))
    dominio = str(d.get("dominio_base", "")).lower()
    puerto = str(d.get("puerto", "") or "")
    esquema = d.get("esquema")
    url = str(d.get("panel_url", ""))
    zona = str(d.get("zona_horaria") or "America/Caracas")
    if not _DOMINIO.match(dominio):
        raise ErrorAgente("Dominio base no válido")
    if esquema not in ("http", "https") or (puerto and not puerto.isdigit()):
        raise ErrorAgente("Esquema o puerto no válidos")
    if not re.match(r"^https?://[A-Za-z0-9.:_-]+(/[A-Za-z0-9/_.-]*)?$", url):
        raise ErrorAgente("URL del panel no válida")
    if not re.match(r"^[A-Za-z_]+(/[A-Za-z_+-]+){0,2}$", zona):
        raise ErrorAgente("Zona horaria no válida")
    return {"sub": sub, "dominio_base": dominio, "puerto": puerto, "esquema": esquema, "panel_url": url, "zona_horaria": zona}


def _esperar_api(sub: str) -> None:
    cmd = "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"
    for _ in range(45):
        if compose(sub, "exec", "-T", "api", "python", "-c", cmd, timeout=30).returncode == 0:
            return
        time.sleep(2)
    raise ErrorAgente("La API de la instancia no arrancó a tiempo (revisa `docker compose logs api`)", 500)


def _crear_api_key(sub: str, nombre: str) -> str:
    out = _exigir(compose(sub, "exec", "-T", "api", "python", "-m", "app.cli", "crear-api-key", "--nombre", nombre), "Crear API key")
    m = re.search(r"^\s{2}(\S{20,})\s*$", out, re.M)
    if not m:
        raise ErrorAgente("No se pudo leer la API key creada", 500)
    return m.group(1)


def _api_url(sub: str) -> str:
    # Nombre de contenedor único: el alias "api" lo comparten todas las APIs de restify-net (incluida la de desarrollo)
    return f"http://{PREFIJO}-{sub}-api-1:8000"


def _confiar_host_api(sub: str) -> bool:
    """El front llama a la API por su nombre de contenedor: debe estar en TRUSTED_HOSTS. True si hubo que cambiarlo."""
    ruta = BASE / sub / "api.env"
    nombre = f"{PREFIJO}-{sub}-api-1"
    lineas = ruta.read_text().splitlines()
    nuevas = []
    for l in lineas:
        if l.startswith("TRUSTED_HOSTS="):
            hosts = json.loads(l.split("=", 1)[1])
            if nombre not in hosts:
                l = "TRUSTED_HOSTS=" + json.dumps([hosts[0], nombre, *hosts[1:]] if hosts else [nombre])
        nuevas.append(l)
    if nuevas == lineas:
        return False
    ruta.write_text("\n".join(nuevas) + "\n")
    return True


def _fijar_api_url(sub: str, front_env: Path) -> None:
    """Migra front.env creados con el alias ambiguo `api`, que a veces resolvía a otra API."""
    lineas = front_env.read_text().splitlines()
    nuevas = [f"API_URL={_api_url(sub)}" if l.startswith("API_URL=") else l for l in lineas]
    if nuevas != lineas:
        front_env.write_text("\n".join(nuevas) + "\n")


def _keys_validas(sub: str, front_env: Path) -> bool:
    """¿La API de la instancia reconoce las keys guardadas? Falla si la base se recreó y front.env quedó viejo."""
    claves = dict(l.split("=", 1) for l in front_env.read_text().splitlines() if "=" in l)
    prueba = (
        "import os, urllib.request, urllib.error\n"
        "r = urllib.request.Request('http://localhost:8000/api/v1/auth/me', headers={'X-API-Key': os.environ['K']})\n"
        "try:\n    urllib.request.urlopen(r, timeout=5)\n"
        "except urllib.error.HTTPError as e:\n    raise SystemExit(1 if b'API key' in e.read() else 0)\n"
    )
    for nombre in ("PANEL_API_KEY", "PUBLIC_API_KEY"):
        if not claves.get(nombre):
            return False
        r = compose(sub, "exec", "-T", "-e", f"K={claves[nombre]}", "api", "python", "-c", prueba, timeout=30)
        if r.returncode != 0:
            return False
    return True


def crear(d: dict) -> dict:
    p = validar_crear(d)
    sub = p["sub"]
    with _candado(sub):
        generar_archivos(sub, p)
        recrear = ["--force-recreate"] if _confiar_host_api(sub) else []  # env_file nuevo: hay que recrear la api
        _exigir(compose(sub, "up", "-d", *recrear, "db", "redis", "api"), "Levantar base y API")
        _esperar_api(sub)
        front_env = BASE / sub / "front.env"
        if front_env.exists():
            _fijar_api_url(sub, front_env)
        if front_env.exists() and not _keys_validas(sub, front_env):
            front_env.unlink()  # la base es nueva (instancia recreada): las keys viejas ya no existen
        if not front_env.exists():  # primera vez: las claves se crean una sola vez
            _escribir_secreto(front_env, _env({
                "API_URL": _api_url(sub),
                "PANEL_API_KEY": _crear_api_key(sub, "Panel web"),
                "PUBLIC_API_KEY": _crear_api_key(sub, "Menu publico"),
                "SESSION_SECRET": secrets.token_urlsafe(48),
                "COOKIE_SECURE": "true" if p["esquema"] == "https" else "false",
                **({"BANNER_ENTORNO": BANNER} if BANNER else {}),
            }))
        _exigir(compose(sub, "up", "-d", "front"), "Levantar el front")
    return {"estado": "en_linea"}


def detener(d: dict) -> dict:
    sub = validar_sub(d.get("sub"))
    with _candado(sub):
        if (BASE / sub).exists():
            _exigir(compose(sub, "stop"), "Detener")
    return {"estado": "detenida"}


def reanudar(d: dict) -> dict:
    sub = validar_sub(d.get("sub"))
    with _candado(sub):
        if not (BASE / sub).exists():
            raise ErrorAgente("La instancia no existe en este servidor", 404)
        _exigir(compose(sub, "start"), "Reanudar")
        _esperar_api(sub)  # "en línea" significa que ya responde, no solo que el contenedor arrancó
    return {"estado": "en_linea"}


def eliminar(d: dict) -> dict:
    sub = validar_sub(d.get("sub"))
    with _candado(sub):
        if (BASE / sub).exists():
            _exigir(compose(sub, "down", "-v", "--remove-orphans"), "Eliminar")
            shutil.rmtree(BASE / sub, ignore_errors=True)
    return {"estado": "eliminada"}


# ---------------------------------------------------------------- respaldos y actualizaciones

_IMG = re.compile(r"^\s+image:\s*(\S+)\s*$", re.M)
_IMAGEN_OK = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,100}(:[A-Za-z0-9_.-]{1,128})?(@sha256:[0-9a-f]{64})?$")


def listar_instancias() -> list[str]:
    return sorted(p.name for p in BASE.iterdir() if p.is_dir() and _SUB.match(p.name)) if BASE.exists() else []


def _corriendo(sub: str) -> bool:
    return bool(compose(sub, "ps", "--status", "running", "-q", "api").stdout.strip())


def respaldar_instancia(sub: str, conservar: int = 7) -> Path:
    """Volcado comprimido de la base (pg_dump). Conserva los últimos `conservar`."""
    sub = validar_sub(sub)
    carpeta = RESPALDOS / sub
    carpeta.mkdir(parents=True, exist_ok=True, mode=0o700)
    destino = carpeta / f"{time.strftime('%Y%m%d-%H%M%S')}.sql.gz"
    codigo = docker_a_archivo(
        ["compose", "-p", f"{PREFIJO}-{sub}", "exec", "-T", "db", "pg_dump", "-U", "restify", "--no-owner", "restify"],
        BASE / sub, destino,
    )
    if codigo != 0 or destino.stat().st_size <= 25:  # un gzip vacío pesa ~20 bytes
        destino.unlink(missing_ok=True)
        raise ErrorAgente(f"No se pudo respaldar {sub} (¿está encendida?)", 500)
    destino.chmod(0o600)
    for viejo in sorted(carpeta.glob("*.sql.gz"))[:-conservar] if conservar > 0 else []:
        viejo.unlink()
    return destino


def actualizar_instancia(sub: str, imagen_api: str | None = None, imagen_front: str | None = None) -> dict:
    """Cambia la versión de una instancia: respalda, aplica, espera a que responda y, si falla, vuelve a la anterior."""
    sub = validar_sub(sub)
    for img in (imagen_api, imagen_front):
        if img is not None and not _IMAGEN_OK.match(img):
            raise ErrorAgente("Imagen no válida")
    with _candado(sub):
        archivo = BASE / sub / "docker-compose.yml"
        if not archivo.exists():
            raise ErrorAgente("La instancia no existe en este servidor", 404)
        actuales = _IMG.findall(archivo.read_text())  # [db, redis, api, front] en el orden de la plantilla
        api, front = imagen_api or actuales[2], imagen_front or actuales[3]
        if (api, front) == (actuales[2], actuales[3]):
            return {"estado": "sin_cambios"}
        encendida = _corriendo(sub)
        if encendida:
            respaldar_instancia(sub)  # sin respaldo no se toca nada
        anterior = archivo.read_text()
        archivo.write_text(_compose(sub, api, front))
        if not encendida:
            return {"estado": "actualizada_apagada"}  # arrancará con la versión nueva cuando se reanude
        try:
            if PULL:
                _exigir(compose(sub, "pull", "api", "front", timeout=600), "Descargar imágenes")
            _exigir(compose(sub, "up", "-d", "api", "front"), "Aplicar versión")
            _esperar_api(sub)
        except ErrorAgente as e:
            archivo.write_text(anterior)  # vuelta atrás automática
            compose(sub, "up", "-d", "api", "front")
            raise ErrorAgente(f"{e} · Se volvió a la versión anterior.", 500) from e
    return {"estado": "actualizada"}


def guardar_imagenes_por_defecto(api: str | None, front: str | None) -> None:
    a, f = imagenes_por_defecto()
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    (BASE / "imagenes.json").write_text(json.dumps({"api": api or a, "front": front or f}))


SERVICIOS_INSTANCIA = ("api", "front", "db", "redis")
MAX_LOG_BYTES = 200_000


def contenedores(d: dict) -> dict:
    """Contenedores de la instancia con su estado (solo lectura)."""
    sub = validar_sub(d.get("sub"))
    if not (BASE / sub).exists():
        return {"contenedores": []}
    out = _exigir(compose(sub, "ps", "-a", "--format", "json", timeout=30), "Listar contenedores")
    filas = [json.loads(l) for l in out.splitlines() if l.strip()]
    lista = [
        {"servicio": f.get("Service"), "nombre": f.get("Name"), "estado": f.get("State"), "detalle": f.get("Status"), "imagen": f.get("Image")}
        for f in filas
        if f.get("Service") in SERVICIOS_INSTANCIA
    ]
    return {"contenedores": sorted(lista, key=lambda c: SERVICIOS_INSTANCIA.index(c["servicio"]))}


def logs(d: dict) -> dict:
    """Últimas líneas de un contenedor de la instancia (solo lectura, tope de tamaño)."""
    sub = validar_sub(d.get("sub"))
    servicio = d.get("servicio")
    if servicio not in SERVICIOS_INSTANCIA:
        raise ErrorAgente("Servicio no válido")
    try:
        lineas = max(1, min(int(d.get("lineas") or 200), 1000))
    except (TypeError, ValueError):
        raise ErrorAgente("Número de líneas no válido")
    if not (BASE / sub).exists():
        raise ErrorAgente("La instancia no existe en este servidor", 404)
    r = compose(sub, "logs", "--no-color", "-t", "--tail", str(lineas), servicio, timeout=30)
    _exigir(r, "Leer logs")
    texto = (r.stdout + r.stderr)[-MAX_LOG_BYTES:]
    return {"logs": texto}


RUTAS = {"/crear": crear, "/detener": detener, "/reanudar": reanudar, "/eliminar": eliminar,
         "/contenedores": contenedores, "/logs": logs}


# ---------------------------------------------------------------- servidor

def firma(secreto: str, ts: str, cuerpo: bytes) -> str:
    return hmac.new(secreto.encode(), ts.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()


def autorizado(secreto: str, ts: str | None, recibida: str | None, cuerpo: bytes, ahora: float | None = None) -> bool:
    if not (ts and recibida and ts.isdigit()):
        return False
    if abs((ahora or time.time()) - int(ts)) > VENTANA_SEG:
        return False
    return hmac.compare_digest(firma(secreto, ts, cuerpo), recibida)


class Manejador(BaseHTTPRequestHandler):
    secreto = ""

    def log_message(self, fmt, *args):  # sin IPs (es un socket) y sin cuerpos
        print(f"[agente] {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}", flush=True)

    def _responder(self, codigo: int, datos: dict) -> None:
        cuerpo = json.dumps(datos).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 4096:
                return self._responder(413, {"error": "Cuerpo demasiado grande"})
            cuerpo = self.rfile.read(largo)
            if not autorizado(self.secreto, self.headers.get("X-Ts"), self.headers.get("X-Firma"), cuerpo):
                return self._responder(401, {"error": "Firma inválida"})
            accion = RUTAS.get(self.path)
            if accion is None:
                return self._responder(404, {"error": "No existe"})
            datos = json.loads(cuerpo or b"{}")
            if not isinstance(datos, dict):
                raise ErrorAgente("Cuerpo no válido")
            self._responder(200, accion(datos))
        except ErrorAgente as e:
            self._responder(e.codigo, {"error": str(e)})
        except (json.JSONDecodeError, subprocess.TimeoutExpired) as e:
            self._responder(400 if isinstance(e, json.JSONDecodeError) else 504, {"error": "Petición no válida o tiempo agotado"})
        except Exception as e:  # nunca se filtran trazas al panel
            print(f"[agente] error: {e!r}", file=sys.stderr, flush=True)
            self._responder(500, {"error": "Error interno del agente"})

    def do_GET(self):
        self._responder(200, {"ok": True}) if self.path == "/salud" else self._responder(404, {"error": "No existe"})


class Servidor(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def get_request(self):
        sock, _ = super().get_request()
        return sock, ("unix", 0)


def cli(argv: list[str]) -> int:
    """Uso local en el servidor (lo llama el despliegue por SSH): sin socket ni firma."""
    import argparse

    ap = argparse.ArgumentParser(prog="agente.py")
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("actualizar", help="Cambia la versión de una instancia (o de todas)")
    a.add_argument("--api")
    a.add_argument("--front")
    a.add_argument("--sub")
    r = sp.add_parser("respaldar", help="Respalda la base de una instancia (o de todas)")
    r.add_argument("--sub")
    r.add_argument("--conservar", type=int, default=7)
    sp.add_parser("listar")
    args = ap.parse_args(argv)

    if args.cmd == "listar":
        print("\n".join(listar_instancias()) or "(sin instancias)")
        return 0
    subs = [args.sub] if args.sub else listar_instancias()
    fallos = 0
    if args.cmd == "actualizar" and not args.sub:
        guardar_imagenes_por_defecto(args.api, args.front)  # las instancias nuevas ya nacen con esta versión
    for sub in subs:
        try:
            if args.cmd == "respaldar":
                print(f"[ok] {sub}: {respaldar_instancia(sub, args.conservar)}")
            else:
                print(f"[ok] {sub}: {actualizar_instancia(sub, args.api, args.front)['estado']}")
        except ErrorAgente as e:
            print(f"[ERROR] {sub}: {e}", file=sys.stderr)
            fallos += 1
            if args.cmd == "actualizar":
                break  # si una falla, no se sigue con las demás
    return 1 if fallos else 0


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] != "servir":
        sys.exit(cli(sys.argv[1:]))
    secreto = os.environ.get("AGENTE_SECRETO", "")
    if len(secreto) < 32:
        sys.exit("Define AGENTE_SECRETO (32+ caracteres, el mismo que en panel/.env). Usa infra/iniciar.sh")
    if docker(["version", "--format", "{{.Server.Version}}"]).returncode != 0:
        sys.exit("No puedo hablar con Docker. ¿Está encendido y tu usuario puede usarlo?")
    Manejador.secreto = secreto
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if SOCKET.exists():
        SOCKET.unlink()
    with Servidor(str(SOCKET), Manejador) as srv:
        # El contenedor del panel corre con otro usuario: el socket es accesible, la firma HMAC es la barrera
        SOCKET.chmod(0o666)
        print(f"[agente] escuchando en {SOCKET} · instancias en {BASE}", flush=True)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\n[agente] detenido")
        finally:
            SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
