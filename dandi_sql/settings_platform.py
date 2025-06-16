"""
Platform deployment settings for Railway, Render, etc.
"""

from .settings import *
import os
import dj_database_url
from decouple import config

# Platform deployment settings
DEBUG = config('DEBUG', default=False, cast=bool)

# Allow platform domains
ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    '.railway.app',
    '.onrender.com',
    '.herokuapp.com',
    '.pythonanywhere.com',
]

# Add your custom domain
custom_domain = config('CUSTOM_DOMAIN', default='')
if custom_domain:
    ALLOWED_HOSTS.append(custom_domain)

# Database configuration for platforms
DATABASE_URL = config('DATABASE_URL', default='')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    # Fallback to default settings if DATABASE_URL not provided
    pass

# Static files for platform deployment
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# Add WhiteNoise for static file serving
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)

# Logging for platforms - console only, no file logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,  # Disable any existing loggers
    'formatters': {
        'simple': {
            'format': '[{levelname}] {asctime} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'dandisets': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'gunicorn': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
