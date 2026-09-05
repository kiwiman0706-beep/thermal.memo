"""QR・メール・秘密情報まわりのテスト。"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from thermal_memo import credentials, mailer, qrcodes, render  # noqa: E402


def _decoder_available() -> bool:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401

        return True
    except ImportError:
        return False


def _decode(image) -> str:
    """OpenCV で QR を読む。

    OpenCV の検出器はページ全体を走査するため、QR の周囲にある文字の量や
    位置で結果が変わることがある。実際 CI（日本語フォントが無く DejaVuSans に
    フォールバックする環境）では、見出し・キャプションの描画が変わった結果
    一部のサイズだけ読めないことがあった。QR 自体は壊れていない。
    スマホのスキャナより弱い検出器なので、テストが環境差で落ちないよう
    等倍・2 倍・detectAndDecodeMulti を順に試し、どれかで読めれば可とする。
    期待値（URL の完全一致）は緩めていない。
    """
    import cv2
    import numpy as np

    detector = cv2.QRCodeDetector()
    candidates = [image.convert("L")]
    candidates.append(candidates[0].resize((image.width * 2, image.height * 2)))

    for candidate in candidates:
        array = np.array(candidate)
        value = detector.detectAndDecode(array)[0]
        if value:
            return value
        try:
            ok, values, _points, _straight = detector.detectAndDecodeMulti(array)
        except Exception:
            continue
        if ok:
            for found in values:
                if found:
                    return found
    return ""


@unittest.skipUnless(qrcodes.available(), "qrcode パッケージが無い")
class TestQr(unittest.TestCase):

    URL = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing"

    def test_matrix_is_square_and_monochrome(self):
        matrix = qrcodes.make_matrix("hello")
        self.assertEqual(matrix.width, matrix.height)
        self.assertEqual(matrix.mode, "1")

    def test_fits_paper_width(self):
        image = qrcodes.make_qr(self.URL, width_dots=576, size_percent=60)
        self.assertEqual(image.width, 576)
        self.assertEqual(image.mode, "1")

    def test_scaling_is_integer_multiple(self):
        """端数拡大でモジュールが歪むと読み取り率が落ちるため整数倍に限る。"""
        data = "https://example.com/x"
        modules = qrcodes.module_count(data)
        for percent in (30, 55, 80, 100):
            image = qrcodes.make_qr(data, width_dots=576, size_percent=percent,
                                    caption="", timestamp=False)
            # 余白 8px を差し引いた QR 本体の高さがモジュール数の整数倍であること
            body = image.height - 16
            self.assertEqual(body % modules, 0, f"size_percent={percent}")

    def test_error_level_changes_size(self):
        low = qrcodes.module_count(self.URL, "L")
        high = qrcodes.module_count(self.URL, "H")
        self.assertGreater(high, low)

    def test_empty_data_raises(self):
        with self.assertRaises(qrcodes.QRError):
            qrcodes.make_qr("", width_dots=576)

    @unittest.skipUnless(_decoder_available(), "OpenCV が無い")
    def test_printed_qr_actually_decodes(self):
        """印刷される 1bit 画像が本当に QR として読めることを確認する。"""
        for percent in (30, 40, 55, 70, 100):
            image = qrcodes.make_qr(self.URL, width_dots=576, size_percent=percent,
                                    label="", caption="", timestamp=False)
            self.assertEqual(_decode(image), self.URL, f"size_percent={percent} で読めない")

    @unittest.skipUnless(_decoder_available(), "OpenCV が無い")
    def test_qr_still_decodes_with_label_and_caption(self):
        """見出し・キャプションを合成しても QR 部分が壊れないこと。"""
        image = qrcodes.make_qr(self.URL, width_dots=576, size_percent=60,
                                label="紹介状スキャン", caption=self.URL, timestamp=True)
        self.assertEqual(_decode(image), self.URL)

    @unittest.skipUnless(_decoder_available(), "OpenCV が無い")
    def test_decodes_without_japanese_font(self):
        """日本語フォントが無い環境（CI 相当）でも読めること。

        フォントが変わると見出し・キャプションの描画が変わり、ページ全体を
        走査する検出器の結果が変わる。実際にこの条件で 60% だけ読めず CI が
        落ちたため、その状況を固定して回帰を防ぐ。
        """
        from unittest import mock

        from thermal_memo import fonts

        fallback = None
        for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                          "/usr/share/fonts/dejavu/DejaVuSans.ttf"):
            if Path(candidate).exists():
                fallback = candidate
                break
        if fallback is None:
            self.skipTest("代替フォントが見つからない")

        with mock.patch.object(fonts, "detect", return_value=fallback):
            for percent in (40, 60, 100):
                image = qrcodes.make_qr(self.URL, width_dots=576, size_percent=percent,
                                        label="紹介状", caption=self.URL, timestamp=True)
                self.assertEqual(_decode(image), self.URL, f"size_percent={percent}")


class TestLongTokenWrapping(unittest.TestCase):
    """URL のような長い 1 語がはみ出さないこと（QR キャプションで必要）。"""

    def test_long_url_is_broken(self):
        font = render.load_font(None, 20)
        url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view"
        lines = render.wrap_text(url, font, 300)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(font.getlength(line), 300)
        self.assertEqual("".join(lines), url)

    def test_short_text_untouched(self):
        font = render.load_font(None, 20)
        self.assertEqual(render.wrap_text("短い行", font, 500), ["短い行"])


class TestMailer(unittest.TestCase):

    def _config(self) -> mailer.MailConfig:
        return mailer.MailConfig(
            enabled=True, host="smtp.example.com", port=465, use_ssl=True,
            username="me@example.com", to_addr="me+memo@example.com",
        )

    def test_subject_template(self):
        when = _dt.datetime(2026, 9, 5, 14, 23)
        subject = mailer.format_subject(
            "[thermal.memo] {date} {time} {kind} {title}",
            title="受付メモ\n2 行目", kind="text", when=when,
        )
        self.assertEqual(subject, "[thermal.memo] 2026-09-05 14:23 text 受付メモ 2 行目")

    def test_unknown_placeholder_is_kept(self):
        when = _dt.datetime(2026, 9, 5, 14, 23)
        subject = mailer.format_subject("{date} {unknown}", title="x", kind="text", when=when)
        self.assertEqual(subject, "2026-09-05 {unknown}")

    def test_message_headers_and_body(self):
        message = mailer.build_message(
            self._config(), title="発注メモ", body="ガーゼ 5 箱", kind="text",
            printer="192.168.1.50:9100", when=_dt.datetime(2026, 9, 5, 14, 23),
        )
        self.assertEqual(message["To"], "me+memo@example.com")
        self.assertEqual(message["From"], "me@example.com")
        self.assertIn("発注メモ", message["Subject"])
        self.assertEqual(message["X-Thermal-Memo"], "1")
        body = message.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("ガーゼ 5 箱", body)
        self.assertIn("192.168.1.50:9100", body)

    def test_attachment_included(self):
        message = mailer.build_message(
            self._config(), title="t", body="b", image_png=b"\x89PNG\r\n\x1a\nfake",
        )
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_content_type(), "image/png")

    def test_attachment_skipped_when_disabled(self):
        cfg = self._config()
        cfg.attach_image = False
        message = mailer.build_message(cfg, title="t", body="b", image_png=b"fake")
        self.assertEqual(list(message.iter_attachments()), [])

    def test_validate_requires_fields(self):
        cfg = self._config()
        cfg.to_addr = ""
        with self.assertRaises(mailer.MailError):
            cfg.validate()

    def test_send_without_password_raises(self):
        with self.assertRaises(mailer.MailError):
            mailer.send(self._config(), mailer.build_message(self._config(), title="t", body="b"), "")

    def test_from_dict_roundtrip(self):
        cfg = mailer.MailConfig.from_dict({
            "enabled": True, "host": " smtp.gmail.com ", "port": 587, "use_ssl": False,
            "username": " me@gmail.com ", "to_addr": "me+memo@gmail.com",
        })
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.host, "smtp.gmail.com")
        self.assertEqual(cfg.username, "me@gmail.com")
        self.assertFalse(cfg.use_ssl)
        self.assertEqual(cfg.sender, "me@gmail.com")


class _FakeSMTP:
    """smtplib.SMTP / SMTP_SSL の代わり。呼ばれた手順を記録する。"""

    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list[str] = []
        self.sent: list[object] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.calls.append("quit")
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(f"login:{username}:{password}")

    def send_message(self, message):
        self.calls.append("send")
        self.sent.append(message)


class TestSendFlow(unittest.TestCase):
    """実際に SMTP をしゃべる部分の手順を検証する（ネットワークは使わない）。"""

    def setUp(self):
        _FakeSMTP.instances = []
        self._ssl = mailer.smtplib.SMTP_SSL
        self._plain = mailer.smtplib.SMTP
        mailer.smtplib.SMTP_SSL = _FakeSMTP
        mailer.smtplib.SMTP = _FakeSMTP

    def tearDown(self):
        mailer.smtplib.SMTP_SSL = self._ssl
        mailer.smtplib.SMTP = self._plain

    def _config(self, use_ssl: bool) -> mailer.MailConfig:
        return mailer.MailConfig(
            enabled=True, host="smtp.gmail.com", port=465 if use_ssl else 587,
            use_ssl=use_ssl, username="me@gmail.com", to_addr="me+memo@gmail.com",
        )

    def test_ssl_path_does_not_starttls(self):
        cfg = self._config(True)
        mailer.send(cfg, mailer.build_message(cfg, title="t", body="b"), "app-pw")
        server = _FakeSMTP.instances[0]
        self.assertEqual(server.port, 465)
        self.assertNotIn("starttls", server.calls)
        self.assertIn("login:me@gmail.com:app-pw", server.calls)
        self.assertIn("send", server.calls)

    def test_starttls_path(self):
        cfg = self._config(False)
        mailer.send(cfg, mailer.build_message(cfg, title="t", body="b"), "app-pw")
        server = _FakeSMTP.instances[0]
        self.assertEqual(server.port, 587)
        self.assertEqual(server.calls[0], "starttls")
        self.assertLess(server.calls.index("starttls"), server.calls.index("send"))

    def test_send_test_delivers_message(self):
        cfg = self._config(True)
        result = mailer.send_test(cfg, "app-pw")
        self.assertIn("me+memo@gmail.com", result)
        self.assertEqual(len(_FakeSMTP.instances[0].sent), 1)
        self.assertIn("thermal.memo", _FakeSMTP.instances[0].sent[0]["Subject"])

    def test_auth_error_is_translated(self):
        class Rejecting(_FakeSMTP):
            def login(self, username, password):
                raise mailer.smtplib.SMTPAuthenticationError(535, b"bad")

        mailer.smtplib.SMTP_SSL = Rejecting
        cfg = self._config(True)
        with self.assertRaises(mailer.MailError) as caught:
            mailer.send(cfg, mailer.build_message(cfg, title="t", body="b"), "wrong")
        self.assertIn("アプリパスワード", str(caught.exception))


class TestCredentials(unittest.TestCase):

    def test_env_var_wins(self):
        os.environ["THERMAL_MEMO_TEST_SECRET"] = "app-password"
        try:
            self.assertEqual(
                credentials.retrieve("no-such-account", "THERMAL_MEMO_TEST_SECRET"),
                "app-password",
            )
        finally:
            del os.environ["THERMAL_MEMO_TEST_SECRET"]

    def test_missing_returns_none(self):
        self.assertIsNone(credentials.retrieve("no-such-account-xyz"))

    def test_backend_name_is_reported(self):
        self.assertTrue(credentials.backend_name())

    def test_store_raises_when_no_backend(self):
        if credentials.can_store():
            self.skipTest("この環境には保管先がある")
        with self.assertRaises(credentials.CredentialError):
            credentials.store("test", "secret")


if __name__ == "__main__":
    unittest.main()
