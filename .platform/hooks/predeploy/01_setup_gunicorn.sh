#!/bin/bash
# Install dependencies and configure Gunicorn
source /var/app/venv/*/bin/activate
pip install uvicorn==0.30.6 gunicorn==23.0.0
cat << GUNICORN_CONF > /var/app/staging/gunicorn.conf.py
bind = '0.0.0.0:8000'
workers = 2
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 60
keepalive = 2
GUNICORN_CONF
GUNICORN_CONF
chmod +x .platform/hooks/predeploy/01_setup_gunicorn.sh