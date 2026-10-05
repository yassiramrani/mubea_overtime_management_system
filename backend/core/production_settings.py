"""Fail-closed deployment configuration. Supply a dedicated environment file."""
from .settings import *  # noqa: F401,F403

if DEBUG:
    raise ImproperlyConfigured('Production requires DEBUG=False.')
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('Production requires a strong, unique SECRET_KEY (at least 50 characters).')
if DB_ENGINE != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('Production requires PostgreSQL.')
if not os.getenv('REDIS_URL'):
    raise ImproperlyConfigured('Production requires REDIS_URL for shared login throttling.')
if EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend':
    raise ImproperlyConfigured('Production requires a configured SMTP email backend.')
# A timer installed before sender verification must not consume outbox attempts.
NOTIFICATIONS_DELIVERY_ENABLED = notification_env_flag('NOTIFICATIONS_DELIVERY_ENABLED', False)
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Production requires explicit ALLOWED_HOSTS.')
if not PUBLIC_BASE_URL.startswith('https://'):
    raise ImproperlyConfigured('Production requires an HTTPS PUBLIC_BASE_URL.')
if AUTH_TOKEN_TTL_SECONDS <= 0 or AUTH_TOKEN_TTL_SECONDS > 86400:
    raise ImproperlyConfigured('AUTH_TOKEN_TTL_SECONDS must be between 1 and 86400.')

DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
# Retain the project's HTTPS-only subdomain policy for production.
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
REST_FRAMEWORK = {**REST_FRAMEWORK, 'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer']}
