"""設定の読み書き。

設定ファイルの場所:
  Windows : %APPDATA%\\thermal.memo\\config.json
  macOS   : ~/Library/Application Support/thermal.memo/config.json
  Linux   : ~/.config/thermal.memo/config.json

リポジトリ直下に local_config.json を置くとそちらが優先される（持ち運び運用向け）。
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import APP_NAME

# 用紙幅 -> 印字ドット数（一般的な 203dpi 機の値）
PAPER_PRESETS: dict[str, int] = {
    "58mm": 384,
    "80mm": 576,
    "80mm (512dot)": 512,
    "112mm": 832,
}

DEFAULTS: dict[str, Any] = {
    "printer": {
        "host": "192.168.1.100",
        "port": 9100,
        "width_dots": 576,
        "paper": "80mm",
        "timeout": 8.0,
        "cut": True,
        "feed_lines": 3,
        "chunk_rows": 128,      # GS v 0 を分割送信する行数（バッファ溢れ対策）
        "copies": 1,
    },
    "text": {
        "font_path": None,      # None = 自動検出
        "font_size": 30,
        "line_spacing": 8,
        "margin": 10,
        "align": "left",        # left / center / right
        "bold": False,
        "header": "",
        "footer": "",
        "timestamp": True,
        "timestamp_format": "%Y-%m-%d %H:%M",
        "rule_line": True,      # 日時とヘッダの下に罫線
    },
    "image": {
        "mode": "dither",       # dither / threshold / adaptive
        "threshold": 128,
        "brightness": 1.0,
        "contrast": 1.0,
        "sharpen": False,
        "invert": False,
        "autocrop": True,
        "scale": 100,           # 用紙幅に対する % 
    },
    "history": {
        "enabled": True,
        "keep_days": 0,         # 0 = 無期限
        "sync_dir": None,       # Google Drive などのローカル同期フォルダ
        "sync_enabled": False,
    },
    "ui": {
        "last_tab": 0,
        "confirm_before_print": False,
        "window": "980x720",
    },
}


def _portable_config() -> Path:
    return Path(__file__).resolve().parent.parent / "local_config.json"


def app_dir() -> Path:
    """設定・履歴を置くディレクトリ。"""
    if os.environ.get("THERMAL_MEMO_HOME"):
        base = Path(os.environ["THERMAL_MEMO_HOME"])
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path() -> Path:
    portable = _portable_config()
    if portable.exists():
        return portable
    return app_dir() / "config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        with path.open(encoding="utf-8") as fh:
            user = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULTS)
    return _deep_merge(DEFAULTS, user if isinstance(user, dict) else {})


def save(cfg: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path
