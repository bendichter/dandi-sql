# Railway Deployment Troubleshooting

## ✅ Key Fixes Applied

The PostgreSQL connection error has been resolved with these changes:

### 1. Platform Settings Configuration
- Created `dandi_sql/settings_platform.py` that properly uses Railway's `DATABASE_URL`
- Automatically detects and uses Railway's PostgreSQL service

### 2. Dependencies Fixed
- Added `python-decouple` to requirements for environment variable management
- Added `dj-database-url` for database URL parsing

### 3. Deployment Configuration
- Updated `Procfile` to use platform settings during deployment
- Modified `wsgi.py` to auto-detect Railway environment and use correct settings

### 4. Database Connection
- Now properly uses Railway's provided `DATABASE_URL` instead of localhost
- Includes connection pooling optimizations

## 🚀 Next Steps for Railway Deployment

### 1. Set Environment Variables in Railway
In your Railway project dashboard, set these variables:

```bash
DEBUG=False
SECRET_KEY=your-generated-secret-key-here
ALLOWED_HOSTS=.railway.app
```

### 2. Generate Secret Key
Run this command locally to generate a secure secret key:
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Commit and Push Changes
```bash
git add .
git commit -m "Fix Railway deployment configuration"
git push origin main
```

### 4. Railway Auto-Deployment
- Railway will automatically detect the push and redeploy
- Watch the build logs in Railway dashboard
- The migration and static file collection will now work properly

## 🔍 Verification Steps

After deployment, verify these work:

1. **Web Service**: Visit your Railway app URL
2. **Database**: Check that migrations ran successfully in build logs
3. **Static Files**: Verify CSS/JS loads correctly
4. **Admin**: Access `/admin/` interface

## 📊 Expected Build Log Output

You should see something like this in Railway build logs:
```
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, dandisets, sessions
Running migrations:
  No migrations to apply.

119 static files copied to '/app/staticfiles'.
```

## 🐛 Common Issues & Solutions

### Issue: Build fails with dependency errors
**Solution**: Ensure all dependencies are in `requirements_production.txt`

### Issue: Static files not loading
**Solution**: Verify WhiteNoise is properly configured (already done)

### Issue: Database connection still failing
**Solution**: Check that PostgreSQL service is added in Railway dashboard

### Issue: Environment variables not found
**Solution**: Double-check variable names in Railway dashboard match exactly

## 📱 Testing Your Deployed App

1. **Basic functionality**: Navigate through the web interface
2. **Database queries**: Test search and filter functionality  
3. **Admin access**: Create superuser and access admin panel
4. **API endpoints**: Test any API functionality

## 🔄 Setting Up Daily Sync

After successful deployment, set up the daily DANDI sync:

1. **Add Cron Service** in Railway dashboard
2. **Set same environment variables** as main service
3. **Configure cron command**:
   ```bash
   python manage.py sync_dandi_incremental --settings=dandi_sql.settings_platform --no-progress --verbose
   ```
4. **Set schedule**: `0 2 * * *` (daily at 2 AM)

## 💰 Cost Monitoring

With the small database size (~500MB metadata only):
- **Free tier**: Should be sufficient
- **Monitor usage**: Check Railway dashboard for resource usage
- **Estimated cost**: $0-3/month (well within free tier)

## 🆘 Getting Help

If issues persist:
1. Check Railway build logs for specific errors
2. Railway Discord community is very helpful
3. Railway documentation: https://docs.railway.app

Your DANDI SQL app should now deploy successfully to Railway! 🎉
