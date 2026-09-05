#!/usr/bin/env python3
"""実機なしで動作確認するための擬似サーマルプリンタ。

TCP 9100 で待ち受け、受信した ESC/POS ラスタを PNG に復元して保存する。

    python tools/fake_printer.py --port 9100 --outdir out
    python -m thermal_memo --host 127.0.0.1 --port 9100 print-text "テスト"
"""

from __future__ import annotations

import argparse
import datetime as _dt
import socketserver
from pathlib import Path

from PIL import Image

ESC = 0x1B
GS = 0x1D


def parse_escpos(data: bytes) -> list[Image.Image]:
    """ラスタコマンドを抜き出して画像へ復元する（連続バンドは 1 枚に結合）。"""
    pages: list[Image.Image] = []
    bands: list[Image.Image] = []
    i = 0
    n = len(data)

    def flush() -> None:
        nonlocal bands
        if not bands:
            return
        width = max(b.width for b in bands)
        height = sum(b.height for b in bands)
        canvas = Image.new("1", (width, height), 1)
        y = 0
        for band in bands:
            canvas.paste(band, (0, y))
            y += band.height
        pages.append(canvas)
        bands = []

    while i < n:
        byte = data[i]
        if byte == GS and i + 1 < n and data[i + 1] == ord("v") and data[i + 2] == ord("0"):
            m = data[i + 3]
            xl, xh, yl, yh = data[i + 4 : i + 8]
            bytes_per_row = xl | (xh << 8)
            rows = yl | (yh << 8)
            start = i + 8
            end = start + bytes_per_row * rows
            payload = data[start:end]
            inverted = bytes((~b) & 0xFF for b in payload)
            band = Image.frombytes("1", (bytes_per_row * 8, rows), inverted)
            bands.append(band)
            i = end
            continue
        if byte == GS and i + 2 < n and data[i + 1] == ord("V"):
            flush()
            i += 3 if data[i + 2] in (0x42, 66) else 3
            continue
        if byte == ESC and i + 1 < n and data[i + 1] == ord("@"):
            i += 2
            continue
        i += 1
    flush()
    return pages


class Handler(socketserver.BaseRequestHandler):
    outdir = Path("out")

    def handle(self) -> None:
        self.request.settimeout(3.0)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = self.request.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.outdir.mkdir(parents=True, exist_ok=True)
        (self.outdir / f"{stamp}.bin").write_bytes(data)
        pages = parse_escpos(data)
        for index, page in enumerate(pages, start=1):
            path = self.outdir / f"{stamp}-{index}.png"
            page.save(path)
            print(f"  -> {path}  ({page.width}x{page.height})")
        print(f"[{stamp}] {len(data)} バイト受信 / {len(pages)} ページ復元 from {self.client_address[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="擬似サーマルプリンタ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--outdir", default="out")
    args = parser.parse_args()

    Handler.outdir = Path(args.outdir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), Handler) as server:
        print(f"擬似プリンタ待受: {args.host}:{args.port}  出力先: {args.outdir}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n終了")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
