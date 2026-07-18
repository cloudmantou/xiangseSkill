from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "tools" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_xiangse_schema as schema  # noqa: E402
import pipeline_new_source as pipeline  # noqa: E402


def valid_source() -> dict:
    actions = {
        name: {
            "actionID": name,
            "parserID": "DOM",
            "requestInfo": "%@result",
            "responseFormatType": "html",
        }
        for name in schema.ACTION_KEYS
    }
    return {
        "sourceName": "Example",
        "sourceUrl": "https://example.com",
        "sourceType": "text",
        "enable": 1,
        "weight": "9999",
        **actions,
    }


def run_args(root: Path, **overrides: object) -> Namespace:
    values: dict[str, object] = {
        "input": str(root / "source.json"),
        "report_dir": str(root),
        "fixtures": None,
        "keyword": "都市",
        "live": False,
        "import_mac": False,
        "app_source_backup": None,
    }
    values.update(overrides)
    return Namespace(**values)


class PipelineGateTests(unittest.TestCase):
    def test_delivery_commands_reject_multi_source_wrappers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "source.json"
            input_path.write_text(
                json.dumps({"Good": valid_source(), "Bad": valid_source()}),
                encoding="utf-8",
            )
            package_args = Namespace(input=str(input_path), output=str(root / "source.xbs"))
            run_values = run_args(root, live=True)
            with (
                mock.patch.object(pipeline, "simulate") as simulate,
                mock.patch.object(pipeline, "encode_xbs") as encode,
            ):
                package_result = pipeline.cmd_package(package_args)
                run_result = pipeline.cmd_run(run_values)

            self.assertNotEqual(package_result, 0)
            self.assertNotEqual(run_result, 0)
            simulate.assert_not_called()
            encode.assert_not_called()

    def test_package_stops_on_editor_high_risk_before_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = valid_source()
            source["bookWorld"] = {
                "分类": {"moreKeys": {"requestFilters": [{"key": "type", "items": []}]}}
            }
            input_path = root / "source.json"
            input_path.write_text(
                json.dumps({"Example": source}, ensure_ascii=False),
                encoding="utf-8",
            )
            args = Namespace(input=str(input_path), output=str(root / "source.xbs"))
            with mock.patch.object(pipeline, "encode_xbs") as encode:
                result = pipeline.cmd_package(args)

            self.assertNotEqual(result, 0)
            encode.assert_not_called()

    def test_run_requires_live_even_when_fixtures_are_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(root, fixtures=str(root / "fixtures"))
            with (
                mock.patch.object(pipeline, "schema_check") as schema_check,
                mock.patch.object(pipeline, "encode_xbs") as encode,
                mock.patch.object(pipeline, "simulate") as simulate,
            ):
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            schema_check.assert_not_called()
            encode.assert_not_called()
            simulate.assert_not_called()
            self.assertFalse((root / "source.xbs").exists())

    def test_failed_requested_simulation_stops_before_encoding_or_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(root, fixtures=str(root / "fixtures"), import_mac=True, live=True)
            failed = {
                "simulation_verdict": {"status": "fail", "pass": False},
                "_cli_output": "SIMULATION_VERDICT: fail",
            }
            passed = {
                "simulation_verdict": {"status": "pass", "pass": True},
                "_cli_output": "SIMULATION_VERDICT: pass",
            }
            with (
                mock.patch.object(pipeline, "schema_check", return_value=(True, "SCHEMA_CHECK: PASS")),
                mock.patch.object(pipeline, "editor_check", return_value=(True, "EDITOR_COMPAT_CHECK: PASS")),
                mock.patch.object(pipeline, "simulate", side_effect=[failed, passed]),
                mock.patch.object(pipeline, "encode_xbs") as encode,
                mock.patch.object(pipeline, "_run") as run,
            ):
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            encode.assert_not_called()
            run.assert_not_called()

    def test_failed_live_simulation_stops_before_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(root, live=True)
            failed = {
                "simulation_verdict": {"status": "blocked", "pass": False},
                "_cli_output": "SIMULATION_VERDICT: blocked",
            }
            with (
                mock.patch.object(pipeline, "schema_check", return_value=(True, "SCHEMA_CHECK: PASS")),
                mock.patch.object(pipeline, "editor_check", return_value=(True, "EDITOR_COMPAT_CHECK: PASS")),
                mock.patch.object(pipeline, "simulate", return_value=failed),
                mock.patch.object(pipeline, "encode_xbs") as encode,
            ):
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            encode.assert_not_called()

    def test_import_mac_runs_only_after_live_pass_and_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(
                root,
                live=True,
                import_mac=True,
                app_source_backup=str(root / "sourceModelList.before.xbs"),
            )
            passed = {
                "simulation_verdict": {"status": "pass", "pass": True},
                "_cli_output": "SIMULATION_VERDICT: pass",
            }

            def write_xbs(_source: Path, output: Path) -> None:
                output.write_bytes(b"xbs")

            completed = mock.Mock(returncode=0, stdout="IMPORT_REQUESTED", stderr="")
            with (
                mock.patch.object(pipeline, "schema_check", return_value=(True, "SCHEMA_CHECK: PASS")),
                mock.patch.object(pipeline, "editor_check", return_value=(True, "EDITOR_COMPAT_CHECK: PASS")),
                mock.patch.object(pipeline, "simulate", return_value=passed),
                mock.patch.object(pipeline, "encode_xbs", side_effect=write_xbs) as encode,
                mock.patch.object(pipeline, "_run", return_value=completed) as run,
            ):
                result = pipeline.cmd_run(args)

            self.assertEqual(result, 0)
            encode.assert_called_once()
            run.assert_called_once()
            self.assertIn("--backup", run.call_args.args[0])

    def test_import_mac_requires_source_list_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(root, live=True, import_mac=True)
            with mock.patch.object(pipeline, "schema_check") as schema_check:
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            schema_check.assert_not_called()

    def test_editor_high_risk_stops_before_simulation_and_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = valid_source()
            source["bookWorld"] = {
                "分类": {"moreKeys": {"requestFilters": [{"key": "type", "items": []}]}}
            }
            Path(run_args(root).input).write_text(
                json.dumps({"Example": source}, ensure_ascii=False),
                encoding="utf-8",
            )
            args = run_args(root, fixtures=str(root / "fixtures"), live=True)
            with (
                mock.patch.object(pipeline, "schema_check", return_value=(True, "SCHEMA_CHECK: PASS")),
                mock.patch.object(pipeline, "simulate") as simulate,
                mock.patch.object(pipeline, "encode_xbs") as encode,
            ):
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            simulate.assert_not_called()
            encode.assert_not_called()

    def test_import_mac_requires_a_requested_live_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            args = run_args(root, fixtures=str(root / "fixtures"), import_mac=True)
            with (
                mock.patch.object(pipeline, "schema_check") as schema_check,
                mock.patch.object(pipeline, "simulate") as simulate,
                mock.patch.object(pipeline, "encode_xbs") as encode,
                mock.patch.object(pipeline, "_run") as run,
            ):
                result = pipeline.cmd_run(args)

            self.assertNotEqual(result, 0)
            schema_check.assert_not_called()
            simulate.assert_not_called()
            encode.assert_not_called()
            run.assert_not_called()

    def test_fetch_samples_requires_explicit_downstream_urls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            base = {
                "output": str(root / "samples"),
                "site": "https://example.com",
                "keyword": "都市",
                "timeout": 20,
                "search_url": None,
                "detail_url": "https://example.com/book/1",
                "list_url": "https://example.com/book/1/chapters",
                "content_url": "https://example.com/book/1/chapter/1",
            }
            for missing in ("detail_url", "list_url", "content_url"):
                values = dict(base)
                values[missing] = None
                with self.subTest(missing=missing), mock.patch.object(pipeline, "_run") as run:
                    result = pipeline.cmd_fetch_samples(Namespace(**values))
                    self.assertNotEqual(result, 0)
                    run.assert_not_called()


