.PHONY: setup test lint download-data run-pipeline classify

setup:
	uv sync
	npm install
	uv run pre-commit install

test:
	uv run pytest tests/

lint:
	uv run ruff check .
	uv run ruff format .

download-data:
	node download_bls.js
	uv run download_data.py

run-pipeline:
	uv run main.py

# Separate target: classification is expensive (~19k LLM calls) and resumable.
classify:
	uv run classify_tasks.py all
