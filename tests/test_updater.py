"""自動更新まわりのテスト（ネットワークには出ない）。"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_memo import updater  # noqa: E402


def _release_payload(tag="v0.2.0", assets=None, prerelease=False):
    return {
        "tag_name": tag,
        "name": f"thermal.memo {tag}",
        "body": "・不具合修正\n・QR の既定サイズを調整",
        "html_url": f"https://github.com/owner/repo/releases/tag/{tag}",
        "published_at": "2026-09-10T01:02:03Z",
        "prerelease": prerelease,
        "assets": [
            {"name": name, "browser_download_url": f"https://example.invalid/{name}", "size": 123}
            for name in (assets if assets is not None else [
                "thermal-memo-0.2.0-windows-setup.exe",
                "thermal-memo-0.2.0-windows-portable.exe",
                "thermal-memo-0.2.0-macos-arm64.dmg",
                "thermal-memo-0.2.0-android.apk",
                "SHA256SUMS.txt",
            ])
        ],
    }


class _FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, headers: dict | None = None):
        super().__init__(data)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


class TestVersionCompare(unittest.TestCase):

    def test_parses_common_forms(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3, 4, 0))
        self.assertEqual(updater.parse_version("1.2"), (1, 2, 0, 4, 0))
        self.assertEqual(updater.parse_version("2"), (2, 0, 0, 4, 0))

    def test_prerelease_is_older_than_final(self):
        self.assertTrue(updater.is_newer("1.0.0", "1.0.0-rc2"))
        self.assertFalse(updater.is_newer("1.0.0-rc2", "1.0.0"))
        self.assertTrue(updater.is_newer("1.0.0-rc2", "1.0.0-rc1"))
        self.assertTrue(updater.is_newer("1.0.0-beta1", "1.0.0-alpha9"))

    def test_ordering(self):
        self.assertTrue(updater.is_newer("0.2.0", "0.1.9"))
        self.assertTrue(updater.is_newer("0.10.0", "0.9.0"))   # 文字列比較では逆転する組
        self.assertFalse(updater.is_newer("0.1.0", "0.1.0"))
        self.assertFalse(updater.is_newer("0.0.9", "0.1.0"))

    def test_unparsable_is_not_newer(self):
        self.assertFalse(updater.is_newer("", "0.1.0"))
        self.assertFalse(updater.is_newer("latest", "0.1.0"))
        self.assertIsNone(updater.parse_version("nightly"))


class TestFetch(unittest.TestCase):

    def test_parses_release(self):
        payload = json.dumps(_release_payload()).encode()
        with mock.patch.object(updater.urllib.request, "urlopen",
                               return_value=_FakeResponse(payload)):
            release = updater.fetch_latest("owner/repo")
        self.assertEqual(release.tag, "v0.2.0")
        self.assertEqual(release.version, "0.2.0")
        self.assertEqual(len(release.assets), 5)
        self.assertIn("QR", release.notes)
        self.assertIsNotNone(release.asset("SHA256SUMS.txt"))

    def test_no_release_yet(self):
        error = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.fetch_latest("owner/repo")
        self.assertIn("リリース", str(caught.exception))

    def test_rate_limit_message(self):
        error = urllib.error.HTTPError("u", 403, "rate limited", {}, None)
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.fetch_latest("owner/repo")
        self.assertIn("回数制限", str(caught.exception))

    def test_offline(self):
        error = urllib.error.URLError("no route")
        with mock.patch.object(updater.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(updater.UpdateError) as caught:
                updater.fetch_latest("owner/repo")
        self.assertIn("ネットワーク", str(caught.exception))


class TestAssetSelection(unittest.TestCase):

    def setUp(self):
        self.release = updater.release_from_json(_release_payload())

    def test_windows_prefers_installer(self):
        with mock.patch.object(updater, "platform_key", return_value="windows"):
            asset = updater.pick_asset(self.release)
        self.assertTrue(asset.name.endswith("windows-setup.exe"))

    def test_windows_portable_when_requested(self):
        with mock.patch.object(updater, "platform_key", return_value="windows"):
            asset = updater.pick_asset(self.release, prefer_installer=False)
        self.assertTrue(asset.name.endswith("windows-portable.exe"))

    def test_macos_picks_dmg_for_architecture(self):
        with mock.patch.object(updater, "platform_key", return_value="macos-arm64"):
            asset = updater.pick_asset(self.release)
        self.assertTrue(asset.name.endswith("macos-arm64.dmg"))

    def test_returns_none_when_nothing_matches(self):
        release = updater.release_from_json(_release_payload(assets=["notes.txt"]))
        with mock.patch.object(updater, "platform_key", return_value="windows"):
            self.assertIsNone(updater.pick_asset(release))

    def test_android_asset_is_not_offered_to_desktop(self):
        with mock.patch.object(updater, "platform_key", return_value="linux"):
            self.assertIsNone(updater.pick_asset(self.release))


class TestDownloadAndVerify(unittest.TestCase):

    def test_download_writes_file_and_reports_progress(self):
        body = b"x" * 5000
        seen: list[tuple[int, int]] = []
        asset = updater.Asset(name="pkg.bin", url="https://example.invalid/pkg.bin", size=len(body))
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                updater.urllib.request, "urlopen",
                return_value=_FakeResponse(body, {"Content-Length": str(len(body))}),
            ):
                path = updater.download(asset, tmp, progress=lambda a, b: seen.append((a, b)))
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), body)
        self.assertTrue(seen)
        self.assertEqual(seen[-1][0], len(body))

    def test_parse_checksums(self):
        text = ("d0" * 32 + "  thermal-memo-0.2.0-windows-setup.exe\n"
                "invalid line\n"
                + "ab" * 32 + " *other.zip\n")
        parsed = updater.parse_checksums(text)
        self.assertEqual(parsed["thermal-memo-0.2.0-windows-setup.exe"], "d0" * 32)
        self.assertEqual(parsed["other.zip"], "ab" * 32)

    def test_verify_accepts_matching_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pkg.bin"
            path.write_bytes(b"hello")
            digest = hashlib.sha256(b"hello").hexdigest()
            updater.verify(path, {"pkg.bin": digest})  # 例外が出なければ成功

    def test_verify_rejects_tampered_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pkg.bin"
            path.write_bytes(b"hello")
            with self.assertRaises(updater.UpdateError):
                updater.verify(path, {"pkg.bin": "00" * 32})

    def test_verify_skips_when_not_listed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pkg.bin"
            path.write_bytes(b"hello")
            updater.verify(path, {})  # チェックサム未提供の版でも止めない


if __name__ == "__main__":
    unittest.main()
