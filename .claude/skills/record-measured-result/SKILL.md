---
name: record-measured-result
description: Use when writing or changing a measured figure (r, p, n, median, count, share, "k of n") in docs/framework.md, docs/charts/*.md, docs/outputs.md, or a plan's Deviations log — including after re-running a pipeline stage, adding a new output CSV, or addressing review findings on results prose.
---

# Record a Measured Result

## Overview

Every number in results prose is copied out of a `data/output/*.csv` by a command you ran in this session, never paraphrased from memory, an earlier doc, or a spec's estimate. Most results-prose corrections in this repo's history were a qualitative word that disagreed with its own numbers, a scope label naming the wrong slice, or one of three copies of a figure left stale.

## Procedure

1. **Query the CSV.** Print every figure you will write, with the exact filter that produced it:

   ```bash
   uv run python - <<'EOF'
   import pandas as pd
   era_comparison_df = pd.read_csv("data/output/composition_model_era_comparison_cps_major.csv")
   headline_rows = era_comparison_df[era_comparison_df["score"] == "composition_net_change"]
   print(headline_rows.to_string())
   EOF
   ```

   For a count-based claim, print the numerator, the denominator, and their ratio.

2. **Write the claim in the house format.** Include every part below:
   - `Measured YYYY-MM-DD` (today's date)
   - the scope: file, filter (`run == "headline"`, `tenure_class == "all_tenures"`), and n with its unit (periods, surveys, groups, codes)
   - the numbers: signed r to three places, with p
   - significance as a count: `11 significant` / `1/21 significant`
   - the reading, which comes last and follows from the numbers above it

3. **Derive every qualitative word from a printed number.**

   | Word | Required evidence |
   |------|-------------------|
   | "under/over half", "most", "few" | print k and n, and write `k of n` beside the word |
   | "median across N surveys" vs "newest survey" | the aggregation you actually ran |
   | "same direction", "opposite in sign" | both signed values, side by side |
   | "significant" | p, plus the n-dependent threshold (n=10 → r≈0.63, n=22 → r≈0.42, n≈25 → r≈0.40) |
   | "positive in all N" | the count of positive rows |

4. **Update every copy.** Search the old value and the output name in the places results prose lives:

   ```bash
   grep -rn "0.271\|era_comparison_cps_major" CLAUDE.md docs/
   ```

   Change every hit in the same commit.

5. **Apply the project's reading rules.**
   - A null is read asymmetrically: it's uninformative, not disconfirming.
   - A predicted vector that's identical across surveys means sign consistency is not independent evidence. Don't pool it or sign-test it.
   - A share result sits beside its employment-size benchmark.
   - CPS and OEWS are never spliced.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Estimating a fraction ("just over half") | Print `k of n` first. Write the word second. |
| Labelling a 21-survey median as the newest survey | Name the aggregation in the sentence. |
| Updating framework.md but not the chart doc | Run the step 4 grep before committing. |
| Putting a figure in a `docs/outputs.md` row | Rows describe the output. The figure goes in framework.md or the chart doc, and the row points there. |
| Carrying a spec's pre-registered estimate forward | Replace it with the measured value, and say what the estimate was. |
| Writing the interpretation first and fitting the numbers to it | Put the numbers first. The reading follows from them. |
