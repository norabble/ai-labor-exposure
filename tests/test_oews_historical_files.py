"""Tests for reading the 1999-2004 OEWS national files: banner rows, column variants, and the 00-0000 row."""

import zipfile

import pandas as pd

from analyze_bls import detect_header_row, load_bls_year, select_major_group_rows


def _write_oews_zip(zip_path, header_row_offset: int, title_column: str, include_all_occupations: bool):
    """Build a small OEWS-shaped workbook with `header_row_offset` banner rows above the header."""
    rows = [
        {"occ_code": "11-0000", "group": "major", title_column: "Management Occupations", "tot_emp": 7_000_000, "a_median": 67_000},
        {"occ_code": "11-1011", "group": None, title_column: "Chief Executives", "tot_emp": 500_000, "a_median": 140_000},
        {"occ_code": "15-0000", "group": "major", title_column: "Computer Occupations", "tot_emp": 3_000_000, "a_median": 80_000},
    ]
    if include_all_occupations:
        rows.insert(
            0, {"occ_code": "00-0000", "group": "major", title_column: "All Occupations", "tot_emp": 127_000_000, "a_median": 30_000}
        )
    data_df = pd.DataFrame(rows)

    banner = pd.DataFrame([[f"banner line {i}"] + [None] * (len(data_df.columns) - 1) for i in range(header_row_offset)])
    excel_path = str(zip_path).replace(".zip", ".xlsx")
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        banner.to_excel(writer, index=False, header=False, startrow=0)
        data_df.to_excel(writer, index=False, header=True, startrow=header_row_offset)
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(excel_path, arcname="national_dl.xlsx")
    return zip_path


class TestHeaderDetection:
    def test_header_on_first_row_is_found(self):
        raw_df = pd.DataFrame([["occ_code", "group"], ["11-0000", "major"]])
        assert detect_header_row(raw_df) == 0

    def test_header_below_banner_rows_is_found(self):
        raw_df = pd.DataFrame([["1999 National OES Estimates", None], [None, None], ["occ_code", "group"]])
        assert detect_header_row(raw_df) == 2

    def test_missing_header_falls_back_to_row_zero(self):
        raw_df = pd.DataFrame([["nothing", "useful"], ["still", "nothing"]])
        assert detect_header_row(raw_df) == 0


class TestHistoricalFileShapes:
    def test_banner_rows_are_skipped(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes99nat.zip", header_row_offset=39, title_column="occ_title", include_all_occupations=False)
        year_frame = load_bls_year(str(zip_path))
        assert "OCC_CODE" in year_frame.columns
        assert "OCC_TITLE" in year_frame.columns

    def test_occ_titl_variant_is_normalised(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes00nat.zip", header_row_offset=38, title_column="occ_titl", include_all_occupations=False)
        year_frame = load_bls_year(str(zip_path))
        assert "OCC_TITLE" in year_frame.columns
        assert "OCC_TITL" not in year_frame.columns

    def test_all_occupations_row_is_not_a_major_group(self, tmp_path):
        zip_path = _write_oews_zip(tmp_path / "oes02nat.zip", header_row_offset=0, title_column="occ_titl", include_all_occupations=True)
        major_rows = select_major_group_rows(load_bls_year(str(zip_path)))
        assert "00" not in set(major_rows["soc_major"])
        assert set(major_rows["soc_major"]) == {"11", "15"}
