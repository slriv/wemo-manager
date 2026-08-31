FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

# Persist runtime state under `/data`.
ENV WEMO_MANAGER_DATABASE_URL=sqlite:////data/wemo_manager.db \
    WEMO_MANAGER_LOG_FILE=/data/logs/wemo_manager.log \
    WEMO_MANAGER_LOCK_FILE=/data/wemo_manager.lock \
    WEMO_MANAGER_APK_PATH=/data/wemo-manager.apk
VOLUME ["/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/devices')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
