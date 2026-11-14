#!/bin/bash
# Runs after the image's 000_install_timescaledb.sh, which installs timescaledb into
# "postgres" and "template1" as well as POSTGRES_DB. Elephant only needs it in POSTGRES_DB,
# and every extra copy runs its own scheduler and telemetry job and never gets upgraded.
# Like all init scripts, this only runs on an empty data volume.
set -euo pipefail

dbs=$(psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tA \
  -c "SELECT datname FROM pg_database WHERE datallowconn;")

for db in ${dbs}; do
  [ "${db}" = "${POSTGRES_DB}" ] && continue
  psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${db}" -c "DROP EXTENSION IF EXISTS timescaledb;"
done
