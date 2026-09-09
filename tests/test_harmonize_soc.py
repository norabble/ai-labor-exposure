"""Tests for harmonize_soc.py — SOC crosswalk loading, aggregate resolution, and unit construction."""

import os

import pandas as pd
import pytest

from analyze_bls import YEAR_CONFIGS, load_bls_year, select_detailed_rows
from harmonize_soc import (
    GENERATION_BY_YEAR,
    HarmonizationResult,
    build_harmonized_units,
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


class TestBuildHarmonizedUnits:
    """
    Synthetic three-generation world exercising a relabel, a merge, a split
    through a residual, an OEWS aggregate, and a discontinued code.
    """

    def _write_fixture_crosswalks(self, tmp_path):
        crosswalk_dir = tmp_path / "crosswalks"
        crosswalk_dir.mkdir()
        padding_rows = [[None] * 4] * 8
        soc_2000_to_2010 = pd.DataFrame(
            padding_rows
            + [["2000 SOC code", "2000 SOC title", "2010 SOC code", "2010 SOC title"], [None] * 4]
            + [
                ["15-1031", "Software engineers, applications", "15-1132", "Software Developers, Applications"],
                ["15-1099", "Computer specialists, all other", "15-1132", "Software Developers, Applications"],
                ["15-1099", "Computer specialists, all other", "15-1199", "Computer Occupations, All Other"],
                ["11-9011", "Farm managers", "11-9013", "Farmers, Ranchers, and Other Agricultural Managers"],
                ["11-9012", "Farmers and ranchers", "11-9013", "Farmers, Ranchers, and Other Agricultural Managers"],
                ["43-0001", "Discontinued clerks", "43-0002", "Discontinued clerks"],
            ]
        )
        soc_2000_to_2010.to_excel(crosswalk_dir / "soc_2000_to_2010_crosswalk.xlsx", header=False, index=False)
        soc_2010_to_2018 = pd.DataFrame(
            [[None] * 4] * 9
            + [["2010 SOC Code", "2010 SOC Title", "2018 SOC Code", "2018 SOC Title"]]
            + [
                ["15-1132", "Software Developers, Applications", "15-1252", "Software Developers"],
                ["15-1199", "Computer Occupations, All Other (#)", "15-1299", "Computer Occupations, All Other (##)"],
                [
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                ],
                ["29-1141", "Registered Nurses", "29-1141", "Registered Nurses"],
            ]
        )
        soc_2010_to_2018.to_excel(crosswalk_dir / "soc_2010_to_2018_crosswalk.xlsx", header=False, index=False)
        hybrid = pd.DataFrame(
            [[None] * 9] * 6
            + [
                [
                    "15-1252",
                    "Software Developers",
                    "15-1252",
                    "Software Developers",
                    "15-1132",
                    "Software Developers, Applications",
                    "15-1132",
                    "Software Developers, Applications",
                    None,
                ],
                [
                    "15-1299",
                    "Computer Occupations, All Other",
                    "15-1299",
                    "Computer Occupations, All Other",
                    "15-1199",
                    "Computer Occupations, All Other",
                    "15-1199",
                    "Computer Occupations, All Other",
                    None,
                ],
                [
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    "11-9013",
                    "Farmers, Ranchers, and Other Agricultural Managers",
                    None,
                ],
                [
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    "29-1141",
                    "Registered Nurses",
                    None,
                ],
            ]
        )
        with pd.ExcelWriter(crosswalk_dir / "oes_2019_hybrid_structure.xlsx") as writer:
            hybrid.to_excel(writer, sheet_name="OES2019 Hybrid", header=False, index=False)
        aggregate_path = tmp_path / "oews_aggregate_codes.csv"
        pd.DataFrame(
            {
                "generation": ["soc2010"],
                "oews_code": ["29-1111"],
                "oews_title": ["Registered Nurses*"],
                "member_soc_code": ["29-1141"],
                "source": ["title"],
            }
        ).to_csv(aggregate_path, index=False)
        return str(crosswalk_dir), str(aggregate_path)

    def _oews_codes_by_year(self):
        return {
            "09": pd.DataFrame(
                {"OCC_CODE": ["15-1031", "15-1099", "11-9011", "11-9012", "43-0001"], "OCC_TITLE": ["a", "b", "c", "d", "e"]}
            ),
            "10": pd.DataFrame(
                {"OCC_CODE": ["15-1132", "15-1199", "11-9013", "29-1111", "43-0002"], "OCC_TITLE": ["a", "b", "c", "d", "e"]}
            ),
            "18": pd.DataFrame({"OCC_CODE": ["15-1132", "15-1199", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
            "19": pd.DataFrame({"OCC_CODE": ["15-1252", "15-1299", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
            "22": pd.DataFrame({"OCC_CODE": ["15-1252", "15-1299", "11-9013", "29-1141"], "OCC_TITLE": ["a", "b", "c", "d"]}),
        }

    def test_relabel_chain_forms_one_unit_and_residual_edge_is_pruned(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        assert isinstance(result, HarmonizationResult)
        developers_2009 = result.membership_df.query("year == '09' and oews_code == '15-1031'")["unit_id"].iloc[0]
        developers_2022 = result.membership_df.query("year == '22' and oews_code == '15-1252'")["unit_id"].iloc[0]
        assert developers_2009 == developers_2022 == "U-15-1252"
        residual_2009 = result.membership_df.query("year == '09' and oews_code == '15-1099'")["unit_id"].iloc[0]
        assert residual_2009 == "U-15-1299"
        assert len(result.pruned_edges_df) == 1
        assert result.pruned_edges_df.iloc[0]["from_code"] == "15-1099"
        assert result.pruned_edges_df.iloc[0]["to_code"] == "15-1132"

    def test_merge_and_aggregate_seed_land_in_one_unit(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        farm_units = set(result.membership_df.query("year == '09' and oews_code in ['11-9011', '11-9012']")["unit_id"])
        assert farm_units == {"U-11-9013"}
        nurses_2010 = result.membership_df.query("year == '10' and oews_code == '29-1111'")["unit_id"].iloc[0]
        assert nurses_2010 == "U-29-1141"

    def test_discontinued_codes_get_a_discontinued_unit(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path)
        clerks_unit = result.membership_df.query("year == '10' and oews_code == '43-0002'")["unit_id"].iloc[0]
        assert clerks_unit == "U-43-0001-discontinued"
        assert result.unit_summary_df.set_index("unit_id").loc[clerks_unit, "discontinued"]

    def test_completeness_marks_years_missing_a_member(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        oews_codes_by_year = self._oews_codes_by_year()
        oews_codes_by_year["18"] = oews_codes_by_year["18"][oews_codes_by_year["18"]["OCC_CODE"] != "11-9013"]
        result = build_harmonized_units(oews_codes_by_year, crosswalk_dir, aggregate_path)
        completeness = result.completeness_df.set_index(["unit_id", "year"])["complete"]
        assert not completeness.loc[("U-11-9013", "18")]
        assert completeness.loc[("U-11-9013", "10")]
        assert completeness.loc[("U-15-1252", "09")]

    def test_no_pruning_fuses_developers_with_the_residual(self, tmp_path):
        crosswalk_dir, aggregate_path = self._write_fixture_crosswalks(tmp_path)
        result = build_harmonized_units(self._oews_codes_by_year(), crosswalk_dir, aggregate_path, prune_residual_edges=False)
        developers = result.membership_df.query("year == '22' and oews_code == '15-1252'")["unit_id"].iloc[0]
        residual = result.membership_df.query("year == '22' and oews_code == '15-1299'")["unit_id"].iloc[0]
        assert developers == residual
        assert result.pruned_edges_df.empty
