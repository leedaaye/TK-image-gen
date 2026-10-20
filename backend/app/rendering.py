"""Local Pillow composition. Editing copy never requires a model request."""
from __future__ import annotations

import io
import os
from pathlib import Path
import re
import unicodedata
import warnings

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

WIDTH, HEIGHT = 1080, 1440
MARGIN = 76
TEXT_WIDTH = WIDTH - 2 * MARGIN
MAX_PIXELS = 40_000_000


def _font_candidates(language: str, text: str) -> list[tuple[Path, int]]:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    configured = os.environ.get("RENDER_FONT", "")
    candidates = [(Path(configured), 0)] if configured else []
    lang = language.lower().strip()
    is_cjk = any("\u2e80" <= char <= "\u9fff" or "\uac00" <= char <= "\ud7af"
                 or "\u3040" <= char <= "\u30ff" for char in text)
    cjk_index = 1 if lang.startswith(("ko", "korean")) else (
        0 if lang.startswith(("ja", "japanese")) else 2)
    if lang.startswith(("ar", "fa", "ur")) or any("\u0600" <= c <= "\u06ff" for c in text):
        candidates.extend([
            (Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"), 0),
            (Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"), 0),
            (windows / "arial.ttf", 0),
        ])
    if lang.startswith(("hi", "hindi")) or any("\u0900" <= c <= "\u097f" for c in text):
        candidates.extend([
            (Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"), 0),
            (windows / "Nirmala.ttf", 0),
        ])
    if is_cjk or lang.startswith(("zh", "ja", "ko", "chinese", "japanese", "korean")):
        candidates.extend([
            (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), cjk_index),
            (Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"), cjk_index),
            (Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"), cjk_index),
            (windows / "msyh.ttc", 0), (windows / "msjh.ttc", 0),
            (windows / "YuGothM.ttc", 0), (windows / "malgun.ttf", 0),
            (Path("/System/Library/Fonts/PingFang.ttc"), 0),
        ])
        # A Latin-only fallback would silently draw tofu for Chinese text.
        return candidates
    candidates.extend([
        (Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"), 0),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), 0),
        (Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"), 0),
        (windows / "arial.ttf", 0), (windows / "msyh.ttc", 0),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), 0),
    ])
    return candidates


def _load_font(size: int, language: str, text: str) -> ImageFont.FreeTypeFont:
    for path, index in _font_candidates(language, text):
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size, index=index)
            except (OSError, ValueError):
                continue
    raise RuntimeError("未找到适用的 Unicode 字体；Linux 请安装 fonts-noto-cjk，或设置 RENDER_FONT")


def _clusters(text: str) -> list[str]:
    """Keep combining marks, variation selectors and joined emoji with their base."""
    clusters: list[str] = []
    for char in text:
        if clusters and (unicodedata.combining(char) or char in "\ufe0e\ufe0f\u200d"
                         or clusters[-1].endswith("\u200d")):
            clusters[-1] += char
        else:
            clusters.append(char)
    return clusters


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Wrap Latin words naturally and split CJK or long tokens by measured glyphs."""
    result = []
    for paragraph in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = ""
        for token in re.findall(r"\s+|[^\s\u2e80-\u9fff\uac00-\ud7af\u3040-\u30ff]+|[\u2e80-\u9fff\uac00-\ud7af\u3040-\u30ff]", paragraph):
            token = " " if token.isspace() else token
            if not line and token.isspace():
                continue
            if font.getlength(line + token) <= width:
                line += token
                continue
            if line.strip():
                result.append(line.rstrip())
                line = ""
            token = token.lstrip()
            for cluster in _clusters(token):
                if line and font.getlength(line + cluster) > width:
                    result.append(line)
                    line = ""
                # Even a pathological glyph is not allowed to exceed the text box.
                if font.getlength(cluster) <= width:
                    line += cluster
        result.append(line.rstrip())
    return result


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent + max(5, round(font.size * 0.18))


def _fit_text(text: str, language: str, width: int, height: int,
              preferred: int, minimum: int) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(preferred, minimum - 1, -2):
        font = _load_font(size, language, text)
        lines = _wrap_text(text, font, width)
        line_height = _line_height(font)
        if len(lines) * line_height <= height:
            return font, lines, line_height
    font = _load_font(minimum, language, text)
    line_height = _line_height(font)
    lines = _wrap_text(text, font, width)
    max_lines = max(1, height // line_height)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1].rstrip()
        while last and font.getlength(last + "…") > width:
            last = last[:-1]
        lines[-1] = last + "…"
    return font, lines, line_height


def render_image(base_path: Path, output_path: Path, title: str, body: str,
                 language: str = "") -> None:
    """Center-crop a base image to 1080×1440 and compose readable editable copy.

    Text shrinks to fit its region; exceptionally long copy is visibly ellipsized.
    The caller stores the unmodified source and full text independently.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(base_path) as source:
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("原图像素超过安全限制")
                source = ImageOps.exif_transpose(source)
                rgba = source.convert("RGBA")
                # Flatten transparent model output onto a neutral canvas before cropping.
                flat = Image.new("RGBA", rgba.size, (241, 241, 237, 255))
                flat.alpha_composite(rgba)
                image = ImageOps.fit(flat.convert("RGB"), (WIDTH, HEIGHT),
                                     method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("原图像素超过安全限制") from None
    except (OSError, UnidentifiedImageError):
        raise ValueError("无法读取用于排版的原始图片") from None
    title = str(title or "").strip()
    body = str(body or "").strip()
    if title or body:
        gradient = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(gradient)
        for y in range(HEIGHT):
            progress = max(0.0, min(1.0, (y - HEIGHT * 0.36) / (HEIGHT * 0.64)))
            alpha = round(235 * progress ** 0.66)
            draw.line((0, y, WIDTH, y), fill=(9, 14, 22, alpha))
        image = Image.alpha_composite(image.convert("RGBA"), gradient)
        draw = ImageDraw.Draw(image)
        title_height = 245 if body else 550
        body_height = 330 if title else 550
        title_font, title_lines, title_step = _fit_text(
            title, language, TEXT_WIDTH, title_height, 70, 36) if title else (None, [], 0)
        body_font, body_lines, body_step = _fit_text(
            body, language, TEXT_WIDTH, body_height, 38, 24) if body else (None, [], 0)
        gap = 26 if title and body else 0
        used = len(title_lines) * title_step + len(body_lines) * body_step + gap
        y = HEIGHT - MARGIN - used
        for font, lines, step, color in (
            (title_font, title_lines, title_step, (255, 255, 255)),
            (body_font, body_lines, body_step, (236, 240, 246)),
        ):
            if font is None:
                continue
            for line in lines:
                draw.text((MARGIN, y), line, font=font, fill=color, anchor="lt",
                          stroke_width=1, stroke_fill=(16, 20, 28))
                y += step
            if font is title_font:
                y += gap
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = image.convert("RGB")
    extension = target.suffix.lower()
    fmt = {".png": "PNG", ".webp": "WEBP", ".jpg": "JPEG", ".jpeg": "JPEG"}.get(extension)
    if fmt is None:
        raise ValueError("排版输出必须为 PNG、JPEG 或 WebP")
    # Encode first so encoder failure does not leave a partially written final image.
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, quality=94)
    target.write_bytes(buffer.getvalue())
