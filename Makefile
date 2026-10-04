.PHONY: setup test lint demo eval ui

setup:
	uv venv && uv pip install -e ".[dev,ui]"

test:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/ruff check src tests

demo:
	PARAG_DATA_DIR=./data-demo PARAG_PASSPHRASE=demo .venv/bin/parag demo

eval:
	.venv/bin/parag eval

ui:
	PARAG_DATA_DIR=./data-demo PARAG_PASSPHRASE=demo .venv/bin/chainlit run src/parag/ui/chainlit_app.py
