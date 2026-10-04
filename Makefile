.PHONY: setup test lint demo eval ui

setup:
	uv venv && uv pip install -e ".[dev,ui]"

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check src tests

demo:
	SMRITI_DATA_DIR=./data-demo SMRITI_PASSPHRASE=demo .venv/bin/smriti demo

eval:
	.venv/bin/smriti eval

ui:
	SMRITI_DATA_DIR=./data-demo SMRITI_PASSPHRASE=demo .venv/bin/chainlit run src/smriti/ui/chainlit_app.py
