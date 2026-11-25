# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Elephant is a FastAPI and TimescaleDB service that serves carbon grid intensity data, mainly to the Green Metrics Tool.

## Setup

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt -r requirements-dev.txt
cp config.example.yml config.yml
```

- `elephant/config.py` loads `config.yml` on import, so almost everything, tests included, fails if the file is missing or invalid.
- `psycopg` needs the system `libpq` (`libpq5` on Debian) or `venv/bin/pip install "psycopg[binary]"`. Without either, tests fail at collection.

## Commands

```bash
make test  # no database needed, but test_bundesnetzagentur.py calls the live SMARD API
venv/bin/python -m pytest tests/test_app.py::test_index_returns_html  # single test
make lint

make db  # start TimescaleDB only
venv/bin/python -m elephant.database  # create the schema and apply migrations
make cron  # run one fetch iteration
make run  # API on :8085; use `venv/bin/python -m elephant --debug` for auto-reload

docker compose up --build  # full stack on :8085
```

## Architecture

`start.sh`, the container entrypoint, initializes the database and then runs two processes. The container exits if either one does.

- **Cron** (`elephant/cron.py`, sync psycopg) polls each due source in `cron.sources` and writes to `carbon`, logging changed values to `carbon_overwrites`.
- **API** (`elephant/app.py`, async pool) serves carbon data from the database. `update=true` runs `run_cron` in a thread first.

Rules that span files:

- **Provider names:** `carbon.provider` stores `{provider}_{region}` in lowercase (`energycharts_de`), not the name a provider returns. Primary lookups and the `provider` filter match on this value.
- **New providers:** subclass `CarbonIntensityProvider` and register it in `_PROVIDER_FACTORIES` (`elephant/providers/helpers.py`). Cron calls `get_historical(region)` without a time range, so `start_time` and `end_time` need defaults. Rows must have exactly the keys `region`, `time`, `carbon_intensity`, `provider`, `resolution` and `estimation`.
- **Emission factors:** providers that derive carbon intensity from a generation mix map their codes to the shared table in `elephant/providers/emission_factors.py` rather than defining their own values.
- **Provider errors:** raise `fastapi.HTTPException` on fetch failures, which skips that source for the round. Any other exception stops cron and therefore the container.
- **Schema changes:** add a numbered SQL file to `migrations/`. `elephant.database` applies each file once, in filename order.
- **Simulations:** `simulationId` on `/carbon-intensity/*`, or the `auth-token` header on the Electricity Maps-compatible `/v3/*` endpoints, serves simulated values instead of stored data.
- **Tests** call endpoint functions directly with fake connections, so they never run SQL or migrations.

## API sources

Provider API docs and emission factor sources are in `API_SOURCES.md`. Read it only when you need them, and add new API links there rather than here.
