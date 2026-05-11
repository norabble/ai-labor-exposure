"""
main.py
───────
Pipeline entry point for the AI Labor Exposure analysis.

Stages (run in order after classification):
  analyze    — Process BLS OEWS zip files → data/output/bls_trends.csv
  synthesize — Match classified tasks to AI penetration → data/output/occupation_impact_report.csv
  plot       — Generate visualizations → data/output/visualizations/
  validate   — Correlate model predictions with actual BLS employment/wage trends

The classify stage (make classify) is kept separate because it is expensive
and slow (~19k LLM calls). Run it once; resume is supported via checkpoint.
"""

import argparse

from analyze_bls import main as analyze_bls
from generate_plots import main as generate_plots
from synthesize_impacts import synthesize
from validate_bls import main as validate_bls

STAGES = ["analyze", "synthesize", "plot", "validate"]


def run_pipeline(stages: list[str]) -> None:
    runners = {
        "analyze": ("Analyzing BLS Data", analyze_bls),
        "synthesize": ("Synthesizing Task Impacts", synthesize),
        "plot": ("Generating Plots", generate_plots),
        "validate": ("Validating Against BLS Trends", validate_bls),
    }
    total = len(stages)
    for i, stage in enumerate(stages, 1):
        label, fn = runners[stage]
        print(f"\n{'='*60}")
        print(f"  Stage {i}/{total}: {label}")
        print(f"{'='*60}")
        fn()


def main():
    parser = argparse.ArgumentParser(
        description="AI Labor Exposure pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
stages:
  analyze    Process BLS OEWS zip files into bls_trends.csv
  synthesize Merge classifications with AI penetration data
  plot       Generate all visualizations
  validate   Correlate predictions with actual BLS trends

examples:
  uv run main.py                     # run all stages
  uv run main.py synthesize plot     # run two stages
  uv run main.py validate            # re-run validation only
        """,
    )
    parser.add_argument(
        "stages",
        nargs="*",
        default=[],
        metavar="stage",
        help=f"stages to run: {{{', '.join(STAGES)}, all}} (default: all)",
    )
    args = parser.parse_args()

    unknown = [s for s in args.stages if s not in STAGES and s != "all"]
    if unknown:
        parser.error(f"invalid stage(s): {unknown}. Choose from: {STAGES + ['all']}")

    stages_to_run = STAGES if not args.stages or "all" in args.stages else args.stages

    run_pipeline(stages_to_run)


if __name__ == "__main__":
    main()
