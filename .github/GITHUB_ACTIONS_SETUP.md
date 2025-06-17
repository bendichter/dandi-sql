# GitHub Actions Setup for DANDI Sync

Since Railway doesn't provide built-in cron jobs, we use GitHub Actions to run scheduled DANDI synchronization.

## Setup Instructions

### 1. Configure GitHub Secrets

In your GitHub repository, go to **Settings** → **Secrets and variables** → **Actions** and add these repository secrets:

#### Required Secrets:

- **`DATABASE_URL`**: Your Railway PostgreSQL connection string
  - Get this from Railway dashboard → Your Project → PostgreSQL service → Variables tab
  - Format: `postgresql://username:password@host:port/database`

- **`SECRET_KEY`**: Your Django secret key
  - Generate a new one: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
  - Should be the same one used in your Railway deployment

### 2. How to Get DATABASE_URL from Railway

1. Go to your Railway project dashboard
2. Click on your PostgreSQL service
3. Go to the **Variables** tab
4. Copy the `DATABASE_URL` value
5. Add it as a GitHub secret

### 3. Verify the Setup

Once secrets are configured:

1. **Manual Test**: Go to **Actions** tab → **Sync DANDI Data** → **Run workflow**
2. **Check Logs**: Monitor the workflow execution logs
3. **Verify Database**: Check your Railway app admin interface to see if sync completed

## Schedule Details

- **Automatic**: Runs daily at 2:00 AM UTC
- **Manual**: Can be triggered anytime from GitHub Actions tab
- **Options**: Can force full sync by selecting the option when manually triggering

## Monitoring

### Success Indicators:
- Green checkmark in GitHub Actions
- Updated `last_modified_by_sync` fields in your Railway database
- New SyncTracker records in Django admin

### Troubleshooting:
- **Red X in Actions**: Check the logs for specific errors
- **Database Connection Errors**: Verify `DATABASE_URL` secret is correct
- **Django Errors**: Verify `SECRET_KEY` secret matches your Railway deployment

## Cost Considerations

- GitHub Actions provides 2,000 free minutes per month for public repos
- DANDI sync typically takes 5-15 minutes depending on updates
- Daily syncs should easily fit within free tier limits

## Alternative Schedules

To change the sync schedule, edit `.github/workflows/sync-dandi.yml`:

```yaml
# Current: Daily at 2 AM UTC
- cron: '0 2 * * *'

# Alternatives:
- cron: '0 */6 * * *'    # Every 6 hours  
- cron: '0 8,20 * * *'   # Twice daily (8 AM, 8 PM UTC)
- cron: '0 2 * * 0'      # Weekly on Sundays
```

## Security Notes

- Secrets are encrypted and only accessible to workflow runs
- Never commit sensitive values to the repository
- Use different secrets for production vs development if needed
