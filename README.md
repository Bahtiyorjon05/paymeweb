"# PaymeBot - Secure Digital Payment Platform

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Environment Setup](#environment-setup)
- [Database Setup](#database-setup)
- [Running the Application](#running-the-application)
- [Deployment](#deployment)
- [Security](#security)
- [API Documentation](#api-documentation)
- [Troubleshooting](#troubleshooting)

## Overview
PaymeBot is a comprehensive digital payment platform built with Django that enables secure peer-to-peer money transfers, card management, and currency conversion. The platform features a complete ecosystem for financial transactions with robust security measures and administrative oversight.

## Features
- User registration and authentication
- Multi-currency support with real-time conversion
- Card management system
- Peer-to-peer money transfers
- Contact management
- Request money functionality
- Transaction history and reporting
- Two-factor authentication
- Administrative dashboard
- Complaint and support system
- RESTful API endpoints

## Prerequisites
- Python 3.8+
- PostgreSQL (for production)
- Redis (for caching)
- Docker and Docker Compose (optional, for containerized deployment)

## Installation

### 1. Clone the repository
```bash
git clone <repository-url>
cd paymebot
```

### 2. Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Environment Setup

### 1. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```

### 2. Configure the environment variables:
```env
SECRET_KEY=your-super-secret-key-here-make-it-long-and-random
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD_HASH=your_hashed_password_here
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your_app_specific_password_here
DATABASE_URL=postgresql://user:password@localhost:5432/paymebot_db
REDIS_URL=redis://localhost:6379/0
```

**Note**: To generate a password hash, use Django's management command:
```bash
python manage.py shell -c "from django.contrib.auth.hashers import make_password; print(make_password('your_password'))"
```

## Database Setup

### For Development (SQLite):
The application will automatically create an SQLite database.

### For Production (PostgreSQL):
1. Install and start PostgreSQL
2. Create a database and user:
```sql
CREATE DATABASE paymebot_db;
CREATE USER paymebot_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE paymebot_db TO paymebot_user;
```

### Run migrations:
```bash
python manage.py makemigrations
python manage.py migrate
```

### Create a superuser:
```bash
python manage.py createsuperuser
```

## Running the Application

### Development:
```bash
python manage.py runserver
```

### Production (using Gunicorn):
```bash
gunicorn paymebot.wsgi:application --config gunicorn_config.py
```

## Deployment

### Option 1: Railway Deployment (Recommended)
1. Push your code to GitHub
2. Connect your GitHub repository to Railway
3. Add the following environment variables in Railway dashboard:
   - `SECRET_KEY`: Generate a strong secret key
   - `DEBUG`: False
   - `ADMIN_USERNAME`: Your admin username
   - `ADMIN_PASSWORD_HASH`: Hashed password for admin
   - `EMAIL_HOST_USER`: Your email address
   - `EMAIL_HOST_PASSWORD`: Your email app password
4. Add PostgreSQL and Redis as addons in Railway
5. Deploy!

### Option 2: Docker Deployment
1. Build and run with Docker Compose:
```bash
docker-compose up --build
```

### Option 3: Manual Deployment
1. Run the deployment script:
```bash
chmod +x deploy.sh
./deploy.sh
```

2. Start the application:
```bash
gunicorn --config gunicorn_config.py paymebot.wsgi:application
```

## Security

### Important Security Measures Implemented:
- SSL/HTTPS enforcement in production
- Secure session cookies
- CSRF protection
- XSS prevention
- SQL injection prevention
- Rate limiting for API endpoints
- Input validation and sanitization
- Secure password hashing
- Two-factor authentication support

### Security Best Practices:
- Never commit sensitive information to version control
- Use strong, unique passwords
- Regularly update dependencies
- Monitor logs for suspicious activity
- Implement proper access controls

## API Documentation
API documentation is available at `/swagger/` endpoint when the application is running.

## Troubleshooting

### Common Issues:

1. **Database Connection Issues**:
   - Ensure PostgreSQL is running
   - Verify database credentials in `.env`
   - Check that the database user has proper permissions

2. **Email Configuration**:
   - For Gmail, enable "App Passwords" and use that instead of your regular password
   - Ensure your email provider allows SMTP connections

3. **Static Files Not Loading**:
   - Run `python manage.py collectstatic`
   - Ensure proper permissions on static files directory

4. **Redis Connection Issues**:
   - Ensure Redis server is running
   - Verify Redis URL in environment variables

### Getting Help:
- Check the logs in the `logs/` directory
- Enable DEBUG mode temporarily to see detailed error messages
- Consult the Django documentation for framework-specific issues

## Maintenance

### Regular Maintenance Tasks:
- Backup database regularly
- Rotate API keys and passwords periodically
- Update dependencies regularly
- Monitor application logs
- Clean up old log files

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License
This project is licensed under the MIT License - see the LICENSE file for details." 
