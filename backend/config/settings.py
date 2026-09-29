"""
Django settings for the EndNote API.

The API is a stateless ASGI service in front of Supabase. Supabase owns auth;
Django only verifies the JWT. There is no Django user model beyond a `Profile`
mirror, no sessions, and no CSRF: authorisation is a Bearer header on every
request, which keeps CORS to a single header. See decisions.md D-004.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-local-dev-key")
DEBUG = env_bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

# A real key is required in production. A default here would mean a deployment
# that boots with a well-known signing key rather than failing to boot.
if not DEBUG and SECRET_KEY == "insecure-local-dev-key":
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "api.middleware.JWTAuthMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

# ASGI, not WSGI. /api/chat/stream is SSE, and phase 5 requires uvicorn as the
# worker class; a sync WSGI worker serialises streams and hits the request
# timeout. See phases/phase-5-deploy.md.
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("SUPABASE_DB_NAME", "postgres"),
        "USER": os.getenv("SUPABASE_DB_USER", "postgres"),
        "PASSWORD": os.getenv("SUPABASE_DB_PASSWORD", ""),
        # Must be the session pooler host, not the direct host. Render has no
        # IPv6, so a direct connection fails at deploy time rather than here.
        "HOST": os.getenv("SUPABASE_DB_HOST", ""),
        "PORT": os.getenv("SUPABASE_DB_PORT", "5432"),
        "OPTIONS": {"sslmode": os.getenv("SUPABASE_DB_SSLMODE", "require")},
        # Session pooler holds a connection per backend process. 60s is short
        # enough that a Render free instance does not leak idle sessions
        # between requests, and long enough to reuse across a poll loop.
        "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": True,
    }
}

# No session, no cookie, no CSRF auth. DEFAULT_PERMISSION_CLASSES would import
# auth models we deliberately do not have; api/authentication.py supplies the
# real class and every view requires it explicitly.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "EXCEPTION_HANDLER": "api.errors.envelope_exception_handler",
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# The browser talks to Django directly with a Bearer header, so CORS is a real
# surface. Allow the Vercel origin exactly, never "*", and never with
# credentials: there are no cookies to send.
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_HEADERS = ["authorization", "content-type", "accept"]
CORS_ALLOW_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]

# --- Supabase -------------------------------------------------------------
# The project ref is the subdomain of the project URL. Deriving the JWKS URL
# from it means one fewer value to keep in sync in two places.
#
# SUPABASE_S3_ENDPOINT is used as a fallback source for the ref because it is
# present in every deployment that can store a file, and an auth setup with no
# audience to verify against fails on every request with an error that looks
# like a bad token rather than a missing setting.
def _project_ref() -> str:
    explicit = os.getenv("SUPABASE_PROJECT_REF", "").strip()
    if explicit:
        return explicit
    url = os.getenv("SUPABASE_URL", "").strip()
    if url:
        # https://<ref>.supabase.co -> <ref>
        return url.split("//", 1)[-1].split(".", 1)[0]
    s3 = os.getenv("SUPABASE_S3_ENDPOINT", "")
    if "://" in s3 and ".storage.supabase.co" in s3:
        return s3.split("://", 1)[-1].split(".", 1)[0]
    return ""


SUPABASE_PROJECT_REF = _project_ref()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/") or (
    f"https://{SUPABASE_PROJECT_REF}.supabase.co" if SUPABASE_PROJECT_REF else ""
)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL") or (
    f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""
)

# A deployment that cannot verify tokens will reject every request with a 401
# that reads like a bad token. Fail at boot instead, with a message that names
# the missing variable.
if not SUPABASE_JWKS_URL:
    raise RuntimeError(
        "Supabase is not configured: set SUPABASE_URL or SUPABASE_PROJECT_REF so "
        "tokens can be verified against the project JWKS."
    )

# --- LLM ------------------------------------------------------------------
# One OpenAI-compatible client, two base_urls. See architecture.md.
# The model is configuration, not a constant: per-model daily token limits
# differ by 5x, so swapping it is a deploy-time change. See quotas.md.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Cloudflare Workers AI. No longer used for embeddings: the local ONNX stack
# replaced it because the free Render instance has 512MB and the CF plan
# required a round trip per batch for a model that costs 274MB in-process.
# Retained because nothing else depends on it being empty, and removing the
# settings would be churn. See architecture.md "Embeddings".
CF_API_KEY = os.getenv("CF_API_KEY", "")
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "")
CF_EMBED_MODEL = os.getenv("CF_EMBED_MODEL", "@cf/baai/bge-m3")
CF_BASE_URL = (
    f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1"
    if CF_ACCOUNT_ID
    else ""
)

# Local embeddings, ONNX Runtime. See api/embeddings.py for the measurement
# that forced this over torch and over Cloudflare.
#
# EMBEDDING_DIM and EMBED_MODEL must agree. Changing the model means
# re-embedding every stored chunk, because vectors from different models are
# not comparable even at identical dimension.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# Cohere rerank sits behind a Reranker interface with a silent no-op fallback,
# because the free tier (~1000 calls/month) exhausts fast. See retrieval.md.
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")

# --- Product limits -------------------------------------------------------
# Enforced in the API layer, not the UI. See quotas.md and risks.md R-3.
MAX_DOCS_PER_LIBRARY = int(os.getenv("MAX_DOCS_PER_LIBRARY", "20"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
DAILY_QUESTION_LIMIT = int(os.getenv("DAILY_QUESTION_LIMIT", "25"))

# unstructured strategy. "fast" only: "hi_res" pulls in detectron2 and will
# not fit the 512MB target. See phases/phase-1-upload-and-parse.md.
PARSE_STRATEGY = os.getenv("PARSE_STRATEGY", "fast")

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/markdown",
    "text/plain",
    "text/csv",
}

# --- Storage --------------------------------------------------------------
# Required from phase 1, not phase 0. If the S3 variables are absent locally,
# fall back to the filesystem rather than failing at import time, so `migrate`
# and the test suite work without a storage bucket.
#
# Exposed as settings in their own right because api/storage.py signs URLs with
# a raw boto3 client and must not have to re-read os.environ.
SUPABASE_S3_ENDPOINT = os.getenv("SUPABASE_S3_ENDPOINT", "")
SUPABASE_S3_ACCESS_KEY = os.getenv("SUPABASE_S3_ACCESS_KEY", "")
SUPABASE_S3_SECRET_KEY = os.getenv("SUPABASE_S3_SECRET_KEY", "")
SUPABASE_S3_BUCKET = os.getenv("SUPABASE_S3_BUCKET", "document")
SUPABASE_S3_REGION = os.getenv("SUPABASE_S3_REGION", "us-east-1")

if SUPABASE_S3_ENDPOINT:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "endpoint_url": SUPABASE_S3_ENDPOINT,
                "access_key": SUPABASE_S3_ACCESS_KEY,
                "secret_key": SUPABASE_S3_SECRET_KEY,
                "bucket_name": os.getenv("SUPABASE_S3_BUCKET", "document"),
                "region_name": os.getenv("SUPABASE_S3_REGION", "us-east-1"),
                "signature_version": "s3v4",
                "default_acl": "private",
                "file_overwrite": False,
                # Signed URLs rather than public objects. Documents are
                # private to their owner and must never be guessable.
                "querystring_auth": True,
            },
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
else:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Row UUIDs come from Postgres gen_random_uuid(), matching data-model.md.
# Django generates them client-side otherwise, which is equivalent but makes
# the database the only place that knows the ids.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}
