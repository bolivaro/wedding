#!/bin/bash
set -e

echo "=== MEDIA_ROOT CONTENT ==="
ls -la /app || true
ls -la /app/media || true

mkdir -p /app/staticfiles
mkdir -p /app/media

python manage.py collectstatic --noinput

echo "=== MEDIA AFTER COLLECTSTATIC ==="
ls -la /app/media || true
find /app/media -maxdepth 3 -type f | head -50 || true

exec gunicorn lesbon.wsgi:application --bind 0.0.0.0:$PORT