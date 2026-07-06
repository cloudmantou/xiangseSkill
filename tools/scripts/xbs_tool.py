#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import check_xiangse_schema as schema_checker

from editor_compat import (
    CORE_ACTIONS,
    build_ab_variants,
    check_editor_risks,
    load_json,
    normalize_source_for_import_fix,
    normalize_source_for_2561,
    pick_source,
    save_json,
    to_editor_safe_profile,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _vendored_xbsrebuild_root(repo_root: Path) -> Path:
    return repo_root / "tools" / "vendor" / "xbsrebuild"


def _validator_root(repo_root: Path) -> Path:
    return repo_root / "tools" / "validator"


def _validator_cli(repo_root: Path) -> Path:
    return _validator_root(repo_root) / "src" / "cli.js"


def _is_windows() -> bool:
    return os.name == "nt" or platform.system().lower().startswith("win")


def _builtin_windows_bin(repo_root: Path) -> Path:
    return repo_root / "tools" / "bin" / "windows" / "xbsrebuild.exe"


def _resolve_runner(repo_root: Path) -> tuple[list[str], Path | None, str]:
    # 1) explicit binary path from env
    env_bin = os.environ.get("XBSREBUILD_BIN", "").strip()
    if env_bin:
        bin_path = Path(env_bin).expanduser().resolve()
        if not bin_path.exists():
            raise FileNotFoundError(f"XBSREBUILD_BIN not found: {bin_path}")
        return [str(bin_path)], None, "env_bin"

    # 2) built-in windows binary
    if _is_windows():
        builtin_bin = _builtin_windows_bin(repo_root)
        if builtin_bin.exists():
            return [str(builtin_bin)], None, "builtin_windows_bin"

    # 3) xbsrebuild in PATH
    path_bin = shutil.which("xbsrebuild")
    if path_bin:
        return [path_bin], None, "path_bin"

    # 4) go run via XBSREBUILD_ROOT
    xbsrebuild_root = os.environ.get("XBSREBUILD_ROOT", "").strip()
    if xbsrebuild_root:
        root = Path(xbsrebuild_root).expanduser().resolve()
        if root.exists():
            if not shutil.which("go"):
                raise RuntimeError(
                    "go command not found. Install Go or set XBSREBUILD_BIN / built-in xbsrebuild.exe."
                )
            return ["go", "run", "."], root, "xbsrebuild_root_env"

    # 5) sibling external repo fallback
    sibling_root = (repo_root.parent / "xbsrebuild").resolve()
    if sibling_root.exists():
        if not shutil.which("go"):
            raise RuntimeError(
                "go command not found. Install Go or set XBSREBUILD_BIN / built-in xbsrebuild.exe."
            )
        return ["go", "run", "."], sibling_root, "sibling_root"

    # 6) vendored source fallback
    vendored_root = _vendored_xbsrebuild_root(repo_root).resolve()
    if vendored_root.exists():
        if not shutil.which("go"):
            raise RuntimeError(
                "go command not found. Install Go or set XBSREBUILD_BIN / built-in xbsrebuild.exe."
            )
        return ["go", "run", "."], vendored_root, "vendored_root"

    raise FileNotFoundError(
        "Cannot find xbsrebuild. Set XBSREBUILD_BIN, use built-in tools/bin/windows/xbsrebuild.exe (Windows), "
        "or provide Go runtime with XBSREBUILD_ROOT/sibling/vendored source."
    )


def _run_xbsrebuild(action: str, input_path: Path, output_path: Path) -> None:
    repo_root = _repo_root()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd_prefix, cwd, _ = _resolve_runner(repo_root)
    cmd = cmd_prefix + [action, "-i", str(input_path), "-o", str(output_path)]

    env = os.environ.copy()
    cache_root = repo_root / ".cache"
    gocache = cache_root / "gocache"
    gomodcache = cache_root / "gomodcache"
    gocache.mkdir(parents=True, exist_ok=True)
    gomodcache.mkdir(parents=True, exist_ok=True)

    env.setdefault("GOPROXY", "https://goproxy.cn,direct")
    env.setdefault("GOSUMDB", "sum.golang.google.cn")
    env["GOCACHE"] = str(gocache)
    env["GOMODCACHE"] = str(gomodcache)

    completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env)
    if completed.returncode != 0:
        raise RuntimeError(f"xbsrebuild command failed: {' '.join(cmd)}")


def _resolve_node_binary() -> str:
    env_bin = os.environ.get("NODE_BIN", "").strip()
    if env_bin:
        p = Path(env_bin).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"NODE_BIN not found: {p}")
        return str(p)

    path_bin = shutil.which("node")
    if path_bin:
        return path_bin

    raise RuntimeError(
        "Node.js not found. Install Node 18+ and run `cd tools/validator && npm install`. "
        "You can still run schema/editor/roundtrip checks without Node."
    )


def _ensure_validator_runtime(repo_root: Path) -> tuple[Path, Path, str]:
    root = _validator_root(repo_root).resolve()
    cli = _validator_cli(repo_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"validator root not found: {root}")
    if not cli.exists():
        raise FileNotFoundError(f"validator CLI not found: {cli}")
    if not (root / "package.json").exists():
        raise FileNotFoundError(f"validator package.json not found: {root / 'package.json'}")
    if not (root / "node_modules").exists():
        raise RuntimeError(
            "validator dependencies are missing. Run `cd tools/validator && npm install`, then retry."
        )
    node_bin = _resolve_node_binary()
    return root, cli, node_bin


