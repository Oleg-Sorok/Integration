#!/bin/sh
set -eu
# For existing pgdata: Compose one-shot service uses a temporary .pgpass in tmpfs.
export PGPASSFILE=/tmp/pgpass
printf 'postgres:5432:*:orders:%s\n' "$(cat /run/secrets/db_password)" > "$PGPASSFILE"
chmod 600 "$PGPASSFILE"
exists="$(psql -h postgres -U orders -d orders -tAc "SELECT 1 FROM pg_database WHERE datname = 'mlflow'" | tr -d '[:space:]')"
if [ "$exists" != '1' ]; then
  echo 'Provisioning MLflow database on existing PostgreSQL volume'
  createdb -h postgres -U orders mlflow
fi
rm -f "$PGPASSFILE"
echo 'MLflow database is present'
