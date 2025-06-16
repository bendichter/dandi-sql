# Uploading Local Database Data to Railway

This guide shows you how to transfer your local database data to your Railway-deployed Django app.

## Method 1: Django Fixtures (Recommended for Railway)

### Step 1: Export Local Data
```bash
# Export all data from local database
python manage.py dumpdata --indent 2 > data_backup.json

# Or export specific apps only
python manage.py dumpdata dandisets --indent 2 > dandisets_data.json

# Export excluding certain apps (if needed)
python manage.py dumpdata --exclude auth.permission --exclude contenttypes --indent 2 > data_backup.json
```

### Step 2: Upload Fixture File to Railway
Since Railway doesn't have direct file upload, you'll commit the fixture file:

```bash
# Add fixture file to your repository
git add data_backup.json
git commit -m "Add local database fixture for migration"
git push origin main
```

### Step 3: Load Data on Railway
Railway will redeploy. Then use Railway CLI to run the management command:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and connect to your project
railway login
railway link

# Run the load command
railway run python manage.py load_local_data --fixture-file data_backup.json
```

## Method 2: Direct Database Transfer via Railway CLI

### Step 1: Install Railway CLI & Connect
```bash
npm install -g @railway/cli
railway login
railway link  # Link to your project
```

### Step 2: Get Railway Database Connection
```bash
# Connect to Railway's PostgreSQL
railway connect postgres
# This opens a psql session to Railway's database
```

### Step 3: Transfer Data
Option A - Direct SQL dump/restore:
```bash
# In a new terminal, export local data
pg_dump -h localhost -U bdichter -d dandi_db --data-only --inserts > local_data.sql

# Copy file content and paste in Railway psql session
# Or use \i command in psql:
\i /path/to/local_data.sql
```

Option B - Using Railway's database URL:
```bash
# Get the DATABASE_URL from Railway
railway variables

# Use the URL to import directly
pg_dump -h localhost -U bdichter -d dandi_db | psql "your-railway-database-url"
```

## Method 3: Using DANDI Sync Command (Recommended for DANDI Data)

If your local data came from DANDI originally, use the built-in sync command:

```bash
# On Railway, run the incremental sync
railway run python manage.py sync_dandi_incremental --verbose

# For specific dandisets
railway run python manage.py sync_dandi_incremental --dandiset-id DANDI:000003 --verbose

# Force full sync (if needed)
railway run python manage.py sync_dandi_incremental --force-full-sync --verbose
```

## Method 4: Custom Data Upload Script

Create a custom management command for complex data transfer:

```python
# dandisets/management/commands/upload_local_data.py
import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from dandisets.models import Dandiset, Asset  # Your models

class Command(BaseCommand):
    help = 'Upload specific data from local backup'
    
    def add_arguments(self, parser):
        parser.add_argument('--json-file', type=str, required=True)
        parser.add_argument('--batch-size', type=int, default=1000)
    
    def handle(self, *args, **options):
        with open(options['json_file'], 'r') as f:
            data = json.load(f)
        
        # Process data in batches
        self.stdout.write(f'Processing {len(data)} records...')
        
        with transaction.atomic():
            # Your custom data processing logic here
            pass
```

## Method 5: Environment-Specific Migration

For large datasets, create environment-specific migrations:

```bash
# Create a data migration
python manage.py makemigrations --empty dandisets

# Edit the migration file to include your data loading logic
# Then deploy and run migrations on Railway
```

## Important Notes for Railway

1. **File Size Limits**: Railway has deployment size limits, so large fixture files might need to be split

2. **Memory Considerations**: Large data imports might hit Railway's memory limits. Use batch processing:
   ```python
   # In your management command
   def handle_large_dataset(self, data):
       batch_size = 1000
       for i in range(0, len(data), batch_size):
           batch = data[i:i + batch_size]
           # Process batch
   ```

3. **Database Connections**: Railway's PostgreSQL has connection limits. Use connection pooling.

4. **Deployment Timing**: Run data uploads after deployment is complete to avoid timeouts.

## Troubleshooting

### Common Issues:

1. **Foreign Key Constraints**:
   ```bash
   # Load data in order of dependencies
   python manage.py loaddata auth_data.json
   python manage.py loaddata dandisets_data.json
   ```

2. **Memory Errors**:
   ```bash
   # Split large fixtures
   python manage.py dumpdata dandisets.dandiset --indent 2 > dandisets.json
   python manage.py dumpdata dandisets.asset --indent 2 > assets.json
   ```

3. **Encoding Issues**:
   ```bash
   # Export with proper encoding
   python manage.py dumpdata --indent 2 --output data_backup.json
   ```

## Recommended Workflow

1. **Test locally first**:
   ```bash
   # Create a test database and load fixtures
   python manage.py migrate --settings=test_settings
   python manage.py loaddata data_backup.json --settings=test_settings
   ```

2. **Use staging environment** (if available)

3. **Backup Railway data** before importing:
   ```bash
   railway run python manage.py dumpdata > railway_backup.json
   ```

4. **Monitor the import**:
   ```bash
   railway logs --tail
   ```

## Quick Start for DANDI SQL

For your specific DANDI SQL project:

```bash
# 1. Export local dandisets data
python manage.py dumpdata dandisets --indent 2 > dandisets_backup.json

# 2. Commit and push
git add dandisets_backup.json
git commit -m "Add local dandisets for Railway migration"
git push origin main

# 3. Load on Railway
railway run python manage.py load_local_data --fixture-file dandisets_backup.json

# 4. Verify data
railway run python manage.py shell --command="from dandisets.models import Dandiset; print(f'Dandisets: {Dandiset.objects.count()}')"
```

This approach is most reliable for Railway deployments since it uses Django's built-in serialization and doesn't require direct database connections.
