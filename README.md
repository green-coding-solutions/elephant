# Elephant 🐘

**Elephant** is a specialized Carbon Grid Intensity (CGI) service. It provides current and historical carbon intensity data from multiple providers.

Its main purpose is the integration into the Green Metrics Tool (GMT) to provide dynamic carbon intensity values.

## Installation

```bash
git clone https://github.com/green-coding-solutions/elephant
cd elephant

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Before running Elephant, you need to configure your data providers:

```bash
# Copy the example configuration
cp config.example.yml config.yml

# Edit config.yml and add your API tokens
# For ElectricityMaps: Replace "your-electricitymaps-api-token-here" with your actual token
```

## Running

You should just be able to do
```bash
docker compose up --build
```

and that should set everythin up so that you can access Elephant under `http://localhost:8000/`

**Required for ElectricityMaps:**

- Sign up at [ElectricityMaps](https://portal.electricitymaps.com/) to get an API token
- Enable the `electricitymaps` provider and add your token in `config.yml`

## Development
You should be able to

```
pip install -r requirements-dev.txt
pylint elephant/**.py
pytest tests
```

Also for development it might be easier to not having to build a docker container all the time. So you can only run the DB with

```bash
docker compose up -d db
```

and then run the commands on your development machine

```bash
python3 -m elephant.database
python3 -m elephant.cron
python3 -m elephant --host 0.0.0.0 --port 8000
```