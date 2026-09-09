"""Tests for harmonize_soc.py — SOC crosswalk loading, aggregate resolution, and unit construction."""

import os

import pandas as pd
import pytest

from analyze_bls import YEAR_CONFIGS, load_bls_year, select_detailed_rows
from harmonize_soc import (
    GENERATION_BY_YEAR,
    clean_crosswalk_title,
    is_residual_title,
    load_aggregate_codes,
    load_oews_hybrid_structure,
    load_soc_2000_to_2010,
    load_soc_2010_to_2018,
    resolve_oews_codes,
    soc_vocabularies,
)

RAW_BLS_PRESENT = os.path.exists("data/raw/bls/oesm22nat.zip")


class TestCrosswalkLoaders:
    def test_2010_to_2018_has_the_software_developer_merge(self):
        crosswalk_edges_df = load_soc_2010_to_2018()
        merged_into_developers = crosswalk_edges_df[crosswalk_edges_df["to_code"] == "15-1252"]
        assert sorted(merged_into_developers["from_code"]) == ["15-1132", "15-1133"]
        assert list(crosswalk_edges_df.columns) == ["from_code", "from_title", "to_code", "to_title"]

    def test_2010_to_2018_titles_are_cleaned(self):
        crosswalk_edges_df = load_soc_2010_to_2018()
        all_other_row = crosswalk_edges_df[crosswalk_edges_df["from_code"] == "15-1199"].iloc[0]
        assert all_other_row["from_title"] == "Computer Occupations, All Other"
        assert "(#" not in " ".join(crosswalk_edges_df["from_title"]) + " ".join(crosswalk_edges_df["to_title"])

    def test_2000_to_2010_has_the_systems_software_relabel(self):
        crosswalk_edges_df = load_soc_2000_to_2010()
        assert list(crosswalk_edges_df[crosswalk_edges_df["from_code"] == "15-1032"]["to_code"]) == ["15-1133"]
        assert crosswalk_edges_df["from_code"].str.match(r"^\d\d-\d{4}$").all()
        assert crosswalk_edges_df["to_code"].str.match(r"^\d\d-\d{4}$").all()

    def test_hybrid_structure_maps_software_developers_both_ways(self):
        hybrid_df = load_oews_hybrid_structure()
        developer_rows = hybrid_df[hybrid_df["hybrid_code"] == "15-1256"]
        assert set(developer_rows["soc_2018_code"]) == {"15-1252", "15-1253"}
        assert set(developer_rows["oews_2018_code"]) == {"15-1132", "15-1133"}
        buyers_rows = hybrid_df[hybrid_df["oews_2018_code"] == "13-1020"]
        assert set(buyers_rows["soc_2010_code"]) == {"13-1021", "13-1022", "13-1023"}


class TestTitleHelpers:
    def test_clean_strips_footnote_markers_and_asterisks(self):
        assert clean_crosswalk_title("Computer Occupations, All Other (#) ") == "Computer Occupations, All Other"
        assert clean_crosswalk_title("Registered Nurses*") == "Registered Nurses"

    def test_residual_detection_is_case_insensitive(self):
        assert is_residual_title("Computer Occupations, All Other (##)")
        assert is_residual_title("computer specialists, all other")
        assert not is_residual_title("Software Developers")


class TestGenerationMap:
    def test_every_year_in_year_configs_has_a_generation(self):
        for year_suffix, _ in YEAR_CONFIGS:
            assert year_suffix in GENERATION_BY_YEAR
        assert GENERATION_BY_YEAR["09"] == "soc2000"
        assert GENERATION_BY_YEAR["10"] == "soc2010"
        assert GENERATION_BY_YEAR["19"] == "hybrid"
        assert GENERATION_BY_YEAR["21"] == "soc2018"


