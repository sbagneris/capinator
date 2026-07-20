# capinator web app image. Runs one process: uvicorn + the in-process background worker
# (see docker-compose.yml — never scale this service to more than one replica / worker).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# entrypoint.sh runs `alembic upgrade head` then execs uvicorn. Invoked via `sh` so it
# does not depend on the file's executable bit surviving the build context.
ENTRYPOINT ["sh", "/app/entrypoint.sh"]
