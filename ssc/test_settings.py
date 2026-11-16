from .settings import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SSCEGOV_INTEGRATION_API_KEY = "test-api-key"
SSCEGOV_INTEGRATION_HMAC_SECRET = "test-hmac-secret"
