# Railway Cron Service Configuration

## Setup Instructions

1. **Create New Cron Service in Railway Dashboard:**
   - Go to your Railway project
   - Click "New Service" → "Cron Job"
   - Connect the same GitHub repository

2. **Environment Variables:**
   Copy these from your main web service:
   ```
   DEBUG=False
   SECRET_KEY=your-secret-key-here
   ALLOWED_HOSTS=.railway.app
   ```
   
   Note: `DATABASE_URL` is automatically provided by Railway

3. **Cron Configuration:**
   - **Command:** `python manage.py sync_dandi_incremental --settings=dandi_sql.settings_platform --no-progress --verbose`
   - **Schedule:** `0 2 * * *` (daily at 2:00 AM UTC)

## Alternative Schedules

- **Every 6 hours:** `0 */6 * * *`
- **Twice daily:** `0 2,14 * * *` (2 AM and 2 PM)
- **Weekly:** `0 2 * * 0` (Sundays at 2 AM)

## Monitoring

- Check Railway dashboard for cron execution logs
- Use the SyncTracker admin interface to monitor sync status
- Set up alerts if needed through Railway notifications

## Troubleshooting

If the cron job fails:

1. **Check Environment Variables:** Ensure all required variables are set
2. **Verify Database Connection:** Ensure PostgreSQL service is connected
3. **Check Logs:** View cron service logs in Railway dashboard
4. **Test Manually:** Run the command manually in Railway's web service to debug

## Cost Considerations

- Railway cron services are typically free within usage limits
- Monitor resource usage in Railway dashboard
- DANDI sync should complete within free tier limits