class TestResolveOewsCodes:
    def _fixture(self):
        vocabularies = {
            "soc2010": {"13-1021", "13-1022", "13-1023", "15-1151", "15-1152", "29-1141"},
            "soc2018": {"15-1252", "15-1253"},
            "soc2000": set(),
        }
        aggregate_codes_df = pd.DataFrame(
            {
                "generation": ["soc2010"],
                "oews_code": ["29-1111"],
                "oews_title": ["Registered Nurses*"],
                "member_soc_code": ["29-1141"],
                "source": ["title"],
            }
        )
        hybrid_df = pd.DataFrame(
            {
                "hybrid_code": ["15-1256", "15-1256"],
                "hybrid_title": ["Software Developers and Software Quality Assurance Analysts and Testers"] * 2,
                "soc_2018_code": ["15-1252", "15-1253"],
                "soc_2018_title": ["Software Developers", "Software Quality Assurance Analysts and Testers"],
                "oews_2018_code": ["15-1132", "15-1133"],
                "oews_2018_title": ["Software Developers, Applications", "Software Developers, Systems Software"],
                "soc_2010_code": ["15-1132", "15-1133"],
                "soc_2010_title": ["Software Developers, Applications", "Software Developers, Systems Software"],
            }
        )
        return vocabularies, aggregate_codes_df, hybrid_df

    def test_identity_seed_and_broad_group_resolutions(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame(
            {
                "OCC_CODE": ["29-1141", "29-1111", "13-1020"],
                "OCC_TITLE": ["Registered Nurses", "Registered Nurses*", "Buyers and Purchasing Agents"],
            }
        )
        resolved_df = resolve_oews_codes(oews_codes_df, "soc2010", vocabularies, aggregate_codes_df, hybrid_df)
        by_code = resolved_df.groupby("oews_code")
        assert list(by_code.get_group("29-1141")["soc_code"]) == ["29-1141"]
        assert list(by_code.get_group("29-1141")["resolution"]) == ["identity"]
        assert list(by_code.get_group("29-1111")["soc_code"]) == ["29-1141"]
        assert list(by_code.get_group("29-1111")["resolution"]) == ["aggregate_seed"]
        assert sorted(by_code.get_group("13-1020")["soc_code"]) == ["13-1021", "13-1022", "13-1023"]
        assert set(by_code.get_group("13-1020")["resolution"]) == {"broad_group"}

    def test_hybrid_codes_resolve_through_the_hybrid_file(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame({"OCC_CODE": ["15-1256"], "OCC_TITLE": ["Software Developers and SQA"]})
        resolved_df = resolve_oews_codes(oews_codes_df, "hybrid", vocabularies, aggregate_codes_df, hybrid_df)
        assert sorted(resolved_df["soc_code"]) == ["15-1252", "15-1253"]
        assert set(resolved_df["resolution"]) == {"hybrid"}

    def test_unresolvable_code_raises_with_the_code_named(self):
        vocabularies, aggregate_codes_df, hybrid_df = self._fixture()
        oews_codes_df = pd.DataFrame({"OCC_CODE": ["99-9999"], "OCC_TITLE": ["Nothing"]})
        with pytest.raises(ValueError, match="99-9999"):
            resolve_oews_codes(oews_codes_df, "soc2010", vocabularies, aggregate_codes_df, hybrid_df)


@pytest.mark.skipif(not RAW_BLS_PRESENT, reason="raw OEWS zips not present")
class TestEveryOewsCodeResolves:
    def test_all_years_resolve_without_error(self):
        vocabularies = soc_vocabularies()
        aggregate_codes_df = load_aggregate_codes()
        hybrid_df = load_oews_hybrid_structure()
        for year_suffix, zip_path in YEAR_CONFIGS:
            detailed_rows_df = select_detailed_rows(load_bls_year(zip_path))
            resolved_df = resolve_oews_codes(
                detailed_rows_df[["OCC_CODE", "OCC_TITLE"]], GENERATION_BY_YEAR[year_suffix], vocabularies, aggregate_codes_df, hybrid_df
            )
            assert set(resolved_df["oews_code"]) == set(detailed_rows_df["OCC_CODE"]), year_suffix
