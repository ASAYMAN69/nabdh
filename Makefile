VENV := .venv
BOOTSTRAP_PYTHON ?= python3
PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

.PHONY: setup run demo serve test lint clean

setup:
	$(BOOTSTRAP_PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000 --reload

demo:
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000

serve:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000

test:
	$(PYTEST)

lint:
	$(RUFF) check app nabdh tests

clean:
	rm -rf .pytest_cache .ruff_cache __pycache__ *.egg-info
