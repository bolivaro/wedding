#!/bin/bash
set -e

mkdir -p /app/staticfiles
mkdir -p /app/media

python manage.py collectstatic --noinput

exec gunicorn lesbon.wsgi:application --bind 0.0.0.0:$PORT