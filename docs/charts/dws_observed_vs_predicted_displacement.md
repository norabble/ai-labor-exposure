# Predicted vs. Measured Displacement (DWS Table 5)

`data/output/visualizations/dws_observed_vs_predicted_displacement.png`, produced
by `composition_displacement_validation.py`.

Each point is one of the ten Displaced Worker Supplement occupation groups. The x
axis is the demand composition model's predicted share of total displacement; the
y axis is the measured share from DWS Table 5. Bubble area is proportional to
group employment, and the dashed line is perfect agreement.

## Why this chart is different from every other validation here

Every other test in this project correlates a model score against employment or
wage growth. This one compares a modeled quantity against a *direct measurement
of that same quantity* — `gross_displacement` against a count of workers who
actually lost a job. **Employment growth never enters**, so circularity is
structurally impossible rather than merely avoided.

It also isolates the two halves of the model. The equilibrium is
`net = K·absorption_capacity − gross_displacement`; correlating `net` against
growth tests both terms jointly, and a failure cannot be attributed to either.
This chart exercises the displacement half alone.

Shares are compared rather than rates because the DWS counts people 20 and over
who lost a job while OEWS counts wage and salary jobs — the denominators are
different populations. Shares are unit-free on both sides. The economy-wide
displacement rate D cancels here for the same reason it cancels everywhere else:
it multiplies every occupation equally, so it cannot move a share.

## Result: null, with an interpretable pattern

| Model | Pearson | Spearman | Leave-one-out |
|---|---|---|---|
| Demand composition | +0.220 (p = 0.541) | +0.600 (p = 0.067) | +0.019 to +0.389 |
| Dynamic, AI penetration | +0.261 (p = 0.466) | +0.491 (p = 0.150) | +0.186 to +0.677 |

Both models point the right way; neither is significant at n = 10. Spearman
exceeding Pearson for the composition model suggests it gets the *ordering* of
groups roughly right while the magnitudes are off.

The per-group misses are systematic, and more informative than the correlation:

| Group | Measured share | Composition predicted | AI model predicted |
|---|---:|---:|---:|
| Management, business, financial | 27.9% | 10.1% | 14.6% |
| Professional and related | 19.2% | 9.3% | 11.9% |
| Production | 10.7% | 6.2% | 1.0% |
| Office and administrative support | 9.6% | 16.5% | **49.0%** |
| Service | 9.2% | **24.9%** | 5.1% |
| Transportation and material moving | 6.5% | 12.4% | 0.5% |

The composition model **under-predicts displacement in management and
professional work by 17.8 and 9.9 points and over-predicts service by 15.7**. The
AI model's error is more extreme in one place: it puts 49% of all displacement in
Office and administrative support against a measured 9.6%.

## Beyond this survey: the ten-survey panel

This chart's subject is the single newest survey (January 2026). BLS also
publishes an archive of prior DWS releases (see the CLAUDE.md correction
referenced below), which the committed panel now uses to repeat this same
comparison against nine earlier surveys, in
`composition_model_displacement_validation_panel.csv`:

- Composition model: Pearson r **+0.220 to +0.645, median +0.387**, 1 of 10
  surveys individually significant.
- Dynamic model: Pearson r **+0.261 to +0.618, median +0.567**, 0 of 10 surveys
  individually significant.
- **All ten surveys are positive for both models.**

That uniformity is not ten independent confirmations: the predicted side of
every survey's correlation is the same 2025-derived model score, so only the
observed side varies across surveys, and consecutive biennial surveys share
overlapping three-year recall windows — a sign test or an averaged r across
them would be invalid. At n = 10 groups, a survey needs r ≈ 0.63 to be
individually significant on its own. Per the project's asymmetric reading rule,
this stays a **null** — a positive result would have been strong evidence,
because the 2025-derived labels are anachronistic and work against the model
finding anything, but a null is uninformative rather than disconfirming. The
consistent positive sign across all ten surveys is noted as suggestive and
nothing more.

## Reading cautions

**This is all-reasons displacement.** The DWS publishes no occupation × reason
cross-tab — Table 5 gives occupation without reason, Table 2 reason without
occupation — so the structural category cannot be isolated by group. "Position or
shift abolished" is 44.4% of the total; the other 55.6% is plant closings and
insufficient work, which are demand and cyclical shocks rather than technological
displacement. Corporate restructuring falls heavily on management and
professional staff, which plausibly explains much of the largest miss. The
dilution should weaken the correlation rather than inflate it.

**n = 10.** Pearson alone is not reportable at that size; Spearman and the
leave-one-out range are given beside it, following the jackknife discipline the
project already applies to its 22-sector results.

**This chart is one survey (January 2026, covering 2023–2025) by design, not for
lack of an archive.** An earlier note claimed BLS published no prior DWS
releases; that was wrong — nine biennial archives exist back to 2008 (see the
correction in `CLAUDE.md` under `seeds/dws_displacement_panel.csv`) — and the
panel now holds all ten surveys. This chart still shows only the newest one,
which remains the headline; see "Beyond this survey" above for the panel
result.

**The composition model's tie structure limits resolution.** 239 of 770
occupations are exactly 100% Bounded and share one score, so within-group
variation is coarse. See `docs/framework.md` § Demand Composition Model.

## Related

- `docs/framework.md` § Demand Composition Model
- `docs/charts/composition_model_signal_over_time.md` — the growth-based era test
