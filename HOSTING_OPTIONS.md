# DANDI SQL Hosting Options

This guide compares different hosting platforms for the DANDI SQL Django application, from free to affordable options.

## Platform Comparison

### 1. Railway 🌟 **RECOMMENDED**

**Pros:**
- Excellent Django support
- Built-in PostgreSQL
- Cron job support
- Git-based deployment
- Generous free tier ($5/month credit)
- Easy environment variable management

**Cons:**
- Newer platform (less established)
- Limited free tier hours

**Cost:** 
- Free: $5/month in credits
- Paid: ~$5-20/month depending on usage

**Setup Process:**
1. Connect GitHub repository
2. Railway auto-detects Django
3. Add PostgreSQL service
4. Configure environment variables
5. Deploy automatically

### 2. Render

**Pros:**
- Great Django documentation
- Managed PostgreSQL
- Built-in cron jobs
- Free tier available
- Auto-deploy from Git
- SSL certificates included

**Cons:**
- Free tier has limitations (sleeps after 15min inactivity)
- Database persistence limited on free tier

**Cost:**
- Free: Limited (sleeps when inactive)
- Paid: $7/month for web service + $7/month for PostgreSQL

### 3. Heroku

**Pros:**
- Mature platform with excellent Django support
- Many add-ons available
- Great documentation
- Easy scaling

**Cons:**
- No longer has free tier
- More expensive than alternatives
- Dyno sleeping on cheaper plans

**Cost:**
- Basic: $7/month for app + $9/month for PostgreSQL
- Total: ~$16/month minimum

### 4. PythonAnywhere

**Pros:**
- Python-focused platform
- Good Django support
- Scheduled tasks included
- Always-on tasks for background processes

**Cons:**
- Interface feels older
- Less modern deployment workflow
- Limited database size on cheaper plans

**Cost:**
- Beginner: $5/month (limited)
- Hacker: $12/month (recommended for this app)

### 5. DigitalOcean App Platform

**Pros:**
- Managed platform with VPS-like control
- Good performance
- Built-in database options
- Reasonable pricing

**Cons:**
- No free tier
- Still requires some DevOps knowledge

**Cost:**
- Basic: $5/month for app + $15/month for managed database
- Total: ~$20/month

### 6. Traditional VPS (Our Script)

**Pros:**
- Full control
- Best performance per dollar
- Can run multiple applications
- Educational value

**Cons:**
- Requires server management
- Security responsibility
- Setup complexity

**Cost:**
- DigitalOcean/Linode: $4-6/month
- AWS EC2 t2.micro: Free tier eligible
- Hetzner: €3.29/month (~$3.50)

## Why Not Vercel?

Vercel is primarily designed for frontend applications and serverless functions. While it supports Python, it has significant limitations for Django applications:

- ❌ No persistent storage
- ❌ No PostgreSQL support
- ❌ No cron job support
- ❌ Limited execution time (10s for Hobby, 300s for Pro)
- ❌ Django ORM not optimized for serverless
- ❌ No built-in session management

## Recommended Deployment Path

### Option 1: Railway (Easiest)

1. **Setup Repository**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin <your-github-repo>
   git push -u origin main
   ```

2. **Create Railway Project**
   - Go to [railway.app](https://railway.app)
   - Connect GitHub account
   - Select your repository
   - Railway auto-detects Django

3. **Add PostgreSQL**
   - In Railway dashboard, click "New Service"
   - Select "PostgreSQL"
   - Railway automatically creates DATABASE_URL

4. **Configure Environment Variables**
   ```bash
   DEBUG=False
   SECRET_KEY=your-secret-key-here
   ALLOWED_HOSTS=your-app.railway.app
   DATABASE_URL=postgresql://... # Auto-provided by Railway
   ```

5. **Create railway.toml**
   ```toml
   [build]
   builder = "nixpacks"
   
   [deploy]
   healthcheckPath = "/"
   healthcheckTimeout = 300
   restartPolicyType = "always"
   
   [[services]]
   name = "web"
   
   [services.web]
   startCommand = "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn dandi_sql.wsgi:application"
   
   [[services]]
   name = "worker"
   
   [services.worker]
   startCommand = "python manage.py sync_dandi_incremental --no-progress"
   cronSchedule = "0 2 * * *"  # Daily at 2 AM
   ```

### Option 2: Render (Balanced)

1. **Create render.yaml**
   ```yaml
   services:
     - type: web
       name: dandi-sql
       env: python
       buildCommand: "pip install -r requirements_production.txt"
       startCommand: "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn dandi_sql.wsgi:application"
       envVars:
         - key: DEBUG
           value: false
         - key: SECRET_KEY
           generateValue: true
         - key: DATABASE_URL
           fromDatabase:
             name: dandi-db
             property: connectionString
   
   databases:
     - name: dandi-db
       databaseName: dandi_db
       user: dandi_user
   
   jobs:
     - type: cron
       name: dandi-sync
       env: python
       buildCommand: "pip install -r requirements_production.txt"
       startCommand: "python manage.py sync_dandi_incremental --no-progress"
       schedule: "0 2 * * *"
   ```

### Option 3: Traditional VPS (Our Script)

Use the deployment script we created:

```bash
# On your VPS
git clone <your-repo>
cd dandi-sql
sudo ./deploy.sh
```

## Configuration for Platform Deployment

### Update Django Settings

<write_to_file>
<path>dandi_sql/settings_platform.py</path>
<content>
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
        'default': dj_database_url.parse(DATABASE_URL)
    }

# Static files for platform deployment
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# Add WhiteNoise for static file serving
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)

# Logging for platforms
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
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
    },
}
