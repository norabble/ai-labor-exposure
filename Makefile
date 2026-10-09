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

# The BLS fetchers run last: each exits non-zero on a failed fetch outside CI, which
# would otherwise abort the O*NET/Anthropic/Eloundou downloads. Their order among
# themselves does not matter — the A-19 page is cross-checked against the API history
# in the pipeline (cps_panel.load_cps_panel), not here.
download-data:
	node download_bls.js
	uv run download_data.py
	uv run btos_adoption.py
	node download_cps.js
	uv run download_dws.py
	uv run download_cps_history.py

run-pipeline:
	uv run main.py

# Separate target: classification is expensive (~19k LLM calls) and resumable.
classify:
	uv run classify_tasks.py all
