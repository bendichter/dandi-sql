# DANDI SQL Management Commands

Quick reference for managing the deployed DANDI SQL application.

## Service Management

```bash
# Check service status
sudo systemctl status dandi-sql

# Start/stop/restart service
sudo systemctl start dandi-sql
sudo systemctl stop dandi-sql
sudo systemctl restart dandi-sql

# View real-time logs
sudo journalctl -u dandi-sql -f

# View recent logs
sudo journalctl -u dandi-sql --since "1 hour ago"
```

## DANDI Synchronization

```bash
# Navigate to application directory
cd /opt/dandi-sql

# Manual incremental sync
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --verbose

# Force full sync (use sparingly)
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --force-full-sync --verbose

# Sync specific dandiset
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --dandiset-id DANDI:000003 --verbose

# Dry run (see what would be synced)
sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --dry-run --verbose
```

## Data Management and Cleanup

```bash
# Navigate to application directory
cd /opt/dandi-sql

# Deduplicate contributors by ORCID/ROR ID
sudo -u www-data venv/bin/python manage.py deduplicate_contributors --verbose

# Dry run to see what would be deduplicated
sudo -u www-data venv/bin/python manage.py deduplicate_contributors --dry-run --verbose

# Deduplicate only specific contributor types
sudo -u www-data venv/bin/python manage.py deduplicate_contributors --schema-key Person --verbose
sudo -u www-data venv/bin/python manage.py deduplicate_contributors --schema-key Organization --verbose

# Normalize anatomy identifiers
sudo -u www-data venv/bin/python manage.py normalize_anatomy_ids --verbose

# Deduplicate anatomy entries
sudo -u www-data venv/bin/python manage.py deduplicate_anatomy --verbose
```

## Database Management

```bash
# Django migrations
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py migrate --settings=dandi_sql.settings_production

# Create superuser
sudo -u www-data venv/bin/python manage.py createsuperuser --settings=dandi_sql.settings_production

# Django shell
sudo -u www-data venv/bin/python manage.py shell --settings=dandi_sql.settings_production

# Database backup
sudo -u postgres pg_dump dandi_db > backup_$(date +%Y%m%d_%H%M%S).sql

# View database size
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('dandi_db'));"
```

## Static Files and Cache

```bash
# Collect static files
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py collectstatic --noinput --settings=dandi_sql.settings_production

# Clear Django cache (if using cache)
sudo -u www-data venv/bin/python manage.py shell --settings=dandi_sql.settings_production -c "from django.core.cache import cache; cache.clear()"
```

## Nginx Management

```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx (without downtime)
sudo systemctl reload nginx

# Restart Nginx
sudo systemctl restart nginx

# View Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

## Log Management

```bash
# View sync logs
sudo tail -f /var/log/dandi-sql/sync.log

# View Django application logs
sudo tail -f /var/log/dandi-sql/django.log

# View Gunicorn logs
sudo journalctl -u dandi-sql | grep gunicorn

# Check disk space for logs
sudo du -sh /var/log/dandi-sql/
```

## Cron Job Management

```bash
# View current cron jobs
sudo cat /etc/cron.d/dandi-sync

# Check cron service status
sudo systemctl status cron

# View cron logs
sudo grep CRON /var/log/syslog | tail -10

# Manually test cron command
cd /opt/dandi-sql && sudo -u www-data venv/bin/python manage.py sync_dandi_incremental --verbose --no-progress
```

## Performance Monitoring

```bash
# Check system resources
top
htop
free -h
df -h

# Check database connections
sudo -u postgres psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname='dandi_db';"

# Check Gunicorn processes
ps aux | grep gunicorn

# Monitor network connections
sudo netstat -tlnp | grep :8000
```

## Troubleshooting

```bash
# Check if all services are running
sudo systemctl status nginx dandi-sql postgresql

# Check port availability
sudo netstat -tlnp | grep -E ':(80|443|8000|5432)'

# Test database connection
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py dbshell --settings=dandi_sql.settings_production

# Check environment variables
cd /opt/dandi-sql
sudo -u www-data cat .env

# Validate Django settings
cd /opt/dandi-sql
sudo -u www-data venv/bin/python manage.py check --settings=dandi_sql.settings_production
```

## Updates and Maintenance

```bash
# Update application code (git pull)
cd /opt/dandi-sql
sudo -u www-data git pull origin main

# Update Python dependencies
sudo -u www-data venv/bin/pip install -r requirements_production.txt --upgrade

# After code updates
sudo -u www-data venv/bin/python manage.py migrate --settings=dandi_sql.settings_production
sudo -u www-data venv/bin/python manage.py collectstatic --noinput --settings=dandi_sql.settings_production
sudo systemctl restart dandi-sql

# System updates
sudo apt update && sudo apt upgrade -y
sudo systemctl restart dandi-sql nginx
```

## Security

```bash
# Check for failed login attempts
sudo grep "Failed password" /var/log/auth.log | tail -10

# View SSL certificate status (if using Let's Encrypt)
sudo certbot certificates

# Renew SSL certificates
sudo certbot renew --dry-run

# Check firewall status
sudo ufw status
```

## Quick Health Check

```bash
#!/bin/bash
# Health check script

echo "=== DANDI SQL Health Check ==="
echo "Service Status:"
sudo systemctl is-active dandi-sql nginx postgresql

echo -e "\nDisk Space:"
df -h /opt/dandi-sql /var/log

echo -e "\nMemory Usage:"
free -h

echo -e "\nDatabase Size:"
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('dandi_db'));" 2>/dev/null || echo "Database check failed"

echo -e "\nLast Sync:"
sudo tail -5 /var/log/dandi-sql/sync.log 2>/dev/null || echo "No sync logs found"

echo -e "\nHTTP Response:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost/ || echo "HTTP check failed"
```

Save this as a script and run periodically for monitoring.
