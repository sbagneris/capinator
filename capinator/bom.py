"""Reusable BOM-building logic, extracted from the old ``capinator.py`` CLI so it can
be shared by the CLI and the web worker. Decoupled from file I/O and ``print``:

- ``parse_spec``  — pasted CSV text  -> list of per-component dicts (keys from the header)
- ``build_bom``   — component dicts + a DigiKey client -> resolved output lines / errors
- ``to_csv``      — the inverse of ``parse_spec``: component dicts -> CSV text

The stored form of an input is the list of dicts (``ComponentList.components`` /
``Job.input_components``); CSV is only ever a derived view rebuilt via ``to_csv``.
"""
import csv
import io
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# Required columns for a capacitor row (kept identical to the original CLI's check).
REQUIRED_FIELDS = ("qty", "capacitance", "voltage")


@dataclass
class BomResult:
    """Outcome of a BOM run. ``lines`` are the CLI-format output rows (found parts);
    ``errors`` are human-readable per-row problems (missing fields, no match, API error).
    Neither is printed here — the caller decides."""
    lines: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def parse_spec(text: str) -> List[Dict[str, str]]:
    """Parse pasted CSV text into a list of component dicts.

    Keys come from the header (first line), exactly like the original CLI's
    ``csv.DictReader``. Blank-named header columns (e.g. from a trailing comma) and
    empty-string cells are dropped so the stored JSON stays clean. Values remain
    strings — ``make_payload`` does its own ``int()``/``float()`` coercion.
    """
    rows: List[Dict[str, str]] = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        row: Dict[str, str] = {}
        for key, value in raw.items():
            if key is None or key == "":
                continue  # blank-named header column (trailing comma) or overflow cells
            if value is None or value == "":
                continue  # drop empty cells
            row[key] = value
        rows.append(row)
    return rows


def to_csv(components: List[Dict[str, Any]]) -> str:
    """Rebuild CSV text from component dicts. Header = the ordered union of keys across
    the components (first-seen order); one row per component, blank for absent keys.

    Inverse of :func:`parse_spec` for anything parse_spec produced:
    ``parse_spec(to_csv(x)) == x``.
    """
    fieldnames: List[str] = []
    for comp in components:
        for key in comp:
            if key not in fieldnames:
                fieldnames.append(key)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for comp in components:
        writer.writerow(comp)
    return out.getvalue()


def build_bom(
    rows: List[Dict[str, Any]],
    api: Any,
    *,
    on_progress: Optional[Callable[[str], None]] = None,
) -> BomResult:
    """Resolve each component row to a DigiKey part number and format the output line.

    Preserves the original CLI's exact behavior: required-field validation per row, the
    ``qty, part_number, <cap>uF <volt>V`` line format, and continue-on-error (one bad row
    never aborts the run). ``on_progress`` receives the same messages the CLI used to
    print; pass ``print`` to reproduce the CLI, or a logger for the worker.
    """
    result = BomResult()

    def note(message: str) -> None:
        if on_progress is not None:
            on_progress(message)

    for row in rows:
        try:
            note(f"Processing: {row.get('capacitance')} uF {row.get('voltage')} V")

            missing = [f for f in REQUIRED_FIELDS if not row.get(f)]
            if missing:
                raise ValueError("Capacitor require qty + capacitance + voltage.")

            params = {k: v for k, v in row.items() if v not in (None, "")}
            part_number = api.find_digikey_pn_by_moq(params)

            if part_number:
                note(f"Found P/N: {part_number}")
                result.lines.append(
                    f"{row['qty']}, {part_number}, "
                    f"{row['capacitance']}uF {row['voltage']}V"
                )
            else:
                message = f"No match found for {params}"
                note(message)
                result.errors.append(message)
        except Exception as e:  # one odd row must not abort the whole BOM
            message = f"Error processing row: {e}"
            note(message)
            result.errors.append(message)

    return result
