# syntax=docker/dockerfile:1.7
# Production image: build SPA, install Python deps in a venv, run Django via Gunicorn (WSGI).
# When Channels/WebSockets land in Phase 1, the entrypoint switches to Daphne (ASGI).

# --- Stage 1: build the SPA ------------------------------------------------
FROM node:26-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: build Python venv -------------------------------------------
FROM python:3.14-slim AS deps
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gettext \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 3: runtime -----------------------------------------------------
FROM python:3.14-slim AS runtime

# Runtime needs:
#  - curl: healthcheck
#  - gettext: provides `msgfmt`, used by `compilemessages` during the image
#    build below. (`gettext-base` does NOT include msgfmt — that's `gettext`.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gettext \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd  --system --uid 1000 --gid app --home /app --shell /usr/sbin/nologin app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=hostcraft.settings

WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY --chown=app:app backend/ /app/
COPY --from=frontend --chown=app:app /app/dist/ /app/spa/

# Compile translations + collect static. SECRET_KEY is bogus at build time on
# purpose — those commands don't need a real one.
RUN DJANGO_SECRET_KEY=build-time-only python manage.py compilemessages -i node_modules -i staticfiles \
    && DJANGO_SECRET_KEY=build-time-only python manage.py collectstatic --noinput \
    && mkdir -p /data /backups \
    && chown app:app /data /backups

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD curl -fsS http://localhost:8000/api/health/ || exit 1

# Migrate, seed admin, run Gunicorn (WSGI). Switch to Daphne in Phase 1.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py bootstrap_admin && exec gunicorn --bind 0.0.0.0:8000 --workers 3 --access-logfile - --error-logfile - hostcraft.wsgi:application"]
