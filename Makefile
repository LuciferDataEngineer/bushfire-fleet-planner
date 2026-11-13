PYTHON ?= .venv/bin/python
export PYTHONPATH := src
export SPARK_LOCAL_IP := 127.0.0.1

.PHONY: setup lint test pipeline soda conftest snapshot all

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

lint:
	$(PYTHON) -m ruff check src tests scripts

test:
	$(PYTHON) -m pytest -m "not contract"

pipeline:
	$(PYTHON) -m bushfire_fleet.pipeline

soda:
	$(PYTHON) -m soda scan -d fleet -c soda/configuration.yml soda/checks.yml

conftest:
	conftest test k8s --policy policy

snapshot:
	$(PYTHON) scripts/build_snapshot.py

all: lint test pipeline soda
