from __future__ import annotations

import hashlib
import importlib.util
import json
import plistlib
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify_ipa_baseline = load_script(
    "verify_ipa_baseline_for_tests",
    "tools/scripts/verify_ipa_baseline.py",
)
mac_xiangse_app = load_script(
    "mac_xiangse_app_for_tests",
    "tools/scripts/mac_xiangse_app.py",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_app(
    root: Path,
    *,
    bundle_id: str,
    version: str,
    executable: str,
    binary: bytes,
    lpnet: bytes,
    wrapped: bool = False,
) -> Path:
    app_root = root / "香色闺阁.app"
    inner = app_root / "Wrapper/StandarReader.app" if wrapped else app_root
    inner.mkdir(parents=True)
    (inner / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundleIdentifier": bundle_id,
                "CFBundleShortVersionString": version,
                "CFBundleVersion": version,
                "CFBundleExecutable": executable,
            }
        )
    )
    (inner / executable).write_bytes(binary)
    (inner / "lpnet_modelInfo").write_bytes(lpnet)
    return app_root


def write_manifest(
    path: Path,
    *,
    official_binary: bytes,
    official_lpnet: bytes,
    reverse_binary: bytes | None = None,
    reverse_lpnet: bytes | None = None,
) -> None:
    data: dict[str, object] = {
        "schema_version": 1,
        "official_static": {
            "bundle_id": "com.appbox.StandarReader",
            "version": "2.56.1",
            "executable": "StandarReader",
            "executable_sha256": sha256(official_binary),
            "lpnet_model_info_sha256": sha256(official_lpnet),
        },
    }
    if reverse_binary is not None and reverse_lpnet is not None:
        data["modified_reverse"] = {
            "bundle_id": "example.reverse",
            "version": "2.56.1",
            "executable": "ReverseReader",
            "executable_sha256": sha256(reverse_binary),
            "lpnet_model_info_sha256": sha256(reverse_lpnet),
        }
    path.write_text(json.dumps(data), encoding="utf-8")


class VerifyIpaBaselineTests(unittest.TestCase):
    def test_parser_defaults_to_installed_official_app(self) -> None:
        args = verify_ipa_baseline.build_parser().parse_args([])

        self.assertEqual(Path(args.official_app), Path("/Applications/香色闺阁.app"))
        self.assertIsNone(args.reverse_app)

    def test_missing_official_app_is_blocked_and_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=b"official",
                official_lpnet=b"lpnet",
            )

            result = verify_ipa_baseline.verify_baseline(
                official_app=root / "missing.app",
                reverse_app=None,
                manifest_path=manifest,
            )

        self.assertEqual(result.exit_code, 2)
        self.assertEqual(result.report["status"], "blocked")
        self.assertEqual(result.report["official_static"]["status"], "blocked")

    def test_official_identity_and_hashes_pass_for_wrapped_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official_binary = b"official-binary"
            official_lpnet = b"official-lpnet"
            app = make_app(
                root,
                bundle_id="com.appbox.StandarReader",
                version="2.56.1",
                executable="StandarReader",
                binary=official_binary,
                lpnet=official_lpnet,
                wrapped=True,
            )
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=official_binary,
                official_lpnet=official_lpnet,
            )

            result = verify_ipa_baseline.verify_baseline(
                official_app=app,
                reverse_app=None,
                manifest_path=manifest,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.report["status"], "pass")
        self.assertFalse(result.report["official_static"]["authoritative_for_runtime"])
        self.assertFalse(result.report["official_static"]["runtime_evidence"])
        self.assertTrue(result.report["official_static"]["official_runtime_target"])
        checks = result.report["official_static"]["checks"]
        self.assertTrue(all(check["pass"] for check in checks.values()))

    def test_optional_reverse_failure_does_not_block_official_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official_binary = b"official-binary"
            official_lpnet = b"official-lpnet"
            official = make_app(
                root / "official",
                bundle_id="com.appbox.StandarReader",
                version="2.56.1",
                executable="StandarReader",
                binary=official_binary,
                lpnet=official_lpnet,
                wrapped=True,
            )
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=official_binary,
                official_lpnet=official_lpnet,
                reverse_binary=b"expected-reverse",
                reverse_lpnet=b"expected-reverse-lpnet",
            )

            result = verify_ipa_baseline.verify_baseline(
                official_app=official,
                reverse_app=root / "missing-reverse.app",
                manifest_path=manifest,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.report["status"], "pass")
        self.assertEqual(result.report["official_static"]["status"], "pass")
        self.assertEqual(result.report["modified_reverse"]["status"], "blocked")

    def test_modified_reverse_evidence_is_separate_from_official(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            official_binary = b"official-binary"
            official_lpnet = b"shared-lpnet"
            reverse_binary = b"reverse-binary"
            reverse_lpnet = b"shared-lpnet"
            official = make_app(
                root / "official",
                bundle_id="com.appbox.StandarReader",
                version="2.56.1",
                executable="StandarReader",
                binary=official_binary,
                lpnet=official_lpnet,
                wrapped=True,
            )
            reverse = make_app(
                root / "reverse",
                bundle_id="example.reverse",
                version="2.56.1",
                executable="ReverseReader",
                binary=reverse_binary,
                lpnet=reverse_lpnet,
            )
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=official_binary,
                official_lpnet=official_lpnet,
                reverse_binary=reverse_binary,
                reverse_lpnet=reverse_lpnet,
            )

            result = verify_ipa_baseline.verify_baseline(
                official_app=official,
                reverse_app=reverse,
                manifest_path=manifest,
            )

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.report["official_static"]["classification"], "official_static")
        self.assertEqual(result.report["modified_reverse"]["classification"], "modified_reverse")
        self.assertFalse(result.report["modified_reverse"]["authoritative_for_runtime"])


