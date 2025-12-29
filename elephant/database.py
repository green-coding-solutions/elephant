import logging
import os
from contextlib import contextmanager
from typing import Iterator, Generator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from elephant.config import config

logger = logging.getLogger(__name__)


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
      provider          TEXT              NULL
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
    """

    with db_connection() as conn, conn.cursor() as cur:
        logger.info("Initializing TimescaleDB schema at %s ...", conn.info.host)
        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        cur.execute(ddl)
        conn.commit()
        logger.info("Database ready.")


def fetch_latest(conn: Connection, region: str) -> dict[str, dict]:
    """Return the most recent row for each provider at a region."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (provider) provider, time, carbon_intensity
            FROM carbon
            WHERE region = %s
            ORDER BY provider, time DESC;
            """,
            (region,),
        )
        rows = cur.fetchall()

    return {
        row["provider"]: {
            "time": row["time"],
            "carbon_intensity": row["carbon_intensity"],
        }
        for row in rows
        if row.get("provider") is not None
    }


def fetch_between(conn: Connection, region: str, start_time, end_time) -> list[dict]:
    """Return rows within the requested window for a region."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT time, carbon_intensity, provider
            FROM carbon
            WHERE region = %s
              AND time >= %s
              AND time <= %s
            ORDER BY time;
            """,
            (region, start_time, end_time),
        )
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
