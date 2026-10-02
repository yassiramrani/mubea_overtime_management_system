"""Deterministic isolated test defaults; production settings remain unchanged."""
from .settings import *  # noqa: F401,F403

SECURE_SSL_REDIRECT = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
# CI can select PostgreSQL explicitly; local tests default to memory-only SQLite.
if os.getenv('TEST_DB_ENGINE') != 'postgresql':
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