def _evaluate_schema(input_json: Path, *, strict_requestinfo: bool) -> dict[str, Any]:
    try:
        doc = schema_checker._load_json(input_json)
    except Exception as exc:
        return {
            "status": "FAIL",
            "errors": [f"invalid JSON: {exc}"],
            "warnings": [],
            "source_count": 0,
        }

    errors: list[str] = []
    warnings: list[str] = []
    sources = schema_checker._iter_sources(doc)
    if not sources:
        errors.append("顶层必须是对象，且至少包含一个 sourceName->sourceConfig 映射。")
    else:
        for name, src in sources:
            schema_checker._check_one_source(
                name,
                src,
                errors,
                warnings,
                strict_requestinfo=strict_requestinfo,
            )

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "source_count": len(sources),
    }


def _evaluate_editor(input_json: Path, *, strict: bool) -> dict[str, Any]:
    try:
        doc = load_json(input_json)
        _, src, mode = pick_source(doc)
    except Exception as exc:
        return {
            "status": "FAIL",
            "strict": strict,
            "risk_count": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "risks": [],
            "error": str(exc),
        }

    risks = check_editor_risks(src, mode=mode)
    high_risks = [r for r in risks if r.level == "high"]
    medium_risks = [r for r in risks if r.level == "medium"]

    status = "PASS"
    if high_risks:
        status = "FAIL"
    elif medium_risks or risks:
        status = "FAIL" if strict and medium_risks else "WARN"

    return {
        "status": status,
        "strict": strict,
        "risk_count": len(risks),
        "high_risk_count": len(high_risks),
        "medium_risk_count": len(medium_risks),
        "risks": [
            {
                "level": r.level,
                "code": r.code,
                "path": r.path,
                "message": r.message,
            }
            for r in risks
        ],
    }


def _prepare_import_fixed_json(
    *,
    input_path: Path,
    temp_dir: Path,
    default_weight: str,
) -> dict[str, Any]:
    suffix = input_path.suffix.lower()
    if suffix not in {".json", ".xbs"}:
        raise ValueError(f"simulate command only supports .json/.xbs input, got: {input_path}")

    decoded_json = input_path
    input_type = "json"
    if suffix == ".xbs":
        input_type = "xbs"
        decoded_json = temp_dir / f"{input_path.stem}.decoded.json"
        _run_xbsrebuild("xbs2json", input_path, decoded_json)

    doc = load_json(decoded_json)
    alias, src, mode = pick_source(doc)
    normalized, changes = normalize_source_for_import_fix(src, default_weight=default_weight)

    if mode == "new":
        out_obj = dict(doc)
        out_obj[alias] = normalized
    else:
        out_obj = normalized

    fixed_json = temp_dir / f"{input_path.stem}.import_fixed.json"
    save_json(fixed_json, out_obj)
    return {
        "input_type": input_type,
        "decoded_json": str(decoded_json),
        "fixed_json": fixed_json,
        "source_alias": alias,
        "mode": mode,
        "changes": changes,
    }


def _summarize_step(step_name: str, step_data: dict[str, Any]) -> dict[str, Any]:
    request_debug = step_data.get("requestDebug", {}) if isinstance(step_data, dict) else {}
    parse_result = step_data.get("parseResult", {}) if isinstance(step_data, dict) else {}
    request = request_debug.get("request", {}) if isinstance(request_debug.get("request", {}), dict) else {}

    list_data = parse_result.get("list", []) if isinstance(parse_result.get("list", []), list) else []
    item_data = parse_result.get("item", {}) if isinstance(parse_result.get("item", {}), dict) else {}
    sample_item = list_data[0] if list_data else item_data
    if not isinstance(sample_item, dict):
        sample_item = {}

    status = "pass"
    if step_data.get("blocked"):
        status = "blocked"
    elif not step_data.get("success", False):
        status = "fail"

    diagnostics = step_data.get("fieldDiagnostics", []) if isinstance(step_data, dict) else []
    errors = [
        d.get("message", "")
        for d in diagnostics
        if isinstance(d, dict) and d.get("level") == "error"
    ]
    warnings = [
        d.get("message", "")
        for d in diagnostics
        if isinstance(d, dict) and d.get("level") == "warning"
    ]

    return {
        "step": step_name,
        "status": status,
        "runtime_engine": request_debug.get("runtimeEngine", ""),
        "blocked": bool(step_data.get("blocked")),
        "blocked_reason": step_data.get("blockedReason", "") or request_debug.get("blockedReason", ""),
        "elapsed_ms": step_data.get("elapsedMs", 0),
        "request": {
            "method": request.get("method", ""),
            "url": request.get("url", ""),
            "http_params_count": len(request.get("httpParams", {}) or {}),
            "http_header_count": len(request.get("httpHeaders", {}) or {}),
        },
        "response": {
            "status": request_debug.get("status", 0),
            "url": request_debug.get("responseUrl", ""),
            "body_mode": request_debug.get("mode", ""),
            "fixture_used": request_debug.get("fixtureUsed", ""),
        },
        "parse": {
            "list_length": parse_result.get("listLengthOnlyDebug", 0),
            "sample_item_keys": sorted(sample_item.keys()),
            "sample_item": sample_item,
        },
        "webview_applied_keys": request_debug.get("webviewAppliedKeys", []),
        "webview_trace": request_debug.get("webviewTrace", []),
        "errors": errors,
        "warnings": warnings,
    }


