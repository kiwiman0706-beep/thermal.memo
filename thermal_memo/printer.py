"""LAN サーマルプリンタ（ESC/POS / RAW 9100）への送信。"""

from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from . import escpos


class PrinterError(RuntimeError):
    pass


@dataclass
class PrinterConfig:
    host: str
    port: int = 9100
    timeout: float = 8.0
    width_dots: int = 576
    cut: bool = True
    feed_lines: int = 3
    chunk_rows: int = 128

    @classmethod
    def from_dict(cls, data: dict) -> "PrinterConfig":
        return cls(
            host=str(data.get("host", "")).strip(),
            port=int(data.get("port", 9100)),
            timeout=float(data.get("timeout", 8.0)),
            width_dots=int(data.get("width_dots", 576)),
            cut=bool(data.get("cut", True)),
            feed_lines=int(data.get("feed_lines", 3)),
            chunk_rows=int(data.get("chunk_rows", 128)),
        )


def send_raw(cfg: PrinterConfig, payload: bytes) -> int:
    """生バイト列をプリンタへ送る。送信バイト数を返す。"""
    if not cfg.host:
        raise PrinterError("プリンタの IP アドレスが未設定です（設定タブで指定してください）")
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout) as sock:
            sock.settimeout(cfg.timeout)
            sock.sendall(payload)
            # 送信直後に close するとバッファを捨てる機種があるため少し待つ
            time.sleep(0.2)
    except socket.timeout as exc:
        raise PrinterError(
            f"{cfg.host}:{cfg.port} への接続がタイムアウトしました（{cfg.timeout:g}秒）"
        ) from exc
    except OSError as exc:
        raise PrinterError(f"{cfg.host}:{cfg.port} へ送信できません: {exc}") from exc
    return len(payload)


def print_image(
    cfg: PrinterConfig,
    image,
    *,
    copies: int = 1,
    center: bool = False,
) -> int:
    """PIL Image を印刷する。画像幅は width_dots 以下である前提。"""
    if image.width > cfg.width_dots:
        raise PrinterError(
            f"画像幅 {image.width}dot が用紙幅 {cfg.width_dots}dot を超えています"
        )
    job = escpos.build_job(
        image,
        copies=copies,
        cut=cfg.cut,
        feed_lines=cfg.feed_lines,
        chunk_rows=cfg.chunk_rows,
        center=center,
    )
    return send_raw(cfg, job)


def feed_and_cut(cfg: PrinterConfig, lines: int = 4) -> int:
    payload = escpos.INIT + escpos.feed(lines)
    if cfg.cut:
        payload += escpos.CUT_PARTIAL
    return send_raw(cfg, payload)


def test_connection(cfg: PrinterConfig) -> tuple[bool, str]:
    """TCP 接続のみ試して結果を返す（用紙は消費しない）。"""
    if not cfg.host:
        return False, "IP アドレスが未設定です"
    started = time.perf_counter()
    try:
        with socket.create_connection((cfg.host, cfg.port), timeout=cfg.timeout):
            pass
    except socket.timeout:
        return False, f"タイムアウト（{cfg.timeout:g}秒）。IP と電源・LAN 接続を確認してください"
    except OSError as exc:
        return False, f"接続失敗: {exc}"
    elapsed = (time.perf_counter() - started) * 1000
    return True, f"接続OK  {cfg.host}:{cfg.port}  ({elapsed:.0f} ms)"


def scan_subnet(
    base_ip: str,
    port: int = 9100,
    timeout: float = 0.25,
    progress: Callable[[int, int], None] | None = None,
) -> list[str]:
    """同一 /24 サブネットを走査して 9100 が開いているホストを列挙する。

    プリンタの IP を忘れたとき用のヘルパ。自分の管理下のネットワークでのみ使うこと。
    """
    parts = base_ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        raise ValueError("IPv4 アドレスを指定してください")
    prefix = ".".join(parts[:3])
    hosts = [f"{prefix}.{last}" for last in range(1, 255)]
    found: list[str] = []
    done = 0

    def probe(host: str) -> str | None:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return host
        except OSError:
            return None

    with ThreadPoolExecutor(max_workers=32) as pool:
        for host, result in zip(hosts, pool.map(probe, hosts)):
            done += 1
            if result:
                found.append(result)
            if progress:
                progress(done, len(hosts))
    return found
