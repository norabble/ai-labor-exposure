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

# download_cps.js runs last: it exits non-zero on a failed fetch outside CI, which
# would otherwise abort the target before the O*NET/Anthropic/Eloundou downloads.
download-data:
	node download_bls.js
	uv run download_data.py
	node download_cps.js
	uv run download_dws.py

run-pipeline:
	uv run main.py

# Separate target: classification is expensive (~19k LLM calls) and resumable.
classify:
	uv run classify_tasks.py all
