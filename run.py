#!/usr/bin/env python3
"""GUI 起動用ランチャ（ダブルクリック / pythonw run.py）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from thermal_memo.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
