#!/usr/bin/env python3
"""Verify the official StandarReader baseline and optional reverse reference."""
from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OFFICIAL_APP = Path("/Applications/香色闺阁.app")
DEFAULT_MANIFEST = REPO / "tools/references/official-app-baseline-2.56.1.json"
DEFAULT_REPORT = REPO / "tools/verification/ipa_baseline_report.json"

EXPECTED_ACTIONS = {
    "searchBook",
    "bookDetail",
    "chapterList",
    "chapterContent",
    "bookWorld",
}
EXPECTED_WEBVIEW = {
    "webView",
    "webViewJs",
    "webViewJsDelay",
    "webViewSkipUrls",
    "webViewSkipUrlsUnless",
    "webViewSniff",
}
EXPECTED_RUNTIME = {"config", "params", "result", "queryInfo", "lastResponse", "responseUrl"}
EXPECTED_CLASSES = {
    "DomModelParser",
    "BookQueryManager",
    "LCJSTool",
    "LPNetWork2",
    "TFHpple",
    "SMJJSONPath",
}


@dataclass(frozen=True)
class BaselineResult:
    report: dict[str, Any]
    exit_code: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_inner_app(app_root: Path) -> Path:
    wrapped = app_root / "Wrapper/StandarReader.app"
    return wrapped if wrapped.is_dir() else app_root


