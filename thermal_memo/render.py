"""印刷用ビットマップの生成（テキストの画像化・画像の二値化）。

サーマルプリンタへは常に「1bit 画像」として送る。
内蔵フォント／コードページを使わないので日本語・記号・レイアウトが自由になる。
"""

from __future__ import annotations

import datetime as _dt
from typing import Iterable

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from . import fonts

# 行頭に置きたくない文字（禁則処理・簡易版）
NO_LINE_START = "、。，．・：；！？」』）］｝〉》”’ゝゞーぁぃぅぇぉっゃゅょゎヵヶァィゥェォッャュョヮ!?,.:;)]}>\"'"
NO_LINE_END = "「『（［｛〈《“‘([{<"


def load_font(path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    resolved = fonts.detect(path)
    if resolved:
        try:
            return ImageFont.truetype(resolved, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _tokenize(line: str) -> list[str]:
    """行を折り返し単位に分割する。ASCII 単語は塊のまま、CJK は 1 文字ずつ。"""
    tokens: list[str] = []
    buffer = ""
    for char in line:
        if char.isascii() and not char.isspace():
            buffer += char
            continue
        if buffer:
            tokens.append(buffer)
            buffer = ""
        tokens.append(char)
    if buffer:
        tokens.append(buffer)
    return tokens


def wrap_text(
    text: str,
    font,
    max_width: int,
    draw: ImageDraw.ImageDraw | None = None,
) -> list[str]:
    """max_width（px）に収まるように折り返す。禁則処理つき。"""
    measure = (draw.textlength if draw else font.getlength)

    def width_of(s: str) -> float:
        try:
            return measure(s, font=font) if draw else font.getlength(s)
        except TypeError:      # ImageFont.ImageFont は font 引数を取らない
            return measure(s)

    lines: list[str] = []
    for raw_line in text.replace("\t", "    ").split("\n"):
        if not raw_line.strip():
            lines.append("")
            continue
        current = ""
        for token in _tokenize(raw_line):
            candidate = current + token
            if current and width_of(candidate) > max_width:
                # 禁則: 次行の先頭に来る文字が行頭禁則なら、はみ出しを許して現在行に残す
                if token and token[0] in NO_LINE_START:
                    current = candidate
                    continue
                # 禁則: 現在行の末尾が行末禁則ならその 1 文字を次行へ送る
                if current[-1] in NO_LINE_END:
                    lines.append(current[:-1])
                    current = current[-1] + token
                else:
                    lines.append(current)
                    current = token
            else:
                current = candidate
        lines.append(current)
    return lines


def text_to_image(
    text: str,
    *,
    width_dots: int = 576,
    font_path: str | None = None,
    font_size: int = 30,
    line_spacing: int = 8,
    margin: int = 10,
    align: str = "left",
    bold: bool = False,
    header: str = "",
    footer: str = "",
    timestamp: bool = True,
    timestamp_format: str = "%Y-%m-%d %H:%M",
    rule_line: bool = True,
    now: _dt.datetime | None = None,
) -> Image.Image:
    """テキストを 1bit 画像へ。"""
    font = load_font(font_path, font_size)
    small = load_font(font_path, max(12, int(font_size * 0.62)))
    stroke = 1 if bold else 0
    content_width = max(16, width_dots - margin * 2)

    blocks: list[tuple[list[str], object, int]] = []  # (lines, font, extra_gap)
    rules: list[int] = []                             # 罫線を入れるブロック番号

    stamp_bits = []
    if timestamp:
        stamp_bits.append((now or _dt.datetime.now()).strftime(timestamp_format))
    if header.strip():
        stamp_bits.append(header.strip())
    if stamp_bits:
        blocks.append(([" / ".join(stamp_bits)], small, 4))
        if rule_line:
            rules.append(len(blocks) - 1)

    body = wrap_text(text.rstrip(), font, content_width)
    blocks.append((body, font, 0))

    if footer.strip():
        if rule_line:
            rules.append(len(blocks) - 1)
        blocks.append((wrap_text(footer.strip(), small, content_width), small, 4))

    # 高さを計算
    def line_height(f) -> int:
        ascent, descent = (f.getmetrics() if hasattr(f, "getmetrics") else (font_size, 4))
        return ascent + descent

    total = margin * 2
    for index, (lines, f, gap) in enumerate(blocks):
        lh = line_height(f) + line_spacing
        total += lh * max(1, len(lines)) + gap
        if index in rules:
            total += 10

    image = Image.new("L", (width_dots, max(total, margin * 2 + font_size)), 255)
    draw = ImageDraw.Draw(image)

    y = margin
    for index, (lines, f, gap) in enumerate(blocks):
        lh = line_height(f) + line_spacing
        for line in lines:
            if line:
                try:
                    w = draw.textlength(line, font=f)
                except TypeError:
                    w = draw.textlength(line)
                if align == "center":
                    x = (width_dots - w) / 2
                elif align == "right":
                    x = width_dots - margin - w
                else:
                    x = margin
                draw.text((x, y), line, font=f, fill=0, stroke_width=stroke, stroke_fill=0)
            y += lh
        y += gap
        if index in rules:
            draw.line([(margin, y + 3), (width_dots - margin, y + 3)], fill=0, width=2)
            y += 10

    return image.convert("1")


# --------------------------------------------------------------------------- 画像

def process_image(
    image: Image.Image,
    *,
    width_dots: int = 576,
    mode: str = "dither",
    threshold: int = 128,
    brightness: float = 1.0,
    contrast: float = 1.0,
    sharpen: bool = False,
    invert: bool = False,
    autocrop: bool = True,
    scale: int = 100,
) -> Image.Image:
    """任意の画像を印刷用 1bit 画像に変換する。

    mode:
      dither    … 誤差拡散（写真・スクショ向け。階調が出る）
      threshold … 単純二値化（文字主体のスクショはこちらが鮮明）
      adaptive  … 適応的二値化（影・グラデーションのある紙の写真向け／要 opencv）
    """
    img = image.convert("RGB") if image.mode in ("RGBA", "P", "LA") else image
    if image.mode in ("RGBA", "LA"):
        # 透過は白背景で合成
        background = Image.new("RGB", image.size, "white")
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        img = background
    img = img.convert("L")

    if autocrop:
        img = _autocrop(img)
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if sharpen:
        img = img.filter(ImageFilter.SHARPEN)

    target = max(16, int(width_dots * max(10, min(100, scale)) / 100))
    if img.width != target:
        height = max(1, round(img.height * target / img.width))
        img = img.resize((target, height), Image.LANCZOS)

    if mode == "threshold":
        out = img.point(lambda p: 255 if p >= threshold else 0, mode="1")
    elif mode == "adaptive":
        out = _adaptive(img, threshold)
    else:
        out = img.convert("1")  # Floyd-Steinberg ディザ

    if invert:
        out = ImageOps.invert(out.convert("L")).convert("1")
    return out


def _autocrop(gray: Image.Image, tolerance: int = 12) -> Image.Image:
    """白い余白を落とす。"""
    mask = gray.point(lambda p: 0 if p > 255 - tolerance else 255, mode="L")
    bbox = mask.getbbox()
    if not bbox:
        return gray
    pad = 4
    left = max(0, bbox[0] - pad)
    top = max(0, bbox[1] - pad)
    right = min(gray.width, bbox[2] + pad)
    bottom = min(gray.height, bbox[3] + pad)
    if right - left < 8 or bottom - top < 8:
        return gray
    return gray.crop((left, top, right, bottom))


def _adaptive(gray: Image.Image, threshold: int) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return gray.point(lambda p: 255 if p >= threshold else 0, mode="1")
    array = np.array(gray)
    block = max(3, (min(array.shape) // 20) | 1)
    offset = int((threshold - 128) / 8)
    binary = cv2.adaptiveThreshold(
        array, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, offset
    )
    return Image.fromarray(binary).convert("1")


def stack(images: Iterable[Image.Image], gap: int = 12, width_dots: int = 576) -> Image.Image:
    """複数画像を縦に連結する（複数ページのサムネイル印刷用）。"""
    items = [im.convert("1") for im in images]
    if not items:
        raise ValueError("画像がありません")
    height = sum(im.height for im in items) + gap * (len(items) - 1)
    canvas = Image.new("1", (width_dots, height), 1)
    y = 0
    for im in items:
        canvas.paste(im, ((width_dots - im.width) // 2, y))
        y += im.height + gap
    return canvas
