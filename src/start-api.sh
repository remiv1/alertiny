#!/bin/sh
set -eu

python - <<'PY'
import models.db
from params.database import initialize_database

initialize_database()
PY

exec uvicorn application:get_app --factory