def inspect_macho_encryption(binary: Path) -> int | None:
    try:
        output = subprocess.check_output(
            ["otool", "-l", str(binary)],
            text=True,
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    match = re.search(r"\bcryptid\s+(\d+)", output)
    return int(match.group(1)) if match else None


def inspect_macho_uuid(binary: Path) -> str:
    try:
        output = subprocess.check_output(
            ["dwarfdump", "--uuid", str(binary)],
            text=True,
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    match = re.search(r"UUID:\s+([0-9A-Fa-f-]+)", output)
    return match.group(1).upper() if match else ""


def inspect_local_dylib_loads(binary: Path) -> list[dict[str, str]]:
    try:
        output = subprocess.check_output(
            ["otool", "-l", str(binary)],
            text=True,
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    loads: list[dict[str, str]] = []
    load_type = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("cmd LC_LOAD") and stripped.split()[-1].endswith("DYLIB"):
            load_type = stripped.split()[-1]
            continue
        if load_type and stripped.startswith("name "):
            name = stripped.split()[1]
            if name.startswith(("@executable_path/", "@loader_path/")):
                loads = [*loads, {"type": load_type, "name": name}]
            load_type = ""
    return loads


def inspect_static_strings(binary: Path, cryptid: int | None) -> dict[str, Any]:
    if cryptid == 1:
        return {
            "status": "not_inspectable",
            "reason": "fairplay_encrypted",
            "actions_found": [],
            "actions_missing": sorted(EXPECTED_ACTIONS),
        }
    try:
        blob = subprocess.check_output(
            ["strings", str(binary)],
            text=True,
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return {"status": "blocked", "reason": str(exc)}

    actions = sorted(value for value in EXPECTED_ACTIONS if value in blob)
    webview = sorted(value for value in EXPECTED_WEBVIEW if value in blob)
    runtime = sorted(value for value in EXPECTED_RUNTIME if value in blob)
    classes = sorted(value for value in EXPECTED_CLASSES if value in blob)
    missing = sorted(EXPECTED_ACTIONS - set(actions))
    return {
        "status": "pass" if not missing else "incomplete",
        "actions_found": actions,
        "actions_missing": missing,
        "webview_found": webview,
        "webview_missing": sorted(EXPECTED_WEBVIEW - set(webview)),
        "runtime_found": runtime,
        "classes_found": classes,
        "wkwebview_post_present": "wkwebview_post" in blob,
    }


def make_check(expected: str, actual: str) -> dict[str, Any]:
    return {"expected": expected, "actual": actual, "pass": actual == expected}


def blocked_evidence(
    classification: str,
    app_root: Path,
    reason: str,
    *,
    authoritative_for_runtime: bool,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "authoritative_for_runtime": authoritative_for_runtime,
        "runtime_evidence": False,
        "official_runtime_target": classification == "official_static",
        "status": "blocked",
        "app_root": str(app_root),
        "reason": reason,
        "checks": {},
    }


def collect_bundle_evidence(
    app_root: Path,
    expected: dict[str, Any],
    *,
    classification: str,
    authoritative_for_runtime: bool,
) -> dict[str, Any]:
    inner = resolve_inner_app(app_root)
    if not inner.is_dir():
        return blocked_evidence(
            classification,
            app_root,
            "app bundle not found",
            authoritative_for_runtime=authoritative_for_runtime,
        )

    info_path = inner / "Info.plist"
    if not info_path.is_file():
        return blocked_evidence(
            classification,
            app_root,
            "Info.plist not found",
            authoritative_for_runtime=authoritative_for_runtime,
        )
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        return blocked_evidence(
            classification,
            app_root,
            f"Info.plist unreadable: {exc}",
            authoritative_for_runtime=authoritative_for_runtime,
        )

    executable_name = str(info.get("CFBundleExecutable", ""))
    binary = inner / executable_name
    lpnet = inner / "lpnet_modelInfo"
    missing = [str(path) for path in (binary, lpnet) if not path.is_file()]
    if missing:
        return blocked_evidence(
            classification,
            app_root,
            f"required baseline input missing: {', '.join(missing)}",
            authoritative_for_runtime=authoritative_for_runtime,
        )

    actual = {
        "bundle_id": str(info.get("CFBundleIdentifier", "")),
        "version": str(info.get("CFBundleShortVersionString", "")),
        "executable": executable_name,
        "executable_sha256": sha256_file(binary),
        "lpnet_model_info_sha256": sha256_file(lpnet),
    }
    checks = {
        field: make_check(str(expected.get(field, "")), value)
        for field, value in actual.items()
    }
    cryptid = inspect_macho_encryption(binary)
    status = "pass" if all(check["pass"] for check in checks.values()) else "fail"
    return {
        "classification": classification,
        "authoritative_for_runtime": authoritative_for_runtime,
        "runtime_evidence": False,
        "official_runtime_target": classification == "official_static",
        "status": status,
        "app_root": str(app_root),
        "resolved_bundle": str(inner),
        "binary": str(binary),
        "lpnet_model_info": str(lpnet),
        "checks": checks,
        "macho": {
            "uuid": inspect_macho_uuid(binary),
            "cryptid": cryptid,
            "app_local_dylib_loads": inspect_local_dylib_loads(binary),
        },
        "static_strings": inspect_static_strings(binary, cryptid),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("official_static"), dict):
        raise ValueError("manifest missing official_static")
    return data


def verify_baseline(
    *,
    official_app: Path,
    reverse_app: Path | None,
    manifest_path: Path,
) -> BaselineResult:
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "status": "blocked",
            "manifest": str(manifest_path),
            "reason": f"baseline manifest unavailable: {exc}",
            "official_static": blocked_evidence(
                "official_static",
                official_app,
                "manifest unavailable",
                authoritative_for_runtime=False,
            ),
            "modified_reverse": None,
        }
        return BaselineResult(report=report, exit_code=2)

    official = collect_bundle_evidence(
        official_app,
        manifest["official_static"],
        classification="official_static",
        authoritative_for_runtime=False,
    )
    reverse: dict[str, Any] | None = None
    if reverse_app is not None:
        expected_reverse = manifest.get("modified_reverse")
        if not isinstance(expected_reverse, dict):
            reverse = blocked_evidence(
                "modified_reverse",
                reverse_app,
                "manifest missing modified_reverse",
                authoritative_for_runtime=False,
            )
        else:
            reverse = collect_bundle_evidence(
                reverse_app,
                expected_reverse,
                classification="modified_reverse",
                authoritative_for_runtime=False,
            )

    # The reverse bundle is optional, modified auxiliary evidence. It must never
    # turn a passing official baseline into a delivery failure.
    if official["status"] == "blocked":
        status, exit_code = "blocked", 2
    elif official["status"] == "fail":
        status, exit_code = "fail", 1
    else:
        status, exit_code = "pass", 0
    report = {
        "status": status,
        "manifest": str(manifest_path),
        "official_static": official,
        "modified_reverse": reverse,
    }
    return BaselineResult(report=report, exit_code=exit_code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify StandarReader 2.56.1 app baselines")
    parser.add_argument(
        "--official-app",
        default=str(DEFAULT_OFFICIAL_APP),
        help="official app path; outer Wrapper app and inner StandarReader.app are supported",
    )
    parser.add_argument("--reverse-app", help="optional modified/decrypted reverse-reference app")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="baseline manifest path")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    result = verify_baseline(
        official_app=Path(args.official_app),
        reverse_app=Path(args.reverse_app) if args.reverse_app else None,
        manifest_path=Path(args.manifest),
    )
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result.report, ensure_ascii=False, indent=2))
    print(f"REPORT: {report_path}")
    print(f"IPA_BASELINE_VERIFY: {result.report['status'].upper()}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
