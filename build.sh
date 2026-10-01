#!/usr/bin/env bash
set -o errexit

python -m pip install -r requirements.txt

python src/manage.py migrate --noinput

python src/manage.py collectstatic --noinput