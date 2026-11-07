"""Capa de infraestructura. Hoy es SIMULADA: escribe en data/instancias/<subdominio>/ los archivos
que se usarían en el VPS (.env, compose y bloque de Caddy) pero no ejecuta nada.

Cuando tengas el VPS se agrega un `AprovisionadorDocker` con la misma interfaz y se elige con
APROVISIONADOR=docker. El resto del panel no cambia.
"""

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from flask import current_app

from app.modelos import Instancia


@dataclass
class Resultado:
    ok: bool
    estado_infra: str
    error: str | None = None


class Aprovisionador:
    def crear(self, inst: Instancia, secretos: dict) -> Resultado: ...
    def detener(self, inst: Instancia) -> Resultado: ...
    def reanudar(self, inst: Instancia) -> Resultado: ...
    def eliminar(self, inst: Instancia) -> Resultado: ...
    def actualizar_dominio(self, inst: Instancia) -> Resultado: ...

    def contenedores(self, inst: Instancia) -> tuple[list[dict], str | None]:
        return [], "Disponible solo con APROVISIONADOR=agente"

    def logs(self, inst: Instancia, servicio: str, lineas: int) -> tuple[str, str | None]:
        return "", "Disponible solo con APROVISIONADOR=agente"


def hosts(inst: Instancia, dominio_base: str) -> list[str]:
    h = [f"{inst.subdominio}.{dominio_base}"]
    if inst.dominio_propio and inst.dominio_verificado:
        h.append(inst.dominio_propio)
    return h


_COMPOSE = """\
# Generado por el panel. No editar a mano: se regenera al cambiar la instancia.
name: restify-{sub}
services:
  api:
    image: restify-api:latest
    env_file: .env
    networks: [interna, proxy]
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
  front:
    image: restify-front:latest
    environment:
      NEXT_PUBLIC_API_URL: https://{host}/api/v1
    networks: [proxy]
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
  db:
    image: postgres:16-alpine
    env_file: .env
    networks: [interna]
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    networks: [interna]
networks:
  interna: {{internal: true}}
  proxy: {{external: true, name: restify-proxy}}
volumes:
  pgdata:
"""

_CADDY = """\
{hosts} {{
    encode zstd gzip
    handle /api/* {{ reverse_proxy restify-{sub}-api-1:8000 }}
    handle {{ reverse_proxy restify-{sub}-front-1:3000 }}
}}
"""


class AprovisionadorSimulado(Aprovisionador):
    def _dir(self, inst: Instancia) -> Path:
        return Path(current_app.config["DIR_INSTANCIAS"]) / inst.subdominio

    def _escribir(self, inst: Instancia, secretos: dict | None = None) -> None:
        d = self._dir(inst)
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        base = current_app.config["DOMINIO_BASE"]
        lista = hosts(inst, base)
        (d / "docker-compose.yml").write_text(_COMPOSE.format(sub=inst.subdominio, host=lista[0]))
        (d / "Caddyfile").write_text(_CADDY.format(sub=inst.subdominio, hosts=", ".join(lista)))
        if secretos is not None:
            env = d / ".env"
            env.touch(mode=0o600)
            env.write_text(
                "\n".join(f"{k}={v}" for k, v in {
                    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
                    "REDIS_PASSWORD": secrets.token_urlsafe(32),
                    "JWT_SECRET": secrets.token_urlsafe(48),
                    # El token NO va aquí: el cliente lo escribe en la pantalla de configuración inicial
                    "PANEL_URL": secretos["panel_url"],
                    "INSTANCIA_SUBDOMINIO": inst.subdominio,
                    "ALLOWED_HOSTS": ",".join(lista),
                }.items()) + "\n"
            )

    def crear(self, inst, secretos):
        self._escribir(inst, secretos)
        return Resultado(True, "en_linea")

    def detener(self, inst):
        return Resultado(True, "detenida")

    def reanudar(self, inst):
        return Resultado(True, "en_linea")

    def eliminar(self, inst):
        import shutil

        shutil.rmtree(self._dir(inst), ignore_errors=True)
        return Resultado(True, "eliminada")

    def actualizar_dominio(self, inst):
        if self._dir(inst).exists():
            self._escribir(inst)
        return Resultado(True, inst.estado_infra)


class AprovisionadorAgente(Aprovisionador):
    """Pide al agente (proceso aparte con acceso a Docker) que cree, detenga, reanude o elimine la instancia.

    El panel nunca toca Docker: habla por un socket Unix firmado con HMAC y el agente valida todo de nuevo.
    """

    def _enviar(self, ruta: str, payload: dict) -> tuple[dict | None, str | None]:
        """Llamada firmada al agente. Devuelve (respuesta, error)."""
        cfg = current_app.config
        if len(cfg["AGENTE_SECRETO"]) < 32:
            return None, "Falta AGENTE_SECRETO en el .env del panel"
        cuerpo = json.dumps(payload).encode()
        ts = str(int(time.time()))
        firma = hmac.new(cfg["AGENTE_SECRETO"].encode(), ts.encode() + b"." + cuerpo, hashlib.sha256).hexdigest()
        try:
            with httpx.Client(transport=httpx.HTTPTransport(uds=cfg["AGENTE_SOCKET"]), base_url="http://agente", timeout=170) as c:
                r = c.post(ruta, content=cuerpo, headers={"X-Ts": ts, "X-Firma": firma, "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            return None, f"No hay conexión con el agente (¿está encendido?): {type(e).__name__}"
        if r.status_code != 200:
            try:
                msg = r.json().get("error", "error desconocido")
            except ValueError:
                msg = f"HTTP {r.status_code}"
            return None, f"El agente respondió: {msg}"
        return r.json(), None

    def _llamar(self, ruta: str, payload: dict) -> Resultado:
        datos, error = self._enviar(ruta, payload)
        if error:
            return Resultado(False, "error", error)
        return Resultado(True, datos.get("estado", "en_linea"))

    def contenedores(self, inst):
        datos, error = self._enviar("/contenedores", {"sub": inst.subdominio})
        return (datos or {}).get("contenedores", []), error

    def logs(self, inst, servicio, lineas):
        datos, error = self._enviar("/logs", {"sub": inst.subdominio, "servicio": servicio, "lineas": lineas})
        return (datos or {}).get("logs", ""), error

    def crear(self, inst, secretos):
        cfg = current_app.config
        return self._llamar("/crear", {
            "sub": inst.subdominio,
            "dominio_base": cfg["DOMINIO_BASE"],
            "esquema": cfg["INSTANCIA_ESQUEMA"],
            "puerto": cfg["INSTANCIA_PUERTO"],
            "panel_url": cfg["PANEL_URL_INTERNA"].rstrip("/") + "/api/v1/estado",
            "zona_horaria": cfg["ZONA_HORARIA_INSTANCIAS"],
        })

    def detener(self, inst):
        return self._llamar("/detener", {"sub": inst.subdominio})

    def reanudar(self, inst):
        return self._llamar("/reanudar", {"sub": inst.subdominio})

    def eliminar(self, inst):
        return self._llamar("/eliminar", {"sub": inst.subdominio})

    def actualizar_dominio(self, inst):
        # Dominios propios: requieren certificados por dominio (Caddy en el VPS). Por ahora no cambia nada.
        return Resultado(True, inst.estado_infra)


def obtener() -> Aprovisionador:
    modo = current_app.config["APROVISIONADOR"]
    if modo == "simulado":
        return AprovisionadorSimulado()
    if modo == "agente":
        return AprovisionadorAgente()
    raise RuntimeError(f"APROVISIONADOR desconocido: {modo!r} (simulado | agente)")
