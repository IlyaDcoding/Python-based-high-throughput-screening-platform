import numpy as np
import pytest

from hec_screen.dataset import load_observations
from hec_screen.screening import min_max, normalize_weights, score_and_rank, screen

from test_dataset import observation, save_observations


@pytest.mark.parametrize(("direction", "expected"), [("max", [0, .25, 1]), ("min", [1, .75, 0])])
def test_min_max_known_vector(direction, expected):
    actual, constant = min_max([2, 3, 6], direction)
    np.testing.assert_allclose(actual, expected)
    assert not constant


def test_constant_near_equal_small_and_extreme_ranges():
    np.testing.assert_array_equal(min_max([10, 10], "min")[0], [.5, .5])
    assert min_max([1, 1 + 1e-13], "max")[1]
    np.testing.assert_allclose(min_max([1e-20, 2e-20], "min")[0], [1, 0])
    np.testing.assert_allclose(min_max([-1.7e308, 0, 1.7e308], "max")[0], [0, .5, 1])
    with pytest.raises(ValueError, match="finite vector"):
        min_max([1, np.nan], "min")


@pytest.mark.parametrize("weights", [[0, 0], [-1, 2], [1, np.inf], []])
def test_invalid_weights(weights):
    with pytest.raises(ValueError, match="Weights"):
        normalize_weights(weights)


def test_huge_weights_and_float_ties():
    np.testing.assert_array_equal(normalize_weights([1.7e308, 1.7e308, 0]), [.5, .5, 0])
    scores, ranks = score_and_rank(np.array([[.5, .5], [.5 + 1e-14, .5], [0, 0]]), [.5, .5])
    assert scores[1] > scores[0]
    assert ranks.tolist() == [1, 1, 3]


def _scenario():
    return {
        "application": "coating", "family": "test", "origin": "synthetic",
        "criteria": [
            {"property": "thermal_conductivity", "direction": "min", "weight": 3, "max": 6},
            {"property": "thermal_expansion", "direction": "max", "weight": 1},
            {"property": "hardness", "direction": "max", "weight": 0},
        ],
    }


def _fixtures():
    rows = []
    for material, k, cte in (("A", 2, 8), ("B", 4, 10), ("C", 6, 12),
                             ("MISSING", 1, ""), ("LIMIT", 7, 13), ("OTHER", 1, 14),
                             ("AMBIGUOUS", 2, 11)):
        tags = "other" if material == "OTHER" else "coating;insulation"
        rows.append(observation(material_id=material, value=k, unit="W/(m*K)", applications=tags))
        rows.append(observation(material_id=material, property="thermal_expansion", value=cte,
                                unit="ppm/K", cohort="cte", applications="another application"))
    rows.append(observation(material_id="AMBIGUOUS", value=3, unit="W/(m*K)", replicate_id="second"))
    rows.append(observation(material_id="SIM", value=2, unit="W/(m*K)",
                            data_type="computational", source_url="https://example.invalid/test-only"))
    return rows


def test_hand_calculation_and_exclusions(tmp_path):
    data, _ = load_observations([save_observations(tmp_path, _fixtures())])
    result = screen(data, _scenario())
    rankings = result["rankings"]
    assert rankings["material_id"].tolist() == ["A", "B", "C"]
    assert rankings["score"].tolist() == pytest.approx([.75, .5, .25])
    assert dict(zip(result["exclusions"]["material_id"], result["exclusions"]["reason"])) == {
        "AMBIGUOUS": "multiple_observations", "LIMIT": "outside_limits", "MISSING": "missing_comparable_value",
    }
    for weights in result["sensitivity"].groupby("scenario"):
        assert weights[1].filter(like="weight_").sum(axis=1).tolist() == pytest.approx([1, 1, 1])
    assert len(result["sensitivity"]) == 15


def test_zero_weight_constraint_still_filters(tmp_path):
    hardness = observation(material_id="A", property="hardness", value=5, unit="GPa", cohort="hardness")
    data, _ = load_observations([save_observations(tmp_path, [*_fixtures(), hardness])])
    scenario = _scenario()
    scenario["criteria"][-1]["min"] = 4
    result = screen(data, scenario)
    assert result["rankings"]["material_id"].tolist() == ["A"]
    assert result["rankings"]["score"].tolist() == [.5]


def test_incompatible_temperature_same_cohort_is_rejected(tmp_path):
    data, _ = load_observations([save_observations(tmp_path, [
        observation(), observation(material_id="B", temperature_c=1000),
    ])])
    with pytest.raises(ValueError, match="incompatible conditions"):
        screen(data, _scenario())


def test_unknown_key_conditions_cannot_pool_sources(tmp_path):
    data, _ = load_observations([save_observations(tmp_path, [
        observation(data_type="experimental", source_url="https://example.invalid/a", temperature_c=""),
        observation(data_type="experimental", source_url="https://example.invalid/b", temperature_c="", material_id="B"),
    ])])
    config = _scenario()
    config["origin"] = "experimental"
    with pytest.raises(ValueError, match="missing key conditions"):
        screen(data, config)


def test_empty_pool_is_a_valid_result(tmp_path):
    data, _ = load_observations([save_observations(tmp_path, _fixtures())])
    config = _scenario()
    config["family"] = "nonexistent"
    result = screen(data, config)
    assert result["rankings"].empty
    assert result["evidence"].empty
    assert result["criteria"].shape[0] == 2

