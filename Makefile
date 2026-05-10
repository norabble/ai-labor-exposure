.PHONY: setup test lint run-pipeline download-data

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
	uv run analyze_bls.py
	uv run synthesize_impacts.py
	uv run generate_plots.py
	uv run validate_bls.py

# A separate command for classification since it costs money and takes time
classify:
	uv run classify_tasks.py all
