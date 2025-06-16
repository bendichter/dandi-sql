"""
WSGI config for dandi_sql project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

# Use platform settings for production deployments, default settings otherwise
default_settings = 'dandi_sql.settings_platform' if os.environ.get('DATABASE_URL') else 'dandi_sql.settings'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', default_settings)

application = get_wsgi_application()
