"""GUI に依存しないコア機能のテスト（python -m unittest discover tests）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from PIL import Image  # noqa: E402

from thermal_memo import documents, escpos, history, render  # noqa: E402


class TestEscpos(unittest.TestCase):
    def test_pack_marks_black_bits(self):
        img = Image.new("1", (8, 1), 1)      # 全部白
        img.putpixel((0, 0), 0)              # 左端だけ黒
        data, bpr, height = escpos.pack_1bit(img)
        self.assertEqual((bpr, height), (1, 1))
        self.assertEqual(data[0], 0b10000000)

    def test_pack_masks_row_padding(self):
        """幅が 8 の倍数でないとき、行末の余りビットが黒にならないこと。"""
        img = Image.new("1", (12, 2), 1)     # 全部白 -> 全ビット 0 であるべき
        data, bpr, _ = escpos.pack_1bit(img)
        self.assertEqual(bpr, 2)
        self.assertEqual(set(data), {0})

    def test_raster_chunk_headers(self):
        img = Image.new("1", (576, 300), 1)
        chunks = list(escpos.raster_chunks(img, chunk_rows=128))
        self.assertEqual(len(chunks), 3)     # 128 + 128 + 44
        head = chunks[0]
        self.assertEqual(head[:3], b"\x1dv0")
        self.assertEqual(head[4] | (head[5] << 8), 72)    # bytes/row
        self.assertEqual(head[6] | (head[7] << 8), 128)   # rows
        self.assertEqual(chunks[-1][6] | (chunks[-1][7] << 8), 44)

    def test_build_job_structure(self):
        img = Image.new("1", (64, 10), 1)
        job = escpos.build_job(img, copies=2, cut=True, feed_lines=2)
        self.assertTrue(job.startswith(escpos.INIT))
        self.assertEqual(job.count(escpos.CUT_PARTIAL), 2)

    def test_roundtrip_through_fake_printer(self):
        """組み立てたジョブを擬似プリンタでデコードすると元画像に戻る。"""
        from fake_printer import parse_escpos

        src = Image.new("1", (64, 40), 1)
        for x in range(0, 64, 3):
            for y in range(0, 40, 2):
                src.putpixel((x, y), 0)
        job = escpos.build_job(src, copies=1, cut=True, feed_lines=1, chunk_rows=16)
        pages = parse_escpos(job)
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].size, src.size)
        self.assertEqual(pages[0].tobytes(), src.tobytes())


class TestRender(unittest.TestCase):
    def test_text_image_width_and_mode(self):
        img = render.text_to_image("テスト\n二行目", width_dots=384, timestamp=False)
        self.assertEqual(img.width, 384)
        self.assertEqual(img.mode, "1")
        self.assertGreater(img.height, 10)

    def test_wrap_respects_width(self):
        font = render.load_font(None, 20)
        lines = render.wrap_text("あ" * 200, font, 200)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(font.getlength(line), 220)  # 禁則による多少の超過は許容

    def test_wrap_keeps_ascii_words(self):
        font = render.load_font(None, 20)
        lines = render.wrap_text("hello world foobar", font, 10_000)
        self.assertEqual(lines, ["hello world foobar"])

    def test_no_line_start_kinsoku(self):
        font = render.load_font(None, 20)
        width = int(font.getlength("あ") * 5)
        lines = render.wrap_text("ああああ、ああ", font, width)
        for line in lines[1:]:
            self.assertNotIn(line[:1], "、。")

    def test_process_image_scales_to_width(self):
        src = Image.new("L", (1000, 400), 200)
        out = render.process_image(src, width_dots=576, mode="threshold", autocrop=False)
        self.assertEqual(out.width, 576)
        self.assertEqual(out.mode, "1")

    def test_process_image_scale_percent(self):
        src = Image.new("L", (1000, 400), 0)
        out = render.process_image(src, width_dots=576, scale=50, autocrop=False)
        self.assertEqual(out.width, 288)

    def test_stack(self):
        a = Image.new("1", (576, 20), 1)
        b = Image.new("1", (576, 30), 1)
        out = render.stack([a, b], gap=10, width_dots=576)
        self.assertEqual(out.size, (576, 60))


class TestDocuments(unittest.TestCase):
    def test_page_spec(self):
        self.assertEqual(documents.parse_page_spec("all", 3), [0, 1, 2])
        self.assertEqual(documents.parse_page_spec("1,3-4", 5), [0, 2, 3])
        self.assertEqual(documents.parse_page_spec("9", 3), [0, 1, 2])  # 範囲外は全ページ

    def test_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memo.txt"
            path.write_text("こんにちは\n世界", encoding="utf-8")
            info = documents.inspect(path)
            self.assertEqual(info.kind, "text")
            self.assertIn("世界", documents.extract_text(path))

    def test_unsupported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"\x00")
            with self.assertRaises(documents.DocumentError):
                documents.inspect(path)


class TestHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.hist = history.History(Path(self._tmp.name))

    def tearDown(self):
        self.hist.close()
        self._tmp.cleanup()

    def test_add_and_list(self):
        img = Image.new("1", (576, 50), 1)
        entry = self.hist.add(kind="text", image=img, title="件名", body="本文です",
                              printer="10.0.0.1:9100")
        self.assertEqual(self.hist.count(), 1)
        self.assertEqual(self.hist.list()[0].title, "件名")
        self.assertIsNotNone(self.hist.image_of(entry))

    def test_search(self):
        self.hist.add(kind="text", title="発注", body="ガーゼ")
        self.hist.add(kind="text", title="連絡", body="検査結果")
        self.assertEqual(len(self.hist.list("ガーゼ")), 1)
        self.assertEqual(len(self.hist.list(kind="text")), 2)

    def test_delete_removes_image(self):
        img = Image.new("1", (100, 10), 1)
        entry = self.hist.add(kind="text", image=img, title="x")
        path = self.hist.images_dir / entry.image_file
        self.assertTrue(path.exists())
        self.hist.delete(entry.id)
        self.assertFalse(path.exists())
        self.assertEqual(self.hist.count(), 0)

    def test_sync_export(self):
        with tempfile.TemporaryDirectory() as sync:
            img = Image.new("1", (100, 10), 1)
            entry = self.hist.add(kind="text", image=img, title="同期テスト",
                                  body="ほんぶん", sync_dir=sync)
            self.assertIsNotNone(entry.synced_path)
            written = list(Path(sync).rglob("*.md"))
            self.assertEqual(len(written), 1)
            self.assertIn("ほんぶん", written[0].read_text(encoding="utf-8"))
            self.assertTrue((Path(sync) / "index.ndjson").exists())
            self.assertEqual(len(list(Path(sync).rglob("*.png"))), 1)

    def test_purge(self):
        self.hist.add(kind="text", title="古い")
        self.hist._conn.execute("UPDATE prints SET created_at='2000-01-01T00:00:00'")
        self.hist._conn.commit()
        self.assertEqual(self.hist.purge_older_than(30), 1)
        self.assertEqual(self.hist.count(), 0)


if __name__ == "__main__":
    unittest.main()
