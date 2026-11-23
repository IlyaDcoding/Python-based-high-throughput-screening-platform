"""Command-line interface for validation and screening."""

import argparse
import sys
import tempfile
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

from .dataset import load_json, load_observations, write_tables
from .schema import COLUMNS
from .screening import screen


def _parser():
    parser = argparse.ArgumentParser(description="High-entropy ceramics screening")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "screen"):
        command = commands.add_parser(name)
        command.add_argument("inputs", type=Path, nargs="+", help="One or more HEC-DB CSV/XLSX files")
        command.add_argument("--sheet", help="Excel worksheet name (default: Measurements or first sheet)")
        command.add_argument("--mapping", type=Path, help="JSON mapping for an external wide table")
        command.add_argument("--output", type=Path, required=True, help="New directory for exported results")
    screening = commands.choices["screen"]
    screening.add_argument("--config", type=Path, required=True, help="Screening scenario JSON")
    screening.add_argument("--top", type=int, default=10, help="Maximum number of shortlisted candidates")
    return parser


def _publish(output, tables, workbook, result=None, top=None):
    if output.exists():
        raise ValueError(f"Output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build the run in a sibling directory so failures cannot publish a partial result.
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        target = Path(staging) / "run"
        target.mkdir()
        for name, table in tables.items():
            write_tables(target / f"{name}.csv", {name: table})
        write_tables(target / workbook, {name.title(): table for name, table in tables.items()})
        if result is not None:
            from .plots import save_plots
            save_plots(result, target, top)
        target.rename(output)


def main(argv=None):
    options = _parser().parse_args(argv)
    try:
        if options.output.exists():
            raise ValueError(f"Output directory already exists: {options.output}")
        if options.mapping and len(options.inputs) != 1:
            raise ValueError("Apply a wide mapping to one input at a time, then merge the validated CSVs")
        mapping = load_json(options.mapping) if options.mapping else None
        if options.mapping and not isinstance(mapping, dict):
            raise ValueError("A wide mapping must be a JSON object")
        data, issues = load_observations(options.inputs, options.sheet, mapping)
        errors = int(issues["severity"].eq("error").sum())
        warnings = len(issues) - errors
        print(f"Accepted observations: {len(data)} | Errors: {errors} | Warnings: {warnings}")
        if errors:
            _publish(options.output, {"validation": issues}, "validation.xlsx")
            print(f"Review {options.output / 'validation.csv'}", file=sys.stderr)
            return 2
        if options.command == "validate":
            _publish(options.output, {"measurements": data.loc[:, list(COLUMNS)], "validation": issues},
                     "validated.xlsx")
            return 0
        if options.top < 1:
            raise ValueError("--top must be positive")
        result = screen(data, load_json(options.config))
        rankings = result["rankings"]
        summary = pd.DataFrame([{
            **result["filters"], "accepted_observations": len(data), "after_metadata_filters": result["after_filters"],
            "ranked": len(rankings), "shortlisted": min(len(rankings), options.top), "shortlist_limit": options.top,
        }])
        tables = {
            "shortlist": rankings.head(options.top), "rankings": rankings, "criteria": result["criteria"],
            "summary": summary, "exclusions": result["exclusions"], "evidence": result["evidence"],
            "sensitivity": result["sensitivity"], "validation": issues,
        }
        _publish(options.output, tables, "screening.xlsx", result, options.top)
        print(f"Ranked candidates: {len(rankings)} | Export: {options.output}")
        if not rankings.empty:
            print(rankings.head(options.top)[["rank", "material_id", "score"]].to_string(index=False))
        return 0
    except (ValueError, OSError, BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

