FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends android-tools-adb ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY sony_poller ./sony_poller

ENV PYTHONUNBUFFERED=1 \
    HOME=/adb \
    HEALTH_PORT=8080

VOLUME ["/adb"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${HEALTH_PORT}/healthz >/dev/null || exit 1

CMD ["python", "/app/app.py"]
