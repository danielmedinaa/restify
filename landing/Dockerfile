FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario sin privilegios
RUN groupadd --system landing && useradd --system --gid landing --home /app landing

ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r ${REQUIREMENTS}

COPY --chown=landing:landing . .
RUN mkdir -p /app/data && chown landing:landing /app/data

USER landing
EXPOSE 8000

CMD ["sh", "-c", "exec gunicorn wsgi:app --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --access-logfile - --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
