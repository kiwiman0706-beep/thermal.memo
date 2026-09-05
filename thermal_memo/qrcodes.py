"""QR コードを印刷用ビットマップにする。

URL でもテキストでも、手帳に貼れる大きさの QR にして返す。
モジュール（黒い正方形）が滲まないよう、拡大は必ず整数倍で行う。
"""

from __future__ import annotations

from PIL import Image

from . import render

ERROR_LEVELS = ("L", "M", "Q", "H")

# 印字が薄れても読めるよう、既定はやや強めの Q にしている
DEFAULT_ERROR = "Q"


class QRError(RuntimeError):
    pass


def available() -> bool:
    try:
        import qrcode  # noqa: F401

        return True
    except ImportError:
        return False


def make_matrix(data: str, error: str = DEFAULT_ERROR) -> Image.Image:
    """1 モジュール = 1 ピクセルの素の QR 画像（余白 4 モジュール付き）を返す。"""
    try:
        import qrcode
        from qrcode.constants import (
            ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q,
        )
    except ImportError as exc:
        raise QRError("QR の生成には qrcode パッケージが必要です（pip install qrcode）") from exc

    if not data:
        raise QRError("QR にする内容が空です")

    levels = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
              "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
    encoder = qrcode.QRCode(
        version=None,
        error_correction=levels.get(error.upper(), ERROR_CORRECT_Q),
        box_size=1,
        border=4,
    )
    encoder.add_data(data)
    try:
        encoder.make(fit=True)
    except Exception as exc:  # データ過多で version 40 に収まらない場合など
        raise QRError(f"QR にできませんでした（内容が長すぎる可能性があります）: {exc}") from exc

    image = encoder.make_image(fill_color="black", back_color="white")
    return image.convert("1")


def make_qr(
    data: str,
    *,
    width_dots: int = 576,
    size_percent: int = 60,
    error: str = DEFAULT_ERROR,
    label: str = "",
    caption: str = "",
    font_path: str | None = None,
    font_size: int = 24,
    timestamp: bool = False,
    timestamp_format: str = "%Y-%m-%d %H:%M",
) -> Image.Image:
    """QR（＋見出し・キャプション）を用紙幅の 1bit 画像にして返す。

    :param size_percent: 用紙幅に対する QR の目標サイズ（%）
    :param label:   QR の上に印字する見出し
    :param caption: QR の下に印字する説明（URL をそのまま入れておくと手入力の保険になる）
    """
    matrix = make_matrix(data, error)
    modules = matrix.width  # 余白込みの一辺（モジュール数）

    target = max(32, int(width_dots * max(10, min(100, size_percent)) / 100))
    scale = max(1, target // modules)          # 整数倍のみ。端数拡大は読み取り率を落とす
    if modules * scale > width_dots:
        scale = max(1, width_dots // modules)
    qr = matrix.resize((modules * scale, modules * scale), Image.NEAREST)

    parts: list[Image.Image] = []
    if label.strip() or timestamp:
        parts.append(render.text_to_image(
            label.strip() or " ",
            width_dots=width_dots, font_path=font_path, font_size=font_size,
            line_spacing=4, margin=10, align="center",
            timestamp=timestamp, timestamp_format=timestamp_format,
            rule_line=False, header="", footer="",
        ))

    canvas = Image.new("1", (width_dots, qr.height + 16), 1)
    canvas.paste(qr, ((width_dots - qr.width) // 2, 8))
    parts.append(canvas)

    if caption.strip():
        parts.append(render.text_to_image(
            caption.strip(),
            width_dots=width_dots, font_path=font_path,
            font_size=max(14, int(font_size * 0.66)),
            line_spacing=2, margin=10, align="center",
            timestamp=False, rule_line=False, header="", footer="",
        ))

    if len(parts) == 1:
        return parts[0]
    return render.stack(parts, gap=4, width_dots=width_dots)


def module_count(data: str, error: str = DEFAULT_ERROR) -> int:
    """余白込みの一辺のモジュール数（サイズ見積り用）。"""
    return make_matrix(data, error).width
