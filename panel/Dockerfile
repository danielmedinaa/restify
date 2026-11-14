FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario sin privilegios
RUN groupadd --system panel && useradd --system --gid panel --home /app panel

ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r ${REQUIREMENTS}

COPY --chown=panel:panel . .
RUN mkdir -p /app/data && chown panel:panel /app/data

USER panel
EXPOSE 8000

CMD ["sh", "-c", "flask --app wsgi db upgrade && flask --app wsgi sembrar && exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --timeout 200 --no-control-socket --access-logfile - --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
