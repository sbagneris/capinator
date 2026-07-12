"""CLI entry point: read an input CSV, resolve each capacitor to a DigiKey part number,
and write ``bulk.csv`` (one line per found part: ``qty, part_number, <cap>uF <volt>V``).

Thin wrapper over :mod:`capinator.bom` so the CLI and the web worker share identical
resolution logic. Replaces the old top-level ``capinator.py``.

    python -m capinator.cli <input.csv>
"""
import sys
from typing import List, Optional

from capinator.bom import build_bom, parse_spec
from capinator.digikey import DigiKeyV4

OUTPUT_PATH = "bulk.csv"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("Usage: python -m capinator.cli <input.csv>")
        return 1

    with open(argv[0], newline="") as f:
        rows = parse_spec(f.read())

    api = DigiKeyV4()
    result = build_bom(rows, api, on_progress=print)

    with open(OUTPUT_PATH, "w") as out:
        for line in result.lines:
            out.write(line + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
