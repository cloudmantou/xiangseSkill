from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import decode_xbs  # noqa: E402
import xbs_tool  # noqa: E402


class XBSRoundtripTests(unittest.TestCase):
    def test_runner_success_without_output_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            output_path = root / "output.xbs"
            input_path.write_text('{"value": 1}', encoding="utf-8")

            runner = ([sys.executable, "-c", "pass"], None, "env_bin")
            with (
                mock.patch.object(xbs_tool, "_repo_root", return_value=root),
                mock.patch.object(xbs_tool, "_resolve_runner", return_value=runner),
            ):
                with self.assertRaisesRegex(RuntimeError, "output"):
                    xbs_tool._run_xbsrebuild("json2xbs", input_path, output_path)

            self.assertFalse(output_path.exists())

    def test_roundtrip_rejects_semantically_different_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            input_path.write_text('{"value": 1}', encoding="utf-8")

            def fake_convert(action: str, _: Path, output_path: Path) -> None:
                if action == "json2xbs":
                    output_path.write_bytes(b"xbs")
                else:
                    output_path.write_text('{"value": 2}', encoding="utf-8")

            args = argparse.Namespace(
                input=str(input_path),
                prefix=str(root / "result"),
                skip_schema_check=True,
                strict_requestinfo=False,
            )
            with mock.patch.object(xbs_tool, "_run_xbsrebuild", side_effect=fake_convert):
                with self.assertRaisesRegex(RuntimeError, "roundtrip.*mismatch"):
                    xbs_tool._command_roundtrip(args)

    def test_roundtrip_appends_suffix_to_dotted_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            input_path.write_text('{"value": 1}', encoding="utf-8")
            calls: list[tuple[str, Path]] = []

            def fake_convert(action: str, _: Path, output_path: Path) -> None:
                calls.append((action, output_path))
                if action == "json2xbs":
                    output_path.write_bytes(b"xbs")
                else:
                    output_path.write_text('{"value": 1}', encoding="utf-8")

            prefix = root / "source.v1"
            args = argparse.Namespace(
                input=str(input_path),
                prefix=str(prefix),
                skip_schema_check=True,
                strict_requestinfo=False,
            )
            with mock.patch.object(xbs_tool, "_run_xbsrebuild", side_effect=fake_convert):
                xbs_tool._command_roundtrip(args)

            resolved_prefix = prefix.resolve()
            self.assertEqual(
                calls,
                [
                    ("json2xbs", Path(f"{resolved_prefix}.xbs")),
                    ("xbs2json", Path(f"{resolved_prefix}.roundtrip.json")),
                ],
            )

    def test_normalize_rebuild_failure_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "source.json"
            input_path.write_text("{}", encoding="utf-8")

            argv = [
                "xbs_tool.py",
                "normalize-2561",
                "--input",
                str(input_path),
                "--rebuild-xbs",
            ]
            normalized = {"sourceName": "example", "sourceUrl": "https://example.com"}
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(xbs_tool, "load_json", return_value={}),
                mock.patch.object(
                    xbs_tool,
                    "pick_source",
                    return_value=("example", normalized, "new"),
                ),
                mock.patch.object(xbs_tool, "_is_strong_book_source", return_value=True),
                mock.patch.object(
                    xbs_tool,
                    "normalize_source_for_2561",
                    return_value=(normalized, ["changed"]),
                ),
                mock.patch.object(
                    xbs_tool,
                    "_run_xbsrebuild",
                    side_effect=RuntimeError("rebuild failed"),
                ),
            ):
                self.assertEqual(xbs_tool.main(), 1)

            self.assertEqual(input_path.read_text(encoding="utf-8"), "{}")
            self.assertFalse(input_path.with_suffix(".xbs").exists())

    def test_import_fix_wraps_bare_source_before_strict_schema(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "legacy.json"
            output_path = root / "fixed.json"
            input_path.write_text("{}", encoding="utf-8")
            normalized = {
                "sourceName": "Migrated Source",
                "sourceUrl": "https://example.com",
            }
            schema_inputs: list[dict[str, object]] = []

            def record_schema(path: Path, *, strict_requestinfo: bool) -> None:
                self.assertFalse(strict_requestinfo)
                schema_inputs.append(json.loads(path.read_text(encoding="utf-8")))

            args = argparse.Namespace(
                input=str(input_path),
                output=str(output_path),
                to_xbs=None,
                report=None,
                default_weight="9999",
                strict_requestinfo=False,
            )
            with (
                mock.patch.object(xbs_tool, "load_json", return_value={}),
                mock.patch.object(
                    xbs_tool,
                    "pick_source",
                    return_value=("<root>", normalized, "legacy"),
                ),
                mock.patch.object(
                    xbs_tool,
                    "normalize_source_for_import_fix",
                    return_value=(normalized, ["changed"]),
                ),
                mock.patch.object(xbs_tool, "_run_schema_check", side_effect=record_schema),
                mock.patch.object(xbs_tool, "check_editor_risks", return_value=[]),
            ):
                xbs_tool._command_import_fix(args)

            expected = {"Migrated Source": normalized}
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), expected)
            self.assertEqual(schema_inputs, [expected])

    def test_import_fix_schema_failure_preserves_in_place_input(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "source.json"
            original = b'{"original":true}\n'
            path.write_bytes(original)
            normalized = {"sourceName": "Broken", "sourceUrl": "https://example.com"}
            args = argparse.Namespace(
                input=str(path),
                output=str(path),
                to_xbs=None,
                report=None,
                default_weight="9999",
                strict_requestinfo=False,
            )
            with (
                mock.patch.object(
                    xbs_tool,
                    "pick_source",
                    return_value=("Source", normalized, "new"),
                ),
                mock.patch.object(
                    xbs_tool,
                    "normalize_source_for_import_fix",
                    return_value=(normalized, ["changed"]),
                ),
                mock.patch.object(
                    xbs_tool,
                    "_run_schema_check",
                    side_effect=RuntimeError("schema failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "schema failed"):
                    xbs_tool._command_import_fix(args)

            self.assertEqual(path.read_bytes(), original)

    def test_import_fix_rebuild_failure_preserves_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            output_json = root / "output.json"
            output_xbs = root / "output.xbs"
            input_path.write_text("{}", encoding="utf-8")
            output_json.write_bytes(b"old-json")
            output_xbs.write_bytes(b"old-xbs")
            normalized = {"sourceName": "Source", "sourceUrl": "https://example.com"}
            args = argparse.Namespace(
                input=str(input_path),
                output=str(output_json),
                to_xbs=str(output_xbs),
                report=None,
                default_weight="9999",
                strict_requestinfo=False,
            )
            with (
                mock.patch.object(
                    xbs_tool,
                    "pick_source",
                    return_value=("Source", normalized, "new"),
                ),
                mock.patch.object(
                    xbs_tool,
                    "normalize_source_for_import_fix",
                    return_value=(normalized, ["changed"]),
                ),
                mock.patch.object(xbs_tool, "_run_schema_check"),
                mock.patch.object(xbs_tool, "check_editor_risks", return_value=[]),
                mock.patch.object(
                    xbs_tool,
                    "_run_xbsrebuild",
                    side_effect=RuntimeError("rebuild failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "rebuild failed"):
                    xbs_tool._command_import_fix(args)

            self.assertEqual(input_path.read_text(encoding="utf-8"), "{}")
            self.assertEqual(output_json.read_bytes(), b"old-json")
            self.assertEqual(output_xbs.read_bytes(), b"old-xbs")

    def test_validator_verdict_exits_return_generated_report(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            output_path = root / "report.json"
            cli_path = root / "cli.js"
            input_path.write_text("{}", encoding="utf-8")
            cli_path.write_text("", encoding="utf-8")
            report = {
                "ok": False,
                "report": {"verdict": {"status": "fail", "pass": False}},
            }

            for returncode in (1, 2):
                with self.subTest(returncode=returncode):
                    def run_validator(
                        *_: object,
                        **__: object,
                    ) -> subprocess.CompletedProcess[str]:
                        output_path.write_text(json.dumps(report), encoding="utf-8")
                        return subprocess.CompletedProcess(
                            args=["node", str(cli_path)],
                            returncode=returncode,
                            stdout="",
                            stderr="validation verdict\n",
                        )

                    with (
                        mock.patch.object(
                            xbs_tool,
                            "_ensure_validator_runtime",
                            return_value=(root, cli_path, "node"),
                        ),
                        mock.patch.object(
                            xbs_tool.subprocess,
                            "run",
                            side_effect=run_validator,
                        ),
                    ):
                        payload = xbs_tool._run_validator_cli(
                            input_json=input_path,
                            mode="live",
                            engine="http",
                            webview_timeout=5,
                            keyword="test",
                            page_index=1,
                            offset=0,
                            book_index=0,
                            chapter_index=0,
                            min_content_length=1,
                            source_key="",
                            fixtures="",
                            output_json=output_path,
                        )

                    self.assertEqual(payload["report"], report["report"])
                    self.assertEqual(payload["_runtime"]["returncode"], returncode)

    def test_validator_fail_report_reaches_pipeline_verdict(self) -> None:
        payload = {
            "ok": False,
            "report": {
                "verdict": {
                    "status": "fail",
                    "pass": False,
                    "blockedReasons": [],
                    "failReasons": ["chapter content too short"],
                    "warnings": [],
                },
                "steps": {},
            },
            "_runtime": {"returncode": 1},
        }

        result = xbs_tool._build_simulation_result(
            input_path=Path("source.json"),
            mode="live",
            engine="http",
            webview_timeout=5,
            prep={},
            schema_result={"status": "PASS"},
            editor_result={"status": "PASS"},
            validator_payload=payload,
            validator_error="",
        )

        self.assertEqual(result["simulation_verdict"]["status"], "fail")
        self.assertEqual(
            result["simulation_verdict"]["fail_reasons"],
            ["chapter content too short"],
        )
        self.assertEqual(result["overall_verdict"], {"status": "fail", "pass": False})

    def test_macos_vendored_startup_failure_uses_python_codec(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "input.json"
            output_path = root / "output.xbs"
            raw_json = b'{"value": 1}'
            input_path.write_bytes(raw_json)
            runner = (["go", "run", "."], root, "vendored_root")
            failed_start = subprocess.CompletedProcess(
                args=["go", "run", "."],
                returncode=-6,
                stdout="",
                stderr="dyld: missing LC_UUID load command\nsignal: abort trap\n",
            )

            with (
                mock.patch.object(xbs_tool, "_repo_root", return_value=root),
                mock.patch.object(xbs_tool, "_resolve_runner", return_value=runner),
                mock.patch.object(xbs_tool.platform, "system", return_value="Darwin"),
                mock.patch.object(xbs_tool.subprocess, "run", return_value=failed_start),
            ):
                xbs_tool._run_xbsrebuild("json2xbs", input_path, output_path)

            self.assertEqual(decode_xbs.xbs2json_bytes(output_path.read_bytes()), raw_json)

    def test_macos_vendored_conversion_failure_is_not_masked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "broken.xbs"
            output_path = root / "output.json"
            input_path.write_bytes(b"not an xbs")
            runner = (["go", "run", "."], root, "vendored_root")
            conversion_failure = subprocess.CompletedProcess(
                args=["go", "run", "."],
                returncode=1,
                stdout="",
                stderr="Error: decode error\n",
            )

            with (
                mock.patch.object(xbs_tool, "_repo_root", return_value=root),
                mock.patch.object(xbs_tool, "_resolve_runner", return_value=runner),
                mock.patch.object(xbs_tool.platform, "system", return_value="Darwin"),
                mock.patch.object(
                    xbs_tool.subprocess,
                    "run",
                    return_value=conversion_failure,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "decode error"):
                    xbs_tool._run_xbsrebuild("xbs2json", input_path, output_path)

            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
