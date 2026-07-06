#!/usr/bin/env python3
"""Compare IPA static strings against validator/schema baseline."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = REPO / "Tg@TrollstoreKios.app/Tg@TrollstoreKios"
LPNET = REPO / "Tg@TrollstoreKios.app/lpnet_modelInfo"
DECODER = REPO / "tools/scripts/decode_xbs.py"

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


def run_strings() -> str:
    return subprocess.check_output(["strings", str(BIN)], text=True, errors="replace")


def decode_lpnet() -> dict:
    raw = subprocess.check_output(
        [sys.executable, str(DECODER), str(LPNET)],
        text=True,
        errors="replace",
    )
    return json.loads(raw)


def main() -> int:
    if not BIN.is_file():
        print(f"MISSING_BINARY: {BIN}")
        return 2

    blob = run_strings()
    lines = set(blob.splitlines())

    action_hits = sorted(k for k in EXPECTED_ACTIONS if k in blob)
    webview_hits = sorted(k for k in EXPECTED_WEBVIEW if k in blob)
    runtime_hits = sorted(k for k in EXPECTED_RUNTIME if k in blob)
    class_hits = sorted(k for k in EXPECTED_CLASSES if k in blob)

    lpnet = decode_lpnet()
    fmt_values = [
        x.get("kv_value", "")
        for x in lpnet.get("responseFormatType", {}).get("kv_valueList", [])
    ]
    decrypt_values = [
        x.get("kv_value", "")
        for x in lpnet.get("responseDecryptType", {}).get("kv_valueList", [])
    ]

    report = {
        "binary": str(BIN),
        "lpnet_modelInfo": str(LPNET),
        "actions_found": action_hits,
        "actions_missing": sorted(EXPECTED_ACTIONS - set(action_hits)),
        "webview_found": webview_hits,
        "webview_missing": sorted(EXPECTED_WEBVIEW - set(webview_hits)),
        "runtime_found": runtime_hits,
        "classes_found": class_hits,
        "responseFormatType_values": fmt_values,
        "responseDecryptType_values": decrypt_values,
        "wkwebview_post_present": "wkwebview_post" in blob,
        "bookWorld_categories_present": "bookWorld.categories" in blob or "categories" in blob,
    }

    out = REPO / "tools/verification/ipa_baseline_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = (
        not report["actions_missing"]
        and not report["webview_missing"]
        and report["wkwebview_post_present"]
        and len(class_hits) == len(EXPECTED_CLASSES)
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT: {out}")
    print("IPA_BASELINE_VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())