# occ1990dd crosswalks (David Dorn)

Committed reference data, not a download step. Retrieved 2026-09-23 from
https://www.ddorn.net/data.htm (files A4–A8) and converted from Stata `.dta` to
CSV with columns `source_code, occ1990dd`. Values are unchanged; `occ2010`'s
zero-padded string codes (`"0010"`) became integers (`10`).

Every source code maps to exactly one `occ1990dd` code. `999` means unclassified.

Please cite:

- occ1980, occ1990, occ2000, occ2005: David Autor and David Dorn. "The Growth of
  Low-Skill Service Jobs and the Polarization of the U.S. Labor Market."
  *American Economic Review* 103(5), 1553–1597, 2013.
- occ2010: David Autor. "Why Are There Still So Many Jobs? The History and Future
  of Workplace Automation." *Journal of Economic Perspectives* 29(3), 3–30, 2015.

`seeds/occ1990dd_groups.csv` is the occupation-group partition from Dorn's
`subfile_occ1990dd_occgroups.do` (file A9, Autor and Dorn 2013): the 16 level-2
non-service groups plus the 9 level-3 service subgroups, with `occ3_protect`
omitted because it is the union of `occ3_guard` and `occ2_firepol`. It covers
every `occ1990dd` code except 905 and 991, which fall in no group.
