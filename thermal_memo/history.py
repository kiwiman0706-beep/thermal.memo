"""印刷履歴（ローカル SQLite）とクラウド同期フォルダへの書き出し。

同期方式について:
  Google Keep には個人アカウントで使える公開 API が無い（Keep API は Workspace の
  管理者向けで、一般ユーザーのメモ操作には使えない。gkeepapi は非公式でアカウント
  ロックのリスクがある）。そのため本アプリは
    ローカル SQLite（検索・再印刷用の正）
      + 「同期フォルダ」への Markdown + PNG 書き出し（Google Drive / iCloud /
        Dropbox の同期フォルダを指定すればスマホからも閲覧できる）
  という構成にしている。将来 Drive API 等を足す場合も、この書き出し層を
  差し替えるだけで済む。
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .config import app_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS prints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,
    kind        TEXT    NOT NULL,       -- text / screenshot / document
    title       TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    image_file  TEXT,
    width_dots  INTEGER NOT NULL DEFAULT 0,
    height_dots INTEGER NOT NULL DEFAULT 0,
    copies      INTEGER NOT NULL DEFAULT 1,
    printer     TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'ok',
    error       TEXT    NOT NULL DEFAULT '',
    params      TEXT    NOT NULL DEFAULT '{}',
    synced_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_prints_created ON prints(created_at DESC);
"""


@dataclass
class Entry:
    id: int
    created_at: str
    kind: str
    title: str
    body: str
    source: str
    image_file: str | None
    width_dots: int
    height_dots: int
    copies: int
    printer: str
    status: str
    error: str
    params: dict[str, Any]
    synced_path: str | None

    @property
    def when(self) -> _dt.datetime:
        try:
            return _dt.datetime.fromisoformat(self.created_at)
        except ValueError:
            return _dt.datetime.now()

    def summary(self, limit: int = 60) -> str:
        text = (self.title or self.body or self.source or "").replace("\n", " ").strip()
        return text[:limit] + ("…" if len(text) > limit else "")


KIND_LABEL = {"text": "テキスト", "screenshot": "スクショ", "document": "ファイル", "qr": "QR"}


