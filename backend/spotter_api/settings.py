"""
Django settings for spotter_api.
Reads secrets from app/.env via python-dotenv in dev, or Railway-provided
process env vars in prod.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent           # /app/backend
REPO_ROOT = BASE_DIR.parent                                  # /app

# In production (Railway) the .env file doesn't exist; load_dotenv is a no-op
# and we rely on the platform's env vars. In dev it pulls from /app/.env.
load_dotenv(REPO_ROOT / ".env")

SECRET_KEY = (
    os.getenv("DJANGO_SECRET_KEY")
    or "django-insecure-dev-only-key-do-not-use-in-prod"
)
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

# ALLOWED_HOSTS: locally, just localhost. On Railway, the platform injects
# a deploy URL like spotter-backend-production.up.railway.app — we accept
# everything under *.up.railway.app plus anything the operator sets in
# DJANGO_ALLOWED_HOSTS.
ALLOWED_HOSTS = [
    h.strip() for h in
    os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    ALLOWED_HOSTS.append(os.environ["RAILWAY_PUBLIC_DOMAIN"])
# Wildcard for Railway's preview/production subdomain pattern.
ALLOWED_HOSTS.append(".up.railway.app")

ORS_API_KEY = os.getenv("ORS_API_KEY", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    # whitenoise serves the Django admin's static files in prod — Railway has
    # no separate static-file server. Insert directly after SecurityMiddleware
    # per whitenoise docs.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# CORS: dev allows the Vite proxy origins; prod adds the deployed frontend
# URL via env var (set after the Vercel deploy lands).
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
if os.getenv("FRONTEND_ORIGIN"):
    CORS_ALLOWED_ORIGINS.append(os.environ["FRONTEND_ORIGIN"])
# Also allow any vercel.app preview URL (read-only API; no cookies involved).
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]

ROOT_URLCONF = "spotter_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "spotter_api.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CSRF: Railway and Vercel both serve over HTTPS. The DRF endpoints we expose
# don't use CSRF tokens (they're stateless JSON), but Django's admin still
# does — so trust both deploy targets.
CSRF_TRUSTED_ORIGINS = [
    "https://*.up.railway.app",
    "https://*.vercel.app",
]
if os.getenv("FRONTEND_ORIGIN"):
    CSRF_TRUSTED_ORIGINS.append(os.environ["FRONTEND_ORIGIN"])

# When DEBUG=False the SecurityMiddleware enforces HTTPS redirects; Railway
# terminates TLS at the edge so Django sees HTTP internally. Trust the
# X-Forwarded-Proto header so request.is_secure() returns True.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}