def _run_validator_cli(
    *,
    input_json: Path,
    mode: str,
    engine: str,
    webview_timeout: int,
    keyword: str,
    page_index: int,
    offset: int,
    book_index: int,
    chapter_index: int,
    min_content_length: int,
    source_key: str,
    fixtures: str,
    output_json: Path,
) -> dict[str, Any]:
    repo_root = _repo_root()
    validator_root, validator_cli, node_bin = _ensure_validator_runtime(repo_root)

    cmd = [
        node_bin,
        str(validator_cli),
        "run",
        "--input",
        str(input_json),
        "--mode",
        mode,
        "--engine",
        engine,
        "--webview-timeout",
        str(webview_timeout),
        "--keyword",
        keyword,
        "--page-index",
        str(page_index),
        "--offset",
        str(offset),
        "--book-index",
        str(book_index),
        "--chapter-index",
        str(chapter_index),
        "--min-content-length",
        str(min_content_length),
        "--output",
        str(output_json),
    ]
    if source_key:
        cmd.extend(["--source-key", source_key])
    if mode == "fixture" and fixtures:
        fixture_path = Path(fixtures).expanduser()
        if not fixture_path.is_absolute():
            fixture_path = (repo_root / fixture_path).resolve()
        cmd.extend(["--fixtures", str(fixture_path)])

    completed = subprocess.run(
        cmd,
        cwd=str(validator_root),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        err_text = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            "validator CLI failed. "
            f"command={' '.join(cmd)}; details={err_text or 'no output'}"
        )

    if not output_json.exists():
        raise RuntimeError("validator CLI completed but output report is missing")

    with output_json.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["_runtime"] = {
        "node_bin": node_bin,
        "validator_root": str(validator_root),
        "validator_cli": str(validator_cli),
        "command": cmd,
    }
    return payload


def _build_simulation_result(
    *,
    input_path: Path,
    mode: str,
    engine: str,
    webview_timeout: int,
    prep: dict[str, Any],
    schema_result: dict[str, Any],
    editor_result: dict[str, Any],
    validator_payload: dict[str, Any] | None,
    validator_error: str,
) -> dict[str, Any]:
    steps_summary: dict[str, Any] = {}
    sim_verdict = {
        "status": "skipped",
        "pass": False,
        "blocked_reason": "",
        "fail_reasons": [],
        "warnings": [],
    }
    runtime_info: dict[str, Any] = {}

    if validator_payload and validator_payload.get("ok"):
        report = validator_payload.get("report", {})
        verdict = report.get("verdict", {}) if isinstance(report, dict) else {}
        steps = report.get("steps", {}) if isinstance(report, dict) else {}
        for step in CORE_ACTIONS:
            step_data = steps.get(step, {}) if isinstance(steps, dict) else {}
            if isinstance(step_data, dict):
                steps_summary[step] = _summarize_step(step, step_data)

        blocked_reasons = verdict.get("blockedReasons", []) if isinstance(verdict, dict) else []
        fail_reasons = verdict.get("failReasons", []) if isinstance(verdict, dict) else []
        warnings = verdict.get("warnings", []) if isinstance(verdict, dict) else []
        sim_verdict = {
            "status": verdict.get("status", "fail"),
            "pass": bool(verdict.get("pass", False)),
            "blocked_reason": "; ".join([str(x) for x in blocked_reasons if str(x).strip()]),
            "fail_reasons": [str(x) for x in fail_reasons],
            "warnings": [str(x) for x in warnings],
        }
        runtime_info = validator_payload.get("_runtime", {})
    elif validator_error:
        sim_verdict = {
            "status": "fail",
            "pass": False,
            "blocked_reason": "",
            "fail_reasons": [validator_error],
            "warnings": [],
        }

    schema_pass = schema_result.get("status") == "PASS"
    editor_status = editor_result.get("status", "FAIL")
    editor_pass = editor_status != "FAIL"
    simulation_pass = sim_verdict.get("status") == "pass" and sim_verdict.get("pass") is True
    overall_pass = schema_pass and editor_pass and simulation_pass
    overall_status = "pass" if overall_pass else ("blocked" if sim_verdict.get("status") == "blocked" else "fail")

    return {
        "input": str(input_path),
        "mode": mode,
        "engine": engine,
        "webview_timeout_seconds": webview_timeout,
        "normalization": {
            "input_type": prep.get("input_type", ""),
            "decoded_json": prep.get("decoded_json", ""),
            "source_alias": prep.get("source_alias", ""),
            "source_mode": prep.get("mode", ""),
            "change_count": len(prep.get("changes", [])),
            "changes": prep.get("changes", []),
        },
        "schema_check": schema_result,
        "editor_check": editor_result,
        "simulation_verdict": sim_verdict,
        "overall_verdict": {
            "status": overall_status,
            "pass": overall_pass,
        },
        "steps": steps_summary,
        "runtime": runtime_info,
    }


