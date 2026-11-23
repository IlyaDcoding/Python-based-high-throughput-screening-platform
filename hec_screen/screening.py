"""Comparable observations, min–max scaling and weighted screening."""

import math

import numpy as np
import pandas as pd

from .schema import CONDITION_FIELDS, ORIGINS, UNITS

RANGE_RTOL = 1e-12
SCORE_DECIMALS = 12
SENSITIVITY_FRACTION = 0.2


def _finite_number(value, label):
    try:
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{label} must be a finite number")
    return value


def normalize_config(config):
    """Validate a screening scenario; limits use canonical property units."""
    if not isinstance(config, dict) or set(config) - {"family", "application", "material_class", "origin", "criteria"}:
        raise ValueError("Scenario expects family, application, material_class, origin and criteria")
    origin = config.get("origin", "experimental")
    if not isinstance(origin, str) or origin not in ORIGINS:
        raise ValueError("Specify one valid origin for the whole run")
    filters = {"origin": origin}
    for name in ("family", "application", "material_class"):
        value = config.get(name, "")
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        filters[name] = value.strip().casefold()

    criteria = config.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("criteria must be a nonempty list")
    checked = {}
    for criterion in criteria:
        if not isinstance(criterion, dict) or set(criterion) - {"property", "direction", "weight", "min", "max", "cohort"}:
            raise ValueError("Invalid criterion fields")
        prop = criterion.get("property")
        if not isinstance(prop, str) or prop not in UNITS or prop in checked:
            raise ValueError(f"Unknown or repeated criterion property {prop!r}")
        direction = criterion.get("direction")
        if direction not in ("min", "max"):
            raise ValueError(f"{prop}: direction must be min or max")
        weight = _finite_number(criterion.get("weight"), f"{prop} weight")
        if weight < 0:
            raise ValueError(f"{prop}: weight must be nonnegative")
        lower, upper = criterion.get("min"), criterion.get("max")
        if lower is not None:
            _finite_number(lower, f"{prop} min")
        if upper is not None:
            _finite_number(upper, f"{prop} max")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"{prop}: min must be <= max")
        cohort = criterion.get("cohort", "")
        if not isinstance(cohort, str):
            raise ValueError(f"{prop}: cohort must be a string")
        checked[prop] = dict(direction=direction, weight=weight, min=lower, max=upper, cohort=cohort.strip().casefold())
    if not any(item["weight"] > 0 for item in checked.values()):
        raise ValueError("At least one criterion must have positive weight")
    return filters, checked


