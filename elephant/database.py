import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Generator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from elephant.config import config

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _database_url() -> str:
    return os.getenv("DATABASE_URL", config.database.url)


@contextmanager
def db_connection() -> Iterator[Connection]:
    """Yield a psycopg connection and ensure it is closed."""
    conn = psycopg.connect(_database_url())
    try:
        yield conn
    finally:
        conn.close()


def connection_dependency() -> Generator[Connection, None, None]:
    """FastAPI dependency that yields a DB connection."""
    with db_connection() as conn:
        yield conn


def init_db() -> None:
    """Create TimescaleDB extension and the carbon hypertable."""
    ddl = """
    CREATE TABLE IF NOT EXISTS carbon (
      time              TIMESTAMPTZ       NOT NULL,
      region            TEXT              NOT NULL,
      carbon_intensity  DOUBLE PRECISION  NULL,
      provider          TEXT              NULL,
      estimation        BOOLEAN           NOT NULL DEFAULT FALSE
    )
    WITH (
      timescaledb.hypertable,
      timescaledb.partition_column='time',
      timescaledb.segmentby='provider'
    );

    CREATE TABLE IF NOT EXISTS simulation_runs (
      simulation_id     UUID PRIMARY KEY,
      grid_values       DOUBLE PRECISION[] NOT NULL,
      calls             INTEGER[] NULL,
      current_index     INTEGER NOT NULL DEFAULT 0,
      created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS simulation_calls (
      id                BIGSERIAL PRIMARY KEY,
      simulation_id     UUID NOT NULL REFERENCES simulation_runs(simulation_id) ON DELETE CASCADE,
      called_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      carbon_intensity  DOUBLE PRECISION NOT NULL,
      idx               INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS last_cron_run (
      source    TEXT PRIMARY KEY,
      last_run  TIMESTAMPTZ NOT NULL
    );
    """

    with db_connection() as conn, conn.cursor() as cur:
        logger.info("Initializing TimescaleDB schema at %s ...", conn.info.host)
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        cur.execute(ddl)
        conn.commit()
    run_migrations()
    logger.info("Database ready.")


def run_migrations() -> None:
    """Run unapplied SQL migrations from the migrations directory."""
    if not MIGRATIONS_DIR.exists():
        logger.info("No migrations directory found at %s. Skipping.", MIGRATIONS_DIR)
        return

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        logger.info("No migration files found in %s. Skipping.", MIGRATIONS_DIR)
        return

    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              filename    TEXT PRIMARY KEY,
              applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )

        cur.execute("SELECT filename FROM schema_migrations;")
        applied = {row[0] for row in cur.fetchall()}

        for migration_file in migration_files:
            if migration_file.name in applied:
                continue

            logger.info("Applying migration %s", migration_file.name)
            sql = migration_file.read_text(encoding="utf-8").strip()
            if sql:
                cur.execute(sql)

            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s);", (migration_file.name,))

        conn.commit()


def fetch_latest(conn: Connection, region: str) -> dict[str, dict]:
    """Return the most recent row for each provider at a region."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (provider) provider, time, carbon_intensity::double precision, estimation
            FROM carbon
            WHERE region = %s
            ORDER BY provider, time DESC;
            """,
            (region,)
        )

        return cur.fetchall()


def fetch_between(conn: Connection, region: str, start_time, end_time, provider = None) -> list[dict]:
    """Return rows within the requested window for a region, optionally filtered by provider."""

    query = """
        SELECT time, carbon_intensity::double precision, provider, estimation
        FROM carbon
        WHERE region = %s
          AND time >= %s
          AND time <= %s
    """
    params = [region, start_time, end_time]

    if provider:
        query += "  AND provider = %s\n"
        params.append(provider.lower())

    query += "ORDER BY time;"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()

def fetch_regions(conn: Connection) -> list[str]:
    """Return a list of distinct regions with data."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT region
            FROM carbon
            WHERE region IS NOT NULL
            ORDER BY region;
            """
        )
        rows = cur.fetchall()
    return [row["region"] for row in rows if row.get("region")]


if __name__ == "__main__":
    init_db()
