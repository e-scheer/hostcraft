"""Django settings for hostcraft.

Configuration is driven entirely by environment variables — never a `.env` file
committed to the repo. The only "default" SECRET_KEY allowed is one explicitly
flagged as insecure, used only when DJANGO_DEBUG is on.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

DEBUG = _env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or (
    "django-insecure-do-not-use-in-prod" if DEBUG else ""
)
if not SECRET_KEY:
    raise RuntimeError(
        "DJANGO_SECRET_KEY must be set in production (DJANGO_DEBUG is off and no key was provided)."
    )

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend,hostcraft")

# CSRF — needed when serving the SPA from the same origin in prod.
CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:5173,http://localhost:8000,http://localhost:8080",
)


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    # Channels needs daphne registered before staticfiles for runserver.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # 3rd party
    "rest_framework",
    "corsheaders",
    # Local
    "users",
    "api",
    "server",
    "files",
    "backups",
    "schedules",
    "audit",
    "network",
    "mods",
    "worldmap",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise comes right after SecurityMiddleware (project convention).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # LocaleMiddleware reads Accept-Language and activates the right gettext
    # catalog before the view runs. Must come AFTER SessionMiddleware and
    # BEFORE CommonMiddleware (Django docs).
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Audit log: must come last so it sees the final response status code.
    "audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "hostcraft.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "spa"],  # so SpaView can find index.html in prod
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "hostcraft.wsgi.application"
ASGI_APPLICATION = "hostcraft.asgi.application"

# Channels — single-process in-memory layer is fine for one-server panel.
# Switch to Redis if/when the panel ever needs to scale to multiple workers.
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv("HOSTCRAFT_DB_PATH", BASE_DIR / "hostcraft.db"),
        "OPTIONS": {
            # Default rollback journal (not WAL): WAL + Docker bind mounts have a
            # known mmap/lock issue where the -wal file disappears between
            # consecutive Python processes (migrate, bootstrap, runserver).
            # WAL is fine in prod where the DB lives in a Docker named volume.
            "timeout": 20,
            "init_command": "PRAGMA foreign_keys=ON;",
        },
    }
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "users.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# DRF + JWT
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "SIGNING_KEY": SECRET_KEY,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ---------------------------------------------------------------------------
# CORS — only used when the SPA hits the API cross-origin (i.e. browser ↔ API
# direct, not through Vite's proxy).
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = _env_list(
    "DJANGO_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# Static / SPA
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "spa" / "assets"] if (BASE_DIR / "spa" / "assets").exists() else []

# WhiteNoise: compressed + hashed manifest in prod.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"} if not DEBUG
    else {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

SPA_INDEX = BASE_DIR / "spa" / "index.html"


# ---------------------------------------------------------------------------
# Bootstrap admin (used by the bootstrap_admin management command).
# ---------------------------------------------------------------------------

INITIAL_ADMIN_USER = os.getenv("HOSTCRAFT_INITIAL_ADMIN_USER", "admin")
INITIAL_ADMIN_PASSWORD = os.getenv("HOSTCRAFT_INITIAL_ADMIN_PASSWORD", "admin" if DEBUG else "")


# ---------------------------------------------------------------------------
# Minecraft container management
# ---------------------------------------------------------------------------

# DOCKER_HOST points at the docker-socket-proxy service (NOT the raw socket).
# The proxy whitelists what we're allowed to do.
DOCKER_HOST = os.getenv("DOCKER_HOST", "tcp://docker-proxy:2375")
MC_CONTAINER_NAME = os.getenv("MC_CONTAINER_NAME", "hostcraft-minecraft")
MC_RCON_HOST = os.getenv("MC_RCON_HOST", "minecraft")
MC_RCON_PORT = int(os.getenv("MC_RCON_PORT", "25575"))
MC_RCON_PASSWORD = os.getenv("MC_RCON_PASSWORD", "")

# Path inside the panel container where the Minecraft data volume is mounted.
# Same Docker named volume as the minecraft container's /data, so file changes
# from one are visible from the other.
MC_DATA_PATH = os.getenv("MC_DATA_PATH", "/mc-data")

# Backups land in their own named volume so they survive panel rebuilds and
# can later be synced off-site (S3 / B2 / Drive — Phase 1.6b).
BACKUP_PATH = os.getenv("HOSTCRAFT_BACKUP_PATH", "/backups")

# Allow up to 1 GiB uploads (we stream chunks to disk; memory is bounded).
DATA_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024  # 25 MB in-memory threshold
FILE_UPLOAD_MAX_MEMORY_SIZE = 25 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if not DEBUG:
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO" if not DEBUG else "DEBUG").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname:8s} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.request": {"level": "WARNING", "propagate": True},
        # Third-party plumbing — keep their chatter out of dev logs even
        # when our own root level is DEBUG.
        "urllib3": {"level": "INFO", "propagate": True},
        "docker": {"level": "INFO", "propagate": True},
        "daphne": {"level": "INFO", "propagate": True},
        "asyncio": {"level": "INFO", "propagate": True},
    },
}


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
