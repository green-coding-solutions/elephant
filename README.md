# Elephant

**Elephant** is a specialized dockerized Carbon Grid Intensity (CGI) service focused on **simulation capabilities** for carbon intensity scenarios. While it can provide current and historical carbon intensity data from multiple providers, its primary differentiator is the advanced simulation functionality for testing and modeling carbon-aware computing scenarios.

Its main purpose is the integration into the Green Metrics Tool (GMT) to provide dynamic carbon intensity values with powerful simulation features. Elephant enables users of GMT to create, store, and replay custom carbon intensity scenarios for testing and development.

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

**Required for ElectricityMaps:**

- Sign up at [ElectricityMaps](https://portal.electricitymaps.com/) to get an API token
- Enable the `electricitymaps` provider and add your token in `config.yml`

**Simulation-only mode:**

- Disable all external providers to run Elephant with simulation capabilities only
- Useful for testing and development without requiring external API tokens

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Start the server (debug mode)
python3 -m elephant --debug

# Or start on custom port
python3 -m elephant --port 8080
```

## API Usage

### Current Carbon Intensity

```bash
# Get current carbon intensity for Germany
curl "http://localhost:8000/carbon-intensity/current?location=DE"
```

### Historical Carbon Intensity

```bash
# Get historical data for Germany from 10:00 to 12:00 UTC
curl "http://localhost:8000/carbon-intensity/history?location=DE&startTime=2025-09-22T10:00:00Z&endTime=2025-09-22T12:00:00Z"
```

### Health Check

```bash
# Check service status and available providers
curl "http://localhost:8000/health"
```

### API Documentation

Once running, visit `http://localhost:8000/docs` for interactive API documentation.

## Contributing

For development setup, contribution guidelines, and information about running tests and code quality checks, please see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Requirements and Design

See the complete [SPECIFICATION.md](./SPECIFICATION.md) for detailed requirements and implementation constraints.
