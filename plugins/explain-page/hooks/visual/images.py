"""Embed a slide-capture (or other source) image as a self-contained
``data:`` URI figure for the visual renderer.

Deck ingestion already produces slide screenshots on disk (PowerPoint
exported to width-1600 PNG on Windows; originals live under
``%TEMP%/deck-work/<deck>/media/sNN-imgK.png``). ``embed_image`` is the
function that turns one such file (or any PNG/JPEG/WebP path) into HTML the
renderer can drop straight into a page: read the file, verify its type by
magic number (never trust the extension), optionally crop and/or annotate
it, shrink it to fit the page's 2MB budget, and encode it inline as
``data:image/...;base64,...`` -- the artifact inspector rejects
``http(s)://`` and ``xmlns`` but accepts ``data:`` URIs, so nothing here
ever emits an external URL or an XML namespace declaration.

Given the same file bytes and the same spec, the output is deterministic
(no clock reads, no randomness). The only non-determinism is the file
system: which bytes are on disk at ``path`` and, for ``deck``/``slide``
lookups, which file the glob resolves to.

No exception ever escapes ``embed_image`` -- every failure mode (missing
file, corrupt/disguised image, invalid crop, encoder failure, ...) is
reported through ``ImageResult.warnings`` instead, with ``html`` left
empty so a caller can skip the figure safely.
"""

from __future__ import annotations

import base64
import hashlib
import io
import tempfile
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, Tuple

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only where PIL is absent
    Image = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False

__all__ = ["ImageResult", "embed_image"]

_VALID_EXT_HINT = "png"  # deck/slide glob patterns only ever look for .png


@dataclass(frozen=True)
class ImageResult:
    html: str
    sha256: str
    source_line: str
    bytes: int
    width: int
    height: int
    warnings: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# File-type detection (magic numbers only -- never trust an extension).
# --------------------------------------------------------------------------


def _detect_kind(data: bytes) -> Optional[str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _png_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    if len(data) < 24:
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width <= 0 or height <= 0:
        return None
    return width, height


def _jpeg_dimensions(data: bytes) -> Optional[Tuple[int, int]]:
    i = 2
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xFF:
            i += 1
            continue
        if i + 4 > n:
            return None
        seg_len = int.from_bytes(data[i + 2 : i + 4], "big")
        is_sof = 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC)
        if is_sof:
            if i + 9 > n:
                return None
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            if width <= 0 or height <= 0:
                return None
            return width, height
        if seg_len < 2:
            return None
        i += 2 + seg_len
    return None


def _header_dimensions(data: bytes, kind: str) -> Optional[Tuple[int, int]]:
    if kind == "png":
        return _png_dimensions(data)
    if kind == "jpeg":
        return _jpeg_dimensions(data)
    return None  # webp header parsing is not implemented; PIL handles it.


# --------------------------------------------------------------------------
# deck/slide resolution (B3 contract).
# --------------------------------------------------------------------------


def _find_deck_slide_image(deck_root: str, deck: str, slide: int) -> Optional[Path]:
    deck_dir = Path(deck_root) / deck
    if not deck_dir.exists() or not deck_dir.is_dir():
        return None
    # 2026-09-10：作業フォルダの実物は s05-img1.png のように0埋め＝%d だけでは見つからなかった。
    patterns = tuple(
        pat
        for width in ("%d", "%02d", "%03d")
        for pat in ("slide-" + width + "*.png", "s" + width + "*.png", "*" + width + "*.png")
        for pat in (pat % slide,)
    )
    for pattern in patterns:
        try:
            matches = sorted(deck_dir.rglob(pattern))
        except OSError:
            continue
        if matches:
            return matches[0]
    return None


# --------------------------------------------------------------------------
# Encoding: shrink to max_width, then pick the smaller of PNG/JPEG.
# --------------------------------------------------------------------------


def _encode_jpeg(img: "Image.Image", max_bytes: int) -> bytes:
    if img.mode in ("RGBA", "LA", "P"):
        rgb = img.convert("RGB")
    elif img.mode not in ("RGB", "L"):
        rgb = img.convert("RGB")
    else:
        rgb = img
    quality = 85
    last = b""
    while True:
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        last = buf.getvalue()
        if len(last) <= max_bytes or quality <= 10:
            return last
        quality -= 15
        if quality < 10:
            quality = 10


