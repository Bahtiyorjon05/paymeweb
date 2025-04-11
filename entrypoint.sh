#!/bin/bash

echo "Starting Postgres setup..."
export PATH="/usr/lib/postgresql/15/bin:$PATH"

# Start Postgres
su - postgres -c "pg_ctl -D $PGDATA -l /tmp/postgres.log start" || \
    { echo "pg_ctl failed, initializing DB..."; su - postgres -c "initdb -D $PGDATA" && su - postgres -c "pg_ctl -D $PGDATA -l /tmp/postgres.log start"; } || \
    { echo "Init or start failed! Check /tmp/postgres.log"; exit 1; }

# Wait for Postgres
echo "Checking if Postgres is ready..."
until su - postgres -c "psql -c 'SELECT 1'" 2>/tmp/psql_error.log; do
    echo "Waiting for PostgreSQL to start..."
    cat /tmp/psql_error.log
    sleep 1
done

# Set up database and user
echo "Setting up database..."
su - postgres -c "psql -c \"CREATE DATABASE ${DB_NAME}\" || true"
su - postgres -c "psql -c \"CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}'\" || true"
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER}\" || true"

# Run migrations and create superuser
echo "Running migrations..."
python3 manage.py migrate
echo "Creating superuser..."
python3 manage.py createsuperuser --noinput --username ${ADMIN_USERNAME} --email admin@example.com || true

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 paymebot.wsgi:application