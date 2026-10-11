from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ENV_FILE = Path(os.environ.get("REVIA_ENV_FILE", BASE_DIR / "backend" / ".env"))
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


def _rate(name: str, count: str, window: str = "min") -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        value = count
    if "/" in value:
        return value
    return f"{value}/{window}"

SECRET_KEY = _required("DJANGO_SECRET_KEY")
DEBUG = _flag("DJANGO_DEBUG", False)

ALLOWED_HOSTS = _csv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

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


def _local_pg_config() -> dict | None:
    host = os.environ.get("REVIA_TEST_PG_HOST", "").strip()
    if not host:
        return None
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("REVIA_TEST_PG_NAME", "postgres"),
        "USER": os.environ.get("REVIA_TEST_PG_USER", "postgres"),
        "PASSWORD": os.environ.get("REVIA_TEST_PG_PASSWORD", ""),
        "HOST": host,
        "PORT": os.environ.get("REVIA_TEST_PG_PORT", "5432"),
    }

TESTING = "pytest" in sys.modules or "test" in sys.argv


def _database_config() -> dict:
    if TESTING and os.environ.get("REVIA_TEST_DB", "sqlite").lower() == "sqlite":
        return {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": os.environ.get("REVIA_TEST_DB_NAME", ":memory:"),
            }
        }

    local = _local_pg_config()
    if local is not None:
        config = {**local, "CONN_MAX_AGE": 0, "OPTIONS": {"connect_timeout": 10}}
        explicit_test_name = os.environ.get("REVIA_TEST_PG_TEST_NAME", "").strip()
        if explicit_test_name:
            config["TEST"] = {"NAME": explicit_test_name}
        return {"default": config}

    if TESTING:
        raise ImproperlyConfigured(
            "REVIA_TEST_DB=postgres needs a local Postgres to run against. Set "
            "REVIA_TEST_PG_HOST (and REVIA_TEST_PG_PORT, _USER, _PASSWORD) to a "
            "pgvector instance, for example:\n"
            "  docker run -d --name revia-test-pg -p 5433:5432 "
            "-e POSTGRES_PASSWORD=revia pgvector/pgvector:pg16"
        )

    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _required("SUPABASE_DB_NAME"),
            "USER": _required("SUPABASE_DB_USER"),
            "PASSWORD": _required("SUPABASE_DB_PASSWORD"),
            "HOST": _required("SUPABASE_DB_HOST"),
            "PORT": os.environ.get("SUPABASE_DB_PORT", "5432"),
            "CONN_MAX_AGE": int(os.environ.get("SUPABASE_DB_CONN_MAX_AGE", "60")),
            "OPTIONS": {"connect_timeout": 10},
        }
    }

DATABASES = _database_config()

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
    # The session is held in a cookie, so it arrives on a state-changing request
    # without any other proof of intent. Without this, any site could POST to
    # this API using the visitor's cookies. The referrer check is the second
    # line of defence, for the case where a browser omits the header.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Per session, which is what a cookie gives us to key on.
        "session": _rate("THROTTLE_SESSION_PER_MINUTE", "60"),
        # Per caller, for anything expensive: embedding and generation both cost
        # money per request, and a cookie session is otherwise unmetered.
        "generation": _rate("THROTTLE_GENERATION_PER_HOUR", "60", "h"),
        "upload": _rate("THROTTLE_UPLOAD_PER_HOUR", "120", "h"),
    },
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

# The same list, reused rather than asked for twice. Django's CSRF check has its
# own trusted-origins setting, and leaving it unset while CORS is configured is
# how the two drift apart and a request ends up passing one and failing the
# other. `api.auth` also reads CORS_ALLOWED_ORIGINS directly for its own origin
# check, so there is one list to keep correct.
CSRF_TRUSTED_ORIGINS = _csv("DJANGO_CSRF_TRUSTED_ORIGINS", ",".join(CORS_ALLOWED_ORIGINS))
# No cookie is written by this service, so there is no CSRF cookie for the
# frontend to echo. The double-submit pattern needs one; the Origin/Referer
# check in `api.auth` is what actually rejects a forged request.
CSRF_COOKIE_NAME = ""

SUPABASE_AUTH_CACHE_SECONDS = int(os.environ.get("SUPABASE_AUTH_CACHE_SECONDS", "300"))
SUPABASE_AUTH_TIMEOUT_SECONDS = float(os.environ.get("SUPABASE_AUTH_TIMEOUT_SECONDS", "5"))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY") or os.environ.get("NVIDIA_KEY", "")
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "local")

EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "384"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

EMBEDDING_CACHE_DIR = os.environ.get("EMBEDDING_CACHE_DIR", "")

EMBEDDING_QUERY_PREFIX = os.environ.get(
    "EMBEDDING_QUERY_PREFIX", "Represent this sentence for searching relevant passages: "
)

STORAGE_ENDPOINT = os.environ.get("SUPABASE_S3_ENDPOINT", "")
STORAGE_ACCESS_KEY = os.environ.get("SUPABASE_S3_ACCESS_KEY", "")
STORAGE_SECRET_KEY = os.environ.get("SUPABASE_S3_SECRET_KEY", "")
STORAGE_BUCKET = os.environ.get("SUPABASE_S3_BUCKET", "document")
STORAGE_REGION = os.environ.get("SUPABASE_S3_REGION", "us-east-1")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
ALLOWED_UPLOAD_EXTENSIONS = (".pdf", ".docx", ".pptx")

PDF_PARTITION_STRATEGY = os.environ.get("PDF_PARTITION_STRATEGY", "hi_res")

RUN_PIPELINE_IN_PROCESS = _flag("REVIA_RUN_PIPELINE_IN_PROCESS", True)

PIPELINE_BATCH_SIZE = int(os.environ.get("PIPELINE_BATCH_SIZE", "10"))

PIPELINE_IDLE_SECONDS = float(os.environ.get("PIPELINE_IDLE_SECONDS", "5"))

PIPELINE_BUSY_SECONDS = float(os.environ.get("PIPELINE_BUSY_SECONDS", "0.5"))

PIPELINE_STALLED_SECONDS = int(
    os.environ.get("PIPELINE_STALLED_SECONDS", "300" if DEBUG else str(15 * 60))
)

CHAT_CONTEXT_WINDOW = int(os.environ.get("CHAT_CONTEXT_WINDOW", "131072"))

ANSWER_MAX_TOKENS = int(os.environ.get("ANSWER_MAX_TOKENS", "1200"))

ANSWER_TEMPERATURE = float(os.environ.get("ANSWER_TEMPERATURE", "0.1"))

CHAT_HISTORY_TURNS = int(os.environ.get("CHAT_HISTORY_TURNS", "8"))
CHAT_HISTORY_MAX_TOKENS = int(os.environ.get("CHAT_HISTORY_MAX_TOKENS", "3000"))

MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", "4000"))

RETRIEVAL_MAX_DISTANCE = float(os.environ.get("RETRIEVAL_MAX_DISTANCE", "0.45"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
