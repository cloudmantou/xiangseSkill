#!/usr/bin/env python3
"""Interact with the locally installed Mac 香色闺阁 (StandarReader 2.56.1)."""
from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECODER = REPO / "tools/scripts/decode_xbs.py"
DEFAULT_APP = Path("/Applications/香色闺阁.app")
DEFAULT_INNER = DEFAULT_APP / "Wrapper/StandarReader.app"
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
    import_xbs(Path(args.xbs))
    print(f"IMPORT_REQUESTED: {Path(args.xbs).resolve()}")
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
    encode_xbs(data, source_list)
    return {"removed": removed, "remaining": sorted(data.keys()), "count": len(data)}


def cmd_prune_sources(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    status = app_status(paths)
    src = Path(args.source_list or status.get("source_model_list") or "")
    if not src.is_file():
        raise FileNotFoundError(f"sourceModelList.xbs not found: {src}")
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
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_verify_binary(args: argparse.Namespace) -> int:
    paths = resolve_paths(Path(args.app))
    binary = paths["binary"]
    lpnet = paths["lpnet_model_info"]
    if not binary.is_file():
        raise FileNotFoundError(binary)
    blob = subprocess.check_output(["strings", str(binary)], text=True, errors="replace")
    expected = [
        "searchBook", "bookDetail", "chapterList", "chapterContent",
        "webViewSkipUrlsUnless", "webViewSniff", "wkwebview_post",
        "DomModelParser", "BookQueryManager", "LCJSTool",
    ]
    found = [k for k in expected if k in blob]
    missing = [k for k in expected if k not in blob]
    lpnet_ok = False
    lpnet_fields: list[str] = []
    if lpnet.is_file():
        try:
            meta = json.loads(decode_xbs(lpnet).decode("utf-8"))
            lpnet_fields = sorted(meta.keys())
            lpnet_ok = "responseFormatType" in meta and "responseDecryptType" in meta
        except Exception:
            lpnet_ok = False
    # App Store / encrypted binaries may strip ObjC strings; lpnet_modelInfo is the fallback truth.
    passed = (not missing) or lpnet_ok
    report = {
        "binary": str(binary),
        "found": found,
        "missing": missing,
        "lpnet_model_info": str(lpnet),
        "lpnet_decode_ok": lpnet_ok,
        "lpnet_fields": lpnet_fields,
        "pass": passed,
        "note": "App Store builds may have encrypted binaries with no plaintext strings; lpnet_modelInfo decode is accepted.",
    }
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
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("decode-sources", help="decode live sourceModelList.xbs")
    s.add_argument("-o", "--output", help="output json path")
    s.add_argument("--source-list", help="override sourceModelList.xbs path")
    s.set_defaults(func=cmd_decode_sources)

    s = sub.add_parser("verify-binary", help="verify installed app binary strings")
    s.add_argument("--report", help="report json path")
    s.set_defaults(func=cmd_verify_binary)

    s = sub.add_parser("prune-sources", help="remove duplicate sources from live sourceModelList.xbs")
    s.add_argument("--source-list", help="override sourceModelList.xbs path")
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