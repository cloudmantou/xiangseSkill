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

import check_xiangse_schema as schema_checker
from editor_compat import check_editor_risks

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


def editor_check(path: Path) -> tuple[bool, str]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"EDITOR_COMPAT_CHECK: FAIL\n- invalid JSON: {exc}"

    sources = schema_checker._iter_sources(doc)
    if not sources:
        return False, "EDITOR_COMPAT_CHECK: FAIL\n- no wrapped source objects found"

    risks: list[tuple[str, object]] = []
    for alias, source in sources:
        risks.extend((alias, risk) for risk in check_editor_risks(source, mode="new"))

    high_risks = [(alias, risk) for alias, risk in risks if risk.level == "high"]
    status = "FAIL" if high_risks else ("WARN" if risks else "PASS")
    lines = [f"EDITOR_COMPAT_CHECK: {status}"]
    lines.extend(
        f"- [{risk.level.upper()}] {alias}.{risk.path}: {risk.code}: {risk.message}"
        for alias, risk in risks
    )
    return not high_risks, "\n".join(lines)


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
    missing = [
        flag
        for flag, value in (
            ("--detail-url", args.detail_url),
            ("--list-url", args.list_url),
            ("--content-url", args.content_url),
        )
        if not str(value or "").strip()
    ]
    if missing:
        print(f"ERROR: explicit downstream sample URLs are required: {', '.join(missing)}", file=sys.stderr)
        return 2

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    site = str(args.site).rstrip("/") + "/"
    keyword = args.keyword
    mapping = {
        "searchBook": args.search_url
        or f"{site}modules/article/search.php?searchkey={quote(keyword)}",
        "bookDetail": args.detail_url,
        "chapterList": args.list_url,
        "chapterContent": args.content_url,
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
    editor_ok, editor_out = editor_check(src)
    print(editor_out)
    if not editor_ok:
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
    pipeline_report = report_dir / f"{stem}.pipeline.json"

    if args.import_mac and not args.live:
        return _fail_run(
            pipeline_report,
            summary,
            "--import-mac requires a requested and passing --live simulation",
        )

    if args.import_mac and not args.app_source_backup:
        return _fail_run(
            pipeline_report,
            summary,
            "--import-mac requires --app-source-backup",
        )

    if not args.live:
        return _fail_run(
            pipeline_report,
            summary,
            "run requires --live; use package for offline-only conversion",
        )

    ok, schema_out = schema_check(src)
    summary["schema_check"] = {"pass": ok, "output": schema_out}
    print(schema_out)
    if not ok:
        return _fail_run(pipeline_report, summary, "schema check failed")

    editor_ok, editor_out = editor_check(src)
    summary["editor_check"] = {"pass": editor_ok, "output": editor_out}
    print(editor_out)
    if not editor_ok:
        return _fail_run(pipeline_report, summary, "editor compatibility high risk")

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
        if not _simulation_passed(verdict):
            return _fail_run(pipeline_report, summary, "fixture simulation did not pass")

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
        if not _simulation_passed(verdict):
            return _fail_run(pipeline_report, summary, "live simulation did not pass")

    encode_xbs(src, xbs_path)
    summary["xbs_path"] = str(xbs_path)
    summary["xbs_sha256"] = sha256_file(xbs_path)

    if args.import_mac:
        cp = _run(
            [
                sys.executable,
                str(MAC_APP),
                "import",
                str(xbs_path),
                "--backup",
                str(Path(args.app_source_backup).expanduser().resolve()),
            ],
            check=False,
        )
        summary["mac_import"] = {
            "handoff_requested": cp.returncode == 0,
            "import_confirmed": False,
            "output": (cp.stdout or cp.stderr or "").strip(),
        }
        print((cp.stdout or cp.stderr or "").strip())
        if cp.returncode != 0:
            return _fail_run(pipeline_report, summary, "Mac import failed")

    summary["status"] = "pass"
    summary["delivery_notes"] = "公众号:好用的软件站"
    _write_summary(pipeline_report, summary)
    print(f"PIPELINE_STATUS: {summary['status']}")
    print(f"XBS: {xbs_path}")
    print(f"SHA256: {summary['xbs_sha256']}")
    return 0


def _simulation_passed(verdict: object) -> bool:
    return (
        isinstance(verdict, dict)
        and verdict.get("status") == "pass"
        and verdict.get("pass") is True
    )


def _fail_run(path: Path, summary: dict, reason: str) -> int:
    summary["status"] = "fail"
    summary["failure_reason"] = reason
    _write_summary(path, summary)
    print("PIPELINE_STATUS: fail")
    print(f"FAILURE_REASON: {reason}")
    return 1


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
    f.add_argument("--detail-url", required=True)
    f.add_argument("--list-url", required=True)
    f.add_argument("--content-url", required=True)
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
    run.add_argument(
        "--app-source-backup",
        help="new backup path for sourceModelList.xbs; required with --import-mac",
    )
    run.add_argument("--report-dir")
    run.set_defaults(func=cmd_run)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
