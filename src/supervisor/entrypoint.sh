#!/bin/sh
set -eu

exec /usr/bin/supervisord \
    -n \
    -c /opt/alertiny/supervisor/supervisord.conf