def _encode_png(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    try:
        img.save(buf, format="PNG", optimize=True)
    except Exception:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _encode_best(img: "Image.Image", max_bytes: int) -> Tuple[bytes, str, List[str]]:
    warnings: List[str] = []
    jpeg_bytes: Optional[bytes] = None
    png_bytes: Optional[bytes] = None
    try:
        jpeg_bytes = _encode_jpeg(img, max_bytes)
    except Exception as exc:
        warnings.append("JPEG encode failed: %s" % exc)
    try:
        png_bytes = _encode_png(img)
    except Exception as exc:
        warnings.append("PNG encode failed: %s" % exc)

    if jpeg_bytes is None and png_bytes is None:
        raise ValueError("both PNG and JPEG encoding failed")
    if jpeg_bytes is None:
        return png_bytes, "png", warnings  # type: ignore[return-value]
    if png_bytes is None:
        return jpeg_bytes, "jpeg", warnings
    # 文字の多い画像はPNGのほうが小さいことがある -- both were tried, keep the smaller.
    if len(png_bytes) <= len(jpeg_bytes):
        return png_bytes, "png", warnings
    return jpeg_bytes, "jpeg", warnings


# --------------------------------------------------------------------------
# marks overlay (strokes only, no fill; a numbered white badge per mark).
# --------------------------------------------------------------------------


def _render_marks_svg(
    marks: Sequence[Any], width: int, height: int, scale: float
) -> str:
    parts: List[str] = []
    for i, m in enumerate(marks, start=1):
        if not isinstance(m, Mapping):
            continue
        try:
            x = float(m.get("x", 0)) * scale
            y = float(m.get("y", 0)) * scale
            w = float(m.get("w", 0)) * scale
            h = float(m.get("h", 0)) * scale
        except (TypeError, ValueError):
            continue
        parts.append(
            '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="none" '
            'stroke="var(--fail)" stroke-width="2"></rect>' % (x, y, w, h)
        )
        label = m.get("label")
        label_text = escape(str(label), quote=True) if label not in (None, "") else str(i)
        parts.append(
            '<circle cx="%.1f" cy="%.1f" r="9" fill="#ffffff" stroke="var(--fail)" '
            'stroke-width="1.5"></circle>' % (x, y)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" text-anchor="middle" dominant-baseline="central" '
            'font-size="10" font-weight="700" fill="var(--fail)">%s</text>'
            % (x, y + 0.5, label_text)
        )
    if not parts:
        return ""
    return '<svg class="marks" viewBox="0 0 %d %d">%s</svg>' % (width, height, "".join(parts))


def _build_figure_html(
    img_tag: str,
    marks_svg: str,
    caption: Any,
    source: Any,
    num: Any,
    max_display_width: Optional[int],
) -> str:
    frame_style = ' style="max-width:%dpx"' % max_display_width if max_display_width else ""
    caption_parts: List[str] = []
    if num not in (None, ""):
        # 2026-09-10：呼び出し側が「図1」まで書いてきたら前置しない（「図図1」の二重表記を防ぐ）
        num_text = str(num)
        caption_parts.append(escape(num_text if num_text.startswith("図") else "図" + num_text, quote=True))
    if caption not in (None, ""):
        caption_parts.append(escape(str(caption), quote=True))
    if source not in (None, ""):
        caption_parts.append("出所：%s" % escape(str(source), quote=True))
    figcaption_html = "<figcaption>%s</figcaption>" % "｜".join(caption_parts) if caption_parts else ""
    return (
        '<figure class="img-figure"><div class="img-frame"%s>%s%s</div>%s</figure>'
        % (frame_style, img_tag, marks_svg, figcaption_html)
    )


# --------------------------------------------------------------------------
# Public entry point.
# --------------------------------------------------------------------------


def embed_image(
    spec: Mapping[str, Any],
    *,
    deck_root: Optional[str] = None,
    max_width: int = 1200,
    max_bytes: int = 350_000,
) -> ImageResult:
    warnings: List[str] = []

    def _empty() -> ImageResult:
        return ImageResult(html="", sha256="", source_line="", bytes=0, width=0, height=0, warnings=warnings)

    try:
        if not isinstance(spec, Mapping):
            warnings.append("image spec must be a mapping")
            return _empty()

        path_value = spec.get("path")
        deck_value = spec.get("deck")
        slide_value = spec.get("slide")

        resolved_path: Optional[Path] = None
        name_part = ""
        detail_part = ""

        if path_value:
            resolved_path = Path(str(path_value))
            name_part = resolved_path.name
        elif deck_value not in (None, "") and slide_value is not None:
            try:
                slide_num = int(slide_value)
            except (TypeError, ValueError):
                warnings.append("slide must be an integer, got %r" % (slide_value,))
                return _empty()
            root = str(deck_root) if deck_root else str(Path(tempfile.gettempdir()) / "deck-work")
            found = _find_deck_slide_image(root, str(deck_value), slide_num)
            if found is None:
                warnings.append(
                    "image not found for deck=%r slide=%r under %r" % (deck_value, slide_num, root)
                )
                return _empty()
            resolved_path = found
            name_part = str(deck_value)
            detail_part = "スライド%d" % slide_num
        else:
            warnings.append("spec must have 'path', or both 'deck' and 'slide'")
            return _empty()

        try:
            exists = resolved_path.is_file()
        except OSError:
            exists = False
        if not exists:
            warnings.append("file not found: %s" % resolved_path)
            return _empty()

        try:
            data = resolved_path.read_bytes()
        except OSError as exc:
            warnings.append("failed to read file: %s (%s)" % (resolved_path, exc))
            return _empty()

        kind = _detect_kind(data)
        if kind is None:
            warnings.append(
                "rejected: not a recognized image (magic number check failed): %s" % resolved_path
            )
            return _empty()

        crop_spec = spec.get("crop")
        crop_box: Optional[Tuple[int, int, int, int]] = None
        if crop_spec is not None:
            try:
                cx, cy, cw, ch = (int(v) for v in crop_spec)
                if cw <= 0 or ch <= 0:
                    raise ValueError("crop width/height must be positive")
                crop_box = (cx, cy, cw, ch)
            except (TypeError, ValueError) as exc:
                warnings.append("invalid crop, ignoring: %r (%s)" % (crop_spec, exc))
                crop_box = None

        cropped_w = 0
        cropped_h = 0
        final_w = 0
        final_h = 0
        embed_bytes = b""
        mime = kind

        if _PIL_AVAILABLE:
            img = None
            try:
                img = Image.open(io.BytesIO(data))
                img.load()
            except Exception as exc:
                warnings.append("PIL failed to open image, embedding original bytes: %s" % exc)
                img = None

            if img is not None:
                if crop_box is not None:
                    cx, cy, cw, ch = crop_box
                    try:
                        img = img.crop((cx, cy, cx + cw, cy + ch))
                        if not detail_part:
                            detail_part = "切り出し%d,%d,%d,%d" % crop_box
                    except Exception as exc:
                        warnings.append("crop failed, using uncropped image: %s" % exc)

                cropped_w, cropped_h = img.size

                if max_width > 0 and cropped_w > max_width:
                    scale = max_width / float(cropped_w)
                    new_w = max_width
                    new_h = max(1, round(cropped_h * scale))
                    try:
                        resample = Image.LANCZOS
                    except AttributeError:  # pragma: no cover - older Pillow
                        resample = Image.BICUBIC
                    img_final = img.resize((new_w, new_h), resample)
                else:
                    img_final = img
                    new_w, new_h = cropped_w, cropped_h

                try:
                    embed_bytes, mime, enc_warnings = _encode_best(img_final, max_bytes)
                    warnings.extend(enc_warnings)
                    final_w, final_h = new_w, new_h
                except Exception as exc:
                    warnings.append("encoding failed, embedding original bytes: %s" % exc)
                    embed_bytes = data
                    mime = kind
                    dims = _header_dimensions(data, kind) or (cropped_w, cropped_h)
                    final_w, final_h = dims
            else:
                embed_bytes = data
                mime = kind
                dims = _header_dimensions(data, kind)
                if dims is None:
                    warnings.append("could not determine image dimensions")
                else:
                    final_w, final_h = dims
                    cropped_w, cropped_h = dims
        else:
            warnings.append("PIL not available - embedding original image without resize/compression")
            if crop_box is not None:
                warnings.append("crop requested but PIL is unavailable; ignoring crop")
            embed_bytes = data
            mime = kind
            dims = _header_dimensions(data, kind)
            if dims is None:
                warnings.append("could not determine image dimensions without PIL")
            else:
                final_w, final_h = dims
                cropped_w, cropped_h = dims

        if max_bytes > 0 and len(embed_bytes) > max_bytes:
            warnings.append(
                "embedded image is %d bytes, exceeds max_bytes=%d despite compression"
                % (len(embed_bytes), max_bytes)
            )

        b64 = base64.b64encode(embed_bytes).decode("ascii")
        data_uri = "data:image/%s;base64,%s" % (mime, b64)

        alt_value = spec.get("alt")
        if alt_value in (None, ""):
            alt_value = spec.get("caption")
        if alt_value in (None, ""):
            alt_value = name_part or "image"
        img_tag = '<img src="%s" alt="%s" width="%d" height="%d">' % (
            data_uri,
            escape(str(alt_value), quote=True),
            final_w,
            final_h,
        )

        marks_spec = spec.get("marks")
        marks_svg = ""
        if marks_spec:
            scale = (final_w / cropped_w) if cropped_w else 1.0
            marks_svg = _render_marks_svg(marks_spec, final_w, final_h, scale)

        max_display_width: Optional[int] = None
        width_spec = spec.get("width")
        if width_spec is not None:
            try:
                max_display_width = int(width_spec)
            except (TypeError, ValueError):
                warnings.append("invalid width (display cap), ignoring: %r" % (width_spec,))

        figure_html = _build_figure_html(
            img_tag,
            marks_svg,
            spec.get("caption"),
            spec.get("source"),
            spec.get("num"),
            max_display_width,
        )

        sha = hashlib.sha256(embed_bytes).hexdigest()
        if not name_part:
            name_part = resolved_path.name
        if not detail_part:
            detail_part = "原本"
        source_line = "実測：画像＝%s・%s・%s｜%s" % (
            name_part,
            detail_part,
            sha[:12],
            str(resolved_path),
        )

        return ImageResult(
            html=figure_html,
            sha256=sha,
            source_line=source_line,
            bytes=len(embed_bytes),
            width=final_w,
            height=final_h,
            warnings=warnings,
        )
    except Exception as exc:  # pragma: no cover - defensive catch-all; never raise.
        warnings.append("unexpected error: %s" % exc)
        return ImageResult(html="", sha256="", source_line="", bytes=0, width=0, height=0, warnings=warnings)
