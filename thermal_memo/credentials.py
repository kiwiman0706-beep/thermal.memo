"""SMTP アプリパスワードなど秘密情報の保管。

平文でファイルに書く経路は用意しない。優先順位:

  1. 環境変数（``THERMAL_MEMO_SMTP_PASSWORD`` など）
  2. keyring（入っていれば OS の資格情報ストアをそのまま使う）
  3. Windows: DPAPI（ctypes 経由。ログイン中の Windows ユーザーだけが復号できる）
  4. macOS: security コマンド（キーチェーン）
  5. 保存しない（使うたびに入力）

どれも使えない環境では ``store()`` が :class:`CredentialError` を送出する。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import app_dir

SERVICE = "thermal.memo"


class CredentialError(RuntimeError):
    pass


# --------------------------------------------------------------------- keyring

def _keyring():
    try:
        import keyring

        # バックエンドが無い環境では keyring は例外を投げるので、ここで確かめる
        backend = keyring.get_keyring()
        name = backend.__class__.__name__
        if "fail" in name.lower() or "null" in name.lower():
            return None
        return keyring
    except Exception:
        return None


# ----------------------------------------------------------------- Windows DPAPI

def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi(protect: bool, data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    def to_blob(payload: bytes) -> Blob:
        buffer = ctypes.create_string_buffer(payload, len(payload))
        return Blob(len(payload), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))

    crypt32 = ctypes.windll.crypt32
    source = to_blob(data)
    result = Blob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    args = [ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)]
    if not function(*args):
        raise CredentialError("Windows の資格情報 API（DPAPI）の呼び出しに失敗しました")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(result.pbData)


def _dpapi_file() -> Path:
    return app_dir() / "secrets.dat"


def _dpapi_load() -> dict:
    path = _dpapi_file()
    if not path.exists():
        return {}
    try:
        raw = _dpapi(False, base64.b64decode(path.read_bytes()))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _dpapi_save(store: dict) -> None:
    payload = json.dumps(store, ensure_ascii=False).encode("utf-8")
    path = _dpapi_file()
    path.write_bytes(base64.b64encode(_dpapi(True, payload)))
    try:
        path.chmod(0o600)
    except OSError:
        pass


# ------------------------------------------------------------- macOS キーチェーン

def _security_available() -> bool:
    if sys.platform != "darwin":
        return False
    from shutil import which

    return which("security") is not None


def _security(args: list[str], capture: bool = False) -> str:
    result = subprocess.run(["security"] + args, capture_output=True, text=True, check=False)
    if result.returncode != 0 and not capture:
        raise CredentialError(f"キーチェーン操作に失敗しました: {result.stderr.strip()}")
    return result.stdout.strip()


# ------------------------------------------------------------------- 公開 API

def backend_name() -> str:
    """実際に使われる保管先の名前（UI 表示用）。"""
    if _keyring():
        return "OS の資格情報ストア（keyring）"
    if _dpapi_available():
        return "Windows DPAPI（このユーザーのみ復号可）"
    if _security_available():
        return "macOS キーチェーン"
    return "保存先なし（毎回入力が必要）"


def can_store() -> bool:
    return bool(_keyring()) or _dpapi_available() or _security_available()


def store(account: str, secret: str) -> str:
    """秘密情報を保存し、使った保管先の名前を返す。"""
    keyring = _keyring()
    if keyring:
        keyring.set_password(SERVICE, account, secret)
        return backend_name()
    if _dpapi_available():
        data = _dpapi_load()
        data[account] = secret
        _dpapi_save(data)
        return backend_name()
    if _security_available():
        _security(["add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", secret])
        return backend_name()
    raise CredentialError(
        "この環境には安全な保管先がありません。"
        "keyring を導入するか、環境変数 THERMAL_MEMO_SMTP_PASSWORD を使ってください。"
    )


def retrieve(account: str, env_var: str | None = None) -> str | None:
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    keyring = _keyring()
    if keyring:
        try:
            return keyring.get_password(SERVICE, account)
        except Exception:
            return None
    if _dpapi_available():
        return _dpapi_load().get(account)
    if _security_available():
        result = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip() or None if result.returncode == 0 else None
    return None


def delete(account: str) -> None:
    keyring = _keyring()
    if keyring:
        try:
            keyring.delete_password(SERVICE, account)
        except Exception:
            pass
        return
    if _dpapi_available():
        data = _dpapi_load()
        if data.pop(account, None) is not None:
            _dpapi_save(data)
        return
    if _security_available():
        subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", account],
                       capture_output=True, check=False)