def _print_simulation_summary(result: dict[str, Any]) -> None:
    schema_status = result.get("schema_check", {}).get("status", "FAIL")
    editor_status = result.get("editor_check", {}).get("status", "FAIL")
    sim_status = result.get("simulation_verdict", {}).get("status", "fail")
    overall_status = result.get("overall_verdict", {}).get("status", "fail")

    print(f"SCHEMA_CHECK: {schema_status}")
    print(f"EDITOR_CHECK: {editor_status}")
    print(f"SIMULATION_VERDICT: {sim_status}")
    blocked_reason = result.get("simulation_verdict", {}).get("blocked_reason", "")
    if blocked_reason:
        print(f"BLOCKED_REASON: {blocked_reason}")
    fail_reasons = result.get("simulation_verdict", {}).get("fail_reasons", []) or []
    if fail_reasons:
        print("FAIL_REASONS:")
        for reason in fail_reasons[:5]:
            print(f"- {reason}")
    print(f"OVERALL_VERDICT: {overall_status}")

    steps = result.get("steps", {})
    for step in CORE_ACTIONS:
        step_obj = steps.get(step, {})
        if not step_obj:
            continue
        print(
            f"- {step}: status={step_obj.get('status')} "
            f"engine={step_obj.get('runtime_engine')} "
            f"http={step_obj.get('response', {}).get('status')} "
            f"list_len={step_obj.get('parse', {}).get('list_length')}"
        )


def _run_simulate(args: argparse.Namespace, *, mode: str) -> None:
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    report_path = Path(args.report).resolve() if args.report else None
    fixtures = str(args.fixtures or "").strip() if mode == "fixture" else ""
    engine = str(args.engine or "auto").strip().lower()
    if engine not in {"auto", "http", "webview"}:
        raise ValueError(f"invalid --engine: {engine}")
    webview_timeout = int(args.webview_timeout)
    if webview_timeout <= 0:
        raise ValueError("--webview-timeout must be > 0")

    with tempfile.TemporaryDirectory(prefix="xbs_sim_") as td:
        temp_dir = Path(td)
        prep = _prepare_import_fixed_json(
            input_path=input_path,
            temp_dir=temp_dir,
            default_weight=str(args.default_weight),
        )
        fixed_json = prep["fixed_json"]

        schema_result = _evaluate_schema(
            fixed_json,
            strict_requestinfo=args.strict_requestinfo,
        )
        editor_result = _evaluate_editor(
            fixed_json,
            strict=args.strict_editor,
        )

        validator_payload: dict[str, Any] | None = None
        validator_error = ""
        if schema_result.get("status") == "PASS":
            validator_report = temp_dir / "validator.report.json"
            try:
                validator_payload = _run_validator_cli(
                    input_json=fixed_json,
                    mode=mode,
                    engine=engine,
                    webview_timeout=webview_timeout,
                    keyword=str(args.keyword),
                    page_index=int(args.page_index),
                    offset=int(args.offset),
                    book_index=int(args.book_index),
                    chapter_index=int(args.chapter_index),
                    min_content_length=int(args.min_content_length),
                    source_key=str(args.source_key or ""),
                    fixtures=fixtures,
                    output_json=validator_report,
                )
            except Exception as exc:
                validator_error = str(exc)
        else:
            validator_error = "Skipped simulation because schema_check failed"

        result = _build_simulation_result(
            input_path=input_path,
            mode=mode,
            engine=engine,
            webview_timeout=webview_timeout,
            prep=prep,
            schema_result=schema_result,
            editor_result=editor_result,
            validator_payload=validator_payload,
            validator_error=validator_error,
        )

        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"REPORT: {report_path}")

    _print_simulation_summary(result)

    if not result.get("overall_verdict", {}).get("pass", False):
        reason = (
            result.get("simulation_verdict", {}).get("blocked_reason")
            or "; ".join(result.get("simulation_verdict", {}).get("fail_reasons", [])[:2])
            or "unknown reason"
        )
        raise RuntimeError(
            "simulate validation failed: "
            f"{reason}. "
            "Fix schema/editor issues or parser rules based on report details."
        )


def _run_schema_check(input_json: Path, *, strict_requestinfo: bool = False) -> None:
    checker = Path(__file__).resolve().parent / "check_xiangse_schema.py"
    if not checker.exists():
        raise FileNotFoundError(f"schema checker not found: {checker}")
    cmd = [sys.executable, str(checker), str(input_json)]
    if strict_requestinfo:
        cmd.append("--strict-requestinfo")
    completed = subprocess.run(cmd)
    if completed.returncode != 0:
        raise RuntimeError(
            "xiangse schema check failed. Fix JSON first, or use --skip-schema-check if you really need to bypass."
        )


def _run_editor_check(input_json: Path, *, strict: bool) -> None:
    checker = Path(__file__).resolve().parent / "check_editor_compat.py"
    if not checker.exists():
        raise FileNotFoundError(f"editor compat checker not found: {checker}")
    cmd = [sys.executable, str(checker), str(input_json)]
    if strict:
        cmd.append("--strict")
    completed = subprocess.run(cmd)
    if completed.returncode != 0:
        raise RuntimeError(
            "editor compatibility check failed. Use profile editor_safe or A/B variants for triage."
        )


