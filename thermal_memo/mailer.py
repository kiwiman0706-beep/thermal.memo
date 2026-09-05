"""印刷内容を自分宛にメールしてアーカイブする（Gmail での検索・ラベル運用向け）。

Gmail API（OAuth）ではなく素の SMTP を使う。理由:
  * 追加ライブラリが要らない（smtplib は標準）
  * Gmail 側はアプリパスワードを作るだけで済む
  * 送信先を Gmail 以外に変えるのも設定 1 行

Gmail 側の受け取り方は docs/GMAIL.md を参照。要点は
「宛先にプラスアドレス（例 you+memo@gmail.com）を使い、
  Gmail のフィルタでラベルを自動付与する」。
"""

from __future__ import annotations

import datetime as _dt
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Any

ENV_PASSWORD = "THERMAL_MEMO_SMTP_PASSWORD"
CREDENTIAL_ACCOUNT = "smtp"

DEFAULT_SUBJECT = "[thermal.memo] {date} {title}"


class MailError(RuntimeError):
    pass


@dataclass
class MailConfig:
    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = 465
    use_ssl: bool = True            # 465=SSL, 587=STARTTLS
    username: str = ""              # Gmail アドレス
    from_addr: str = ""             # 空なら username を使う
    to_addr: str = ""               # 例: you+memo@gmail.com
    subject_template: str = DEFAULT_SUBJECT
    attach_image: bool = True
    timeout: float = 20.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MailConfig":
        base = cls()
        return cls(
            enabled=bool(data.get("enabled", base.enabled)),
            host=str(data.get("host", base.host)).strip(),
            port=int(data.get("port", base.port)),
            use_ssl=bool(data.get("use_ssl", base.use_ssl)),
            username=str(data.get("username", base.username)).strip(),
            from_addr=str(data.get("from_addr", base.from_addr)).strip(),
            to_addr=str(data.get("to_addr", base.to_addr)).strip(),
            subject_template=str(data.get("subject_template", base.subject_template)),
            attach_image=bool(data.get("attach_image", base.attach_image)),
            timeout=float(data.get("timeout", base.timeout)),
        )

    @property
    def sender(self) -> str:
        return self.from_addr or self.username

    def validate(self) -> None:
        if not self.host:
            raise MailError("SMTP サーバーが未設定です")
        if not self.username:
            raise MailError("SMTP ユーザー名（Gmail アドレス）が未設定です")
        if not self.to_addr:
            raise MailError("送信先アドレスが未設定です")


def format_subject(template: str, *, title: str, kind: str, when: _dt.datetime) -> str:
    """件名テンプレートを展開する。未知のプレースホルダはそのまま残す。"""
    values = {
        "date": when.strftime("%Y-%m-%d"),
        "time": when.strftime("%H:%M"),
        "datetime": when.strftime("%Y-%m-%d %H:%M"),
        "title": (title or "メモ").replace("\n", " ").strip()[:80],
        "kind": kind,
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result.strip() or "[thermal.memo]"


def build_message(
    cfg: MailConfig,
    *,
    title: str,
    body: str,
    kind: str = "text",
    printer: str = "",
    source: str = "",
    image_png: bytes | None = None,
    when: _dt.datetime | None = None,
) -> EmailMessage:
    """アーカイブ用のメールを組み立てる。"""
    cfg.validate()
    now = when or _dt.datetime.now()

    message = EmailMessage()
    message["Subject"] = format_subject(cfg.subject_template, title=title, kind=kind, when=now)
    message["From"] = cfg.sender
    message["To"] = cfg.to_addr
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain="thermal.memo")
    # Gmail のフィルタからは参照できないが、他のクライアントでの仕分けに使える
    message["X-Thermal-Memo"] = "1"
    message["X-Thermal-Memo-Kind"] = kind

    lines = [
        body.rstrip() if body else "（本文なし）",
        "",
        "----",
        f"日時: {now:%Y-%m-%d %H:%M:%S}",
        f"種別: {kind}",
    ]
    if source:
        lines.append(f"元: {source}")
    if printer:
        lines.append(f"プリンタ: {printer}")
    message.set_content("\n".join(lines))

    if image_png and cfg.attach_image:
        message.add_attachment(
            image_png, maintype="image", subtype="png",
            filename=f"{now:%Y%m%d-%H%M%S}.png",
        )
    return message


def send(cfg: MailConfig, message: EmailMessage, password: str) -> None:
    """SMTP で送る。必ずワーカースレッドから呼ぶこと。"""
    cfg.validate()
    if not password:
        raise MailError(
            "アプリパスワードが未設定です（設定タブで登録するか、"
            f"環境変数 {ENV_PASSWORD} を設定してください）"
        )
    try:
        if cfg.use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=cfg.timeout)
        else:
            server = smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout)
        with server:
            if not cfg.use_ssl:
                server.starttls()
            server.login(cfg.username, password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(
            "認証に失敗しました。Gmail では通常のパスワードではなく"
            "「アプリパスワード」が必要です（2 段階認証の有効化が前提）"
        ) from exc
    except smtplib.SMTPException as exc:
        raise MailError(f"送信に失敗しました: {exc}") from exc
    except OSError as exc:
        raise MailError(f"SMTP サーバーへ接続できません: {exc}") from exc


def send_test(cfg: MailConfig, password: str) -> str:
    """設定確認用の 1 通を送る。"""
    now = _dt.datetime.now()
    message = build_message(
        cfg,
        title="送信テスト",
        body="thermal.memo からの送信テストです。\n"
             "この件名でフィルタを作るとラベルが自動で付きます。",
        kind="test", when=now,
    )
    send(cfg, message, password)
    return f"{cfg.to_addr} へ送信しました（件名: {message['Subject']}）"
