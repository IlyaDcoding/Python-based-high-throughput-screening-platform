"""Import, validate and export traceable HEC-DB observations."""

import csv
import json
import math
import re
import textwrap
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException

from .schema import COLUMNS, CONDITION_FIELDS, NUMERIC, ORIGINS, POSITIVE_PROPERTIES, REQUIRED, unit_conversion

ISSUE_COLUMNS = ["severity", "input_file", "input_row", "code", "detail"]
DOI = re.compile(r"10\.\d{4,9}/\S+", re.I)
TABULAR_ERRORS = ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#NULL!")
MISSING_MARKERS = {"", "na", "n/a", "nan", "#n/a", "nd", "n.d.", "-", "—"}


def load_json(path):
    with open(path, encoding="utf-8-sig") as file:
        return json.load(file)


def column_name(value):
    return re.sub(r"[\s-]+", "_", str(value).strip().lower())


def read_table(path, sheet=None):
    """Read CSV or XLSX without treating literal identifiers such as NA as missing."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        try:
            with path.open(encoding="utf-8-sig", newline="") as file:
                rows = list(csv.reader(file, strict=True))
        except csv.Error as exc:
            raise ValueError(f"{path}: invalid CSV ({exc})") from exc
    elif path.suffix.lower() == ".xlsx":
        try:
            excel = load_workbook(path, read_only=True)
        except (InvalidFileException, KeyError) as exc:
            raise ValueError(f"{path}: invalid XLSX ({exc})") from exc
        try:
            selected = sheet or ("Measurements" if "Measurements" in excel.sheetnames else excel.sheetnames[0])
            if selected not in excel.sheetnames:
                raise ValueError(f"{path}: worksheet {selected!r} was not found")
            rows = []
            for cells in excel[selected].iter_rows():
                result = []
                for cell in cells:
                    if cell.data_type == "f":
                        raise ValueError(f"{path}: worksheet {selected!r} cell {cell.coordinate} contains a formula; paste its value")
                    result.append(cell.value)
                while result and result[-1] is None:
                    result.pop()
                rows.append(result)
        finally:
            excel.close()
    else:
        raise ValueError(f"{path}: expected .csv or .xlsx")
    if not rows or not rows[0]:
        raise ValueError(f"{path}: empty table")
    headers = [column_name(value) if value is not None else "" for value in rows[0]]
    if "" in headers or len(headers) != len(set(headers)):
        raise ValueError(f"{path}: blank or duplicate column header")
    body, indices = [], []
    for index, row in enumerate(rows[1:], start=2):
        if len(row) > len(headers) or (path.suffix.lower() == ".csv" and row and len(row) != len(headers)):
            raise ValueError(f"{path}: row {index} has {len(row)} fields, expected {len(headers)}")
        if any(value is not None and str(value).strip() for value in row):
            body.append(row + [""] * (len(headers) - len(row)))
            indices.append(index - 2)
    if not body:
        raise ValueError(f"{path}: no data rows")
    if "_input_row" in headers:
        raise ValueError(f"{path}: _input_row is reserved for import diagnostics")
    return pd.DataFrame(body, columns=headers, index=indices, dtype=object)


def map_wide(frame, mapping):
    """Map explicitly specified wide-table columns and constants to long observations."""
    common_fields = set(COLUMNS) - {"property", "value", "unit", "uncertainty"}
    property_fields = set(COLUMNS) - {"material_id", "composition", "family", "material_class"}
    allowed_groups = {"columns", "defaults", "properties"}
    if not isinstance(mapping, dict) or set(mapping) - allowed_groups:
        raise ValueError("Wide mapping expects columns, defaults and properties")
    properties = mapping.get("properties", [])
    if not isinstance(properties, list) or not properties:
        raise ValueError("Wide mapping requires a nonempty properties list")

    def build(fields, columns, defaults, allowed):
        if not isinstance(columns, dict) or not isinstance(defaults, dict):
            raise ValueError("Mapping columns and defaults must be objects")
        if (set(columns) | set(defaults)) - allowed:
            raise ValueError("Wide mapping contains an unknown or misplaced target field")
        for target, value in defaults.items():
            fields[target] = value
        for target, name in columns.items():
            key = column_name(name)
            if key not in frame:
                raise ValueError(f"Mapped column {name!r} was not found")
            fields[target] = frame[key]
        return fields

    common = build(pd.DataFrame(index=frame.index), mapping.get("columns", {}),
                   mapping.get("defaults", {}), common_fields)
    converted = []
    for spec in properties:
        if not isinstance(spec, dict) or set(spec) - {"columns", "defaults"}:
            raise ValueError("Each property mapping expects columns and defaults")
        part = build(common.copy(), spec.get("columns", {}), spec.get("defaults", {}), property_fields)
        if not {"property", "value", "unit"}.issubset(part.columns):
            raise ValueError("Each property mapping requires property, value and unit")
        part["_input_row"] = frame.index + 2
        converted.append(part)
    return pd.concat(converted, ignore_index=True).fillna("")


def _number(value):
    if value.casefold() in MISSING_MARKERS:
        return math.nan
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("expected a finite number")
    return number


def _url_ok(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not any(c.isspace() for c in value)
    except ValueError:
        return False


def _key(row, fields):
    values = []
    for name in fields:
        value = row[name]
        values.append(None if pd.isna(value) else value.casefold() if isinstance(value, str) else value)
    return tuple(values)


def _validate_row(raw, report):
    row = {name: str(raw.get(name, "")).strip() if pd.notna(raw.get(name, "")) else "" for name in COLUMNS}
    for name in ("family", "material_class", "property", "data_type", "cohort"):
        row[name] = row[name].casefold()
    row["applications"] = ";".join(sorted({item.strip().casefold()
                                            for item in row["applications"].split(";") if item.strip()}))
    for name in sorted(REQUIRED - {"value"}):
        if not row[name]:
            report("error", "missing_field", name)
    for name in COLUMNS:
        if row[name] in TABULAR_ERRORS:
            report("error", "spreadsheet_error", name)
    if row["data_type"] not in ORIGINS:
        report("error", "invalid_data_type", row["data_type"])
    if row["doi"]:
        row["doi"] = re.sub(r"^(https?://(?:dx\.)?doi\.org/|doi:\s*)", "", row["doi"], flags=re.I).lower()
        if not DOI.fullmatch(row["doi"]):
            report("error", "invalid_doi", row["doi"])
    if row["source_url"] and not _url_ok(row["source_url"]):
        report("error", "invalid_url", row["source_url"])
    if row["data_type"] != "synthetic" and not (row["doi"] or row["source_url"]):
        report("error", "missing_source", "Supply a DOI or source URL")

    missing_value = row["value"].casefold() in MISSING_MARKERS
    for name in NUMERIC:
        try:
            row[name] = _number(row[name])
        except ValueError:
            report("error", "invalid_number", f"{name}={row[name]!r}")
            row[name] = math.nan
    if missing_value:
        report("warning", "missing_value", row["property"])
    if row["uncertainty"] < 0:
        report("error", "invalid_uncertainty", "Uncertainty must be nonnegative")
    if pd.notna(row["uncertainty"]) and not row["uncertainty_type"]:
        report("warning", "missing_uncertainty_type", "Specify the nature of the reported ± value if known")
    if (row["temperature_c"] < -273.15
            or row["temperature_start_c"] < -273.15
            or row["temperature_start_c"] > row["temperature_c"]
            or (pd.notna(row["temperature_start_c"]) and pd.isna(row["temperature_c"]))):
        report("error", "invalid_temperature", "Check temperature bounds in degC")
    if row["frequency_hz"] <= 0 or row["pressure_kpa"] < 0:
        report("error", "invalid_conditions", "Frequency must be positive and pressure nonnegative")
    if not all(row[name] for name in ("cohort", "specimen_form", "method", "basis")):
        report("warning", "unclassified_conditions", "Cohort, form, method and basis are required for screening")
    try:
        row["unit_canonical"], factor, offset = unit_conversion(row["property"], row["unit"])
        row["value_canonical"] = row["value"] * factor + offset
        row["uncertainty_canonical"] = row["uncertainty"] * abs(factor)
        for name in ("value", "uncertainty"):
            if pd.notna(row[name]) and not math.isfinite(row[f"{name}_canonical"]):
                report("error", "conversion_overflow", name)
        value = row["value_canonical"]
        if ((row["property"] in POSITIVE_PROPERTIES and value <= 0)
                or (row["property"] in {"relative_density", "efficiency"} and value > 100)
                or (row["property"] in {"efficiency", "dielectric_loss", "energy_storage_density",
                                        "electrical_conductivity"} and value < 0)
                or (row["unit_canonical"] == "degC" and value < -273.15)):
            report("error", "invalid_property_value", row["property"])
    except ValueError as exc:
        report("error", "invalid_unit_or_property", str(exc))
    return row


def load_observations(paths, sheet=None, mapping=None):
    """Read observations and return validated rows plus a file/row-level audit."""
    observations, issues = [], []
    known_results, known_materials = {}, {}
    for path in paths:
        frame = read_table(path, sheet)
        if mapping is not None:
            frame = map_wide(frame, mapping)
        missing = REQUIRED - set(frame.columns)
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
        for index, raw in zip(frame.index, frame.to_dict("records")):
            input_row = int(raw.get("_input_row", index + 2))
            start = len(issues)

            def report(severity, code, detail):
                issues.append(dict(zip(ISSUE_COLUMNS, (severity, str(path), input_row, code, detail))))

            row = _validate_row(raw, report)
            if any(issue["severity"] == "error" for issue in issues[start:]):
                continue
            material_fields = ("composition", "family", "material_class", "crystal_structure", "specimen_form",
                               "synthesis_method", "processing_conditions")
            material = known_materials.get(row["material_id"], {})
            if any(material.get(name) and row[name] and material[name] != row[name] for name in material_fields):
                report("error", "conflicting_material_id", row["material_id"])
                continue
            source = row["doi"] or row["source_url"] or row["publication_title"]
            result_fields = ("property", "data_type", "replicate_id", *CONDITION_FIELDS)
            key = (row["material_id"], *_key(row, result_fields), source)
            if key in known_results:
                previous = known_results[key]
                applications = ";".join(sorted(set(row["applications"].split(";") + previous["applications"].split(";"))))
                if pd.isna(previous["value"]) != pd.isna(row["value"]):
                    # Prefer the real observation to an explicit placeholder for the same result.
                    if pd.isna(row["value"]):
                        previous["applications"] = applications
                        report("warning", "missing_duplicate", "Retained the existing measurement")
                        continue
                    report("warning", "replaced_missing_duplicate", "Retained the populated measurement")
                    observations.remove(previous)
                    row["applications"] = applications
                elif (_key(row, ("cohort", "uncertainty_type"))
                      == _key(previous, ("cohort", "uncertainty_type")) and all(
                          (pd.isna(previous[name]) and pd.isna(row[name]))
                          or math.isclose(previous[name], row[name], rel_tol=1e-12, abs_tol=0.0)
                          for name in ("value_canonical", "uncertainty_canonical"))):
                    previous["applications"] = applications
                    report("warning", "duplicate", f"Retained {previous['input_file']} row {previous['input_row']}")
                    continue
                else:
                    report("error", "conflicting_result", f"Compare {previous['input_file']} row {previous['input_row']}")
                    continue
            row.update(input_file=str(path), input_row=input_row)
            known_results[key] = row
            known_materials[row["material_id"]] = {name: row[name] or material.get(name, "")
                                                   for name in material_fields}
            observations.append(row)
    columns = [*COLUMNS, "value_canonical", "unit_canonical", "uncertainty_canonical", "input_file", "input_row"]
    data = pd.DataFrame(observations, columns=columns)
    return data, pd.DataFrame(issues, columns=ISSUE_COLUMNS)


def write_tables(path, tables):
    """Write one CSV or an XLSX with a named worksheet for each output table."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".csv" and len(tables) == 1:
        next(iter(tables.values())).to_csv(path, index=False, encoding="utf-8-sig")
    elif path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for name, frame in tables.items():
                frame.to_excel(writer, sheet_name=name, index=False, freeze_panes=(1, 0))
                worksheet = writer.sheets[name]
                worksheet.auto_filter.ref = worksheet.dimensions
                worksheet.sheet_view.showGridLines = False
                worksheet.row_dimensions[1].height = 26
                wrapped = Alignment(wrap_text=True, vertical="center")
                header_font = Font(bold=True, color="FFFFFF")
                header_fill = PatternFill("solid", fgColor="183D52")
                for column in worksheet.iter_cols():
                    header = column[0]
                    header.font, header.fill, header.alignment = header_font, header_fill, wrapped
                    longest = max(len(str(cell.value or "")) for cell in column)
                    width = min(54, max(13, longest + 4))
                    worksheet.column_dimensions[header.column_letter].width = width
                    for cell in column[1:]:
                        if cell.data_type in {"e", "f"}:
                            cell.data_type = "s"
                        if isinstance(cell.value, str) and len(cell.value) > width - 4:
                            cell.alignment = wrapped
                            row = worksheet.row_dimensions[cell.row]
                            row.height = max(row.height or 15, 15 * len(textwrap.wrap(cell.value, width - 4)) + 5)
                        if header.value == "score" or str(header.value).startswith("normalized_"):
                            cell.number_format = "0.000000"
    else:
        raise ValueError("Export expects a single table for .csv or named tables for .xlsx")