class MacVerifyBinaryTests(unittest.TestCase):
    def test_source_backup_is_exact_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_list = root / "sourceModelList.xbs"
            backup = root / "backups" / "sourceModelList.before.xbs"
            source_list.write_bytes(b"source-list-data")

            digest = mac_xiangse_app.create_source_backup(source_list, backup)

            self.assertEqual(backup.read_bytes(), source_list.read_bytes())
            self.assertEqual(digest, sha256(source_list.read_bytes()))
            with self.assertRaises(FileExistsError):
                mac_xiangse_app.create_source_backup(source_list, backup)

    def test_import_refuses_to_touch_running_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xbs = root / "source.xbs"
            xbs.write_bytes(b"source")
            args = Namespace(
                app="/Applications/香色闺阁.app",
                xbs=str(xbs),
                backup=str(root / "sourceModelList.before.xbs"),
            )
            with (
                mock.patch.object(
                    mac_xiangse_app,
                    "app_status",
                    return_value={"running": True, "source_model_list": str(root / "live.xbs")},
                ),
                mock.patch.object(mac_xiangse_app, "import_xbs") as import_xbs,
            ):
                with self.assertRaises(RuntimeError):
                    mac_xiangse_app.cmd_import(args)

        import_xbs.assert_not_called()

    def test_matching_lpnet_cannot_make_arbitrary_binary_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected_binary = b"expected-official-binary"
            actual_binary = b"arbitrary-binary"
            lpnet = b"matching-lpnet"
            app = make_app(
                root,
                bundle_id="com.appbox.StandarReader",
                version="2.56.1",
                executable="StandarReader",
                binary=actual_binary,
                lpnet=lpnet,
            )
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=expected_binary,
                official_lpnet=lpnet,
            )

            decoded_lpnet = json.dumps(
                {"responseFormatType": {}, "responseDecryptType": {}}
            ).encode("utf-8")
            with mock.patch.object(mac_xiangse_app, "decode_xbs", return_value=decoded_lpnet):
                report = mac_xiangse_app.verify_binary(
                    mac_xiangse_app.resolve_paths(app),
                    manifest_path=manifest,
                )

        self.assertFalse(report["pass"])
        self.assertFalse(report["static_identity"]["checks"]["executable_sha256"]["pass"])

    def test_encrypted_matching_official_is_not_inspectable_but_passes_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = b"encrypted-official-binary"
            lpnet = b"official-lpnet"
            app = make_app(
                root,
                bundle_id="com.appbox.StandarReader",
                version="2.56.1",
                executable="StandarReader",
                binary=binary,
                lpnet=lpnet,
            )
            manifest = root / "baseline.json"
            write_manifest(
                manifest,
                official_binary=binary,
                official_lpnet=lpnet,
            )

            decoded_lpnet = json.dumps(
                {"responseFormatType": {}, "responseDecryptType": {}}
            ).encode("utf-8")
            with mock.patch.object(mac_xiangse_app, "inspect_macho_encryption", return_value=1):
                with mock.patch.object(mac_xiangse_app, "decode_xbs", return_value=decoded_lpnet):
                    report = mac_xiangse_app.verify_binary(
                        mac_xiangse_app.resolve_paths(app),
                        manifest_path=manifest,
                    )

        self.assertTrue(report["pass"])
        self.assertEqual(report["binary_inspection"]["status"], "not_inspectable")
        self.assertEqual(report["binary_inspection"]["reason"], "fairplay_encrypted")


if __name__ == "__main__":
    unittest.main()
