"""chart_manifest.py — save pipeline charts together with a content fingerprint.

Purpose:
    Every pipeline chart is saved through `save_figure`, which writes the PNG and
    records a fingerprint of what the figure plots in `chart_manifest.json` beside
    it. The fingerprint hashes the plotted content — line and scatter data, bar
    geometry, colours, text, axis limits and tick labels — never the rendered
    pixels, so it does not change with dpi, fonts, or the platform that drew the
    chart. `check_charts.py` compares a run's manifest against the one committed
    in `docs/charts/images/` to find committed charts that no longer match what
    the current data and code produce.

Inputs:
    A matplotlib Figure and the path to save it to.

Outputs:
    The PNG, plus a `{filename: fingerprint}` entry merged into
    `chart_manifest.json` in the same directory.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
from matplotlib.patches import Rectangle

MANIFEST_FILENAME = "chart_manifest.json"
SIGNIFICANT_DIGITS = 6


def _normalized(plotted_value):
    """Reduce a plotted value to nested tuples of rounded strings, so float noise below display precision cannot change the hash."""
    if plotted_value is None or plotted_value is np.ma.masked:
        return "none"
    if isinstance(plotted_value, str):
        return plotted_value
    if isinstance(plotted_value, (bool, np.bool_, int, np.integer)):
        return str(plotted_value)
    if isinstance(plotted_value, (float, np.floating)):
        return f"{plotted_value:.{SIGNIFICANT_DIGITS}g}"
    if isinstance(plotted_value, np.ma.MaskedArray):
        return _normalized(plotted_value.astype(object).filled(None).tolist())
    if isinstance(plotted_value, np.ndarray):
        return _normalized(plotted_value.tolist())
    if isinstance(plotted_value, (list, tuple)):
        return tuple(_normalized(element) for element in plotted_value)
    return repr(plotted_value)


def _patch_description(patch):
    if isinstance(patch, Rectangle):
        geometry = (patch.get_x(), patch.get_y(), patch.get_width(), patch.get_height())
    else:
        geometry = patch.get_patch_transform().transform(patch.get_path().vertices)
    return ("patch", type(patch).__name__, geometry, patch.get_facecolor())


def _axes_description(axes):
    description = [
        ("titles", [axes.get_title(loc=location) for location in ("left", "center", "right")]),
        ("labels", axes.get_xlabel(), axes.get_ylabel()),
        ("limits", axes.get_xlim(), axes.get_ylim(), axes.get_xscale(), axes.get_yscale()),
        ("xticks", [tick_label.get_text() for tick_label in axes.get_xticklabels()]),
        ("yticks", [tick_label.get_text() for tick_label in axes.get_yticklabels()]),
    ]
    for line in axes.get_lines():
        description.append(("line", line.get_xydata(), line.get_color(), line.get_linestyle(), line.get_marker(), line.get_label()))
    for collection in axes.collections:
        description.append(
            (
                "collection",
                type(collection).__name__,
                collection.get_offsets(),
                [path.vertices for path in collection.get_paths()],
                collection.get_array(),
                collection.get_sizes(),
                collection.get_facecolor(),
            )
        )
    description.extend(_patch_description(patch) for patch in axes.patches)
    for text in axes.texts:
        description.append(("text", text.get_text(), text.get_position()))
    for image in axes.images:
        description.append(("image", image.get_array()))
    legend = axes.get_legend()
    if legend is not None:
        description.append(("legend", [legend_text.get_text() for legend_text in legend.get_texts()]))
    return description


def figure_fingerprint(figure):
    """Return a sha256 hex digest of what the figure plots, independent of how it is rendered."""
    figure.canvas.draw()  # resolves categorical and auto-located tick labels
    description = [("figure_text", text.get_text()) for text in figure.texts]
    description.extend(_axes_description(axes) for axes in figure.axes)
    return hashlib.sha256(repr(_normalized(description)).encode()).hexdigest()


def save_figure(figure, output_path, **savefig_kwargs):
    """Save the figure and record its fingerprint in the manifest beside it."""
    output_path = Path(output_path)
    figure.savefig(output_path, **savefig_kwargs)
    manifest_path = output_path.parent / MANIFEST_FILENAME
    chart_fingerprints = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    chart_fingerprints[output_path.name] = figure_fingerprint(figure)
    manifest_path.write_text(json.dumps(chart_fingerprints, indent=2, sort_keys=True) + "\n")
