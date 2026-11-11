#!/bin/sh
set -eu

python - <<'PY'
import models.db
from models.db._common import Base
from params.database import engine

Base.metadata.create_all(bind=engine, checkfirst=True)
PY

exec uvicorn application:get_app --factory