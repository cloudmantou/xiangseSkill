#!/usr/bin/env python3
"""End-to-end pipeline: JSON rules -> validate -> simulate -> XBS -> optional Mac import."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "tools/scripts/check_xiangse_schema.py"
XBS_TOOL = REPO / "tools/scripts/xbs_tool.py"
DECODER = REPO / "tools/scripts/decode_xbs.py"
MAC_APP = REPO / "tools/scripts/mac_xiangse_app.py"

STEPS = ["searchBook", "bookDetail", "chapterList", "chapterContent"]
UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def schema_check(path: Path) -> tuple[bool, str]:
    cp = _run([sys.executable, str(SCHEMA), str(path)], check=False)
    out = (cp.stdout or "") + (cp.stderr or "")
    ok = "SCHEMA_CHECK: PASS" in out
    return ok, out.strip()


def encode_xbs(json_path: Path, xbs_path: Path) -> None:
    cp = _run(
        [sys.executable, str(DECODER), "--encode", str(json_path), str(xbs_path)],
        check=False,
    )
    if cp.returncode != 0:
        cp2 = _run(
            [sys.executable, str(XBS_TOOL), "json2xbs", "-i", str(json_path), "-o", str(xbs_path)],
            check=False,
        )
        if cp2.returncode != 0:
            raise RuntimeError(
                "json2xbs failed:\n"
                f"decode_xbs: {cp.stderr or cp.stdout}\n"
                f"xbs_tool: {cp2.stderr or cp2.stdout}"
            )


def simulate(path: Path, *, mode: str, fixtures: str, keyword: str, report: Path) -> dict:
    cmd = [
        sys.executable,
        str(XBS_TOOL),
        f"simulate-{mode}",
        "-i",
        str(path),
        "--engine",
        "auto",
        "--webview-timeout",
        "25",
        "--keyword",
        keyword,
        "--book-index",
        "0",
        "--chapter-index",
        "0",
        "--report",
        str(report),
    ]
    if mode == "fixture":
        cmd.extend(["--fixtures", fixtures])
    cp = _run(cmd, check=False)
    text = (cp.stdout or "") + (cp.stderr or "")
    if not report.is_file():
        raise RuntimeError(f"simulate failed: {text}")
    data = json.loads(report.read_text(encoding="utf-8"))
    data["_cli_output"] = text
    return data


def cmd_fetch_samples(args: argparse.Namespace) -> int:
    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    site = str(args.site).rstrip("/") + "/"
    keyword = args.keyword
    mapping = {
        "searchBook": args.search_url
        or f"{site}modules/article/search.php?searchkey={quote(keyword)}",
        "bookDetail": args.detail_url or site,
        "chapterList": args.list_url or site,
        "chapterContent": args.content_url or site,
    }
    results = {}
    for step, url in mapping.items():
        target = out_dir / f"{step}.html"
        cp = _run(
            ["curl", "-fsSL", "--max-time", str(args.timeout), "-A", UA, url, "-o", str(target)],
            check=False,
        )
        ok = cp.returncode == 0 and target.is_file() and target.stat().st_size > 0
        results[step] = {"url": url, "file": str(target), "ok": ok, "bytes": target.stat().st_size if ok else 0}
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"MANIFEST: {manifest}")
    return 0 if all(v["ok"] for v in results.values()) else 1


def cmd_package(args: argparse.Namespace) -> int:
    src = Path(args.input).resolve()
    dst = Path(args.output).resolve()
    ok, out = schema_check(src)
    print(out)
    if not ok:
        return 1
    encode_xbs(src, dst)
    print(f"OK_XBS: {dst}")
    print(f"SHA256: {sha256_file(dst)}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    src = Path(args.input).resolve()
    report_dir = Path(args.report_dir or src.parent).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    xbs_path = report_dir / f"{stem}.xbs"
    summary: dict = {
        "input": str(src),
        "started_at": int(time.time()),
        "steps": {},
    }

    ok, schema_out = schema_check(src)
    summary["schema_check"] = {"pass": ok, "output": schema_out}
    print(schema_out)
    if not ok:
        summary["status"] = "fail"
        _write_summary(report_dir / f"{stem}.pipeline.json", summary)
        return 1

    if args.fixtures:
        fixture_report = report_dir / f"{stem}.fixture.simulate.json"
        fixture_res = simulate(
            src,
            mode="fixture",
            fixtures=str(Path(args.fixtures).resolve()),
            keyword=args.keyword,
            report=fixture_report,
        )
        verdict = fixture_res.get("simulation_verdict", {})
        summary["steps"]["fixture"] = {
            "report": str(fixture_report),
            "verdict": verdict.get("status", "unknown"),
            "pass": bool(verdict.get("pass")),
        }
        print((fixture_res.get("_cli_output") or "").strip())

    if args.live:
        live_report = report_dir / f"{stem}.simulate.json"
        live_res = simulate(
            src,
            mode="live",
            fixtures="",
            keyword=args.keyword,
            report=live_report,
        )
        verdict = live_res.get("simulation_verdict", {})
        summary["steps"]["live"] = {
            "report": str(live_report),
            "verdict": verdict.get("status", "unknown"),
            "pass": bool(verdict.get("pass")),
            "blocked_reason": verdict.get("blocked_reason", ""),
        }
        print((live_res.get("_cli_output") or "").strip())

    encode_xbs(src, xbs_path)
    summary["xbs_path"] = str(xbs_path)
    summary["xbs_sha256"] = sha256_file(xbs_path)

    if args.import_mac:
        cp = _run([sys.executable, str(MAC_APP), "import", str(xbs_path)], check=False)
        summary["mac_import"] = {
            "ok": cp.returncode == 0,
            "output": (cp.stdout or cp.stderr or "").strip(),
        }
        print((cp.stdout or cp.stderr or "").strip())

    # overall pass if fixture pass when fixtures given; live optional
    fixture_pass = summary["steps"].get("fixture", {}).get("pass", True)
    live_pass = summary["steps"].get("live", {}).get("pass", True) if args.live else True
    summary["status"] = "pass" if fixture_pass and live_pass else "fail"
    summary["delivery_notes"] = "公众号:好用的软件站"
    _write_summary(report_dir / f"{stem}.pipeline.json", summary)
    print(f"PIPELINE_STATUS: {summary['status']}")
    print(f"XBS: {xbs_path}")
    print(f"SHA256: {summary['xbs_sha256']}")
    return 0 if summary["status"] == "pass" else 1


def _write_summary(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PIPELINE_REPORT: {path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Website -> Xiangse booksource pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch-samples", help="download 4-step HTML samples")
    f.add_argument("--site", required=True)
    f.add_argument("-o", "--output", required=True)
    f.add_argument("--keyword", default="都市")
    f.add_argument("--timeout", type=int, default=20)
    f.add_argument("--search-url")
    f.add_argument("--detail-url")
    f.add_argument("--list-url")
    f.add_argument("--content-url")
    f.set_defaults(func=cmd_fetch_samples)

    pkg = sub.add_parser("package", help="schema check + json2xbs")
    pkg.add_argument("-i", "--input", required=True)
    pkg.add_argument("-o", "--output", required=True)
    pkg.set_defaults(func=cmd_package)

    run = sub.add_parser("run", help="full validate/simulate/package pipeline")
    run.add_argument("-i", "--input", required=True)
    run.add_argument("--fixtures")
    run.add_argument("--keyword", default="都市")
    run.add_argument("--live", action="store_true")
    run.add_argument("--import-mac", action="store_true")
    run.add_argument("--report-dir")
    run.set_defaults(func=cmd_run)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())