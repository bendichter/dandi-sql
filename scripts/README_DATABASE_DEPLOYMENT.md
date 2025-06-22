# Database Deployment Scripts for Railway

This directory contains scripts to export your local database and upload it to your Railway deployment, replacing the existing database.

## Scripts Available

### 1. `deploy_database_django.sh` (Recommended)

Uses Django fixtures for data export/import. This is the **recommended approach** for Railway deployments.

**Advantages:**
- More reliable for Railway deployments
- Handles Django-specific data properly
- Smaller file sizes than SQL dumps
- Better error handling for foreign keys
- Works well with Railway's constraints

**Usage:**
```bash
./scripts/deploy_database_django.sh
```

### 2. `deploy_database.sh` (Alternative)

Uses PostgreSQL's pg_dump/pg_restore for direct database export/import.

**Advantages:**
- Complete database structure and data
- Preserves all PostgreSQL-specific features
- Good for complex database schemas

**Usage:**
```bash
# Basic usage
./scripts/deploy_database.sh

# Create backup of Railway database first
./scripts/deploy_database.sh --backup-first
```

## Prerequisites

Before running any script, ensure you have:

1. **Railway CLI installed:**
   ```bash
   npm install -g @railway/cli
   ```

2. **Railway project linked:**
   ```bash
   railway login
   railway link
   ```

3. **Git repository configured** (for Django method)

4. **PostgreSQL client tools** (for SQL method):
   - `pg_dump`
   - `psql`

5. **Environment variables set** in `.env` file:
   ```
   DB_NAME=your_local_db
   DB_USER=your_user
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   ```

## Quick Start Guide

### Step 1: Choose Your Method

**For most users, start with the Django method:**
```bash
./scripts/deploy_database_django.sh
```

### Step 2: Monitor the Process

The script will:
1. Export your local data
2. Create backups
3. Upload to Railway via git
4. Load data into Railway database
5. Verify the transfer
6. Clean up temporary files

### Step 3: Verify Your Deployment

After completion:
```bash
# Open your Railway app
railway open

# Check data counts
railway run python manage.py shell -c "
from dandisets.models import Dandiset, Asset
print(f'Dandisets: {Dandiset.objects.count()}')
print(f'Assets: {Asset.objects.count()}')
"
```

## Troubleshooting

### Common Issues

1. **Railway CLI not linked:**
   ```bash
   railway link
   # Select your project
   ```

2. **Git repository issues:**
   ```bash
   git status
   git add .
   git commit -m "Initial commit"
   ```

3. **Large data sets failing:**
   - Use the Django method (smaller files)
   - Check Railway's file size limits

4. **Authentication issues:**
   ```bash
   railway login
   railway whoami
   ```

### Error Recovery

If a script fails midway:

1. **Check Railway logs:**
   ```bash
   railway logs --tail
   ```

2. **Restore from backup:**
   ```bash
   # Backups are stored in database_backups/
   ls database_backups/
   
   # Use the Django loaddata command to restore
   railway run python manage.py loaddata path/to/backup.json
   ```

3. **Manual verification:**
   ```bash
   railway run python manage.py migrate
   railway run python manage.py collectstatic --noinput
   ```

## What Each Script Does

### Django Method (`deploy_database_django.sh`)

1. **Export Phase:**
   - Creates Django fixtures from local database
   - Exports data in JSON format
   - Creates app-specific backups

2. **Upload Phase:**
   - Commits fixture files to git
   - Pushes to Railway for deployment
   - Waits for Railway deployment

3. **Import Phase:**
   - Clears existing Railway data
   - Loads fixture data
   - Handles errors with fallback methods

4. **Verification Phase:**
   - Counts records in Railway database
   - Runs pending migrations
   - Shows sample data

### SQL Method (`deploy_database.sh`)

1. **Export Phase:**
   - Uses `pg_dump` to create SQL dump
   - Creates both SQL and Django fixtures
   - Compresses backup files

2. **Upload Phase:**
   - Temporarily adds files to git
   - Pushes to Railway
   - Connects to Railway PostgreSQL

3. **Import Phase:**
   - Restores using `psql` commands
   - Falls back to Django fixtures if needed
   - Handles Railway connection specifics

4. **Verification Phase:**
   - Verifies data counts
   - Cleans up temporary files

## File Structure

After running, you'll have:

```
database_backups/
├── dandi_data_20250621_200101.tar.gz     # Compressed backup
├── railway_backup_20250621_200101.json   # Railway backup (if created)
└── [timestamp files...]                  # Temporary files (cleaned up)
```

## Security Notes

- Backup files may contain sensitive data
- Files are temporarily added to git during upload
- Scripts clean up temporary files automatically
- Consider adding `database_backups/` to `.gitignore`

## Best Practices

1. **Always test first:**
   ```bash
   # Test with a small dataset
   railway run python manage.py dumpdata dandisets.dandiset --output test.json
   ```

2. **Create backups:**
   ```bash
   ./scripts/deploy_database.sh --backup-first
   ```

3. **Monitor deployment:**
   ```bash
   railway logs --tail
   ```

4. **Verify after deployment:**
   - Check your web application
   - Test key functionality
   - Verify data integrity

## Getting Help

If you encounter issues:

1. **Check the script output** - errors are color-coded
2. **Review Railway logs** - `railway logs`
3. **Verify prerequisites** - all tools installed and configured
4. **Use help flags** - `./script.sh --help`

## Advanced Usage

### Custom Data Selection

For Django method, you can modify the export commands in the script:

```bash
# Export specific apps only
python manage.py dumpdata dandisets --output custom_export.json

# Exclude specific models
python manage.py dumpdata --exclude dandisets.largemodel --output smaller_export.json
```

### Performance Optimization

For large datasets:

1. **Split exports by app:**
   ```bash
   python manage.py dumpdata dandisets.dandiset --output dandisets_only.json
   python manage.py dumpdata dandisets.asset --output assets_only.json
   ```

2. **Use compression:**
   ```bash
   python manage.py dumpdata --output - | gzip > export.json.gz
   ```

3. **Batch processing:**
   - Modify scripts to process data in smaller chunks
   - Use `--batch-size` options where available

This documentation should help you successfully deploy your database to Railway while understanding the process and handling any issues that arise.
