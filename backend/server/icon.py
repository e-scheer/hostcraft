"""Server-icon management.

Minecraft reads ``server-icon.png`` (64×64 PNG) at the root of the server's
data dir on container start. We expose:

- a curated set of preset icons generated on the fly with Pillow (no
  copyrighted texture, no static assets to ship), and
- custom uploads (PNG/JPEG/WebP, auto-resized + re-encoded to PNG 64×64).

The current icon is just ``MC_DATA_PATH/server-icon.png`` — the same file
the Minecraft container picks up.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger(__name__)

SIZE = 64
MAX_UPLOAD_BYTES = 1_048_576  # 1 MB
ICON_FILENAME = "server-icon.png"
ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP"}


def icon_path() -> Path:
    return Path(settings.MC_DATA_PATH) / ICON_FILENAME


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    top: str       # hex color, top of gradient
    bottom: str    # hex color, bottom of gradient
    accent: str    # hex color, glyph/accent fill


# Curated palette — keep names i18n-friendly (frontend translates by id).
PRESETS: tuple[Preset, ...] = (
    Preset("ember",     "Ember",     "#ff7a45", "#7a1f0a", "#fff4e6"),
    Preset("ocean",     "Ocean",     "#4cc9f0", "#03045e", "#caf0f8"),
    Preset("forest",    "Forest",    "#9ef01a", "#1b4332", "#d8f3dc"),
    Preset("amethyst",  "Amethyst",  "#c77dff", "#3c096c", "#f3e8ff"),
    Preset("rose",      "Rose",      "#ff8fab", "#6a040f", "#ffe5ec"),
    Preset("sand",      "Sand",      "#fcbf49", "#5c3d10", "#fff3bf"),
    Preset("mint",      "Mint",      "#9bf6ff", "#0d4f3c", "#d8f3dc"),
    Preset("slate",     "Slate",     "#94a3b8", "#0f172a", "#e2e8f0"),
)


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# In-memory cache of generated preset bytes. Cheap to regenerate, but the
# app calls this on every preset list/preview, so memoize.
_preset_cache: dict[str, bytes] = {}


def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


def _generate_preset(preset: Preset) -> bytes:
    cached = _preset_cache.get(preset.id)
    if cached is not None:
        return cached

    top = _hex_to_rgb(preset.top)
    bottom = _hex_to_rgb(preset.bottom)
    accent = _hex_to_rgb(preset.accent)

    img = Image.new("RGB", (SIZE, SIZE), bottom)
    pixels = img.load()
    for y in range(SIZE):
        t = _smoothstep(y / (SIZE - 1))
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(SIZE):
            pixels[x, y] = (r, g, b)

    # Subtle radial highlight in upper-left for a premium 3D feel.
    highlight = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(highlight).ellipse(
        [-12, -12, SIZE // 2 + 8, SIZE // 2 + 8], fill=110
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(10))
    overlay = Image.new("RGB", (SIZE, SIZE), accent)
    img = Image.composite(overlay, img, highlight)

    # Inset rounded square — geometric accent.
    accent_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(accent_layer)
    pad = 18
    draw.rounded_rectangle(
        [pad, pad, SIZE - pad, SIZE - pad],
        radius=6,
        outline=accent + (235,),
        width=2,
    )
    img = Image.alpha_composite(img.convert("RGBA"), accent_layer).convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    data = buf.getvalue()
    _preset_cache[preset.id] = data
    return data


def list_presets() -> list[dict]:
    return [{"id": p.id, "name": p.name} for p in PRESETS]


def get_preset_bytes(preset_id: str) -> bytes | None:
    for p in PRESETS:
        if p.id == preset_id:
            return _generate_preset(p)
    return None


def apply_preset(preset_id: str) -> bool:
    data = get_preset_bytes(preset_id)
    if data is None:
        return False
    p = icon_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return True


class IconError(ValueError):
    """Validation error for uploaded icon."""


def apply_upload(blob: bytes, declared_content_type: str | None = None) -> int:
    """Validate, normalize, and write the uploaded image.

    Returns the on-disk size in bytes. Raises IconError on validation failure.
    """
    if not blob:
        raise IconError("Empty upload.")
    if len(blob) > MAX_UPLOAD_BYTES:
        raise IconError(f"Image too large (max {MAX_UPLOAD_BYTES // 1024} KB).")

    try:
        img = Image.open(io.BytesIO(blob))
        img.load()
    except Exception as exc:  # noqa: BLE001
        log.warning("Icon upload not a valid image: %s", exc)
        raise IconError("File is not a valid image.") from exc

    if img.format not in ACCEPTED_FORMATS:
        raise IconError("Only PNG, JPEG, or WebP are accepted.")

    # Resize on any non-64×64 input. Preserve transparency on the way in,
    # flatten to opaque RGB on the way out (Minecraft expects PNG; alpha is
    # technically supported but flattening keeps the wire format predictable).
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    if img.size != (SIZE, SIZE):
        img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    if img.mode == "RGBA":
        bg = Image.new("RGB", (SIZE, SIZE), (15, 23, 42))
        bg.paste(img, mask=img.split()[-1])
        img = bg

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    data = out.getvalue()

    p = icon_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return len(data)


def remove() -> bool:
    p = icon_path()
    if p.exists():
        p.unlink()
        return True
    return False


def current_state() -> dict:
    p = icon_path()
    if not p.exists():
        return {"present": False, "size": 0, "etag": None}
    data = p.read_bytes()
    return {
        "present": True,
        "size": len(data),
        "etag": hashlib.md5(data, usedforsecurity=False).hexdigest(),
    }


def read_current() -> bytes | None:
    p = icon_path()
    if not p.exists():
        return None
    return p.read_bytes()
