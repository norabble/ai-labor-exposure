"""check_charts.py — detect committed charts that are missing, undocumented, or out of date.

Purpose:
    Two layers of checks on `docs/charts/images/`, the committed chart images the
    docs render:

    Coverage (needs only the repository):
      - every chart in the `docs/outputs.md` Visualizations table has a committed image
      - every committed image has a row in that table
      - every markdown image link in README.md and docs/ resolves to a file

    Freshness (needs a local pipeline run):
      - compares the fingerprints the latest run recorded in
        `data/output/visualizations/chart_manifest.json` against the committed
        `docs/charts/images/chart_manifest.json` (see chart_manifest.py). A chart
        is stale when the current data and code plot something different from
        the committed image.

Inputs:
    docs/outputs.md, docs/charts/images/, README.md, docs/**/*.md, and, if present,
    data/output/visualizations/chart_manifest.json.

Outputs:
    A report on stdout. Exit status 1 if any coverage problem or stale chart is
    found, else 0. `--quiet` prints nothing when everything passes.

Usage:
    uv run check_charts.py [--quiet]
"""

import json
import re
import sys
from pathlib import Path

from chart_manifest import MANIFEST_FILENAME

REPO_ROOT = Path(__file__).resolve().parent
OUTPUTS_REFERENCE_PATH = REPO_ROOT / "docs" / "outputs.md"
COMMITTED_IMAGES_DIR = REPO_ROOT / "docs" / "charts" / "images"
RUN_VISUALIZATIONS_DIR = REPO_ROOT / "data" / "output" / "visualizations"

TABLE_ROW_NAME_PATTERN = re.compile(r"^\| `([^`]+\.png)`", re.MULTILINE)
MARKDOWN_IMAGE_LINK_PATTERN = re.compile(r"\]\(([^)#\s]+\.png)\)")


def visualization_names(outputs_markdown):
    """Return the chart filenames listed in the Visualizations section of docs/outputs.md."""
    visualizations_section = outputs_markdown.split("## Visualizations", 1)[-1]
    return set(TABLE_ROW_NAME_PATTERN.findall(visualizations_section))


def find_missing_images(documented_charts, images_dir):
    return sorted(chart_name for chart_name in documented_charts if not (Path(images_dir) / chart_name).exists())


def find_orphan_images(documented_charts, images_dir):
    return sorted(image_path.name for image_path in Path(images_dir).glob("*.png") if image_path.name not in documented_charts)


def find_broken_image_links(markdown_paths):
    broken_links = []
    for markdown_path in markdown_paths:
        for image_link in MARKDOWN_IMAGE_LINK_PATTERN.findall(Path(markdown_path).read_text()):
            if "://" not in image_link and not (Path(markdown_path).parent / image_link).exists():
                broken_links.append((markdown_path, image_link))
    return broken_links


def classify_freshness(run_manifest, committed_manifest):
    """Sort charts into fresh, stale, unverified (no committed fingerprint yet), and not_run (not drawn by this run)."""
    freshness = {"fresh": [], "stale": [], "unverified": [], "not_run": []}
    for chart_name, run_fingerprint in run_manifest.items():
        if chart_name not in committed_manifest:
            freshness["unverified"].append(chart_name)
        elif committed_manifest[chart_name] == run_fingerprint:
            freshness["fresh"].append(chart_name)
        else:
            freshness["stale"].append(chart_name)
    freshness["not_run"] = [chart_name for chart_name in committed_manifest if chart_name not in run_manifest]
    return {status: sorted(chart_names) for status, chart_names in freshness.items()}


def _read_manifest(manifest_path):
    return json.loads(manifest_path.read_text()) if manifest_path.exists() else None


def run_checks():
    """Return (report_lines, has_failures) for the repository."""
    report_lines = []
    documented_charts = visualization_names(OUTPUTS_REFERENCE_PATH.read_text())

    coverage_problems = [
        f"missing image (documented in docs/outputs.md, not committed): {chart_name}"
        for chart_name in find_missing_images(documented_charts, COMMITTED_IMAGES_DIR)
    ]
    coverage_problems += [
        f"orphan image (committed, no docs/outputs.md row): {chart_name}"
        for chart_name in find_orphan_images(documented_charts, COMMITTED_IMAGES_DIR)
    ]
    markdown_paths = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]
    coverage_problems += [
        f"broken image link: {markdown_path.relative_to(REPO_ROOT)} -> {image_link}"
        for markdown_path, image_link in find_broken_image_links(markdown_paths)
    ]
    report_lines += coverage_problems

    run_manifest = _read_manifest(RUN_VISUALIZATIONS_DIR / MANIFEST_FILENAME)
    committed_manifest = _read_manifest(COMMITTED_IMAGES_DIR / MANIFEST_FILENAME) or {}
    stale_charts = []
    if run_manifest is None:
        report_lines.append("freshness not checked: no pipeline run manifest at data/output/visualizations/chart_manifest.json")
    else:
        freshness = classify_freshness(run_manifest, committed_manifest)
        stale_charts = freshness["stale"]
        report_lines += [f"stale image (latest run plots different content): {chart_name}" for chart_name in stale_charts]
        if freshness["unverified"]:
            unverified_count = len(freshness["unverified"])
            report_lines.append(
                f"unverified: {unverified_count} charts drawn by the latest run have no committed fingerprint to compare against"
            )
        fresh_count, not_run_count = len(freshness["fresh"]), len(freshness["not_run"])
        report_lines.append(f"freshness: {fresh_count} fresh, {len(stale_charts)} stale, {not_run_count} not drawn by the latest run")

    if coverage_problems or stale_charts:
        report_lines.append(
            "To refresh: cp data/output/visualizations/<chart>.png data/output/visualizations/chart_manifest.json docs/charts/images/"
        )
    return report_lines, bool(coverage_problems or stale_charts)


def main(argv):
    report_lines, has_failures = run_checks()
    if has_failures or "--quiet" not in argv:
        print("\n".join(report_lines))
    return 1 if has_failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
