"""日本語フォントの自動検出。"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

WINDOWS_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\YuGothR.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
    r"C:\Windows\Fonts\NotoSansCJKjp-Regular.otf",
]

MAC_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/ヒラギノ角ゴ Pro W3.otf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

LINUX_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _fc_match() -> list[str]:
    """Linux: fontconfig に日本語フォントを問い合わせる。"""
    import shutil
    import subprocess

    if not shutil.which("fc-match"):
        return []
    try:
        out = subprocess.run(
            ["fc-match", "-f", "%{file}", ":lang=ja"],
            capture_output=True, text=True, timeout=5, check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return []
    return [out] if out and Path(out).exists() else []


@lru_cache(maxsize=1)
def candidates() -> list[str]:
    if sys.platform == "win32":
        base = WINDOWS_CANDIDATES
    elif sys.platform == "darwin":
        base = MAC_CANDIDATES
    else:
        base = LINUX_CANDIDATES
    found = [p for p in base if Path(p).exists()]
    if not found and sys.platform not in ("win32", "darwin"):
        found = _fc_match()
    return found


def detect(preferred: str | None = None) -> str | None:
    """使用するフォントのパスを返す。見つからなければ None（Pillow既定フォント）。"""
    if preferred and Path(preferred).exists():
        return preferred
    found = candidates()
    return found[0] if found else None


def display_name(path: str | None) -> str:
    return Path(path).name if path else "(Pillow 既定フォント／日本語不可)"