class History:
    def __init__(self, base: Path | None = None):
        self.base = Path(base) if base else app_dir()
        self.base.mkdir(parents=True, exist_ok=True)
        self.images_dir = self.base / "history_images"
        self.images_dir.mkdir(exist_ok=True)
        self.db_path = self.base / "history.sqlite3"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ 書き込み
    def add(
        self,
        *,
        kind: str,
        image: Image.Image | None = None,
        title: str = "",
        body: str = "",
        source: str = "",
        copies: int = 1,
        printer: str = "",
        status: str = "ok",
        error: str = "",
        params: dict[str, Any] | None = None,
        sync_dir: str | Path | None = None,
    ) -> Entry:
        now = _dt.datetime.now()
        image_file = None
        if image is not None:
            name = f"{now:%Y%m%d-%H%M%S-%f}.png"
            target = self.images_dir / name
            image.convert("1").save(target, optimize=True)
            image_file = name

        cursor = self._conn.execute(
            """INSERT INTO prints
               (created_at, kind, title, body, source, image_file, width_dots, height_dots,
                copies, printer, status, error, params)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now.isoformat(timespec="seconds"), kind, title, body, source, image_file,
                image.width if image else 0, image.height if image else 0,
                copies, printer, status, error, json.dumps(params or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        entry = self.get(int(cursor.lastrowid))
        assert entry is not None

        if sync_dir:
            try:
                path = self.export_entry(entry, sync_dir)
                self._conn.execute("UPDATE prints SET synced_path=? WHERE id=?", (str(path), entry.id))
                self._conn.commit()
                entry.synced_path = str(path)
            except OSError:
                pass  # 同期フォルダが一時的に使えなくても印刷自体は成功扱い
        return entry

    # -------------------------------------------------------------------- 読み出し
    def get(self, entry_id: int) -> Entry | None:
        row = self._conn.execute("SELECT * FROM prints WHERE id=?", (entry_id,)).fetchone()
        return self._to_entry(row) if row else None

    def list(self, query: str = "", kind: str = "", limit: int = 300) -> list[Entry]:
        sql = "SELECT * FROM prints WHERE 1=1"
        args: list[Any] = []
        if query:
            sql += " AND (title LIKE ? OR body LIKE ? OR source LIKE ?)"
            like = f"%{query}%"
            args += [like, like, like]
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        args.append(limit)
        return [self._to_entry(row) for row in self._conn.execute(sql, args)]

    def image_of(self, entry: Entry) -> Image.Image | None:
        if not entry.image_file:
            return None
        path = self.images_dir / entry.image_file
        if not path.exists():
            return None
        return Image.open(path).convert("1")

    def delete(self, entry_id: int) -> None:
        entry = self.get(entry_id)
        if entry and entry.image_file:
            (self.images_dir / entry.image_file).unlink(missing_ok=True)
        self._conn.execute("DELETE FROM prints WHERE id=?", (entry_id,))
        self._conn.commit()

    def purge_older_than(self, days: int) -> int:
        if days <= 0:
            return 0
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=days)).isoformat(timespec="seconds")
        rows = self._conn.execute("SELECT id FROM prints WHERE created_at < ?", (cutoff,)).fetchall()
        for row in rows:
            self.delete(int(row["id"]))
        return len(rows)

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM prints").fetchone()[0])

    # ---------------------------------------------------------------------- 同期
    def export_entry(self, entry: Entry, sync_dir: str | Path) -> Path:
        """1 件を同期フォルダへ Markdown（＋PNG）で書き出す。"""
        root = Path(sync_dir).expanduser()
        folder = root / f"{entry.when:%Y}" / f"{entry.when:%m}"
        folder.mkdir(parents=True, exist_ok=True)
        stem = f"{entry.when:%Y%m%d-%H%M%S}-{entry.id:05d}"

        image_link = ""
        image = self.image_of(entry)
        if image is not None:
            png = folder / f"{stem}.png"
            image.save(png, optimize=True)
            image_link = f"\n![print]({png.name})\n"

        lines = [
            f"# {entry.summary(80) or KIND_LABEL.get(entry.kind, entry.kind)}",
            "",
            f"- 日時: {entry.when:%Y-%m-%d %H:%M:%S}",
            f"- 種別: {KIND_LABEL.get(entry.kind, entry.kind)}",
            f"- プリンタ: {entry.printer}",
            f"- 状態: {entry.status}{(' / ' + entry.error) if entry.error else ''}",
        ]
        if entry.source:
            lines.append(f"- 元ファイル: {entry.source}")
        lines += ["", image_link, "", "---", "", entry.body or ""]
        md = folder / f"{stem}.md"
        md.write_text("\n".join(lines), encoding="utf-8")

        self._append_journal(root, entry)
        return md

    def _append_journal(self, root: Path, entry: Entry) -> None:
        """機械可読な追記型ジャーナル（将来の双方向同期用）。"""
        journal = root / "index.ndjson"
        record = {
            "id": entry.id,
            "created_at": entry.created_at,
            "kind": entry.kind,
            "title": entry.title,
            "summary": entry.summary(200),
            "source": entry.source,
            "status": entry.status,
        }
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def export_all(self, sync_dir: str | Path, entries: Iterable[Entry] | None = None) -> int:
        count = 0
        for entry in (entries if entries is not None else self.list(limit=100000)):
            try:
                self.export_entry(entry, sync_dir)
                count += 1
            except OSError:
                continue
        return count

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ internal
    @staticmethod
    def _to_entry(row: sqlite3.Row) -> Entry:
        try:
            params = json.loads(row["params"] or "{}")
        except json.JSONDecodeError:
            params = {}
        return Entry(
            id=int(row["id"]), created_at=row["created_at"], kind=row["kind"],
            title=row["title"], body=row["body"], source=row["source"],
            image_file=row["image_file"], width_dots=int(row["width_dots"]),
            height_dots=int(row["height_dots"]), copies=int(row["copies"]),
            printer=row["printer"], status=row["status"], error=row["error"],
            params=params, synced_path=row["synced_path"],
        )
