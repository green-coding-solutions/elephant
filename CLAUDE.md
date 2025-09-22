# Elephant Development Guide

## Quick Start

```bash
source venv/bin/activate
python3 -m elephant --debug
```

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API server
python3 -m elephant

# Execute linting and formatting
pre-commit run --files $(git diff --name-only --diff-filter=ACMR HEAD)
```

## Tech Stack

Python with venv, pip, and pytest

## Code Principles

**Write self-documenting code:**

- Use descriptive variable and function names
- Structure code to reveal intent
- Add comments only when code doesn't speak for itself (explain WHY, not WHAT)

**Keep it simple:**

- Choose the simplest solution that works
- Avoid abstractions until duplication becomes painful
- Minimize external dependencies

**Be explicit:**

- Use type annotations
- Validate inputs early
- Surface clear error messages

## Style & Workflow

- **Follow PEP8**
- **Activate venv first**: `source venv/bin/activate` at the beginning of a new session
- **Lint after each task** - always ensure good code quality
- **Commit frequently**
- **Add tests for new functionality**
- **If you do measurements, persist the used scripts / commands** - measurements should be repeatable

## Project Structure

- `elephant/` - Main package (app.py for API, config.py, models.py)
- `elephant/providers/` - Data provider implementations
- `tests/` - Test suite with corresponding test files
- `config.example.yml` - Configuration template

## Project Files

- [README.md](./README.md) - Overview with links to detailed docs
- [SPECIFICATION.md](./SPECIFICATION.md) - Requirements and constraints