def _command_json2xbs(args: argparse.Namespace) -> None:
    input_json = Path(args.input).resolve()
    if not args.skip_schema_check:
        _run_schema_check(input_json, strict_requestinfo=args.strict_requestinfo)
    _run_xbsrebuild("json2xbs", input_json, Path(args.output).resolve())
    print(f"OK: {Path(args.output).resolve()}")


def _command_xbs2json(args: argparse.Namespace) -> None:
    _run_xbsrebuild("xbs2json", Path(args.input).resolve(), Path(args.output).resolve())
    print(f"OK: {Path(args.output).resolve()}")


def _command_roundtrip(args: argparse.Namespace) -> None:
    input_json = Path(args.input).resolve()
    prefix = Path(args.prefix).resolve()
    xbs_path = prefix.with_suffix(".xbs")
    roundtrip_json = prefix.with_suffix(".roundtrip.json")

    if not args.skip_schema_check:
        _run_schema_check(input_json, strict_requestinfo=args.strict_requestinfo)

    _run_xbsrebuild("json2xbs", input_json, xbs_path)
    _run_xbsrebuild("xbs2json", xbs_path, roundtrip_json)

    print("Roundtrip done:")
    print(f"- {xbs_path}")
    print(f"- {roundtrip_json}")


def _command_doctor(_: argparse.Namespace) -> None:
    repo_root = _repo_root()
    builtin_bin = _builtin_windows_bin(repo_root)
    builtin_meta = repo_root / "tools" / "bin" / "windows" / "xbsrebuild.metadata.json"
    vendored_root = _vendored_xbsrebuild_root(repo_root)
    sibling_root = repo_root.parent / "xbsrebuild"
    validator_root = _validator_root(repo_root)
    validator_cli = _validator_cli(repo_root)
    print(f"repo_root: {repo_root}")
    print(f"python: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"is_windows: {_is_windows()}")
    print(f"go_in_path: {shutil.which('go') or ''}")
    print(f"node_in_path: {shutil.which('node') or ''}")
    print(f"xbsrebuild_in_path: {shutil.which('xbsrebuild') or ''}")
    print(f"XBSREBUILD_BIN: {os.environ.get('XBSREBUILD_BIN', '')}")
    print(f"XBSREBUILD_ROOT: {os.environ.get('XBSREBUILD_ROOT', '')}")
    print(f"NODE_BIN: {os.environ.get('NODE_BIN', '')}")
    print(f"builtin_windows_bin: {builtin_bin}")
    print(f"builtin_windows_bin_exists: {builtin_bin.exists()}")
    print(f"builtin_windows_metadata: {builtin_meta}")
    print(f"builtin_windows_metadata_exists: {builtin_meta.exists()}")
    print(f"sibling_xbsrebuild_root: {sibling_root}")
    print(f"sibling_xbsrebuild_root_exists: {sibling_root.exists()}")
    print(f"vendored_xbsrebuild_root: {vendored_root}")
    print(f"vendored_xbsrebuild_root_exists: {vendored_root.exists()}")
    print(f"validator_root: {validator_root}")
    print(f"validator_root_exists: {validator_root.exists()}")
    print(f"validator_cli: {validator_cli}")
    print(f"validator_cli_exists: {validator_cli.exists()}")
    print(f"validator_node_modules_exists: {(validator_root / 'node_modules').exists()}")
    if builtin_meta.exists():
        try:
            data = json.loads(builtin_meta.read_text(encoding="utf-8"))
            print(f"builtin_windows_metadata_commit: {data.get('source_commit_short') or data.get('source_commit') or ''}")
            print(f"builtin_windows_metadata_sha256: {data.get('sha256') or ''}")
        except Exception as exc:
            print(f"builtin_windows_metadata_error: {exc}")
    try:
        cmd, cwd, source = _resolve_runner(repo_root)
        print(f"resolved_runner_source: {source}")
        print(f"resolved_runner: {' '.join(cmd)}")
        print(f"resolved_cwd: {cwd or ''}")
    except Exception as exc:
        print(f"resolved_runner_error: {exc}")


def _command_check_editor(args: argparse.Namespace) -> None:
    input_json = Path(args.input).resolve()
    _run_editor_check(input_json, strict=args.strict)
    print(f"OK: {input_json}")


def _command_profile(args: argparse.Namespace) -> None:
    if args.profile != "editor_safe":
        raise ValueError(f"unsupported profile: {args.profile}")

    input_json = Path(args.input).resolve()
    out_json = Path(args.output).resolve()

    doc = load_json(input_json)
    alias, src, mode = pick_source(doc)
    prof = to_editor_safe_profile(src, keep_bookworld=not args.drop_bookworld)
    if mode == "new":
        out_obj = {alias: prof}
    else:
        out_obj = prof
    save_json(out_json, out_obj)
    print(f"OK: {out_json}")

    if args.to_xbs:
        out_xbs = Path(args.to_xbs).resolve()
        _run_xbsrebuild("json2xbs", out_json, out_xbs)
        print(f"OK: {out_xbs}")


def _command_build_ab(args: argparse.Namespace) -> None:
    input_json = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    prefix = args.prefix

    doc = load_json(input_json)
    alias, src, mode = pick_source(doc)
    variants = build_ab_variants(src)

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in variants.items():
        out_json = out_dir / f"{prefix}_{name}.json"
        if mode == "new":
            out_obj = {alias: obj}
        else:
            out_obj = obj
        save_json(out_json, out_obj)
        print(f"OK: {out_json}")
        if args.to_xbs:
            out_xbs = out_dir / f"{prefix}_{name}.xbs"
            _run_xbsrebuild("json2xbs", out_json, out_xbs)
            print(f"OK: {out_xbs}")


def _iter_json_files(path: Path) -> list[Path]:
    if path.is_file():
        if path.suffix.lower() == ".json":
            return [path]
        return []
    return sorted([p for p in path.rglob("*.json") if p.is_file()])


def _is_strong_book_source(source: dict[str, object], mode: str) -> bool:
    if not isinstance(source, dict):
        return False
    has_action = any(k in source for k in CORE_ACTIONS) or "bookWorld" in source
    if mode == "new":
        return has_action and ("sourceName" in source) and ("sourceUrl" in source)
    return has_action and ("bookSourceName" in source) and ("bookSourceUrl" in source)


def _command_normalize_2561(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    report_path = Path(args.report).resolve() if args.report else None
    backup_suffix = args.backup_suffix
    default_weight = str(args.default_weight)

    files = _iter_json_files(input_path)
    if not files:
        raise RuntimeError(f"no json files found: {input_path}")

    changed_json_count = 0
    rebuilt_xbs_count = 0
    skipped_count = 0
    failed_count = 0
    details: list[dict[str, str | list[str] | bool]] = []

    for p in files:
        try:
            doc = load_json(p)
        except Exception:
            skipped_count += 1
            details.append({"path": str(p), "status": "skip", "reason": "invalid_json"})
            continue

        try:
            alias, src, mode = pick_source(doc)
        except Exception:
            skipped_count += 1
            details.append({"path": str(p), "status": "skip", "reason": "not_book_source"})
            continue
        if not _is_strong_book_source(src, mode):
            skipped_count += 1
            details.append({"path": str(p), "status": "skip", "reason": "weak_match_non_source"})
            continue

        try:
            normalized, changes = normalize_source_for_2561(src, default_weight=default_weight)
            if not changes:
                details.append({"path": str(p), "status": "skip", "reason": "no_change"})
                skipped_count += 1
                continue

            backup_path = p.with_name(p.name + backup_suffix)
            if not backup_path.exists():
                shutil.copy2(p, backup_path)

            if mode == "new":
                out_obj = dict(doc)
                out_obj[alias] = normalized
            else:
                out_obj = normalized
            save_json(p, out_obj)
            changed_json_count += 1

            rebuilt = False
            rebuilt_xbs_path = ""
            if args.rebuild_xbs:
                xbs_path = p.with_suffix(".xbs")
                _run_xbsrebuild("json2xbs", p, xbs_path)
                rebuilt = True
                rebuilt_xbs_count += 1
                rebuilt_xbs_path = str(xbs_path)

            details.append(
                {
                    "path": str(p),
                    "status": "changed",
                    "changes": changes,
                    "backup": str(backup_path),
                    "rebuild_xbs": rebuilt,
                    "xbs_path": rebuilt_xbs_path,
                }
            )
        except Exception as exc:
            failed_count += 1
            details.append({"path": str(p), "status": "failed", "reason": str(exc)})

    summary = {
        "input": str(input_path),
        "default_weight": default_weight,
        "total_json_scanned": len(files),
        "changed_json_count": changed_json_count,
        "rebuilt_xbs_count": rebuilt_xbs_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "details": details,
    }

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"REPORT: {report_path}")

    print(f"TOTAL_JSON_SCANNED: {len(files)}")
    print(f"CHANGED_JSON_COUNT: {changed_json_count}")
    print(f"REBUILT_XBS_COUNT: {rebuilt_xbs_count}")
    print(f"SKIPPED_COUNT: {skipped_count}")
    print(f"FAILED_COUNT: {failed_count}")

    if failed_count > 0:
        print("FAILED_FILES:")
        for d in details:
            if d.get("status") == "failed":
                print(f"- {d['path']}: {d['reason']}")


def _command_import_fix(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    output_json = Path(args.output).resolve()
    output_xbs = Path(args.to_xbs).resolve() if args.to_xbs else None
    report_path = Path(args.report).resolve() if args.report else None
    default_weight = str(args.default_weight)

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix not in {".xbs", ".json"}:
        raise ValueError(f"import-fix only supports .xbs or .json input, got: {input_path}")

    from_xbs = suffix == ".xbs"
    temp_dir_ctx = tempfile.TemporaryDirectory(prefix="xbs_import_fix_") if from_xbs else None
    temp_dir = Path(temp_dir_ctx.name) if temp_dir_ctx else None

    try:
        input_json = input_path
        if from_xbs:
            input_json = temp_dir / f"{input_path.stem}.decoded.json"
            _run_xbsrebuild("xbs2json", input_path, input_json)

        doc = load_json(input_json)
        alias, src, mode = pick_source(doc)
        normalized, changes = normalize_source_for_import_fix(
            src, default_weight=default_weight
        )

        if mode == "new":
            out_obj = dict(doc)
            out_obj[alias] = normalized
        else:
            out_obj = normalized
        save_json(output_json, out_obj)

        _run_schema_check(
            output_json,
            strict_requestinfo=args.strict_requestinfo,
        )

        risks = check_editor_risks(normalized, mode=mode)
        high_risks = [r for r in risks if r.level == "high"]
        editor_result = "PASS" if not risks else ("FAIL" if high_risks else "WARN")

        if output_xbs:
            _run_xbsrebuild("json2xbs", output_json, output_xbs)

        summary = {
            "input": str(input_path),
            "input_type": "xbs" if from_xbs else "json",
            "decoded_json": str(input_json),
            "output_json": str(output_json),
            "output_xbs": str(output_xbs) if output_xbs else "",
            "default_weight": default_weight,
            "source_alias": alias,
            "mode": mode,
            "changed": bool(changes),
            "changes": changes,
            "schema_check": "PASS",
            "editor_check": editor_result,
            "editor_risk_count": len(risks),
            "editor_high_risk_count": len(high_risks),
            "editor_risks": [
                {
                    "level": r.level,
                    "code": r.code,
                    "path": r.path,
                    "message": r.message,
                }
                for r in risks
            ],
        }

        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            print(f"REPORT: {report_path}")

        print(f"OK_JSON: {output_json}")
        if output_xbs:
            print(f"OK_XBS: {output_xbs}")
        print(f"SCHEMA_CHECK: {summary['schema_check']}")
        print(f"EDITOR_CHECK: {summary['editor_check']}")
        print(f"CHANGE_COUNT: {len(changes)}")
    finally:
        if temp_dir_ctx:
            temp_dir_ctx.cleanup()


def _command_simulate_live(args: argparse.Namespace) -> None:
    _run_simulate(args, mode="live")


def _command_simulate_fixture(args: argparse.Namespace) -> None:
    if not args.fixtures:
        raise ValueError("simulate-fixture requires --fixtures")
    _run_simulate(args, mode="fixture")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Xiangse-only (StandarReader 2.56.1) helper for JSON <-> XBS conversion and validation."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("json2xbs", help="Convert JSON to XBS")
    p1.add_argument("-i", "--input", required=True, help="Input JSON path")
    p1.add_argument("-o", "--output", required=True, help="Output XBS path")
    p1.add_argument(
        "--skip-schema-check",
        action="store_true",
        help="Skip xiangse schema guard before conversion",
    )
    p1.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as schema errors.",
    )
    p1.set_defaults(func=_command_json2xbs)

    p2 = sub.add_parser("xbs2json", help="Convert XBS to JSON")
    p2.add_argument("-i", "--input", required=True, help="Input XBS path")
    p2.add_argument("-o", "--output", required=True, help="Output JSON path")
    p2.set_defaults(func=_command_xbs2json)

    p3 = sub.add_parser("roundtrip", help="Convert JSON -> XBS -> JSON")
    p3.add_argument("-i", "--input", required=True, help="Input JSON path")
    p3.add_argument("-p", "--prefix", required=True, help="Output prefix path")
    p3.add_argument(
        "--skip-schema-check",
        action="store_true",
        help="Skip xiangse schema guard before conversion",
    )
    p3.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as schema errors.",
    )
    p3.set_defaults(func=_command_roundtrip)

    p4 = sub.add_parser("doctor", help="Show environment diagnosis")
    p4.set_defaults(func=_command_doctor)

    p5 = sub.add_parser("check-editor", help="Check StandarReader editor-save compatibility risks")
    p5.add_argument("-i", "--input", required=True, help="Input JSON path")
    p5.add_argument(
        "--strict",
        action="store_true",
        help="Fail on medium/high risk (default only fail on high risk)",
    )
    p5.set_defaults(func=_command_check_editor)

    p6 = sub.add_parser("profile", help="Generate compatibility profile JSON")
    p6.add_argument("-i", "--input", required=True, help="Input JSON path")
    p6.add_argument("-o", "--output", required=True, help="Output JSON path")
    p6.add_argument(
        "--profile",
        default="editor_safe",
        choices=["editor_safe"],
        help="Compatibility profile name",
    )
    p6.add_argument(
        "--drop-bookworld",
        action="store_true",
        help="Drop bookWorld in generated profile JSON",
    )
    p6.add_argument(
        "--to-xbs",
        help="Optional output XBS path. Converted with schema-check bypass semantics.",
    )
    p6.set_defaults(func=_command_profile)

    p7 = sub.add_parser("build-ab", help="Generate A0-A3 editor-save A/B variants")
    p7.add_argument("-i", "--input", required=True, help="Input JSON path")
    p7.add_argument("-d", "--output-dir", required=True, help="Output directory")
    p7.add_argument(
        "--prefix",
        default="source_editor_ab",
        help="Output file prefix (default: source_editor_ab)",
    )
    p7.add_argument(
        "--to-xbs",
        action="store_true",
        help="Also convert each variant JSON to XBS",
    )
    p7.set_defaults(func=_command_build_ab)

    p8 = sub.add_parser("normalize-2561", help="Normalize book sources for StandarReader 2.56.1 save compatibility")
    p8.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input JSON file or directory (recursive for directory)",
    )
    p8.add_argument(
        "--default-weight",
        default="9999",
        help="Default weight string when missing/invalid (default: 9999)",
    )
    p8.add_argument(
        "--backup-suffix",
        default=".bak_2561",
        help="Backup suffix for changed JSON files (default: .bak_2561)",
    )
    p8.add_argument(
        "--rebuild-xbs",
        action="store_true",
        help="Rebuild same-name .xbs after JSON normalization",
    )
    p8.add_argument(
        "--report",
        help="Optional report JSON output path",
    )
    p8.set_defaults(func=_command_normalize_2561)

    p9 = sub.add_parser(
        "import-fix",
        help="Fix legacy/invalid source (.xbs/.json) to Xiangse 2.56.1 import-ready JSON",
    )
    p9.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input .xbs or .json file",
    )
    p9.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output fixed JSON path",
    )
    p9.add_argument(
        "--to-xbs",
        help="Optional output XBS path rebuilt from fixed JSON",
    )
    p9.add_argument(
        "--report",
        help="Optional report JSON output path",
    )
    p9.add_argument(
        "--default-weight",
        default="9999",
        help='Default weight string when missing/invalid (default: "9999")',
    )
    p9.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as schema errors.",
    )
    p9.set_defaults(func=_command_import_fix)

    p10 = sub.add_parser(
        "simulate-live",
        help="Run Xiangse 2.56.1 real-network 4-step simulation (search/detail/list/content)",
    )
    p10.add_argument("-i", "--input", required=True, help="Input .xbs or .json")
    p10.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "http", "webview"],
        help="simulation engine (default: auto)",
    )
    p10.add_argument(
        "--webview-timeout",
        type=int,
        default=25,
        help="webview timeout seconds for --engine webview/auto (default: 25)",
    )
    p10.add_argument(
        "--keyword",
        default="都市",
        help="search keyword for searchBook step (default: 都市)",
    )
    p10.add_argument(
        "--page-index",
        type=int,
        default=1,
        help="search page index (default: 1)",
    )
    p10.add_argument(
        "--offset",
        type=int,
        default=0,
        help="search offset (default: 0)",
    )
    p10.add_argument(
        "--book-index",
        type=int,
        default=0,
        help="pick index from search list (default: 0)",
    )
    p10.add_argument(
        "--chapter-index",
        type=int,
        default=0,
        help="pick index from chapter list (default: 0)",
    )
    p10.add_argument(
        "--min-content-length",
        type=int,
        default=50,
        help="minimal chapter content length for pass verdict (default: 50)",
    )
    p10.add_argument(
        "--source-key",
        default="",
        help="optional source alias key when input has multiple sources",
    )
    p10.add_argument(
        "--default-weight",
        default="9999",
        help='default weight for import-fix normalization (default: "9999")',
    )
    p10.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as schema errors",
    )
    p10.add_argument(
        "--strict-editor",
        action="store_true",
        help="Treat medium editor risks as failure (default only high risks fail)",
    )
    p10.add_argument(
        "--report",
        help="optional JSON report output path",
    )
    p10.set_defaults(func=_command_simulate_live)

    p11 = sub.add_parser(
        "simulate-fixture",
        help="Run Xiangse 4-step simulation in fixture mode (offline replay)",
    )
    p11.add_argument("-i", "--input", required=True, help="Input .xbs or .json")
    p11.add_argument(
        "--fixtures",
        required=True,
        help="fixture directory/file/map-json-string passed to validator",
    )
    p11.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "http", "webview"],
        help="simulation engine (default: auto)",
    )
    p11.add_argument(
        "--webview-timeout",
        type=int,
        default=25,
        help="webview timeout seconds for --engine webview/auto (default: 25)",
    )
    p11.add_argument(
        "--keyword",
        default="都市",
        help="search keyword for searchBook step (default: 都市)",
    )
    p11.add_argument(
        "--page-index",
        type=int,
        default=1,
        help="search page index (default: 1)",
    )
    p11.add_argument(
        "--offset",
        type=int,
        default=0,
        help="search offset (default: 0)",
    )
    p11.add_argument(
        "--book-index",
        type=int,
        default=0,
        help="pick index from search list (default: 0)",
    )
    p11.add_argument(
        "--chapter-index",
        type=int,
        default=0,
        help="pick index from chapter list (default: 0)",
    )
    p11.add_argument(
        "--min-content-length",
        type=int,
        default=50,
        help="minimal chapter content length for pass verdict (default: 50)",
    )
    p11.add_argument(
        "--source-key",
        default="",
        help="optional source alias key when input has multiple sources",
    )
    p11.add_argument(
        "--default-weight",
        default="9999",
        help='default weight for import-fix normalization (default: "9999")',
    )
    p11.add_argument(
        "--strict-requestinfo",
        action="store_true",
        help="Treat method:/data:/headers: in requestInfo as schema errors",
    )
    p11.add_argument(
        "--strict-editor",
        action="store_true",
        help="Treat medium editor risks as failure (default only high risks fail)",
    )
    p11.add_argument(
        "--report",
        help="optional JSON report output path",
    )
    p11.set_defaults(func=_command_simulate_fixture)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
