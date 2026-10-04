#!/usr/bin/env bash
# Build step for the backend on Render (and any similar host).
# Render runs this once per deploy, before starting the server.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# The shared rate-limit counters live in a database table (DJANGO_CACHE=db).
python manage.py createcachetable