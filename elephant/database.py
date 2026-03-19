import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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


def fetch_latest(conn: Connection, region: str) -> list[dict]:
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

        rows = cur.fetchall()

    if rows:
        return rows

    return _fetch_latest_yearly(conn, region)


def fetch_between(
    conn: Connection,
    region: str,
    start_time: datetime,
    end_time: datetime,
    provider: str | None = None,
) -> list[dict]:
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
        rows = cur.fetchall()

    if rows:
        return rows

    return _fetch_between_yearly(conn, region, start_time, end_time, provider)


def fetch_regions(conn: Connection) -> list[str]:
    """Return a list of distinct regions with data."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT region
            FROM (
                SELECT DISTINCT region
                FROM carbon
                WHERE region IS NOT NULL

                UNION

                SELECT DISTINCT region
                FROM carbon_yearly
                WHERE region IS NOT NULL
            ) AS regions
            WHERE region IS NOT NULL
            ORDER BY region;
            """
        )
        rows = cur.fetchall()
    return [row["region"] for row in rows if row.get("region")]


def fetch_yearly_regions(conn: Connection) -> set[str]:
    """Return regions that have yearly fallback data."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT region
            FROM carbon_yearly
            WHERE region IS NOT NULL
            ORDER BY region;
            """
        )
        rows = cur.fetchall()
    return {row["region"] for row in rows if row.get("region")}


def _fetch_latest_yearly(conn: Connection, region: str) -> list[dict]:
    """Return the latest available yearly fallback entry for a region."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT year, provider, carbon_intensity::double precision, estimation
            FROM carbon_yearly
            WHERE region = %s
            ORDER BY year DESC, provider ASC;
            """,
            (region,),
        )
        rows = cur.fetchall()

    if not rows:
        return []

    latest_year = rows[0]["year"]
    latest_time = _yearly_latest_timestamp(latest_year)

    return [
        {
            "provider": row["provider"],
            "time": latest_time,
            "carbon_intensity": row["carbon_intensity"],
            "estimation": row["estimation"],
        }
        for row in rows
        if row["year"] == latest_year
    ]


def _fetch_between_yearly(
    conn: Connection,
    region: str,
    start_time: datetime,
    end_time: datetime,
    provider: str | None = None,
) -> list[dict]:
    """Expand yearly fallback values into synthetic 15-minute rows for a requested range."""
    yearly_rows = _fetch_yearly_rows(conn, region, start_time.year, end_time.year, provider)
    if not yearly_rows:
        return []

    records_by_year: dict[int, list[dict]] = {}
    for row in yearly_rows:
        records_by_year.setdefault(row["year"], []).append(row)

    current = _align_to_quarter_hour(start_time)
    results: list[dict] = []

    while current <= end_time:
        for row in records_by_year.get(current.year, []):
            results.append(
                {
                    "time": current,
                    "carbon_intensity": row["carbon_intensity"],
                    "provider": row["provider"],
                    "estimation": row["estimation"],
                }
            )
        current += timedelta(minutes=15)

    return results


def _fetch_yearly_rows(
    conn: Connection,
    region: str,
    start_year: int,
    end_year: int,
    provider: str | None = None,
) -> list[dict]:
    """Fetch yearly fallback rows for a region and year range."""
    query = """
        SELECT year, carbon_intensity::double precision, provider, estimation
        FROM carbon_yearly
        WHERE region = %s
          AND year >= %s
          AND year <= %s
    """
    params = [region, start_year, end_year]

    if provider:
        query += "  AND provider = %s\n"
        params.append(provider.lower())

    query += "ORDER BY year ASC, provider ASC;"

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def _align_to_quarter_hour(dt: datetime) -> datetime:
    """Round a datetime up to the next 15-minute boundary."""
    if dt.second == 0 and dt.microsecond == 0 and dt.minute % 15 == 0:
        return dt

    minute_offset = 15 - (dt.minute % 15)
    aligned = dt + timedelta(minutes=minute_offset)
    return aligned.replace(second=0, microsecond=0)


def _yearly_latest_timestamp(year: int) -> datetime:
    """Return a representative timestamp for the latest yearly fallback value."""
    now = datetime.now(timezone.utc)
    year_end = datetime(year, 12, 31, 23, 45, tzinfo=timezone.utc)
    return min(now, year_end)


if __name__ == "__main__":
    init_db()
