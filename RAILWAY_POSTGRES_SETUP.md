# How to Add PostgreSQL Database on Railway

## Step-by-Step Instructions

### 1. Access Your Railway Project
1. Go to [railway.app](https://railway.app)
2. Sign in to your account
3. Navigate to your DANDI SQL project

### 2. Add PostgreSQL Service
1. **In your project dashboard**, click the **"+ New Service"** button
2. **Select "Database"** from the dropdown menu
3. **Choose "PostgreSQL"** from the database options
4. Railway will automatically provision a PostgreSQL instance

### 3. Verify Database Creation
After a few moments, you should see:
- A new **PostgreSQL service** appears in your project
- The service shows a **green "Active"** status
- Railway automatically generates database credentials

### 4. Check Auto-Generated Environment Variables
Railway automatically creates these environment variables for your web service:
- `DATABASE_URL` - Complete connection string
- `POSTGRES_HOST` - Database host
- `POSTGRES_PORT` - Database port (usually 5432)
- `POSTGRES_DB` - Database name
- `POSTGRES_USER` - Database username  
- `POSTGRES_PASSWORD` - Database password

### 5. Verify Variables Are Available
1. Go to your **web service** (not the database service)
2. Click on the **"Variables"** tab
3. You should see `DATABASE_URL` listed there
4. If not visible, the database might not be connected to your web service

### 6. Connect Database to Web Service (if needed)
If the `DATABASE_URL` isn't automatically available in your web service:

1. In your web service, go to **"Settings"**
2. Scroll to **"Service Connections"**
3. Click **"Connect"** next to your PostgreSQL service
4. This will make the database variables available to your web service

## 🔍 Troubleshooting

### Issue: Database service not showing up
**Solution**: 
1. Refresh your browser
2. Wait 1-2 minutes for provisioning
3. Check Railway status page for any outages

### Issue: DATABASE_URL not available in web service
**Solution**:
1. Ensure database is connected to web service (Step 6 above)
2. Redeploy your web service after connecting
3. Check the Variables tab again

### Issue: Database connection still failing
**Solution**:
1. Verify `DATABASE_URL` format looks like: 
   ```
   postgresql://username:password@host:port/database
   ```
2. Check that your code uses `settings_platform.py` (already configured)
3. Redeploy after confirming database connection

## ✅ What Happens Next

Once PostgreSQL is properly set up:

1. **Railway automatically provides `DATABASE_URL`**
2. **Your Django app will use this instead of localhost**
3. **Migrations will run successfully during deployment**
4. **Your app should start without database connection errors**

## 🚀 Deploy After Database Setup

After adding PostgreSQL:

1. **Commit your recent changes**:
   ```bash
   git add .
   git commit -m "Add Railway deployment configuration"
   git push origin main
   ```

2. **Railway will auto-deploy** and should now work correctly

3. **Watch the build logs** for successful migration output

## 📱 Visual Guide

Your Railway dashboard should look like this after setup:

```
┌─────────────────┐    ┌─────────────────┐
│   Web Service   │────│  PostgreSQL     │
│   (Your Django  │    │   Database      │
│    Application) │    │                 │
└─────────────────┘    └─────────────────┘
```

Both services should show **green "Active"** status.

## 🎯 Expected Result

After following these steps, your deployment should succeed with logs showing:
```
Operations to perform:
  Apply all migrations: admin, auth, contenttypes, dandisets, sessions
Running migrations:
  Applying contenttypes.0001_initial... OK
  Applying auth.0001_initial... OK
  [... more migrations ...]

119 static files copied to '/app/staticfiles'.
```

The PostgreSQL connection error should be completely resolved! 🎉
