"""Google ドライブへファイルを上げてリンクを取り出す（QR 印刷用）。

前提: Google Cloud Console で「デスクトップアプリ」の OAuth クライアントを作り、
credentials.json をアプリのデータフォルダに置くこと。手順は docs/DRIVE_QR.md。

共有設定は既定で **変更しない**。自分のアカウントでスマホから開くだけなら
公開する必要がないため。「リンクを知っている全員」に公開したいときだけ
share_anyone=True を明示する。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import app_dir

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET_NAME = "credentials.json"
TOKEN_NAME = "drive_token.json"


class DriveError(RuntimeError):
    pass


@dataclass
class DriveFile:
    id: str
    name: str
    link: str
    shared: bool


def client_secret_path() -> Path:
    return app_dir() / CLIENT_SECRET_NAME


def token_path() -> Path:
    return app_dir() / TOKEN_NAME


def libraries_available() -> bool:
    try:
        import google.oauth2.credentials  # noqa: F401
        import google_auth_oauthlib.flow  # noqa: F401
        import googleapiclient.discovery  # noqa: F401

        return True
    except ImportError:
        return False


def configured() -> bool:
    return libraries_available() and client_secret_path().exists()


def status_text() -> str:
    """設定状況を 1 行で説明する（UI 表示用）。"""
    if not libraries_available():
        return ("未設定: pip install google-api-python-client google-auth-oauthlib "
                "が必要です")
    if not client_secret_path().exists():
        return f"未設定: {client_secret_path()} に OAuth クライアントの JSON を置いてください"
    if token_path().exists():
        return "設定済み（認証トークンあり）"
    return "設定済み（初回アップロード時にブラウザで認証します）"


def _credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = token_path()
    creds = None
    if token.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            pass

    secret = client_secret_path()
    if not secret.exists():
        raise DriveError(
            f"OAuth クライアントの JSON がありません: {secret}\n"
            "docs/DRIVE_QR.md の手順で作成して置いてください。"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    token.write_text(creds.to_json(), encoding="utf-8")
    try:
        token.chmod(0o600)
    except OSError:
        pass
    return creds


def upload(
    path: str | Path,
    *,
    folder_id: str | None = None,
    share_anyone: bool = False,
) -> DriveFile:
    """ファイルをアップロードして共有リンクを返す。

    :param folder_id:     置き先フォルダ（省略時はマイドライブ直下）
    :param share_anyone:  True にすると「リンクを知っている全員が閲覧可」にする。
                          患者情報を含むファイルでは絶対に使わないこと。
    """
    if not libraries_available():
        raise DriveError(
            "Google ドライブ連携には追加ライブラリが必要です:\n"
            "pip install google-api-python-client google-auth-oauthlib"
        )
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    source = Path(path)
    if not source.exists():
        raise DriveError(f"ファイルが見つかりません: {source}")

    service = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
    metadata: dict = {"name": source.name}
    if folder_id:
        metadata["parents"] = [folder_id]

    media = MediaFileUpload(str(source), resumable=source.stat().st_size > 5 * 1024 * 1024)
    created = service.files().create(
        body=metadata, media_body=media, fields="id, name, webViewLink"
    ).execute()

    file_id = created["id"]
    if share_anyone:
        service.permissions().create(
            fileId=file_id, body={"role": "reader", "type": "anyone"},
        ).execute()

    link = created.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
    return DriveFile(id=file_id, name=created.get("name", source.name),
                     link=link, shared=share_anyone)
