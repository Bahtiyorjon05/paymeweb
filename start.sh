#!/bin/bash

# Run Django migrations
echo "Running Django migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start the application with Gunicorn
echo "Starting PaymeBot application..."
exec gunicorn paymebot.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120