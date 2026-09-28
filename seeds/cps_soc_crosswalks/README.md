# Census occupation code lists (CPS coding vintages → SOC)

Committed reference data, not a download step. Retrieved 2026-09-23 from
https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/ and
committed unchanged.

| File | CPS years using these codes | SOC generation of the reference column |
|---|---|---|
| `2002-census-occupation-codes.xls` (sheet `Occ Codes`) | 2003–2010 | SOC 2000 |
| `2010-occ-codes-with-crosswalk-from-2002-2011.xls` (sheet `2010OccCodeList`) | 2011–2019 | SOC 2010 |
| `2018-occupation-code-list-and-crosswalk.xlsx` (sheet `2018 Census Occ Code List`) | 2020 onward | SOC 2018 |

The 2018 file's sheet `2010 to 2018 Crosswalk ` (trailing space) also relates
2010 Census codes to 2018 Census codes; `occ1990dd_reference.load_census_2018_to_2010`
reads it.

Read by `occ1990dd_reference.py`. The SOC reference column mixes detailed codes,
broad groups ending in `0`, and wildcards containing `X`;
`occ1990dd_reference.expand_soc_reference` resolves all three to detailed codes.
