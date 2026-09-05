#!/usr/bin/env python3
"""プリンタ探索・疎通確認ユーティリティ。

    python tools/printer_probe.py --scan 192.168.1.1
    python tools/printer_probe.py --check 192.168.1.50
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_memo import printer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="サーマルプリンタ探索")
    parser.add_argument("--scan", metavar="IP", help="同一 /24 を走査（自分の管理下の LAN のみ）")
    parser.add_argument("--check", metavar="IP", help="1 台の疎通確認")
    parser.add_argument("--port", type=int, default=9100)
    args = parser.parse_args()

    if args.check:
        ok, message = printer.test_connection(
            printer.PrinterConfig(host=args.check, port=args.port)
        )
        print(message)
        return 0 if ok else 1

    if args.scan:
        def progress(i: int, n: int) -> None:
            print(f"\r走査中 {i}/{n}", end="", file=sys.stderr)

        found = printer.scan_subnet(args.scan, args.port, progress=progress)
        print(file=sys.stderr)
        if not found:
            print("見つかりませんでした")
            return 1
        for host in found:
            print(host)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
