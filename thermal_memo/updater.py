"""GitHub Releases を見て新しい版を取ってくる自動更新。

依存は標準ライブラリだけ（urllib）。公開リポジトリなので認証は不要。

流れ:
  1. ``fetch_latest()`` で最新リリースの情報を取る
  2. ``is_newer()`` で今動いている版より新しいか判定
  3. ``pick_asset()`` で今の OS・実行形態に合うファイルを選ぶ
  4. ``download()`` で落とし、SHA256SUMS.txt と突き合わせる
  5. ``launch_installer()`` でインストーラを起動し、本体は終了する

ソースから動かしている場合はファイルを置き換えず、git pull を案内する。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import __version__

DEFAULT_REPO = "kiwiman0706-beep/thermal.memo"
API_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
USER_AGENT = f"thermal.memo/{__version__}"
CHECKSUM_ASSET = "SHA256SUMS.txt"

# 事前リリースの重み。数字が大きいほど新しい。
_STAGES = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3, "": 4}

_VERSION_RE = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?"
    r"(?:[-_.]?(dev|alpha|beta|rc|a|b)\.?(\d+)?)?",
    re.IGNORECASE,
)


class UpdateError(RuntimeError):
    pass


@dataclass
class Asset:
    name: str
    url: str
    size: int


@dataclass
class Release:
    tag: str
    version: str
    name: str
    notes: str
    html_url: str
    published_at: str
    prerelease: bool = False
    assets: list[Asset] = field(default_factory=list)

    def asset(self, name: str) -> Asset | None:
        for item in self.assets:
            if item.name == name:
                return item
        return None


# ------------------------------------------------------------------ バージョン

def parse_version(text: str) -> tuple[int, int, int, int, int] | None:
    """'v1.2.3-rc2' → (1, 2, 3, 3, 2)。読めなければ None。"""
    if not text:
        return None
    match = _VERSION_RE.match(text.strip())
    if not match:
        return None
    major, minor, patch, stage, stage_number = match.groups()
    return (
        int(major),
        int(minor or 0),
        int(patch or 0),
        _STAGES.get((stage or "").lower(), 4),
        int(stage_number or 0),
    )


def is_newer(candidate: str, current: str = __version__) -> bool:
    """candidate が current より新しければ True。読めない版は「新しくない」扱い。"""
    left = parse_version(candidate)
    right = parse_version(current)
    if left is None or right is None:
        return False
    return left > right


# ------------------------------------------------------------------ 取得

def fetch_latest(repo: str = DEFAULT_REPO, timeout: float = 10.0) -> Release:
    """最新リリースの情報を取る。"""
    request = urllib.request.Request(
        API_TEMPLATE.format(repo=repo),
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("まだリリースが公開されていません") from exc
        if exc.code == 403:
            raise UpdateError("GitHub API の回数制限に達しました。しばらく待ってください") from exc
        raise UpdateError(f"更新情報を取得できません（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise UpdateError(f"ネットワークに接続できません: {exc.reason}") from exc
    except (ValueError, TimeoutError) as exc:
        raise UpdateError(f"更新情報を読み取れません: {exc}") from exc

    return release_from_json(payload)


def release_from_json(payload: dict) -> Release:
    tag = str(payload.get("tag_name", ""))
    assets = [
        Asset(name=str(item.get("name", "")),
              url=str(item.get("browser_download_url", "")),
              size=int(item.get("size", 0)))
        for item in payload.get("assets", []) or []
        if item.get("browser_download_url")
    ]
    return Release(
        tag=tag,
        version=tag.lstrip("vV"),
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url", "")),
        published_at=str(payload.get("published_at", "")),
        prerelease=bool(payload.get("prerelease", False)),
        assets=assets,
    )


# ------------------------------------------------------------------ 実行形態

def is_frozen() -> bool:
    """PyInstaller などで固めた実行ファイルとして動いているか。"""
    return bool(getattr(sys, "frozen", False))


def platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos-arm64" if platform.machine() in ("arm64", "aarch64") else "macos-x86_64"
    return "linux"


def pick_asset(release: Release, prefer_installer: bool = True) -> Asset | None:
    """今の OS に合う配布物を選ぶ。

    Windows は setup（インストーラ）を優先し、無ければ portable。
    macOS は dmg。いずれも見つからなければ None（＝手動更新を案内する）。
    """
    key = platform_key()
    if key == "windows":
        order = ["windows-setup.exe", "windows-portable.exe"]
        if not prefer_installer:
            order.reverse()
    elif key.startswith("macos"):
        order = [f"{key}.dmg", "macos.dmg", f"{key}.zip"]
    else:
        order = ["linux.tar.gz"]

    for suffix in order:
        for asset in release.assets:
            if asset.name.endswith(suffix):
                return asset
    return None


# ------------------------------------------------------------------ ダウンロード

def download(
    asset: Asset,
    dest_dir: str | Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    timeout: float = 30.0,
) -> Path:
    """配布物を落として保存先パスを返す。"""
    directory = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="thermal_memo_update_"))
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / asset.name

    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or asset.size or 0)
            received = 0
            with target.open("wb") as handle:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total)
    except urllib.error.URLError as exc:
        raise UpdateError(f"ダウンロードに失敗しました: {exc.reason}") from exc
    return target


def sha256_of(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str) -> dict[str, str]:
    """`<sha256>  <filename>` 形式を辞書にする。"""
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 64:
            result[parts[-1].lstrip("*")] = parts[0].lower()
    return result


def verify(path: str | Path, checksums: dict[str, str]) -> None:
    """SHA256SUMS.txt に載っていれば突き合わせる。

    載っていない場合は例外にしない（チェックサムを出していない版もあるため）。
    """
    name = Path(path).name
    expected = checksums.get(name)
    if not expected:
        return
    actual = sha256_of(path)
    if actual != expected:
        raise UpdateError(
            f"ダウンロードしたファイルのチェックサムが一致しません（{name}）。"
            "通信経路の問題か、配布物が壊れています。"
        )


def fetch_checksums(release: Release, timeout: float = 15.0) -> dict[str, str]:
    asset = release.asset(CHECKSUM_ASSET)
    if not asset:
        return {}
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return parse_checksums(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError):
        return {}


# ------------------------------------------------------------------ 適用

def launch_installer(path: str | Path) -> None:
    """落としたインストーラ／ディスクイメージを開く。呼んだ側は直後に終了すること。"""
    target = Path(path)
    if not target.exists():
        raise UpdateError(f"ファイルが見つかりません: {target}")
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except OSError as exc:
        raise UpdateError(f"インストーラを起動できません: {exc}") from exc


def manual_instructions() -> str:
    """自動更新できない場合の案内。"""
    if is_frozen():
        return "リリースページから最新版をダウンロードして上書きしてください。"
    return "ソースから実行中です。`git pull` で更新してください。"
