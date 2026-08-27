# Hydra World — API
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /app/apps/api/requirements.txt

COPY packages /app/packages
COPY apps/api /app/apps/api
COPY database /app/database
COPY scripts /app/scripts

# One .pth file makes every `hydra.*` package importable from its own directory.
RUN python /app/scripts/install_dev_paths.py

ENV PYTHONPATH=/app/apps/api PORT=8000
EXPOSE 8000

# Cloud Run injects $PORT and ignores EXPOSE, so the port has to be read at start, not baked.
# Shell form on purpose: exec form would pass the literal string "$PORT" to uvicorn.
CMD exec uvicorn hydra_api.main:app --host 0.0.0.0 --port ${PORT}
