# DANDI SQL Deployment Guide

This guide provides comprehensive instructions for deploying the DANDI SQL Django application to a production server with automated daily DANDI synchronization.

## Quick Start

For a fully automated deployment, run:

```bash
sudo ./deploy.sh
```

For development deployment with SQLite:

```bash
sudo ./deploy.sh --dev
```

## Manual Deployment Steps

### Prerequisites

- Ubuntu/Debian server (tested on Ubuntu 20.04+)
- Root or sudo access
- Internet connectivity
- At least 4GB RAM recommended
- 50GB+ disk space for DANDI data

### 1. System Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv python3-dev \
                    postgresql postgresql-contrib nginx git curl \
                    build-essential libpq-dev supervisor cron logrotate
```

### 2. Database Setup

#### PostgreSQL (Production)

```bash
# Start PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql
```

```sql
CREATE DATABASE dandi_db;
CREATE USER dandi_user WITH PASSWORD 'your_secure_password';
ALTER ROLE dandi_user SET client_encoding TO 'utf8';
ALTER ROLE dandi_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE dandi_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE dandi_db TO dandi_user;
\q
```

### 3. Application Setup

```bash
# Create application directory
sudo mkdir -p /opt/dandi-sql
sudo mkdir -p /var/log/dandi-sql
sudo mkdir -p /var/run/dandi-sql

# Create service user (if not exists)
sudo useradd --system --home /opt/dandi-sql --shell /bin/bash www-data || true

# Copy application files
sudo rsync -av ./ /opt/dandi-sql/
sudo chown -R www-data:www-data /opt/dandi-sql
sudo chown -R www-data:www-data /var/log/dandi-sql
sudo chown -R www-data:www-data /var/run/dandi-sql
```

### 4. Python Environment

```bash
# Create virtual environment
sudo -u www-data python3 -m venv /opt/dandi-sql/venv

# Install dependencies
sudo -u www-data /opt/dandi-sql/venv/bin/pip install --upgrade pip
sudo -u www-data /opt/dandi-sql/venv/bin/pip install -r /opt/dandi-sql/requirements_production.txt
```

### 5. Django Configuration

Create `/opt/dandi-sql/.env`:

```bash
# Production environment
DEBUG=False
SECRET_KEY=your_django_secret_key_here
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com

# Database
DB_NAME=dandi_db
DB_USER=dandi_user
DB_PASSWORD=your_secure_password
DB_HOST=localhost
DB_PORT=5432

# Optional: Email configuration
EMAIL_HOST=smtp.your-provider.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@domain.com
EMAIL_HOST_PASSWORD=your-email-password
EMAIL_USE_TLS=True
ADMIN_EMAIL=admin@your-domain.com
```

Set proper permissions:

```bash
sudo chown www-data:www-data /opt/dandi-sql/.env
sudo chmod 600 /opt/dandi-sql/.env
```

### 6. Django Setup

```bash
cd /opt/dandi-sql

# Run migrations
sudo -u www-data venv/bin/python manage.py migrate --settings=dandi_sql.settings_production

# Collect static files
sudo -u www-data venv/bin/python manage.py collectstatic --noinput --settings=dandi_sql.settings_production

# Create superuser
sudo -u www-data venv/bin/python manage.py createsuperuser --settings=dandi_sql.settings_production
```

### 7. Systemd Service

```bash
# Copy service file
sudo cp /opt/dandi-sql/deploy/dandi-sql.service /etc/systemd/system/

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable dandi-sql
sudo systemctl start dandi-sql
```

### 8. Nginx Configuration

```bash
# Copy Nginx config
sudo cp /opt/dandi-sql/deploy/nginx-dandi-sql.conf /etc/nginx/sites-available/dandi-sql

# Enable site
sudo ln -sf /etc/nginx/sites-available/dandi-sql /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and restart Nginx
sudo nginx -t
sudo systemctl restart nginx
```

### 9. Cron Job Setup

```bash
# Copy cron configuration
sudo cp /opt/dandi-sql/deploy/dandi-sync-cron /etc/cron.d/dandi-sync
sudo chmod 644 /etc/cron.d/dandi-sync
sudo systemctl restart cron
```

## Post-Deployment Configuration

### 1. Update Domain Configuration

Edit `/etc/nginx/sites-available/dandi-sql` and replace `your-domain.com` with your actual domain.

### 2. SSL/HTTPS Setup (Recommended)

Install Certbot for Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 3. Firewall Configuration

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 4. Initial Data Load

Load initial DANDI data:

```bash
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --verbose
```

## Monitoring and Maintenance

### Service Management

```bash
# Check service status
sudo systemctl status dandi-sql

# View logs
sudo journalctl -u dandi-sql -f

# Restart service
sudo systemctl restart dandi-sql
```

### Manual Sync

```bash
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --verbose
```

### Log Files

- Application logs: `/var/log/dandi-sql/`
- Nginx logs: `/var/log/nginx/`
- Sync logs: `/var/log/dandi-sql/sync.log`

### Database Backup

```bash
# Create backup
sudo -u postgres pg_dump dandi_db > dandi_backup_$(date +%Y%m%d).sql

# Restore backup
sudo -u postgres psql dandi_db < dandi_backup_YYYYMMDD.sql
```

## Daily Sync Schedule

The application is configured to automatically sync with DANDI daily at 2:00 AM. The cron job:

- Runs incremental sync daily
- Logs output to `/var/log/dandi-sql/sync.log`
- Automatically cleans old logs monthly

## Troubleshooting

### Common Issues

1. **Service won't start**: Check logs with `journalctl -u dandi-sql`
2. **Database connection errors**: Verify database credentials in `.env`
3. **Static files not loading**: Run `collectstatic` command
4. **Sync failures**: Check DANDI API connectivity and sync logs

### Performance Tuning

1. **Database optimization**: Consider connection pooling for high traffic
2. **Worker processes**: Adjust Gunicorn workers based on CPU cores
3. **Rate limiting**: Configure Nginx rate limits based on usage patterns

### Scaling Considerations

For high-traffic deployments:

1. Use a dedicated database server
2. Implement Redis for caching
3. Use a CDN for static files
4. Consider load balancing with multiple app servers

## Security Considerations

1. Change default database passwords
2. Generate secure Django SECRET_KEY
3. Configure proper firewall rules
4. Enable HTTPS with valid SSL certificates
5. Regular security updates
6. Monitor logs for suspicious activity

## API Documentation

The deployed application provides several API endpoints:

- Web interface: `http://your-domain.com/`
- Admin interface: `http://your-domain.com/admin/`
- API documentation: Available in the repository's API_SEARCH_DOCUMENTATION.md

## Support

For issues or questions:

1. Check the logs first
2. Review this documentation
3. Check the Django application logs
4. Verify DANDI API connectivity
