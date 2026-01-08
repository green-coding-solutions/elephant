"""Simulation utilities for staged carbon intensity responses."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable, List, Sequence

from psycopg import Connection
from psycopg.rows import dict_row


class SimulationNotFoundError(KeyError):
    """Raised when a simulation_id does not exist."""


class SimulationExhaustedError(IndexError):
    """Raised when attempting to advance beyond available values."""


SimulationValueInput = float | tuple[float, int | None]


class SimulationStore:
    """Simulation runs persisted in the database."""

    def __init__(self, time_provider: Callable[[], datetime] | None = None) -> None:
        self._time_provider = time_provider or (lambda: datetime.now(timezone.utc))

    def _require_conn(self, conn: Connection | None) -> Connection:
        if conn is None:
            raise ValueError("Database connection is required")
        return conn

    def _normalize_calls(self, calls: Sequence[int | None] | None, length: int) -> list[int | None]:
        normalized = [None] * length
        if calls is None:
            return normalized

        for idx, value in enumerate(list(calls)[:length]):
            normalized[idx] = None if value is None else int(value)

        return normalized

    def _split_values_and_calls(self, values: List[SimulationValueInput]) -> tuple[list[float], list[int | None]]:
        grid_values: list[float] = []
        call_counts: list[int | None] = []

        for entry in values:
            if  isinstance(entry, (list, tuple)):
                if len(entry) != 2:
                    raise ValueError("Each tuple value must contain (value, calls)")
                value, calls = entry
                call_counts.append(None if calls is None else int(calls))
            else:
                value = entry
                call_counts.append(None)

            grid_values.append(float(value))

        return grid_values, call_counts

    def _fetch_run(self, simulation_id: str, conn: Connection, for_update: bool = False) -> dict:
        """Return grid values, current index, and call configuration for a simulation."""
        conn = self._require_conn(conn)
        sql = """
            SELECT grid_values, current_index, calls
            FROM simulation_runs
            WHERE simulation_id = %s
        """
        if for_update:
            sql += " FOR UPDATE"

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (simulation_id,))
            row = cur.fetchone()

        if not row:
            raise SimulationNotFoundError(f"Simulation '{simulation_id}' not found")

        values = [float(v) for v in row["grid_values"]]
        calls = self._normalize_calls(row.get("calls"), len(values))

        return {
            "values": values,
            "calls": calls,
            "current_index": int(row["current_index"]),
        }

    def create(self, values: List[SimulationValueInput], conn: Connection | None = None) -> str:
        """Create a new simulation and return its ID."""
        conn = self._require_conn(conn)
        now = self._time_provider()

        if not values:
            raise ValueError("At least one grid intensity value is required")

        grid_values, call_counts = self._split_values_and_calls(values)
        simulation_id = str(uuid.uuid4())

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO simulation_runs (simulation_id, grid_values, calls, current_index)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (simulation_id, grid_values, call_counts, 0),
                )
                cur.execute(
                    """
                    INSERT INTO simulation_calls (simulation_id, called_at, carbon_intensity, idx)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (simulation_id, now, grid_values[0], 0),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return simulation_id

    def current_value(self, simulation_id: str, conn: Connection | None = None) -> float:
        """Return the current value for a simulation and auto-advance based on call thresholds."""
        conn = self._require_conn(conn)

        try:
            run = self._fetch_run(simulation_id, conn, for_update=True)

            values = run["values"]
            calls = list(run["calls"])
            current_index = run["current_index"]

            if current_index >= len(values):
                return values[current_index]

            current_value = values[current_index]
            remaining_calls = calls[current_index]

            should_advance = False

            if remaining_calls is not None and remaining_calls >= 0:
                new_remaining = remaining_calls - 1
                calls[current_index] = new_remaining

                if new_remaining <= 0 and (current_index + 1) < len(values):
                    should_advance = True
                elif new_remaining <= 0:
                    calls[current_index] = -1

            new_index = current_index + 1 if should_advance else current_index

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE simulation_runs
                    SET current_index = %s, calls = %s
                    WHERE simulation_id = %s;
                    """,
                    (new_index, calls, simulation_id),
                )

                if should_advance:
                    next_value = values[new_index]
                    cur.execute(
                        """
                        INSERT INTO simulation_calls (simulation_id, called_at, carbon_intensity, idx)
                        VALUES (%s, %s, %s, %s);
                        """,
                        (simulation_id, self._time_provider(), next_value, new_index),
                    )

            conn.commit()
            return current_value
        except Exception:
            conn.rollback()
            raise

    def advance(self, simulation_id: str, conn: Connection | None = None) -> float:
        """Advance a simulation to its next value and record the call."""
        conn = self._require_conn(conn)
        now = self._time_provider()

        try:
            run = self._fetch_run(simulation_id, conn, for_update=True)

            next_index = run["current_index"] + 1
            if next_index >= len(run["values"]):
                return run["values"][next_index - 1]

            next_value = run["values"][next_index]

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE simulation_runs
                    SET current_index = %s, calls = %s
                    WHERE simulation_id = %s;
                    """,
                    (next_index, run["calls"], simulation_id),
                )
                cur.execute(
                    """
                    INSERT INTO simulation_calls (simulation_id, called_at, carbon_intensity, idx)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (simulation_id, now, next_value, next_index),
                )

            conn.commit()
            return next_value
        except Exception:
            conn.rollback()
            raise

    def stats(self, simulation_id: str, conn: Connection | None = None) -> dict:
        """Return diagnostic information for a simulation."""
        conn = self._require_conn(conn)
        run = self._fetch_run(simulation_id, conn)

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT called_at, carbon_intensity, idx
                FROM simulation_calls
                WHERE simulation_id = %s
                ORDER BY called_at;
                """,
                (simulation_id,),
            )
            calls = cur.fetchall()

        return [
            {
                'provider': simulation_id,
                'time': call["called_at"].isoformat(),
                'carbon_intensity': float(call["carbon_intensity"]),
                'estimation': True,
             }
             for call in calls
        ]



    def reset(self, conn: Connection | None = None) -> None:
        """Clear simulation tables (intended for tests)."""
        if conn is None:
            return

        try:
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE simulation_calls;")
                cur.execute("TRUNCATE TABLE simulation_runs;")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


simulation_store = SimulationStore()
