FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8080 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY static ./static
COPY run.py .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8080

# Syslog: порт задаётся в UI; в Docker пробросьте диапазон (см. docker-compose.yml) или один порт в docker run.
EXPOSE 5000-5999/tcp 5000-5999/udp

CMD ["python", "run.py"]
