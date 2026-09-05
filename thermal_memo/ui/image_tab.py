"""スクリーンショット／画像タブ（二値化調整つき）。"""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from .. import capture, render
from .common import LabeledScale, debounce, section

MODES = [("dither", "ディザ（写真向き）"), ("threshold", "しきい値（文字向き）"),
         ("adaptive", "適応的（紙の写真向き）")]


class ImageTab(ttk.Frame):
    title = "スクショ・画像"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.source_image: Image.Image | None = None
        self.source_name = ""
        cfg = app.cfg["image"]

        self.mode = tk.StringVar(value=cfg["mode"])
        self.threshold = tk.IntVar(value=cfg["threshold"])
        self.brightness = tk.DoubleVar(value=cfg["brightness"])
        self.contrast = tk.DoubleVar(value=cfg["contrast"])
        self.scale = tk.IntVar(value=cfg["scale"])
        self.sharpen = tk.BooleanVar(value=cfg["sharpen"])
        self.invert = tk.BooleanVar(value=cfg["invert"])
        self.autocrop = tk.BooleanVar(value=cfg["autocrop"])
        self.caption = tk.StringVar(value="")

        refresh = debounce(self, 150)(self.app.refresh_preview)
        self.refresh = refresh

        # --- 取り込み
        grab = section(self, "取り込み")
        row = ttk.Frame(grab)
        row.pack(fill="x")
        os_label = "範囲選択（Win 標準）" if sys.platform == "win32" else "範囲選択（OS 標準）"
        ttk.Button(row, text=os_label, command=self.capture_os).pack(side="left", padx=(0, 4))
        ttk.Button(row, text="範囲選択（内蔵）", command=self.capture_overlay).pack(side="left", padx=4)
        ttk.Button(row, text="画面全体", command=self.capture_full).pack(side="left", padx=4)
        ttk.Button(row, text="クリップボード", command=self.paste_clipboard).pack(side="left", padx=4)
        ttk.Button(row, text="画像ファイル…", command=self.open_file).pack(side="left", padx=4)

        self.source_label = ttk.Label(grab, text="画像が未選択です", foreground="#777")
        self.source_label.pack(anchor="w", pady=(6, 0))
        ttk.Label(
            grab,
            text="ヒント: Win+Shift+S（Mac は ⌘⇧4 + Ctrl）で切り取ってから「クリップボード」でも取り込めます",
            foreground="#999", wraplength=520, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # --- 二値化
        binar = section(self, "二値化・調整")
        mode_row = ttk.Frame(binar)
        mode_row.pack(fill="x", pady=(0, 6))
        ttk.Label(mode_row, text="方式").pack(side="left")
        for value, label in MODES:
            ttk.Radiobutton(mode_row, text=label, value=value, variable=self.mode,
                            command=refresh).pack(side="left", padx=3)

        LabeledScale(binar, "しきい値", 0, 255, self.threshold, command=refresh).pack(fill="x")
        LabeledScale(binar, "明るさ", 0.2, 2.5, self.brightness, resolution=0.05,
                     fmt="{:.2f}", command=refresh).pack(fill="x")
        LabeledScale(binar, "コントラスト", 0.2, 3.0, self.contrast, resolution=0.05,
                     fmt="{:.2f}", command=refresh).pack(fill="x")
        LabeledScale(binar, "幅 %", 20, 100, self.scale, command=refresh).pack(fill="x")

        toggles = ttk.Frame(binar)
        toggles.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(toggles, text="シャープ", variable=self.sharpen, command=refresh).pack(side="left")
        ttk.Checkbutton(toggles, text="白黒反転", variable=self.invert, command=refresh).pack(side="left", padx=8)
        ttk.Checkbutton(toggles, text="余白を自動カット", variable=self.autocrop,
                        command=refresh).pack(side="left")
        ttk.Button(toggles, text="初期値に戻す", command=self.reset).pack(side="right")

        # --- キャプション
        cap = section(self, "キャプション（画像の上に印字）")
        entry = ttk.Entry(cap, textvariable=self.caption)
        entry.pack(fill="x")
        entry.bind("<KeyRelease>", lambda _e: refresh())

    # ------------------------------------------------------------------ 取り込み
    def _set_source(self, image: Image.Image | None, name: str) -> None:
        if image is None:
            return
        self.source_image = image
        self.source_name = name
        self.source_label.configure(
            text=f"{name}  ({image.width}×{image.height}px)", foreground="#333"
        )
        self.app.refresh_preview()

    def capture_os(self) -> None:
        if sys.platform not in ("win32", "darwin"):
            self.capture_overlay()
            return
        self.app.status("範囲選択中…", "busy")
        self.app.hide_window()

        def worker() -> None:
            try:
                image = capture.os_region_capture()
            except capture.CaptureCancelled as exc:
                self.app.post(lambda: self.app.status(str(exc), "warn"))
                image = None
            except Exception as exc:  # noqa: BLE001
                self.app.post(lambda e=exc: self.app.status(f"取り込み失敗: {e}", "error"))
                image = None
            finally:
                self.app.post(self.app.show_window)
            if image is not None:
                self.app.post(lambda: self._set_source(image, "スクリーンショット"))
                self.app.post(lambda: self.app.status("取り込みました", "ok"))

        threading.Thread(target=worker, daemon=True).start()

    def capture_overlay(self) -> None:
        self.app.hide_window()
        self.after(250, self._run_overlay)

    def _run_overlay(self) -> None:
        try:
            image = capture.OverlaySelector(self.app.winfo_toplevel()).select()
        except capture.CaptureCancelled as exc:
            self.app.show_window()
            self.app.status(str(exc), "warn")
            return
        except Exception as exc:  # noqa: BLE001
            self.app.show_window()
            messagebox.showerror("取り込み失敗", str(exc))
            return
        self.app.show_window()
        self._set_source(image, "スクリーンショット")
        self.app.status("取り込みました", "ok")

    def capture_full(self) -> None:
        self.app.hide_window()
        self.after(300, self._run_full)

    def _run_full(self) -> None:
        try:
            image = capture.grab_fullscreen()
        except Exception as exc:  # noqa: BLE001
            self.app.show_window()
            messagebox.showerror("取り込み失敗", str(exc))
            return
        self.app.show_window()
        self._set_source(image, "画面全体")

    def paste_clipboard(self) -> None:
        image = capture.clipboard_image()
        if image is None:
            self.app.status("クリップボードに画像がありません", "warn")
            return
        self._set_source(image, "クリップボード")

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="画像を選択",
            filetypes=[("画像", "*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff"), ("すべて", "*.*")],
        )
        if path:
            self.load_path(path)

    def load_path(self, path: str) -> None:
        try:
            image = Image.open(path)
            image.load()
        except OSError as exc:
            messagebox.showerror("読み込み失敗", str(exc))
            return
        self._set_source(image, Path(path).name)

    def reset(self) -> None:
        self.mode.set("dither")
        self.threshold.set(128)
        self.brightness.set(1.0)
        self.contrast.set(1.0)
        self.scale.set(100)
        self.sharpen.set(False)
        self.invert.set(False)
        self.autocrop.set(True)
        self.app.refresh_preview()

    # ------------------------------------------------------------------ 公開 API
    def build_image(self) -> Image.Image | None:
        if self.source_image is None:
            return None
        processed = render.process_image(
            self.source_image,
            width_dots=self.app.width_dots,
            mode=self.mode.get(),
            threshold=self.threshold.get(),
            brightness=self.brightness.get(),
            contrast=self.contrast.get(),
            sharpen=self.sharpen.get(),
            invert=self.invert.get(),
            autocrop=self.autocrop.get(),
            scale=self.scale.get(),
        )
        caption = self.caption.get().strip()
        if not caption:
            if processed.width == self.app.width_dots:
                return processed
            canvas = Image.new("1", (self.app.width_dots, processed.height), 1)
            canvas.paste(processed, ((self.app.width_dots - processed.width) // 2, 0))
            return canvas

        cfg = self.app.cfg["text"]
        head = render.text_to_image(
            caption,
            width_dots=self.app.width_dots,
            font_path=cfg["font_path"],
            font_size=max(20, int(cfg["font_size"] * 0.8)),
            line_spacing=4, margin=cfg["margin"], align="left",
            timestamp=cfg["timestamp"], timestamp_format=cfg["timestamp_format"],
            rule_line=True, header="", footer="",
        )
        return render.stack([head, processed], gap=8, width_dots=self.app.width_dots)

    def describe(self) -> dict:
        return {
            "kind": "screenshot",
            "title": self.caption.get().strip() or self.source_name,
            "body": self.caption.get().strip(),
            "source": self.source_name,
            "params": {
                "mode": self.mode.get(),
                "threshold": self.threshold.get(),
                "brightness": self.brightness.get(),
                "contrast": self.contrast.get(),
                "scale": self.scale.get(),
            },
        }

    def empty_message(self) -> str:
        return "先に画像を取り込んでください"

    def persist(self) -> None:
        self.app.cfg["image"].update({
            "mode": self.mode.get(),
            "threshold": self.threshold.get(),
            "brightness": self.brightness.get(),
            "contrast": self.contrast.get(),
            "sharpen": self.sharpen.get(),
            "invert": self.invert.get(),
            "autocrop": self.autocrop.get(),
            "scale": self.scale.get(),
        })
