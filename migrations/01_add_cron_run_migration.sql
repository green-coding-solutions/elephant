CREATE TABLE IF NOT EXISTS last_cron_run (
  source    TEXT PRIMARY KEY,
  last_run  TIMESTAMPTZ NOT NULL
);
