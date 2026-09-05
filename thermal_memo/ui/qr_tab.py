"""QR タブ。URL やテキストを QR にして印刷する。

Google ドライブへファイルを上げて、そのリンクの QR を出す導線もここに置く。
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from .. import drive, qrcodes
from .common import LabeledScale, debounce, section

PRESETS = [
    ("院内Wi-Fi", "WIFI:T:WPA;S:SSID;P:PASSWORD;;"),
    ("電話", "tel:0300000000"),
    ("地図", "https://maps.google.com/?q="),
]


class QrTab(ttk.Frame):
    title = "QR"

    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        cfg = app.cfg["qr"]

        self.size_percent = tk.IntVar(value=cfg["size_percent"])
        self.error = tk.StringVar(value=cfg["error"])
        self.caption_url = tk.BooleanVar(value=cfg["caption_url"])
        self.timestamp = tk.BooleanVar(value=cfg["timestamp"])
        self.label = tk.StringVar(value="")
        self.share_anyone = tk.BooleanVar(value=app.cfg["drive"]["share_anyone"])
        self.uploaded_name = ""

        refresh = debounce(self, 250)(self.app.refresh_preview)
        self.refresh = refresh

        # --- 内容
        content = section(self, "QR にする内容（URL / テキスト）")
        wrapper = ttk.Frame(content, relief="sunken", borderwidth=1)
        wrapper.pack(fill="both", expand=True)
        self.text = tk.Text(wrapper, wrap="char", height=5, undo=True, font=("", 11),
                            borderwidth=0, highlightthickness=0)
        self.text.pack(fill="both", expand=True)
        self.text.bind("<KeyRelease>", lambda _e: refresh())

        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="クリップボードから貼付", command=self.paste).pack(side="left")
        ttk.Button(buttons, text="消去", command=self.clear).pack(side="left", padx=6)
        for name, value in PRESETS:
            ttk.Button(buttons, text=name, width=9,
                       command=lambda v=value: self.set_content(v)).pack(side="left", padx=2)

        self.info = ttk.Label(content, text="", foreground="#777")
        self.info.pack(anchor="w", pady=(6, 0))

        # --- Google ドライブ
        gdrive = section(self, "Google ドライブにアップして QR にする")
        row = ttk.Frame(gdrive)
        row.pack(fill="x")
        self.upload_button = ttk.Button(row, text="ファイルを選んでアップロード…",
                                        command=self.upload_file)
        self.upload_button.pack(side="left")
        ttk.Checkbutton(row, text="リンクを知っている全員に公開",
                        variable=self.share_anyone).pack(side="left", padx=10)
        self.drive_status = ttk.Label(gdrive, text=drive.status_text(), foreground="#777",
                                      wraplength=520, justify="left")
        self.drive_status.pack(anchor="w", pady=(6, 0))
        ttk.Label(
            gdrive,
            text=("公開設定は既定で変更しません（自分のアカウントで開くだけなら公開不要です）。"
                  "患者情報を含むファイルを公開にしないでください。"),
            foreground="#8a6d00", wraplength=520, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # --- 体裁
        style = section(self, "体裁")
        LabeledScale(style, "サイズ %", 20, 100, self.size_percent, command=refresh).pack(fill="x")

        row = ttk.Frame(style)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="誤り訂正").pack(side="left")
        for level in qrcodes.ERROR_LEVELS:
            ttk.Radiobutton(row, text=level, value=level, variable=self.error,
                            command=refresh).pack(side="left", padx=2)
        ttk.Label(row, text="（H ほど汚れ・かすれに強いが大きくなる）",
                  foreground="#999").pack(side="left", padx=6)

        row = ttk.Frame(style)
        row.pack(fill="x", pady=(6, 0))
        ttk.Checkbutton(row, text="URL も文字で印字", variable=self.caption_url,
                        command=refresh).pack(side="left")
        ttk.Checkbutton(row, text="日時", variable=self.timestamp,
                        command=refresh).pack(side="left", padx=8)
        ttk.Label(row, text="見出し").pack(side="left", padx=(12, 4))
        entry = ttk.Entry(row, textvariable=self.label)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<KeyRelease>", lambda _e: refresh())

        if not qrcodes.available():
            ttk.Label(self, text="QR の生成には qrcode パッケージが必要です（pip install qrcode）",
                      foreground="#b3261e").pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------ 内容操作
    def content(self) -> str:
        return self.text.get("1.0", "end").strip()

    def set_content(self, value: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        self.app.refresh_preview()

    def clear(self) -> None:
        self.uploaded_name = ""
        self.set_content("")

    def paste(self) -> None:
        try:
            value = self.clipboard_get()
        except tk.TclError:
            self.app.status("クリップボードにテキストがありません", "warn")
            return
        self.set_content(value.strip())

    # ------------------------------------------------------------------ ドライブ
    def upload_file(self) -> None:
        if not drive.libraries_available():
            messagebox.showinfo(
                "Google ドライブ連携",
                "追加ライブラリが必要です:\n\n"
                "pip install google-api-python-client google-auth-oauthlib\n\n"
                "設定手順は docs/DRIVE_QR.md を参照してください。\n"
                "なお、ドライブの画面でコピーしたリンクを上の欄に貼り付ければ、"
                "連携なしでも QR は作れます。",
            )
            return
        path = filedialog.askopenfilename(title="アップロードするファイルを選択")
        if not path:
            return
        if self.share_anyone.get() and not messagebox.askyesno(
            "公開の確認",
            "「リンクを知っている全員が閲覧可」にしてアップロードします。\n"
            "リンクを知れば誰でも開けます。患者情報を含むファイルでは行わないでください。\n\n"
            "続けますか？",
        ):
            return

        self.app.cfg["drive"]["share_anyone"] = self.share_anyone.get()
        self.upload_button.configure(state="disabled")
        self.app.status("アップロード中…", "busy")
        folder = self.app.cfg["drive"].get("folder_id") or None
        share = self.share_anyone.get()

        def worker() -> None:
            try:
                result = drive.upload(path, folder_id=folder, share_anyone=share)
            except Exception as exc:  # noqa: BLE001
                self.app.post(lambda e=exc: self._upload_failed(e))
                return
            self.app.post(lambda: self._upload_done(result))

        threading.Thread(target=worker, daemon=True).start()

    def _upload_done(self, result: drive.DriveFile) -> None:
        self.upload_button.configure(state="normal")
        self.uploaded_name = result.name
        if not self.label.get().strip():
            self.label.set(result.name)
        self.set_content(result.link)
        note = "（リンクを知る全員に公開）" if result.shared else "（共有設定は変更していません）"
        self.app.status(f"アップロードしました: {result.name} {note}", "ok")
        self.drive_status.configure(text=drive.status_text())

    def _upload_failed(self, exc: Exception) -> None:
        self.upload_button.configure(state="normal")
        self.app.status(f"アップロード失敗: {exc}", "error")
        messagebox.showerror("アップロード失敗", str(exc))

    # ------------------------------------------------------------------ 公開 API
    def build_image(self) -> Image.Image | None:
        data = self.content()
        if not data:
            self.info.configure(text="")
            return None
        cfg = self.app.cfg
        try:
            image = qrcodes.make_qr(
                data,
                width_dots=self.app.width_dots,
                size_percent=self.size_percent.get(),
                error=self.error.get(),
                label=self.label.get(),
                caption=data if self.caption_url.get() else "",
                font_path=cfg["text"]["font_path"],
                font_size=cfg["qr"]["font_size"],
                timestamp=self.timestamp.get(),
                timestamp_format=cfg["text"]["timestamp_format"],
            )
        except qrcodes.QRError as exc:
            self.info.configure(text=str(exc))
            return None
        modules = qrcodes.module_count(data, self.error.get())
        self.info.configure(
            text=f"{len(data)} 文字 / {modules}×{modules} モジュール / 誤り訂正 {self.error.get()}"
        )
        return image

    def describe(self) -> dict:
        data = self.content()
        title = self.label.get().strip() or self.uploaded_name or data[:60]
        return {
            "kind": "qr",
            "title": title,
            "body": data,
            "source": self.uploaded_name,
            "params": {"error": self.error.get(), "size_percent": self.size_percent.get()},
        }

    def empty_message(self) -> str:
        return "QR にする URL かテキストを入力してください"

    def persist(self) -> None:
        self.app.cfg["qr"].update({
            "size_percent": self.size_percent.get(),
            "error": self.error.get(),
            "caption_url": self.caption_url.get(),
            "timestamp": self.timestamp.get(),
        })
        self.app.cfg["drive"]["share_anyone"] = self.share_anyone.get()

    def load_path_link(self, path: str) -> None:
        """他タブからファイルを渡してアップロードさせる用の入口。"""
        self.app.select_tab(self)
        self.label.set(Path(path).name)
