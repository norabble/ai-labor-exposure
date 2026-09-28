"""Tests for check_charts: chart coverage (docs vs committed images) and freshness (committed vs latest run)."""

from pathlib import Path

from check_charts import (
    classify_freshness,
    find_broken_image_links,
    find_missing_images,
    find_orphan_images,
    visualization_names,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

OUTPUTS_MARKDOWN = """# Outputs Reference

## Data files — `data/output/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `bls_trends.csv` | `analyze_bls.py` | Trends. |

## Visualizations — `data/output/visualizations/`

| File | Produced by | Purpose |
|------|-------------|---------|
| `alpha_chart.png` | `generate_plots.py` | Alpha. |
| `beta_chart.png` | `validate_bls.py` | Beta. |
"""


class TestCoverage:
    def test_visualization_names_reads_only_the_visualizations_table(self):
        assert visualization_names(OUTPUTS_MARKDOWN) == {"alpha_chart.png", "beta_chart.png"}

    def test_documented_chart_without_committed_image_is_missing(self, tmp_path):
        (tmp_path / "alpha_chart.png").write_bytes(b"png")
        assert find_missing_images({"alpha_chart.png", "beta_chart.png"}, tmp_path) == ["beta_chart.png"]

    def test_committed_image_without_documentation_is_orphaned(self, tmp_path):
        (tmp_path / "alpha_chart.png").write_bytes(b"png")
        (tmp_path / "retired_chart.png").write_bytes(b"png")
        (tmp_path / "chart_manifest.json").write_text("{}")
        assert find_orphan_images({"alpha_chart.png"}, tmp_path) == ["retired_chart.png"]

    def test_image_link_to_a_missing_file_is_broken(self, tmp_path):
        (tmp_path / "images").mkdir()
        (tmp_path / "images" / "present.png").write_bytes(b"png")
        chart_doc = tmp_path / "chart.md"
        chart_doc.write_text("![ok](images/present.png)\n![gone](images/absent.png)\n[anchor](other.md#section)\n")
        assert find_broken_image_links([chart_doc]) == [(chart_doc, "images/absent.png")]


class TestFreshness:
    def test_classifies_each_chart_against_the_committed_manifest(self):
        run_manifest = {"same.png": "aaa", "changed.png": "bbb", "never_recorded.png": "ccc"}
        committed_manifest = {"same.png": "aaa", "changed.png": "old", "not_in_this_run.png": "ddd"}
        freshness = classify_freshness(run_manifest, committed_manifest)
        assert freshness == {
            "fresh": ["same.png"],
            "stale": ["changed.png"],
            "unverified": ["never_recorded.png"],
            "not_run": ["not_in_this_run.png"],
        }


class TestRepositoryCoverage:
    """The committed repository itself must have no coverage gaps — this is the CI gate."""

    def test_every_documented_chart_has_a_committed_image(self):
        documented_charts = visualization_names((REPO_ROOT / "docs" / "outputs.md").read_text())
        assert find_missing_images(documented_charts, REPO_ROOT / "docs" / "charts" / "images") == []

    def test_every_committed_image_is_documented(self):
        documented_charts = visualization_names((REPO_ROOT / "docs" / "outputs.md").read_text())
        assert find_orphan_images(documented_charts, REPO_ROOT / "docs" / "charts" / "images") == []

    def test_no_markdown_links_to_a_missing_image(self):
        markdown_paths = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").rglob("*.md"))]
        assert find_broken_image_links(markdown_paths) == []
