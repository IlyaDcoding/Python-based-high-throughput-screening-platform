from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hec_screen.__main__ import main
from hec_screen.dataset import load_json, load_observations
from hec_screen.screening import screen

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data/hec_measurements.csv"
XLSX = ROOT / "data/hec_measurements.xlsx"
CONFIG = ROOT / "configs/tbc.json"


def test_packaged_workbook_matches_csv():
    csv_data, csv_issues = load_observations([CSV])
    xlsx_data, xlsx_issues = load_observations([XLSX])
    assert csv_issues.empty and xlsx_issues.empty
    assert len(csv_data) == 106
    assert csv_data["material_id"].nunique() == 31
    assert csv_data["doi"].nunique() == 4
    pd.testing.assert_frame_equal(csv_data.drop(columns="input_file"), xlsx_data.drop(columns="input_file"))


def test_verified_ranking_matches_independent_values_and_weight_perturbation():
    data, _ = load_observations([CSV])
    result = screen(data, load_json(CONFIG))
    ranks = result["rankings"]
    assert ranks["material_id"].tolist() == ["SGDETZO", "GDHETZO", "GDHEYZO"]
    np.testing.assert_allclose(ranks["score"], [1, .35 * .50 / .59, .65 * .06 / .14])
    assert result["evidence"]["doi"].unique().tolist() == ["10.3390/coatings16010079"]
    cases = result["sensitivity"]
    assert cases.query("material_id == 'SGDETZO'")["rank"].tolist() == [1] * 5
    assert cases.query("material_id == 'GDHETZO'")["rank"].tolist() == [2, 2, 3, 3, 2]


def test_cli_exports_reproducible_tables_and_plots(tmp_path):
    path = tmp_path / "run"
    assert main(["screen", str(CSV), "--config", str(CONFIG), "--output", str(path), "--top", "2"]) == 0
    shortlist = pd.read_csv(path / "shortlist.csv")
    assert shortlist["material_id"].tolist() == ["SGDETZO", "GDHETZO"]
    xlsx = pd.read_excel(path / "screening.xlsx", sheet_name="Shortlist")
    pd.testing.assert_frame_equal(shortlist, xlsx, check_exact=False, check_dtype=False)
    for name in ("ranking", "properties", "sensitivity"):
        assert (path / f"{name}.png").read_bytes().startswith(b"\x89PNG")
    assert main(["screen", str(CSV), "--config", str(CONFIG), "--output", str(path)]) == 2


def test_cli_validate_audits_invalid_data_without_exporting_partial_dataset(tmp_path):
    invalid = tmp_path / "bad.csv"
    content = CSV.read_text(encoding="utf-8")
    invalid.write_text(content.replace("W/(m*K)", "nonsense", 1), encoding="utf-8")
    output = tmp_path / "run"
    assert main(["validate", str(invalid), "--output", str(output)]) == 2
    assert not (output / "measurements.csv").exists()
    audit = pd.read_csv(output / "validation.csv")
    assert audit["code"].tolist() == ["invalid_unit_or_property"]

