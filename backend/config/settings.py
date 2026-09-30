"""Django settings for the EndNote backend.

Configuration is environment-only. There are no hard-coded credentials and no
fallbacks that silently invent a working value: a missing key raises at import
time, so a misconfigured deployment fails immediately instead of quietly
talking to the wrong database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_FILE = Path(os.environ.get("ENDNOTE_ENV_FILE", BASE_DIR / "backend" / ".env"))
if ENV_FILE.is_file():
    load_dotenv(ENV_FILE)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = _required("DJANGO_SECRET_KEY")
DEBUG = _flag("DJANGO_DEBUG", False)

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS")

# Authentication is owned by Supabase. Django's own user model, sessions and
# admin are deliberately absent: a second identity system would be a second
# source of truth for "who is this".
INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = []

SUPABASE_URL = _required("SUPABASE_URL").rstrip("/")
SUPABASE_ANON_KEY = _required("SUPABASE_ANON_KEY")


def _direct_connection() -> dict[str, str]:
    """A direct (unpooled) Postgres connection, for the test database only.

    The application connects through Supabase's pooler, which is the right
    choice for serving traffic. It is the wrong choice for tests: the pooler
    holds idle sessions open, and an idle session makes `DROP DATABASE` fail, so
    the test runner could never clean up and left a stray `endnote_test` behind
    on the shared project.

    The pooler also authenticates as `postgres.<project-ref>`, a role that does
    not exist on the direct host, so the ref suffix is stripped for the direct
    connection.
    """
    explicit_host = os.environ.get("SUPABASE_DB_DIRECT_HOST", "").strip()
    if explicit_host:
        host = explicit_host
    else:
        project_ref = SUPABASE_URL.split("//", 1)[1].split(".", 1)[0]
        host = f"db.{project_ref}.supabase.co"

    explicit_user = os.environ.get("SUPABASE_DB_DIRECT_USER", "").strip()
    user = explicit_user or _required("SUPABASE_DB_USER").split(".")[0]

    return {
        "HOST": host,
        "PORT": os.environ.get("SUPABASE_DB_DIRECT_PORT", "5432"),
        "USER": user,
    }


# Supabase Postgres over psycopg 3. The pool is small on purpose: this service
# is I/O bound on Postgres for the pipeline and on third-party APIs for chat.
# `sys.argv[0]` is the full path to the pytest executable, so argv cannot be
# searched for the literal "pytest". Checking sys.modules works because the
# settings module is only imported after pytest itself is loaded. The argv
# check covers Django's own runner, invoked as `manage.py test`.
TESTING = "pytest" in sys.modules or "test" in sys.argv

# Tests default to an in-memory SQLite database.
#
# The alternative, running them against the real Supabase project, is not
# workable here. Django creates and drops a test database around every run, and
# neither available route to that project allows the drop: through the pooler,
# Supavisor holds an idle session open, and the direct host is an unreliable
# IPv6 path from this machine. The result was a stray `endnote_test` database
# left on the shared project.
#
# SQLite keeps the suite hermetic and fast, and nothing a test does can reach
# the live database. The cost is that Postgres-specific behaviour is not
# exercised, which matters once pgvector and full-text search land: set
# ENDNOTE_TEST_DB=postgres to run against a real Postgres, and expect that
# target to be a local container or a dedicated project rather than this one.
if TESTING and os.environ.get("ENDNOTE_TEST_DB", "sqlite").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("ENDNOTE_TEST_DB_NAME", ":memory:"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _required("SUPABASE_DB_NAME"),
            "USER": _required("SUPABASE_DB_USER"),
            "PASSWORD": _required("SUPABASE_DB_PASSWORD"),
            "HOST": _required("SUPABASE_DB_HOST"),
            "PORT": os.environ.get("SUPABASE_DB_PORT", "5432"),
            "CONN_MAX_AGE": 0 if TESTING else int(os.environ.get("SUPABASE_DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {"connect_timeout": 10},
            # Django uses this name verbatim, with no `test_` prefix of its own.
            "TEST": {
                "NAME": os.environ.get("SUPABASE_DB_TEST_NAME", "endnote_test"),
                **_direct_connection(),
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.auth.CookieSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "UNAUTHENTICATED_USER": None,
}

# The browser holds the Supabase session cookie, so credentialed cross-origin
# requests are mandatory. Origins are explicit, never "*".
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = _csv(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000",
)
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "x-csrftoken"]

# Token verification hits the Supabase Auth API and caches by token hash. A
# verified token is immutable, so caching on it is safe; the TTL is a guard
# against unbounded growth rather than a correctness requirement.
SUPABASE_AUTH_CACHE_SECONDS = int(os.environ.get("SUPABASE_AUTH_CACHE_SECONDS", "300"))
SUPABASE_AUTH_TIMEOUT_SECONDS = float(os.environ.get("SUPABASE_AUTH_TIMEOUT_SECONDS", "5"))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_KEY", "")
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))

STORAGE_ENDPOINT = os.environ.get("SUPABASE_S3_ENDPOINT", "")
STORAGE_ACCESS_KEY = os.environ.get("SUPABASE_S3_ACCESS_KEY", "")
STORAGE_SECRET_KEY = os.environ.get("SUPABASE_S3_SECRET_KEY", "")
STORAGE_BUCKET = os.environ.get("SUPABASE_S3_BUCKET", "document")
STORAGE_REGION = os.environ.get("SUPABASE_S3_REGION", "us-east-1")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".pptx")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
