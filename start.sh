#!/bin/bash
set -e

python manage.py collectstatic --noinput

exec gunicorn lesbon.wsgi:application --bind 0.0.0.0:$PORT
