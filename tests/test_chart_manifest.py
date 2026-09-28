"""Tests for chart_manifest: content fingerprints of saved figures and the manifest that records them."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from chart_manifest import MANIFEST_FILENAME, figure_fingerprint, save_figure  # noqa: E402


def build_sample_figure(y_values=(1.0, 2.0, 3.0), title="Employment growth", bar_heights=(4.0, 5.0)):
    figure, (line_axes, bar_axes) = plt.subplots(1, 2)
    line_axes.plot([0, 1, 2], list(y_values), color="tab:blue")
    line_axes.scatter([0.5, 1.5], [2.5, 1.5])
    line_axes.set_title(title)
    line_axes.set_xlabel("Period")
    bar_axes.bar(["Bounded", "Unbounded"], list(bar_heights))
    return figure


class TestFigureFingerprint:
    def test_identical_figures_share_a_fingerprint(self):
        first_figure = build_sample_figure()
        second_figure = build_sample_figure()
        assert figure_fingerprint(first_figure) == figure_fingerprint(second_figure)
        plt.close("all")

    def test_changed_line_data_changes_the_fingerprint(self):
        original_figure = build_sample_figure()
        changed_figure = build_sample_figure(y_values=(1.0, 2.0, 3.5))
        assert figure_fingerprint(original_figure) != figure_fingerprint(changed_figure)
        plt.close("all")

    def test_changed_bar_height_changes_the_fingerprint(self):
        original_figure = build_sample_figure()
        changed_figure = build_sample_figure(bar_heights=(4.0, 6.0))
        assert figure_fingerprint(original_figure) != figure_fingerprint(changed_figure)
        plt.close("all")

    def test_changed_title_changes_the_fingerprint(self):
        original_figure = build_sample_figure()
        changed_figure = build_sample_figure(title="Wage growth")
        assert figure_fingerprint(original_figure) != figure_fingerprint(changed_figure)
        plt.close("all")

    def test_float_noise_below_display_precision_is_ignored(self):
        original_figure = build_sample_figure()
        noisy_figure = build_sample_figure(y_values=(1.0, 2.0, 3.0 + 1e-13))
        assert figure_fingerprint(original_figure) == figure_fingerprint(noisy_figure)
        plt.close("all")


class TestSaveFigure:
    def test_writes_the_png_and_a_manifest_entry(self, tmp_path):
        figure = build_sample_figure()
        output_path = tmp_path / "sample_chart.png"
        save_figure(figure, output_path, dpi=50)

        assert output_path.exists()
        manifest = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
        assert manifest["sample_chart.png"] == figure_fingerprint(figure)
        plt.close("all")

    def test_fingerprint_does_not_depend_on_dpi(self, tmp_path):
        low_dpi_dir = tmp_path / "low"
        high_dpi_dir = tmp_path / "high"
        low_dpi_dir.mkdir()
        high_dpi_dir.mkdir()
        save_figure(build_sample_figure(), low_dpi_dir / "chart.png", dpi=50)
        save_figure(build_sample_figure(), high_dpi_dir / "chart.png", dpi=150, bbox_inches="tight")

        low_manifest = json.loads((low_dpi_dir / MANIFEST_FILENAME).read_text())
        high_manifest = json.loads((high_dpi_dir / MANIFEST_FILENAME).read_text())
        assert low_manifest["chart.png"] == high_manifest["chart.png"]
        plt.close("all")

    def test_later_saves_merge_into_the_existing_manifest(self, tmp_path):
        save_figure(build_sample_figure(), tmp_path / "first_chart.png", dpi=50)
        save_figure(build_sample_figure(title="Other"), tmp_path / "second_chart.png", dpi=50)

        manifest = json.loads((tmp_path / MANIFEST_FILENAME).read_text())
        assert set(manifest) == {"first_chart.png", "second_chart.png"}
        plt.close("all")
