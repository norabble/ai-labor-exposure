"""Tests for harmonize_soc.py — SOC crosswalk loading, aggregate resolution, and unit construction."""

from harmonize_soc import (
    clean_crosswalk_title,
    is_residual_title,
    load_oews_hybrid_structure,
    load_soc_2000_to_2010,
    load_soc_2010_to_2018,
)


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
