# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        build-essential \
        libpq-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project (including the newly created paymebot folder)
COPY . /app/

# Create logs directory
RUN mkdir -p /var/log/paymebot /var/www/paymebot/static

# Expose port (Railway will set PORT environment variable)
EXPOSE $PORT

# Create start script that handles migrations and static files at runtime
RUN echo '#!/bin/bash\npython manage.py migrate --noinput\npython manage.py collectstatic --noinput --clear\nexec gunicorn paymebot.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --timeout 120' > /app/start_server.sh
RUN chmod +x /app/start_server.sh

# Run the application
CMD ["/app/start_server.sh"]