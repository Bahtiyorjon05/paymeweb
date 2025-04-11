# Use the official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Collect static files during build
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run migrations and create/update superuser at runtime
CMD ["sh", "-c", "python manage.py migrate && echo \"from core.models import User; user = User.objects.filter(username='admin1').first(); (user.set_password('$DJANGO_SUPERUSER_PASSWORD') if user else User.objects.create_superuser(username='admin1', email='admin@example.com', password='$DJANGO_SUPERUSER_PASSWORD')); user.is_staff = True if user else User.objects.create_superuser(username='admin1', email='admin@example.com', password='$DJANGO_SUPERUSER_PASSWORD', is_staff=True, is_superuser=True); user.is_superuser = True if user else None; user.save() if user else None\" | python manage.py shell && gunicorn --bind 0.0.0.0:8000 paymebot.wsgi:application"]