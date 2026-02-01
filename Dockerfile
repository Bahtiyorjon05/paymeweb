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
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . /app/

# Create logs directory
RUN mkdir -p /var/log/paymebot /var/www/paymebot/static

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port (Railway will set PORT environment variable)
EXPOSE $PORT

# Run the application
CMD ["gunicorn", "paymebot.wsgi:application", "--bind", "0.0.0.0:$PORT", "--workers", "1"]