import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Generator, AsyncGenerator

import psycopg
from psycopg import Connection, AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from elephant.config import config

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_pool: AsyncConnectionPool | None = None


def _database_url() -> str:
    return os.getenv("DATABASE_URL", config.database.url)


# --- Sync connection (used by cron process and init scripts) ---

@contextmanager
def db_connection() -> Iterator[Connection]:
    """Yield a psycopg connection and ensure it is closed."""
    conn = psycopg.connect(_database_url())
    try:
        yield conn
    finally:
        conn.close()


def connection_dependency_sync() -> Generator[Connection, None, None]:
    """Sync FastAPI dependency (kept for cron-triggered paths)."""
    with db_connection() as conn:
        yield conn


# --- Async connection pool (used by the web server) ---

async def create_pool(min_size: int = 2, max_size: int = 10) -> None:
    global _pool
    pool = AsyncConnectionPool(
        conninfo=_database_url(),
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    await pool.open(wait=True)
    _pool = pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def connection_dependency() -> AsyncGenerator[AsyncConnection, None]:
    """FastAPI async dependency that yields a pooled DB connection."""
    assert _pool is not None, "Connection pool not initialized"
    async with _pool.connection() as conn:
        yield conn


# --- Query helpers (async, used by web server endpoints) ---

async def fetch_latest(conn: AsyncConnection, region: str) -> list[dict]:
    """Return the most recent row for each provider at a region."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT DISTINCT ON (provider) provider, time, carbon_intensity::double precision, estimation
            FROM carbon
            WHERE region = %s
            ORDER BY provider, time DESC;
            """,
            (region,),
        )
        return await cur.fetchall()


async def fetch_between(
    conn: AsyncConnection,
    region: str,
    start_time,
    end_time,
    provider=None,
) -> list[dict]:
    """Return rows within the requested window for a region, optionally filtered by provider."""
    query = """
        SELECT time, carbon_intensity::double precision, provider, estimation
        FROM carbon
        WHERE region = %s
          AND time >= %s
          AND time <= %s
    """
    params: list = [region, start_time, end_time]

    if provider:
        query += "  AND provider = %s\n"
        params.append(provider.lower())

    query += "ORDER BY time;"

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, params)
        return await cur.fetchall()


async def fetch_regions(conn: AsyncConnection) -> list[str]:
    """Return a list of distinct regions with data."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT DISTINCT region
            FROM carbon
            WHERE region IS NOT NULL
            ORDER BY region;
            """
        )
        rows = await cur.fetchall()
    return [row["region"] for row in rows if row.get("region")]


# --- Schema init (sync, run once at container startup) ---

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


if __name__ == "__main__":
    init_db()
