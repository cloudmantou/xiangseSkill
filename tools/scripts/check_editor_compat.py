#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from editor_compat import check_editor_risks, load_json, pick_source
from check_xiangse_schema import _iter_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Check editor-save compatibility risks for StandarReader 2.56.1")
    parser.add_argument("input", help="Path to source JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on medium/high risks (default: fail only on high risks)",
    )
    args = parser.parse_args()

    path = Path(args.input).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        doc = load_json(path)
        _, src, mode = pick_source(doc)
        if mode == "new" and len(_iter_sources(doc)) != 1:
            raise ValueError("delivery JSON must contain exactly one wrapped source")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    risks = check_editor_risks(src, mode=mode)
    if not risks:
        print("EDITOR_COMPAT_CHECK: PASS")
        print("RISK_COUNT: 0")
        return 0

    print("EDITOR_COMPAT_CHECK: WARN")
    for r in risks:
        print(f"- [{r.level.upper()}] {r.code} @ {r.path}: {r.message}")

    levels = {r.level for r in risks}
    if "high" in levels:
        return 1
    if args.strict and ("medium" in levels):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
