#!/usr/bin/env bash
# Render build step: install deps, collect static assets, apply migrations.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Free tier has no Shell, so seed the doctor account here. seed_doctor is
# idempotent (get_or_create), so running it every deploy is safe.
python manage.py seed_doctor
