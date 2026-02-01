@echo off
REM Railway deployment preparation script

echo Preparing PaymeBot for Railway deployment...

REM Run Django checks
echo Running Django system checks...
python manage.py check --deploy

REM Collect static files
echo Collecting static files...
python manage.py collectstatic --noinput

echo PaymeBot is ready for Railway deployment!
echo Next steps:
echo 1. Commit all changes: git add . ^&^& git commit -m "Prepare for Railway deployment"
echo 2. Push to GitHub: git push origin main
echo 3. Connect your repo to Railway and deploy