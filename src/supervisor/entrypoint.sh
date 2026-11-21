#!/bin/sh
set -eu

# Lancement de supervisord
exec /usr/bin/supervisord \
    -n \
    -c /opt/alertiny/supervisor/supervisord.conf