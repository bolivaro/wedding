from datetime import date, datetime
from pathlib import Path
import sys
import environ

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "apps"))

env = environ.Env(
    DEBUG=(bool, False),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_USE_SSL=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")

SITE_BASE_URL = env("SITE_BASE_URL", default="http://127.0.0.1:8000")
WEDDING_DATE = date.fromisoformat(env("WEDDING_DATE", default="2026-10-17"))
WEDDING_PROGRAM_URL = env(
    "WEDDING_PROGRAM_URL",
    default=f"{SITE_BASE_URL.rstrip('/')}/programme/",
)
WEDDING_DRESS_CODE_URL = env(
    "WEDDING_DRESS_CODE_URL",
    default=f"{SITE_BASE_URL.rstrip('/')}/dress-code/",
)
GOOGLE_MAPS_EMBED_API_KEY = env("GOOGLE_MAPS_EMBED_API_KEY", default="")
GOOGLE_MY_MAPS_EMBED_URL = env("GOOGLE_MY_MAPS_EMBED_URL", default="")
RSVP_DEADLINE = datetime.fromisoformat(
    env("RSVP_DEADLINE", default="2026-09-15T23:59:59+02:00")
)
RSVP_SUPPORT_EMAIL = env("RSVP_SUPPORT_EMAIL", default="nous@leslieniboli.fr")
GUEST_ACCESS_LIFETIME_DAYS = env.int("GUEST_ACCESS_LIFETIME_DAYS", default=120)
GUEST_ACCESS_MAX_FAILURES = env.int("GUEST_ACCESS_MAX_FAILURES", default=5)
GUEST_ACCESS_LOCK_MINUTES = env.int("GUEST_ACCESS_LOCK_MINUTES", default=15)
GUEST_EMAIL_TOKEN_MINUTES = env.int("GUEST_EMAIL_TOKEN_MINUTES", default=30)

TICKET_TEMPLATE_STATIC_PATH = env(
    "TICKET_TEMPLATE_STATIC_PATH",
    default="guests/images/billet-template-v1.jpg",
)
TICKET_TEMPLATE_VERSION = env("TICKET_TEMPLATE_VERSION", default="billet-v1")
TICKET_FONT_STATIC_PATH = env(
    "TICKET_FONT_STATIC_PATH",
    default="guests/fonts/STIXGeneralItalic.otf",
)
TICKET_INFO_FONT_STATIC_PATH = env(
    "TICKET_INFO_FONT_STATIC_PATH",
    default="guests/fonts/CormorantGaramond.ttf",
)
TICKET_REFERENCE_WIDTH = env.int("TICKET_REFERENCE_WIDTH", default=1796)
TICKET_REFERENCE_HEIGHT = env.int("TICKET_REFERENCE_HEIGHT", default=2528)
TICKET_NAME_BOX = (
    env.int("TICKET_NAME_LEFT", default=100),
    env.int("TICKET_NAME_TOP", default=100),
    env.int("TICKET_NAME_RIGHT", default=1696),
    env.int("TICKET_NAME_BOTTOM", default=480),
)
TICKET_NAME_FONT_POINTS = env.int("TICKET_NAME_FONT_POINTS", default=14)
TICKET_NAME_COLOR = env("TICKET_NAME_COLOR", default="#CD9241")
TICKET_QR_BOX = (
    env.int("TICKET_QR_LEFT", default=180),
    env.int("TICKET_QR_TOP", default=1410),
    env.int("TICKET_QR_RIGHT", default=420),
    env.int("TICKET_QR_BOTTOM", default=1650),
)
TICKET_QR_FOREGROUND = env("TICKET_QR_FOREGROUND", default="#B12200")
TICKET_QR_BACKGROUND = env("TICKET_QR_BACKGROUND", default="#FFEEEC")
TICKET_OUTPUT_DPI = env.int("TICKET_OUTPUT_DPI", default=300)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://127.0.0.1:8000", "http://localhost:8000"],
)
SECURE_REFERRER_POLICY = "same-origin"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "guests",
    "specialdemands",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lesbon.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "lesbon.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

OBJECT_STORAGE_ENABLED = env.bool("OBJECT_STORAGE_ENABLED", default=False)

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if OBJECT_STORAGE_ENABLED:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("OBJECT_STORAGE_BUCKET_NAME"),
            "access_key": env("OBJECT_STORAGE_ACCESS_KEY_ID"),
            "secret_key": env("OBJECT_STORAGE_SECRET_ACCESS_KEY"),
            "endpoint_url": env("OBJECT_STORAGE_ENDPOINT"),
            "region_name": env("OBJECT_STORAGE_REGION", default="auto"),
            "addressing_style": env(
                "OBJECT_STORAGE_ADDRESSING_STYLE",
                default="virtual",
            ),
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": env.int(
                "OBJECT_STORAGE_URL_EXPIRE",
                default=3600,
            ),
            "file_overwrite": False,
        },
    }

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="ssl0.ovh.net")
EMAIL_PORT = env("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_TIMEOUT = 10

BREVO_API_KEY = env("BREVO_API_KEY")
BREVO_SENDER_EMAIL = env("BREVO_SENDER_EMAIL", default="nous@leslieniboli.fr")
BREVO_SENDER_NAME = env("BREVO_SENDER_NAME", default="Leslie & Bolivar")

# optionnel si tu veux garder un from email cohérent ailleurs
DEFAULT_FROM_EMAIL = f"{BREVO_SENDER_NAME} <{BREVO_SENDER_EMAIL}>"
SERVER_EMAIL = DEFAULT_FROM_EMAIL

SPECIAL_DEMAND_REPLY_TO_EMAIL = env(
    "SPECIAL_DEMAND_REPLY_TO_EMAIL",
    default=EMAIL_HOST_USER,
)

SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS = env.list(
    "SPECIAL_DEMAND_DEFAULT_NOTIFY_EMAILS",
    default=[EMAIL_HOST_USER],
)

WHATSAPP_NUMBER_1 = env("WHATSAPP_NUMBER_1", default="")
WHATSAPP_NUMBER_2 = env("WHATSAPP_NUMBER_2", default="")
WHATSAPP_LABEL_1 = env("WHATSAPP_LABEL_1", default="Leslie")
WHATSAPP_LABEL_2 = env("WHATSAPP_LABEL_2", default="Bolivar")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
