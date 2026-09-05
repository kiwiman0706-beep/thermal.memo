"""スクリーンショット取得。

3 つの経路を用意する:
  1. OS 標準の範囲選択（Windows: ms-screenclip / macOS: screencapture -i）
  2. アプリ内蔵のオーバーレイ選択（Tk・全 OS 共通のフォールバック）
  3. クリップボードから貼り付け（Win+Shift+S / Cmd+Ctrl+Shift+4 のあと）
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageGrab


class CaptureCancelled(RuntimeError):
    """ユーザーが範囲選択を中断した。"""


def clipboard_image() -> Image.Image | None:
    """クリップボードの画像を取得（無ければ None）。"""
    try:
        data = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(data, Image.Image):
        return data
    if isinstance(data, list) and data:
        # ファイルパスのリスト（エクスプローラからのコピー）
        for entry in data:
            path = Path(str(entry))
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
                try:
                    return Image.open(path)
                except OSError:
                    continue
    return None


def grab_fullscreen(all_screens: bool = True) -> Image.Image:
    if sys.platform == "win32":
        return ImageGrab.grab(all_screens=all_screens)
    return ImageGrab.grab()


def os_region_capture(timeout: float = 90.0) -> Image.Image:
    """OS 標準の範囲選択 UI を呼び出す。"""
    if sys.platform == "darwin":
        return _mac_region(timeout)
    if sys.platform == "win32":
        return _windows_snip(timeout)
    raise CaptureCancelled("この OS では内蔵オーバーレイ選択を使ってください")


def _mac_region(timeout: float) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "capture.png"
        # -i: 対話的選択, -x: シャッター音なし
        result = subprocess.run(
            ["screencapture", "-i", "-x", str(target)],
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            raise CaptureCancelled("範囲選択がキャンセルされました")
        return Image.open(target).copy()


def _windows_snip(timeout: float) -> Image.Image:
    """Windows の切り取り＆スケッチ（結果はクリップボードに入る）。"""
    before = _clipboard_signature()
    subprocess.run(["cmd", "/c", "start", "", "ms-screenclip:"], check=False,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.3)
        image = clipboard_image()
        if image is not None and _signature(image) != before:
            return image
    raise CaptureCancelled("範囲選択がキャンセル、またはタイムアウトしました")


def _clipboard_signature() -> str | None:
    image = clipboard_image()
    return _signature(image) if image else None


def _signature(image: Image.Image) -> str:
    small = image.convert("L").resize((16, 16))
    return f"{image.size}:{hash(small.tobytes())}"


class OverlaySelector:
    """Tk 製の範囲選択オーバーレイ（OS 非依存フォールバック）。

    使い方:
        image = OverlaySelector(root).select()   # 中断時は CaptureCancelled
    """

    def __init__(self, master=None):
        self.master = master

    def select(self) -> Image.Image:
        import tkinter as tk
        from PIL import ImageTk

        screenshot = grab_fullscreen(all_screens=False)
        top = tk.Toplevel(self.master) if self.master else tk.Tk()
        top.attributes("-fullscreen", True)
        top.attributes("-topmost", True)
        top.configure(cursor="crosshair", bg="black")
        try:
            top.attributes("-alpha", 0.999)
        except tk.TclError:
            pass

        screen_w = top.winfo_screenwidth()
        screen_h = top.winfo_screenheight()
        preview = screenshot.resize((screen_w, screen_h)) if screenshot.size != (screen_w, screen_h) else screenshot
        photo = ImageTk.PhotoImage(preview.convert("RGB"))

        canvas = tk.Canvas(top, highlightthickness=0, bd=0, width=screen_w, height=screen_h)
        canvas.pack(fill="both", expand=True)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.create_rectangle(0, 0, screen_w, screen_h, fill="black", stipple="gray25", outline="")
        canvas.create_text(
            screen_w // 2, 40,
            text="ドラッグで範囲選択 / Esc でキャンセル",
            fill="white", font=("", 16),
        )

        state = {"x0": 0, "y0": 0, "rect": None, "bbox": None}

        def on_press(event):
            state["x0"], state["y0"] = event.x, event.y
            if state["rect"]:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="#39c5ff", width=2
            )

        def on_drag(event):
            if state["rect"]:
                canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

        def on_release(event):
            x0, y0 = state["x0"], state["y0"]
            state["bbox"] = (min(x0, event.x), min(y0, event.y), max(x0, event.x), max(y0, event.y))
            top.destroy()

        def on_escape(_event=None):
            state["bbox"] = None
            top.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        top.bind("<Escape>", on_escape)
        top.focus_force()
        canvas.image = photo  # GC 回避
        top.grab_set()
        top.wait_window()

        bbox = state["bbox"]
        if not bbox or bbox[2] - bbox[0] < 5 or bbox[3] - bbox[1] < 5:
            raise CaptureCancelled("範囲選択がキャンセルされました")

        # 画面座標 -> 元スクショ座標へスケール
        sx = screenshot.width / screen_w
        sy = screenshot.height / screen_h
        crop = (
            int(bbox[0] * sx), int(bbox[1] * sy),
            int(bbox[2] * sx), int(bbox[3] * sy),
        )
        return screenshot.crop(crop)
