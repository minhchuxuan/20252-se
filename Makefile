# Convenience targets for the AI-Driven Smart Home Energy Optimizer.
# Usage: make <target>

BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup backend frontend test build clean

help:
	@echo "Targets:"
	@echo "  make setup     - create venv, install backend deps, install frontend deps"
	@echo "  make backend   - run the FastAPI backend (seeds demo data on first run)"
	@echo "  make frontend  - run the Vite dev server"
	@echo "  make test      - run the backend test suite (pytest)"
	@echo "  make build     - production build of the frontend"
	@echo "  make clean     - remove venv, node_modules, build output and the demo DB"

setup:
	cd $(BACKEND) && python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -r requirements.txt
	cd $(FRONTEND) && npm install

backend:
	cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd $(FRONTEND) && npm run dev

test:
	cd $(BACKEND) && . .venv/bin/activate && pytest

build:
	cd $(FRONTEND) && npm run build

clean:
	rm -rf $(VENV) $(FRONTEND)/node_modules $(FRONTEND)/dist $(BACKEND)/sheo.db $(BACKEND)/.pytest_cache
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
