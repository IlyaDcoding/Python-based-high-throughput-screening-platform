import csv
import math
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from hec_screen.dataset import load_json, load_observations, write_tables
from hec_screen.schema import COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def observation(**changes):
    return {
        "material_id": "NA", "composition": "Fixture A", "family": "test",
        "material_class": "test", "specimen_form": "bulk", "applications": "coating",
        "property": "thermal_conductivity", "value": 1580, "unit": "mW/(m*K)",
        "uncertainty": 20, "uncertainty_type": "synthetic interval", "temperature_c": 25,
        "method": "test method", "basis": "test basis", "cohort": "test-k",
        "data_type": "synthetic", "publication_title": "Synthetic unit tests",
        "source_locator": "Generated test rows", **changes,
    }


def save_observations(tmp_path, rows, name="test.csv"):
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_same_observation_after_unit_conversion_and_application_merge(tmp_path):
    first = save_observations(tmp_path, [observation()])
    second = save_observations(tmp_path, [observation(value=1.58, unit="W/(m*K)", uncertainty=.02,
                                                     applications="insulation")], "peer.csv")
    data, issues = load_observations([first, second])
    assert len(data) == 1
    row = data.iloc[0]
    assert row["material_id"] == "NA"
    assert row["value_canonical"] == pytest.approx(1.58)
    assert row["uncertainty_canonical"] == pytest.approx(.02)
    assert row["unit"] == "mW/(m*K)"
    assert row["applications"] == "coating;insulation"
    assert issues["code"].tolist() == ["duplicate"]
    assert issues.iloc[0]["input_file"] == str(second)


def test_blank_and_na_remain_missing_but_real_zero_survives(tmp_path):
    path = save_observations(tmp_path, [
        observation(value="", uncertainty=""),
        observation(material_id="B", value="N/A", uncertainty=""),
        observation(material_id="C", property="dielectric_loss", unit="1", value=0, uncertainty=""),
    ])
    data, issues = load_observations([path])
    assert data["value"].isna().tolist() == [True, True, False]
    assert math.isnan(data.iloc[0]["value_canonical"])
    assert data.iloc[2]["value_canonical"] == 0
    assert issues["code"].tolist() == ["missing_value", "missing_value"]


def test_prefer_populated_duplicate(tmp_path):
    path = save_observations(tmp_path, [observation(value="", uncertainty=""), observation()])
    data, issues = load_observations([path])
    assert data["value"].tolist() == [1580.0]
    assert issues["code"].tolist() == ["missing_value", "replaced_missing_duplicate"]


@pytest.mark.parametrize(("updates", "code"), [
    ({"unit": "kg/m3"}, "invalid_unit_or_property"),
    ({"value": "inf"}, "invalid_number"),
    ({"uncertainty": -10}, "invalid_uncertainty"),
    ({"temperature_start_c": 26}, "invalid_temperature"),
    ({"frequency_hz": 0}, "invalid_conditions"),
    ({"data_type": "theoretical"}, "invalid_data_type"),
    ({"data_type": "experimental"}, "missing_source"),
    ({"doi": "fake"}, "invalid_doi"),
    ({"source_url": "http://[invalid"}, "invalid_url"),
    ({"value": "#REF!"}, "spreadsheet_error"),
])
def test_invalid_rows_are_audited(tmp_path, updates, code):
    path = save_observations(tmp_path, [observation(**updates)])
    data, issues = load_observations([path])
    assert data.empty
    assert code in issues["code"].tolist()
    assert set(issues["input_row"]) == {2}
    assert "error" in issues["severity"].tolist()


def test_conflicting_result_and_material_id(tmp_path):
    path = save_observations(tmp_path, [observation(), observation(value=1590),
                                       observation(composition="Fixture B")])
    data, issues = load_observations([path])
    assert len(data) == 1
    assert issues["code"].tolist() == ["conflicting_result", "conflicting_material_id"]


def test_invalid_csv_shape_and_headers(tmp_path):
    path = tmp_path / "shape.csv"
    path.write_text("Material ID,material-id\nx,y\n")
    with pytest.raises(ValueError, match="duplicate column header"):
        load_observations([path])
    path.write_text("id,name\nx,y,z\n")
    with pytest.raises(ValueError, match="row 2 has 3 fields"):
        load_observations([path])


def test_blank_rows_preserve_input_row_numbers(tmp_path):
    path = save_observations(tmp_path, [observation(), observation(value="bad", material_id="B")])
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([lines[0], "", *lines[1:]]) + "\n", encoding="utf-8")
    data, issues = load_observations([path])
    assert data["input_row"].tolist() == [3]
    assert issues["input_row"].tolist() == [4]


def test_xlsx_select_sheet_and_roundtrip(tmp_path):
    source = pd.DataFrame([observation(composition="=literal", value=None)], columns=COLUMNS)
    path = tmp_path / "table.xlsx"
    write_tables(path, {"Other": pd.DataFrame({"other": [2]}), "Peer Data": source})
    data, issues = load_observations([path], sheet="Peer Data")
    assert data.iloc[0]["composition"] == "=literal"
    assert math.isnan(data.iloc[0]["value"])
    assert set(issues["code"]) == {"missing_value"}


def test_xlsx_formula_must_be_pasted_as_literal(tmp_path):
    path = tmp_path / "formulas.xlsx"
    book = Workbook()
    book.active.append(["column"])
    book.active.append(["=1+2"])
    book.save(path)
    with pytest.raises(ValueError, match="A2 contains a formula"):
        load_observations([path])


def test_wide_mapping_describes_each_property(tmp_path):
    path = tmp_path / "peer.csv"
    pd.DataFrame([{
        "Sample ID": "E01", "Formula": "Test mix", "Material family": "oxide",
        "Material class": "complex oxide", "Structure": "test phase", "Applications": "thermal barrier coatings",
        "Origin": "synthetic", "Publication title": "Synthetic fixture", "DOI": "", "k_mW_mK": 1200,
        "k temperature C": 25, "k reference": "Fixture location 1", "CTE_ppm_K": 11,
        "CTE temperature C": 1000, "CTE reference": "Fixture location 2",
    }]).to_csv(path, index=False)
    data, issues = load_observations([path], mapping=load_json(ROOT / "configs/wide_mapping.example.json"))
    assert issues.empty
    assert data["value_canonical"].tolist() == pytest.approx([1.2, 11])
    assert data["temperature_c"].tolist() == [25, 1000]
    assert data["input_row"].tolist() == [2, 2]
    assert data["source_locator"].tolist() == ["Fixture location 1", "Fixture location 2"]

