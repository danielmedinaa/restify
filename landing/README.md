# RESTIFY · Landing

Página de venta de RESTIFY, hecha con Flask (backend y plantillas Jinja). No necesita
Node, CDNs ni build: el CSS y el JS están en `app/static`.

## Correr

```bash
cp .env.example .env        # cambia SECRET_KEY, WhatsApp, correo e Instagram
docker compose up -d --build   # http://localhost:8020
docker compose --profile test run --rm --build tests
```

## Editar textos y precios

Todo el contenido vive en [app/contenido.py](app/contenido.py): hero, problemas, funciones, flujo,
planes, proceso, razones y preguntas. En los títulos, `*palabra*` se muestra resaltada.
**Los precios de los planes son de ejemplo**: ajústalos antes de publicar.

## Solicitudes de demo

El formulario guarda cada solicitud en SQLite (volumen `leads`). Para exportarlas a CSV (Excel):

```bash
docker compose exec web flask --app wsgi leads --salida /app/data/leads.csv
docker compose cp web:/app/data/leads.csv .
```

## Seguridad

- **CSP estricta:** solo recursos propios, sin scripts ni estilos en línea.
- **Headers de seguridad** en todas las respuestas, y HSTS en producción.
- **Formulario:** token CSRF, campo trampa para bots, validación en el servidor y un máximo de
  solicitudes por IP. La IP no se guarda: solo un hash con sal.
- **Contenedor:** corre sin privilegios. `SECRET_KEY` es obligatoria en producción.
- **Detrás de un proxy:** define `PROXY_SALTOS` y `FORWARDED_ALLOW_IPS` para que el límite por IP use
  la IP real del cliente.