def min_max(values, direction):
    """Normalize a finite, nonempty vector. A constant criterion is neutral."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise ValueError("Min–max scaling requires a nonempty finite vector")
    if direction not in ("min", "max"):
        raise ValueError("direction must be min or max")
    low, high = float(values.min()), float(values.max())
    span = high - low
    if math.isclose(low, high, rel_tol=RANGE_RTOL, abs_tol=0):
        return np.full(values.shape, 0.5), True
    if not math.isfinite(span):
        # Avoid overflow for finite endpoints of opposite sign near float limits.
        scale = max(abs(low), abs(high))
        values, low, high = values / scale, low / scale, high / scale
        span = high - low
    scaled = (values - low) / span if direction == "max" else (high - values) / span
    return np.clip(scaled, 0, 1), False


def normalize_weights(raw):
    """Scale before summation so even large finite weights can be normalized."""
    raw = np.asarray(raw, dtype=float)
    if raw.ndim != 1 or not raw.size or not np.isfinite(raw).all() or (raw < 0).any() or raw.max() == 0:
        raise ValueError("Weights must be finite, nonnegative and have a positive sum")
    relative = raw / raw.max()
    return relative / relative.sum()


def score_and_rank(matrix, weights):
    scores = np.clip(matrix @ weights, 0, 1)
    rank_key = pd.Series(scores.round(SCORE_DECIMALS))
    return scores, rank_key.rank(method="min", ascending=False).to_numpy(dtype=int)


def _cohort_observations(rows, prop, requested):
    """Refuse pooled comparisons if records differ in their declared basis."""
    candidates = rows.loc[rows["property"].eq(prop)].copy()
    if requested:
        candidates = candidates.loc[candidates["cohort"].eq(requested)]
    candidates = candidates.loc[candidates["value_canonical"].notna()]
    if candidates.empty:
        return candidates
    required_labels = ["cohort", "specimen_form", "method", "basis"]
    if candidates[required_labels].eq("").any().any():
        raise ValueError(f"{prop}: observations need cohort, form, method and basis")
    fields = ["cohort", *CONDITION_FIELDS]
    fingerprints = candidates[fields].copy()
    for name in fingerprints.select_dtypes(exclude="number"):
        fingerprints[name] = fingerprints[name].str.casefold()
    if len(fingerprints.drop_duplicates()) != 1:
        available = ", ".join(sorted(candidates["cohort"].unique()))
        raise ValueError(f"{prop}: incompatible conditions or cohorts ({available}). Choose one comparable cohort.")
    # Unspecified conditions can be defended within a study, but not silently pooled across studies.
    unspecified = candidates["temperature_c"].isna().any()
    if prop in {"dielectric_constant", "dielectric_loss"}:
        unspecified |= candidates["frequency_hz"].isna().any()
    source = candidates["doi"].where(candidates["doi"].ne(""), candidates["source_url"])
    if unspecified and source.nunique() > 1:
        raise ValueError(f"{prop}: missing key conditions for a cross-source comparison")
    return candidates


def _violates(value, lower, upper):
    below = lower is not None and value < lower and not math.isclose(value, lower, rel_tol=RANGE_RTOL)
    above = upper is not None and value > upper and not math.isclose(value, upper, rel_tol=RANGE_RTOL)
    return below or above


def _sensitivity(ids, matrix, raw_weights, active, scores, ranks):
    result = []
    base_weights = normalize_weights(raw_weights)

    def add(label, weights, scenario_scores, scenario_ranks):
        for index, material in enumerate(ids):
            result.append({
                "scenario": label, "material_id": material, "score": scenario_scores[index],
                "rank": scenario_ranks[index], "rank_change": scenario_ranks[index] - ranks[index],
                **{f"weight_{name}": value for name, value in zip(active, weights)},
            })

    add("baseline", base_weights, scores, ranks)
    if len(active) > 1:
        # Multiplying relative weights avoids overflow for large user inputs.
        relative = raw_weights / raw_weights.max()
        for index, prop in enumerate(active):
            for delta in (-SENSITIVITY_FRACTION, SENSITIVITY_FRACTION):
                changed = relative.copy()
                changed[index] *= 1 + delta
                weight = normalize_weights(changed)
                perturbed_scores, perturbed_ranks = score_and_rank(matrix, weight)
                add(f"{prop} {delta:+.0%}", weight, perturbed_scores, perturbed_ranks)
    return pd.DataFrame(result, columns=["scenario", "material_id", "score", "rank", "rank_change",
                                        *[f"weight_{name}" for name in active]])


def screen(data, config):
    """Return ranked candidates, exclusions, source observations and weight scenarios."""
    filters, criteria = normalize_config(config)
    active = [prop for prop, item in criteria.items() if item["weight"] > 0]
    used = {prop: item for prop, item in criteria.items()
            if item["weight"] or item["min"] is not None or item["max"] is not None}
    scoped = data.loc[data["data_type"].eq(filters["origin"])]
    for field in ("family", "material_class"):
        if filters[field]:
            scoped = scoped.loc[scoped[field].eq(filters[field])]
    if filters["application"]:
        matches = scoped["applications"].str.split(";").map(lambda items: filters["application"] in items)
        matching_ids = scoped.loc[matches.astype(bool), "material_id"]
        scoped = scoped.loc[scoped["material_id"].isin(matching_ids)]
    materials = scoped[["material_id", "composition", "family", "material_class"]].drop_duplicates("material_id")
    rankings = materials.set_index("material_id").sort_index()
    excluded, trace_parts, criterion_info = [], [], []
    for prop, item in used.items():
        selected = _cohort_observations(scoped, prop, item["cohort"])
        trace_parts.append(selected)
        ambiguous = set(selected.loc[selected["material_id"].duplicated(keep=False), "material_id"])
        unique = selected.loc[~selected["material_id"].isin(ambiguous)].set_index("material_id")
        rankings[prop] = unique["value_canonical"]
        for material, value in rankings[prop].items():
            if material in ambiguous:
                excluded.append((material, prop, "multiple_observations"))
            elif pd.isna(value):
                excluded.append((material, prop, "missing_comparable_value"))
            elif _violates(value, item["min"], item["max"]):
                excluded.append((material, prop, "outside_limits"))
        context = selected.iloc[0] if not selected.empty else {}
        criterion_info.append({
            "property": prop, **item, "cohort": context.get("cohort", item["cohort"]),
            "unit": UNITS[prop][0], **{name: context.get(name) for name in CONDITION_FIELDS},
        })

    exclusions = pd.DataFrame(excluded, columns=["material_id", "property", "reason"])
    rankings = rankings.drop(index=exclusions["material_id"].unique())
    raw_weights = np.array([criteria[prop]["weight"] for prop in active], dtype=float)
    weights = dict(zip(active, normalize_weights(raw_weights)))
    for row in criterion_info:
        prop = row["property"]
        row.update(weight_normalized=weights.get(prop, 0), value_min=rankings[prop].min(),
                   value_max=rankings[prop].max(), constant=None)
        if prop in active:
            if rankings.empty:
                rankings[f"normalized_{prop}"] = pd.Series(dtype=float)
            else:
                scaled, constant = min_max(rankings[prop], row["direction"])
                rankings[f"normalized_{prop}"] = scaled
                row["constant"] = constant
    matrix = rankings[[f"normalized_{prop}" for prop in active]].to_numpy()
    scores, ranks = score_and_rank(matrix, np.array(list(weights.values())))
    sensitivity = _sensitivity(rankings.index, matrix, raw_weights, active, scores, ranks)
    rankings.insert(0, "rank", ranks)
    rankings.insert(1, "score", scores)
    rankings = rankings.reset_index().sort_values(["rank", "material_id"], kind="stable")
    evidence = pd.concat([part for part in trace_parts if not part.empty], ignore_index=True) if any(
        not part.empty for part in trace_parts) else data.iloc[0:0].copy()
    return {
        "rankings": rankings, "exclusions": exclusions, "sensitivity": sensitivity,
        "evidence": evidence, "criteria": pd.DataFrame(criterion_info), "after_filters": len(materials),
        "filters": filters,
    }

