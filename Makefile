.PHONY: test lint run db cron commit

VENV ?= venv
PYTHON = $(VENV)/bin/python

test:
	$(PYTHON) -m pytest tests

lint:
	$(PYTHON) -m pylint --recursive=y elephant/

run:
	$(PYTHON) -m elephant --host 0.0.0.0 --port 8085

db:
	docker compose up -d db

cron:
	$(PYTHON) -m elephant.cron

commit: test lint
