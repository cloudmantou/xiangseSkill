#!/usr/bin/env python3
"""Interact with the locally installed Mac 香色闺阁 (StandarReader 2.56.1)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DECODER = REPO / "tools/scripts/decode_xbs.py"
DEFAULT_APP = Path("/Applications/香色闺阁.app")
DEFAULT_INNER = DEFAULT_APP / "Wrapper/StandarReader.app"
DEFAULT_BASELINE_MANIFEST = REPO / "tools/references/official-app-baseline-2.56.1.json"
BUNDLE_ID = "com.appbox.StandarReader"
APP_NAME = "香色闺阁"


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def resolve_paths(app_root: Path) -> dict[str, Path]:
    inner = app_root / "Wrapper/StandarReader.app"
    if not inner.is_dir():
        inner = app_root
    return {
        "app_root": app_root,
        "inner": inner,
        "binary": inner / "StandarReader",
        "info_plist": inner / "Info.plist",
        "lpnet_model_info": inner / "lpnet_modelInfo",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _make_check(expected: str, actual: str) -> dict[str, Any]:
    return {"expected": expected, "actual": actual, "pass": actual == expected}


def _load_official_baseline(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    official = manifest.get("official_static")
    if not isinstance(official, dict):
        raise ValueError("baseline manifest missing official_static")
    return official


def _inspect_plaintext_binary(binary: Path, expected: list[str]) -> dict[str, Any]:
    try:
        blob = subprocess.check_output(
            ["strings", str(binary)],
            text=True,
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return {
            "status": "blocked",
            "reason": str(exc),
            "found": [],
            "missing": expected,
        }
    found = [value for value in expected if value in blob]
    missing = [value for value in expected if value not in blob]
    return {
        "status": "pass" if not missing else "fail",
        "found": found,
        "missing": missing,
    }


def verify_binary(
    paths: dict[str, Path],
    *,
    manifest_path: Path = DEFAULT_BASELINE_MANIFEST,
) -> dict[str, Any]:
    binary = paths["binary"]
    info_path = paths["info_plist"]
    lpnet = paths["lpnet_model_info"]
    for required in (info_path, binary, lpnet):
        if not required.is_file():
            raise FileNotFoundError(required)

    expected_baseline = _load_official_baseline(manifest_path)
    info = plistlib.loads(info_path.read_bytes())
    actual = {
        "bundle_id": str(info.get("CFBundleIdentifier", "")),
        "version": str(info.get("CFBundleShortVersionString", "")),
        "executable": str(info.get("CFBundleExecutable", "")),
        "executable_sha256": sha256_file(binary),
        "lpnet_model_info_sha256": sha256_file(lpnet),
    }
    checks = {
        field: _make_check(str(expected_baseline.get(field, "")), value)
        for field, value in actual.items()
    }
    static_identity_pass = all(check["pass"] for check in checks.values())

    expected_strings = [
        "searchBook",
        "bookDetail",
        "chapterList",
        "chapterContent",
        "webViewSkipUrlsUnless",
        "webViewSniff",
        "wkwebview_post",
        "DomModelParser",
        "BookQueryManager",
        "LCJSTool",
    ]
    cryptid = inspect_macho_encryption(binary)
    if cryptid == 1:
        binary_inspection = {
            "status": "not_inspectable",
            "reason": "fairplay_encrypted",
            "cryptid": cryptid,
            "found": [],
            "missing": expected_strings,
        }
        binary_semantics_acceptable = True
    elif cryptid == 0:
        plaintext = _inspect_plaintext_binary(binary, expected_strings)
        binary_inspection = {"cryptid": cryptid, **plaintext}
        binary_semantics_acceptable = plaintext["status"] == "pass"
    else:
        binary_inspection = {
            "status": "blocked",
            "reason": "macho_encryption_state_unknown",
            "cryptid": None,
            "found": [],
            "missing": expected_strings,
        }
        binary_semantics_acceptable = False

    lpnet_decode_ok = False
    lpnet_fields: list[str] = []
    try:
        meta = json.loads(decode_xbs(lpnet).decode("utf-8"))
        lpnet_fields = sorted(meta.keys())
        lpnet_decode_ok = "responseFormatType" in meta and "responseDecryptType" in meta
    except (OSError, ValueError, subprocess.SubprocessError):
        lpnet_decode_ok = False

    passed = static_identity_pass and binary_semantics_acceptable
    return {
        "classification": "official_static",
        "manifest": str(manifest_path),
        "binary": str(binary),
        "lpnet_model_info": str(lpnet),
        "static_identity": {
            "status": "pass" if static_identity_pass else "fail",
            "checks": checks,
        },
        "binary_inspection": binary_inspection,
        "found": binary_inspection["found"],
        "missing": binary_inspection["missing"],
        "lpnet_decode_ok": lpnet_decode_ok,
        "lpnet_fields": lpnet_fields,
        "pass": passed,
        "note": (
            "FairPlay-encrypted official binaries are not plaintext-inspectable; "
            "identity, version, executable hash, and lpnet hash must still match."
        ),
    }


def find_container(bundle_id: str = BUNDLE_ID) -> Path | None:
    containers = Path.home() / "Library/Containers"
    if not containers.is_dir():
        return None
    for entry in containers.iterdir():
        plist = entry / ".com.apple.containermanagerd.metadata.plist"
        if not plist.is_file():
            continue
        try:
            meta = plistlib.loads(plist.read_bytes())
        except Exception:
            continue
        if meta.get("MCMMetadataIdentifier") == bundle_id:
            return entry / "Data"
    return None


def app_status(paths: dict[str, Path]) -> dict:
    proc = _run(["pgrep", "-lf", "StandarReader"], check=False)
    running = bool(proc.stdout.strip())
    container = find_container()
    info = {}
    if paths["info_plist"].is_file():
        info = plistlib.loads(paths["info_plist"].read_bytes())
    source_list = None
    if container:
        candidate = container / "Library/appdata/sourceModelList.xbs"
        if candidate.is_file():
            source_list = candidate
    return {
        "app_name": APP_NAME,
        "running": running,
        "processes": [line for line in proc.stdout.splitlines() if line.strip()],
        "bundle_id": info.get("CFBundleIdentifier", BUNDLE_ID),
        "version": info.get("CFBundleShortVersionString", ""),
        "app_root": str(paths["app_root"]),
        "inner_app": str(paths["inner"]),
        "binary": str(paths["binary"]),
        "container_data": str(container) if container else "",
        "source_model_list": str(source_list) if source_list else "",
    }


def launch_app() -> None:
    _run(["open", "-a", APP_NAME])


def import_xbs(xbs_path: Path) -> None:
    if not xbs_path.is_file():
        raise FileNotFoundError(xbs_path)
    _run(["open", "-a", APP_NAME, str(xbs_path.resolve())])


def create_source_backup(source_list: Path, backup: Path) -> str:
    """Create a verified backup without ever overwriting an existing file."""
    source_list = source_list.expanduser().resolve()
    backup = backup.expanduser().resolve()
    if not source_list.is_file():
        raise FileNotFoundError(source_list)
    if backup == source_list:
        raise ValueError("backup path must differ from sourceModelList.xbs")
    if backup.exists():
        raise FileExistsError(f"refusing to overwrite existing backup: {backup}")

    backup.parent.mkdir(parents=True, exist_ok=True)
    expected = sha256_file(source_list)
    try:
        with source_list.open("rb") as src, backup.open("xb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(chunk)
        actual = sha256_file(backup)
        if actual != expected:
            raise OSError("sourceModelList backup hash mismatch")
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    return expected


def decode_xbs(src: Path, dst: Path | None = None) -> bytes:
    cmd = [sys.executable, str(DECODER), str(src)]
    if dst:
        cmd.append(str(dst))
    out = subprocess.check_output(cmd, text=True)
    if dst:
        return dst.read_bytes()
    return out.encode("utf-8")


def cmd_status(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    print(json.dumps(app_status(paths), ensure_ascii=False, indent=2))
    return 0


def cmd_launch(args: argparse.Namespace) -> int:
    launch_app()
    print(f"LAUNCHED: {APP_NAME}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    xbs_path = Path(args.xbs).expanduser().resolve()
    if not xbs_path.is_file():
        raise FileNotFoundError(xbs_path)
    paths = resolve_paths(Path(args.app))
    status = app_status(paths)
    if status.get("running"):
        raise RuntimeError("quit 香色闺阁 before importing so sourceModelList.xbs can be backed up")
    source_list = Path(status.get("source_model_list") or "")
    if not source_list.is_file():
        raise FileNotFoundError(f"sourceModelList.xbs not found: {source_list}")
    backup = Path(args.backup).expanduser().resolve()
    digest = create_source_backup(source_list, backup)
    import_xbs(xbs_path)
    print(f"SOURCE_BACKUP: {backup}")
    print(f"SOURCE_BACKUP_SHA256: {digest}")
    print(f"IMPORT_REQUESTED: {xbs_path}")
    return 0


def cmd_decode_sources(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    status = app_status(paths)
    src = Path(args.source_list or status.get("source_model_list") or "")
    if not src.is_file():
        raise FileNotFoundError(f"sourceModelList.xbs not found: {src}")
    out = Path(args.output) if args.output else None
    decode_xbs(src, out)
    if out:
        data = json.loads(out.read_text(encoding="utf-8"))
        print(json.dumps({
            "source_list": str(src),
            "output": str(out),
            "count": len(data),
            "names": list(data.keys()),
        }, ensure_ascii=False, indent=2))
    return 0


def encode_xbs(data: dict, dst: Path) -> None:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False)
        tmp_path = Path(tmp.name)
    try:
        subprocess.check_call([sys.executable, str(DECODER), "--encode", str(tmp_path), str(dst)])
    finally:
        tmp_path.unlink(missing_ok=True)


def prune_sources(
    source_list: Path,
    *,
    remove_prefixes: list[str] | None = None,
    remove_keys: list[str] | None = None,
    keep_keys: list[str] | None = None,
) -> dict:
    data = json.loads(decode_xbs(source_list).decode("utf-8"))
    removed: list[str] = []
    if keep_keys is not None:
        keep = set(keep_keys)
        for key in list(data.keys()):
            if key not in keep:
                removed.append(key)
                del data[key]
    else:
        for key in list(data.keys()):
            if remove_keys and key in remove_keys:
                removed.append(key)
                del data[key]
                continue
            if remove_prefixes and any(key.startswith(p) for p in remove_prefixes):
                removed.append(key)
                del data[key]
    stage = source_list.with_name(f".{source_list.name}.prune.tmp")
    if stage.exists():
        raise FileExistsError(f"refusing to overwrite stale prune stage: {stage}")
    try:
        encode_xbs(data, stage)
        decoded = json.loads(decode_xbs(stage).decode("utf-8"))
        if decoded != data:
            raise ValueError("staged source list failed semantic roundtrip")
        os.chmod(stage, source_list.stat().st_mode)
        os.replace(stage, source_list)
    finally:
        stage.unlink(missing_ok=True)
    return {"removed": removed, "remaining": sorted(data.keys()), "count": len(data)}


def cmd_prune_sources(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    status = app_status(paths)
    src = Path(args.source_list or status.get("source_model_list") or "")
    if not src.is_file():
        raise FileNotFoundError(f"sourceModelList.xbs not found: {src}")
    if status.get("running"):
        raise RuntimeError("quit 香色闺阁 before pruning sourceModelList.xbs")
    backup = Path(args.backup).expanduser().resolve()
    backup_sha256 = create_source_backup(src, backup)
    remove_prefixes = [p for p in (args.remove_prefix or []) if p]
    remove_keys = [k for k in (args.remove_key or []) if k]
    keep_keys = [k for k in (args.keep_key or []) if k] or None
    report = prune_sources(
        src,
        remove_prefixes=remove_prefixes or None,
        remove_keys=remove_keys or None,
        keep_keys=keep_keys,
    )
    report["source_list"] = str(src)
    report["backup"] = str(backup)
    report["backup_sha256"] = backup_sha256
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_verify_binary(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    report = verify_binary(paths, manifest_path=Path(args.manifest))
    out = Path(args.report) if args.report else REPO / "tools/verification/mac_app_binary_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT: {out}")
    return 0 if report["pass"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mac 香色闺阁 local integration")
    p.add_argument("--app", default=str(DEFAULT_APP), help="path to 香色闺阁.app")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="show app/container status")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("launch", help="launch 香色闺阁")
    s.set_defaults(func=cmd_launch)

    s = sub.add_parser("import", help="open .xbs with 香色闺阁")
    s.add_argument("xbs", help="path to .xbs")
    s.add_argument("--backup", required=True, help="new backup path for sourceModelList.xbs")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("decode-sources", help="decode live sourceModelList.xbs")
    s.add_argument("-o", "--output", help="output json path")
    s.add_argument("--source-list", help="override sourceModelList.xbs path")
    s.set_defaults(func=cmd_decode_sources)

    s = sub.add_parser("verify-binary", help="verify installed app binary strings")
    s.add_argument("--report", help="report json path")
    s.add_argument("--manifest", default=str(DEFAULT_BASELINE_MANIFEST), help="baseline manifest path")
    s.set_defaults(func=cmd_verify_binary)

    s = sub.add_parser("prune-sources", help="remove duplicate sources from live sourceModelList.xbs")
    s.add_argument("--source-list", help="override sourceModelList.xbs path")
    s.add_argument("--backup", required=True, help="new backup path for sourceModelList.xbs")
    s.add_argument("--remove-prefix", action="append", help="remove keys with this prefix (repeatable)")
    s.add_argument("--remove-key", action="append", help="remove exact key (repeatable)")
    s.add_argument("--keep-key", action="append", help="keep only these keys (repeatable)")
    s.set_defaults(func=cmd_prune_sources)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
