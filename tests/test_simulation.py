"""Tests for simulation endpoints and state transitions."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from elephant import app as app_module
from elephant.app import (
    SimulationCreateRequest,
    advance_simulation,
    create_simulation,
    get_simulation_carbon,
    simulation_stats,
)


class FakeCursor:
    """Minimal cursor stub to emulate psycopg for simulation tests."""

    def __init__(self, conn, row_factory=None):
        self.conn = conn
        self.row_factory = row_factory
        self._results = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        params = params or ()

        if "insert into simulation_runs" in normalized:
            if len(params) == 4:
                sim_id, values, calls, current_index = params
            else:
                sim_id, values, current_index = params
                calls = [None] * len(values)

            self.conn.sim_runs[sim_id] = {
                "grid_values": list(values),
                "calls": list(calls) if calls is not None else [None] * len(values),
                "current_index": current_index,
            }
            self._results = []
        elif "select grid_values" in normalized:
            sim_id = params[0]
            run = self.conn.sim_runs.get(sim_id)
            self._results = [run] if run else []
        elif "update simulation_runs" in normalized:
            if len(params) == 3:
                new_idx, calls, sim_id = params
            else:
                new_idx, sim_id = params
                calls = self.conn.sim_runs.get(sim_id, {}).get("calls")

            if sim_id in self.conn.sim_runs:
                self.conn.sim_runs[sim_id]["current_index"] = new_idx
                if calls is not None:
                    self.conn.sim_runs[sim_id]["calls"] = list(calls)
            self._results = []
        elif "insert into simulation_calls" in normalized:
            sim_id, called_at, carbon_intensity, idx = params
            self.conn.calls.append(
                {
                    "simulation_id": sim_id,
                    "called_at": called_at,
                    "carbon_intensity": carbon_intensity,
                    "idx": idx,
                }
            )
            self._results = []
        elif "select called_at" in normalized:
            sim_id = params[0]
            self._results = [call for call in self.conn.calls if call["simulation_id"] == sim_id]
        elif "truncate table simulation_calls" in normalized:
            self.conn.calls = []
            self._results = []
        elif "truncate table simulation_runs" in normalized:
            self.conn.sim_runs = {}
            self._results = []
        else:
            raise NotImplementedError(f"SQL not supported: {sql}")

    def fetchone(self):
        if not self._results:
            return None
        row = self._results[0]
        return dict(row) if isinstance(row, dict) else row

    def fetchall(self):
        return [dict(row) if isinstance(row, dict) else row for row in self._results]


class FakeConnection:
    """Minimal connection stub to capture simulation persistence."""

    def __init__(self):
        self.sim_runs = {}
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, row_factory=None):
        return FakeCursor(self, row_factory=row_factory)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.fixture
def conn():
    """Fresh fake connection per test."""
    connection = FakeConnection()
    app_module.simulation_store.reset(conn=connection)
    yield connection
    app_module.simulation_store.reset(conn=connection)


@pytest.mark.asyncio
async def test_simulation_flow_advances_values(monkeypatch, conn) -> None:
    """Simulation endpoints return values in order and track stats."""
    fixed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module.simulation_store, "_time_provider", lambda: fixed_time)

    payload = SimulationCreateRequest(carbon_values=[5, 10, 15])
    create_response = await create_simulation(payload, db=conn)
    simulation_id = create_response["simulation_id"]

    assert conn.sim_runs[simulation_id]["calls"] == [None, None, None]

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    next_value = await advance_simulation(simulation_id=simulation_id, db=conn)
    assert next_value["carbon_intensity"] == 10.0

    current_after_advance = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current_after_advance["carbon_intensity"] == 10.0

    current_after_advance = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current_after_advance["carbon_intensity"] == 10.0

    next_value = await advance_simulation(simulation_id=simulation_id, db=conn)
    assert next_value["carbon_intensity"] == 15.0


    stats = await simulation_stats(simulation_id=simulation_id, db=conn)

    assert len(stats) == 3
    assert stats[0]['time'] == fixed_time.isoformat()
    assert stats[0]['carbon_intensity'] == 5.0
    assert stats[1]['carbon_intensity'] == 10.0
    assert stats[2]['carbon_intensity'] == 15.0

@pytest.mark.asyncio
async def test_simulation_flow_advances_values_tuple(monkeypatch, conn) -> None:
    """Simulation endpoints return values in order and track stats."""
    fixed_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module.simulation_store, "_time_provider", lambda: fixed_time)

    payload = SimulationCreateRequest(carbon_values=[5, (10,2), 15])
    create_response = await create_simulation(payload, db=conn)
    simulation_id = create_response["simulation_id"]

    assert conn.sim_runs[simulation_id]["calls"] == [None, 2, None]

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0

    next_value = await advance_simulation(simulation_id=simulation_id, db=conn)
    assert next_value["carbon_intensity"] == 10.0

    current_after_advance = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current_after_advance["carbon_intensity"] == 10.0

    current_after_advance = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current_after_advance["carbon_intensity"] == 10.0

    current_after_advance = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current_after_advance["carbon_intensity"] == 15.0


    stats = await simulation_stats(simulation_id=simulation_id, db=conn)
    assert len(stats) == 3
    assert stats[0]['time'] == fixed_time.isoformat()
    assert stats[0]['carbon_intensity'] == 5.0
    assert stats[1]['carbon_intensity'] == 10.0
    assert stats[2]['carbon_intensity'] == 15.0


@pytest.mark.asyncio
async def test_simulation_invalid_id_raises_not_found(conn) -> None:
    """Invalid simulation IDs return a 404 HTTPException."""
    with pytest.raises(HTTPException) as exc:
        await get_simulation_carbon(simulation_id="missing", db=conn)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_simulation_next_returns_same(conn) -> None:
    """Advancing past the end of the simulation always returns the last value."""
    create_response = await create_simulation(SimulationCreateRequest(carbon_values=[1]), db=conn)
    simulation_id = create_response["simulation_id"]
    current = await advance_simulation(simulation_id=simulation_id, db=conn)
    assert current["carbon_intensity"] == 1.0


@pytest.mark.asyncio
async def test_simulation_persists_and_reads_from_db(conn) -> None:
    """Simulation endpoints write and read state through the DB connection."""
    create_response = await create_simulation(SimulationCreateRequest(carbon_values=[2, 4]), db=conn)
    simulation_id = create_response["simulation_id"]

    assert simulation_id in conn.sim_runs
    assert conn.sim_runs[simulation_id]["current_index"] == 0
    assert conn.sim_runs[simulation_id]["calls"] == [None, None]

    await advance_simulation(simulation_id=simulation_id, db=conn)
    assert conn.sim_runs[simulation_id]["current_index"] == 1

    current = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert current["carbon_intensity"] == 4.0

    stats = await simulation_stats(simulation_id=simulation_id, db=conn)
    assert stats[0]["carbon_intensity"] == 2.0
    assert conn.commits >= 2


@pytest.mark.asyncio
async def test_simulation_auto_advances_after_calls(monkeypatch, conn) -> None:
    """Values with a calls threshold auto-advance after repeated reads."""
    fixed_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
    monkeypatch.setattr(app_module.simulation_store, "_time_provider", lambda: fixed_time)

    payload = SimulationCreateRequest(carbon_values=[(5, 2), (10, 1)])
    create_response = await create_simulation(payload, db=conn)
    simulation_id = create_response["simulation_id"]

    first = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert first["carbon_intensity"] == 5.0
    assert conn.sim_runs[simulation_id]["calls"][0] == 1

    second = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert second["carbon_intensity"] == 5.0
    assert conn.sim_runs[simulation_id]["current_index"] == 1

    third = await get_simulation_carbon(simulation_id=simulation_id, db=conn)
    assert third["carbon_intensity"] == 10.0
    assert conn.sim_runs[simulation_id]["calls"][1] == -1

    stats = await simulation_stats(simulation_id=simulation_id, db=conn)
    assert len(stats) == 2
    assert stats[0]['time'] == fixed_time.isoformat()
    assert stats[0]['carbon_intensity'] == 5.0
    assert stats[1]['carbon_intensity'] == 10.0
