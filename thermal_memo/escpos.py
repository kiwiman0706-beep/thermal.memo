"""ESC/POS コマンド生成とラスタ画像のパック処理。

このモジュールは GUI にもネットワークにも依存しない純粋なバイト列生成器。
スマホ版（Flutter / Kotlin など）へ移植する際の参照実装でもある。
詳細は docs/PROTOCOL.md を参照。
"""

from __future__ import annotations

from typing import Iterator

ESC = b"\x1b"
GS = b"\x1d"

INIT = ESC + b"@"                     # プリンタ初期化
LEFT_MARGIN_0 = GS + b"L\x00\x00"     # 左マージン 0
ALIGN_LEFT = ESC + b"a\x00"
ALIGN_CENTER = ESC + b"a\x01"
CUT_PARTIAL = GS + b"V\x42\x00"       # Function B: 用紙送り後パーシャルカット


def feed(lines: int) -> bytes:
    """n 行フィード（ESC d n）。"""
    n = max(0, min(255, int(lines)))
    return ESC + b"d" + bytes([n]) if n else b""


def pack_1bit(image) -> tuple[bytes, int, int]:
    """PIL Image を ESC/POS ラスタ用のビット列に変換する。

    戻り値: (data, bytes_per_row, height)
    ビットが 1 の箇所が「黒（印字）」。行末の余りビットは 0（白）で埋める。
    """
    img = image.convert("1")
    width, height = img.size
    bytes_per_row = (width + 7) // 8
    raw = img.tobytes()  # mode "1": 1=白, 行は byte 境界までパディング済み

    # 余りビットを白のまま残すためのマスク（反転後に 0 にする）
    spare = bytes_per_row * 8 - width
    tail_mask = 0xFF if spare == 0 else (0xFF << spare) & 0xFF

    out = bytearray(len(raw))
    for row in range(height):
        start = row * bytes_per_row
        end = start + bytes_per_row
        for i in range(start, end):
            out[i] = (~raw[i]) & 0xFF   # 反転して 1=黒 にする
        out[end - 1] &= tail_mask       # 行末パディングを白へ
    return bytes(out), bytes_per_row, height


def raster_chunks(image, chunk_rows: int = 128) -> Iterator[bytes]:
    """GS v 0 コマンド列を chunk_rows 行ずつ生成する。

    一度に大量の行を送るとプリンタ側の受信バッファを溢れさせる機種があるため、
    帯（バンド）に分割して送る。
    """
    data, bytes_per_row, height = pack_1bit(image)
    chunk_rows = max(1, int(chunk_rows))
    for top in range(0, height, chunk_rows):
        rows = min(chunk_rows, height - top)
        body = data[top * bytes_per_row : (top + rows) * bytes_per_row]
        header = (
            GS + b"v0" + b"\x00"
            + bytes([bytes_per_row & 0xFF, (bytes_per_row >> 8) & 0xFF])
            + bytes([rows & 0xFF, (rows >> 8) & 0xFF])
        )
        yield header + body


def build_job(
    image,
    *,
    copies: int = 1,
    cut: bool = True,
    feed_lines: int = 3,
    chunk_rows: int = 128,
    center: bool = False,
) -> bytes:
    """1 枚分の印刷ジョブ（バイト列）を組み立てる。"""
    parts = [INIT, LEFT_MARGIN_0, ALIGN_CENTER if center else ALIGN_LEFT]
    chunks = list(raster_chunks(image, chunk_rows))
    for index in range(max(1, int(copies))):
        if index:
            parts.append(feed(1))
        parts.extend(chunks)
        parts.append(feed(feed_lines))
        if cut:
            parts.append(CUT_PARTIAL)
    return b"".join(parts)
