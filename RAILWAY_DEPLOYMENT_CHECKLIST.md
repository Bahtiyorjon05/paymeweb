# Railway Deployment Checklist

## Before Connecting to Railway

### 1. Environment Variables to Set in Railway:
- `SECRET_KEY` - Generate a strong secret key (use `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`)
- `DEBUG` - Set to `False`
- `ADMIN_USERNAME` - Your admin username
- `ADMIN_PASSWORD_HASH` - Hashed password (use Django's make_password function)
- `EMAIL_HOST_USER` - Your email address for sending emails
- `EMAIL_HOST_PASSWORD` - App password for your email provider
- `ALLOWED_HOSTS` - Will be set automatically by Railway

### 2. Add-ons to Create in Railway:
- PostgreSQL database
- Redis (for caching and sessions)

### 3. Build Configuration:
- Builder: Dockerfile
- No additional build commands needed

### 4. Run Configuration:
- The Procfile will be automatically detected
- Port will be automatically assigned by Railway

## Steps to Deploy:

1. Commit all changes to your GitHub repository
2. Go to Railway.app and sign in
3. Click "New Project"
4. Select "Deploy from GitHub"
5. Choose your repository
6. Railway will automatically detect it's a Docker project
7. Add the environment variables listed above
8. Add PostgreSQL and Redis as add-ons
9. Click "Deploy"

## Post-Deployment:

1. Run initial setup:
   - Access the Railway console for your project
   - Run: `python manage.py migrate`
   - Run: `python manage.py createsuperuser` (or use the setup management command)

2. Your app will be accessible at: `https://[your-project-name].up.railway.app`

## Troubleshooting:

- Check logs in Railway dashboard if deployment fails
- Ensure all required environment variables are set
- Verify database connection works
- Check that static files are served correctly

## Admin Access:
- Admin panel: `https://[your-project-name].up.railway.app/admin/`
- Use the username/password you set during createsuperuser or via environment variables