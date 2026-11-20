#!/usr/bin/env python3
"""Herramienta de RESTIFY para firmar plugins. Se corre en TU equipo, nunca en el servidor.

  python3 firmar.py claves   --privada ~/.restify/plugins.key     # crea el par de claves (una sola vez)
  python3 firmar.py firmar   manifiesto.json --privada ~/.restify/plugins.key --salida paquete.json
  python3 firmar.py verificar paquete.json --publica <clave_publica_base64>

La clave PRIVADA no se comparte ni se sube a ningún repositorio ni servidor. La PÚBLICA va en la
variable PLUGIN_CLAVES_PUBLICAS del backend, por ejemplo: PLUGIN_CLAVES_PUBLICAS='["...base64..."]'.
La firma cubre el manifiesto exacto: cualquier cambio (permisos, versión, huella de imagen) exige firmar otra vez.
Requiere: pip install cryptography
"""

import argparse
import base64
import json
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonico(m: dict) -> bytes:
    # Debe ser idéntico al del backend (app/services/plugins.py)
    return json.dumps(m, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def publica_b64(clave: Ed25519PrivateKey) -> str:
    raw = clave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def cargar_privada(ruta: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(Path(ruta).expanduser().read_text().strip()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claves"); c.add_argument("--privada", required=True)
    f = sub.add_parser("firmar"); f.add_argument("manifiesto"); f.add_argument("--privada", required=True); f.add_argument("--salida", required=True)
    v = sub.add_parser("verificar"); v.add_argument("paquete"); v.add_argument("--publica", required=True)
    a = ap.parse_args()

    if a.cmd == "claves":
        ruta = Path(a.privada).expanduser()
        if ruta.exists():
            sys.exit(f"Ya existe {ruta}. No la piso: si la pierdes no podrás firmar más plugins.")
        ruta.parent.mkdir(parents=True, exist_ok=True)
        clave = Ed25519PrivateKey.generate()
        raw = clave.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
        fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(base64.b64encode(raw).decode() + "\n")
        print(f"Clave privada guardada en {ruta} (permisos 600). Respáldala en un lugar seguro.")
        print(f"Clave pública para PLUGIN_CLAVES_PUBLICAS:\n{publica_b64(clave)}")
    elif a.cmd == "firmar":
        manifiesto = json.loads(Path(a.manifiesto).read_text())
        firma = base64.b64encode(cargar_privada(a.privada).sign(canonico(manifiesto))).decode()
        Path(a.salida).write_text(json.dumps({"manifiesto": manifiesto, "firma": firma}, indent=2, ensure_ascii=False) + "\n")
        print(f"Paquete firmado en {a.salida}")
    else:
        p = json.loads(Path(a.paquete).read_text())
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(a.publica)).verify(base64.b64decode(p["firma"]), canonico(p["manifiesto"]))
        except (InvalidSignature, KeyError, ValueError):
            sys.exit("Firma NO válida")
        print("Firma válida")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
