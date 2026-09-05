#!/usr/bin/env python3
"""PyInstaller で配布物を作る。

    python packaging/build.py --mode onedir     # インストーラ用（起動が速い）
    python packaging/build.py --mode onefile    # 持ち運び用の単一 exe

CI（.github/workflows/release.yml）からも同じスクリプトを呼ぶので、
手元とビルドサーバで同じものができる。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "thermal-memo"

# Pillow + Tkinter の組み合わせで PyInstaller が取りこぼす定番
HIDDEN_IMPORTS = [
    "PIL._tkinter_finder",
]

# 任意依存。入っていればバンドルし、無ければその機能だけ無効な実行ファイルになる
OPTIONAL_MODULES = [
    "qrcode",
    "fitz",              # PyMuPDF
    "pdfplumber",
    "docx",              # python-docx
    "googleapiclient",
    "google_auth_oauthlib",
]


def installed(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def build(mode: str, icon: str | None) -> Path:
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]
    command.append("--onefile" if mode == "onefile" else "--onedir")
    if icon and Path(icon).exists():
        command += ["--icon", icon]

    for module in HIDDEN_IMPORTS:
        command += ["--hidden-import", module]
    for module in OPTIONAL_MODULES:
        if installed(module):
            command += ["--collect-submodules", module]
            print(f"  同梱: {module}")
        else:
            print(f"  省略: {module}（未インストール）")

    command.append(str(ROOT / "run.py"))
    print("$", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)

    if mode == "onefile":
        produced = ROOT / "dist" / (NAME + (".exe" if sys.platform == "win32" else ""))
    elif sys.platform == "darwin":
        produced = ROOT / "dist" / f"{NAME}.app"
    else:
        produced = ROOT / "dist" / NAME
    if not produced.exists():
        raise SystemExit(f"想定した出力が見つかりません: {produced}")
    return produced


def main() -> int:
    parser = argparse.ArgumentParser(description="配布物のビルド")
    parser.add_argument("--mode", choices=["onedir", "onefile"], default="onedir")
    parser.add_argument("--icon", default=None, help="アイコンファイル（.ico / .icns）")
    parser.add_argument("--clean", action="store_true", help="dist/build を先に消す")
    args = parser.parse_args()

    if args.clean:
        for name in ("dist", "build"):
            shutil.rmtree(ROOT / name, ignore_errors=True)

    icon = args.icon
    if icon is None:
        default = ROOT / "assets" / ("icon.ico" if sys.platform == "win32" else "icon.icns")
        icon = str(default) if default.exists() else None

    output = build(args.mode, icon)
    print(f"できました: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
