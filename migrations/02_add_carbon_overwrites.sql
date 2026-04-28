CREATE TABLE IF NOT EXISTS carbon_overwrites (
  time            TIMESTAMPTZ       NOT NULL,
  region          TEXT              NOT NULL,
  provider        TEXT              NOT NULL,
  old_value       DOUBLE PRECISION  NULL,
  new_value       DOUBLE PRECISION  NULL,
  old_estimation  BOOLEAN           NULL,
  new_estimation  BOOLEAN           NULL,
  overwritten_at  TIMESTAMPTZ       NOT NULL DEFAULT NOW()
)
WITH (
  timescaledb.hypertable,
  timescaledb.partition_column='overwritten_at',
  timescaledb.segmentby='provider'
);