class SchemaTests(unittest.TestCase):
    def test_default_schema_rejects_bare_source(self) -> None:
        self.assertEqual(schema._iter_sources(valid_source()), [])
        wrapped = {"Example": valid_source()}
        self.assertEqual(schema._iter_sources(wrapped), [("Example", wrapped["Example"])])

    def test_wrapper_rejects_empty_alias_and_non_source_siblings(self) -> None:
        source = valid_source()

        self.assertEqual(schema._iter_sources({"": source}), [])
        self.assertEqual(
            schema._iter_sources({"Example": source, "garbage": "not-a-source"}),
            [],
        )

    def test_source_url_rejects_whitespace_and_credentials(self) -> None:
        for source_url in (
            "https://exa mple.com",
            "https://user:password@example.com",
            "https://example.com:abc",
            "https://example.com/path\nnext",
        ):
            source = valid_source()
            source["sourceUrl"] = source_url
            errors: list[str] = []
            warnings: list[str] = []

            schema._check_one_source(
                "Example",
                source,
                errors,
                warnings,
                strict_requestinfo=False,
            )

            with self.subTest(source_url=source_url):
                self.assertTrue(any("sourceUrl" in error for error in errors))

    def test_critical_fields_must_be_nonempty_and_enumerated(self) -> None:
        source = valid_source()
        source.update(
            {
                "sourceName": "",
                "sourceUrl": "ftp://example.com",
                "sourceType": "novel",
                "enable": 2,
                "weight": 9999,
            }
        )
        source["searchBook"].update(
            {
                "actionID": "bookDetail",
                "parserID": "UNKNOWN",
                "requestInfo": "",
                "responseFormatType": "text",
            }
        )
        errors: list[str] = []
        warnings: list[str] = []

        schema._check_one_source(
            "Example",
            source,
            errors,
            warnings,
            strict_requestinfo=False,
        )

        combined = "\n".join(errors)
        for field in (
            "sourceName",
            "sourceUrl",
            "sourceType",
            "enable",
            "weight",
            "actionID",
            "parserID",
            "requestInfo",
            "responseFormatType",
        ):
            with self.subTest(field=field):
                self.assertIn(field, combined)
        self.assertFalse(any("weight" in warning for warning in warnings))

    def test_empty_response_format_type_is_an_official_baseline_value(self) -> None:
        source = valid_source()
        source["searchBook"]["responseFormatType"] = ""
        errors: list[str] = []
        warnings: list[str] = []

        schema._check_one_source(
            "Example",
            source,
            errors,
            warnings,
            strict_requestinfo=False,
        )

        self.assertFalse(any("responseFormatType" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
