.PHONY: setup test lint demo ui eval

setup:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev,ui]"

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check src tests

demo:
	.venv/bin/smriti ui --demo

ui:
	.venv/bin/smriti ui

eval:
	.venv/bin/smriti eval
