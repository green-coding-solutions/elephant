# Elephant

**Elephant** is a specialized dockerized Carbon Grid Intensity (CGI) service focused on **simulation capabilities** for carbon intensity scenarios. While it can provide current and historical carbon intensity data from multiple providers, its primary differentiator is the advanced simulation functionality for testing and modeling carbon-aware computing scenarios.

Its main purpose it the integration into the Green Metrics Tool (GMT) to provide dynamic carbon intensity values with powerful simulation features. Elephant enables users of GMT to create, store, and replay custom carbon intensity scenarios for testing and development.

## Installation

```bash
git clone https://github.com/green-coding-solutions/elephant
cd elephant
pip install .
```

## Quick Start

```bash
# Start the server
python3 -m elephant
```

## Contributing

For development setup, contribution guidelines, and information about running tests and code quality checks, please see [CONTRIBUTING.md](./CONTRIBUTING.md).

## Requirements and Design

See the complete [SPECIFICATION.md](./SPECIFICATION.md) for detailed requirements and implementation constraints.
