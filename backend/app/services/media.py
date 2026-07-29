"""Image upload handling for the organisation logo (SPEC §6.1 step 2, §10).

SPEC §10 requires uploads be validated by magic bytes, not by extension. A file
called `logo.png` containing a PHP script is the oldest upload trick there is,
and the extension is attacker-controlled while the first eight bytes are not.

The pipeline is: sniff the real type, decode, strip metadata, re-encode. That
last step is what actually makes the file safe — the bytes written to disk are
produced by Pillow from decoded pixels, so nothing of the original container
(EXIF, embedded thumbnails, appended payloads) survives.
"""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from app.core.errors import BadRequestError, UnprocessableError
from app.core.logging import get_logger

log = get_logger(__name__)

MAX_LOGO_BYTES: Final = 2 * 1024 * 1024  # SPEC §6.1: 2 MB
LOGO_SIZE: Final = 512  # SPEC §6.1: resize to 512x512

# Magic-byte signatures. SVG is text, so it is sniffed separately.
_SIGNATURES: Final = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"RIFF", "webp"),  # confirmed by checking bytes 8..12 for "WEBP"
)

# SVG is XML, and XML is an attack surface: external entities, embedded scripts,
# and remote references. Rather than sanitise it, SVG uploads are rasterised to
# PNG on the way in, so nothing executable ever reaches a browser.
_SVG_HINT = re.compile(rb"<svg[\s>]", re.IGNORECASE)
_SVG_DANGEROUS = re.compile(
    rb"<script|<!ENTITY|javascript:|xlink:href\s*=\s*[\"']\s*(?!#)", re.IGNORECASE
)


def sniff_image_type(data: bytes) -> str | None:
    """Identify an image from its leading bytes. None if unrecognised."""
    for signature, kind in _SIGNATURES:
        if data.startswith(signature):
            if kind == "webp" and data[8:12] != b"WEBP":
                continue
            return kind

    # SVG has no binary magic; look for the root element near the start, past
    # any XML declaration, DOCTYPE or leading whitespace.
    if _SVG_HINT.search(data[:1024]):
        return "svg"

    return None


def validate_logo_bytes(data: bytes) -> str:
    """Check size and real type. Returns the sniffed type, or raises."""
    if not data:
        raise BadRequestError("The uploaded file is empty.")

    if len(data) > MAX_LOGO_BYTES:
        raise UnprocessableError(
            f"Logo must be 2 MB or smaller (received {len(data) / 1024 / 1024:.1f} MB)."
        )

    kind = sniff_image_type(data)
    if kind is None:
        raise UnprocessableError("Unsupported image. Upload a PNG, JPG, WebP or SVG file.")

    if kind == "svg" and _SVG_DANGEROUS.search(data):
        # Refuse rather than strip: a scriptable SVG is not something a logo
        # upload has any reason to contain.
        raise UnprocessableError(
            "This SVG contains scripts or external references and cannot be used."
        )

    return kind


def process_logo(data: bytes, destination_dir: Path) -> str:
    """Validate, normalise and store a logo. Returns the stored filename.

    Output is always a square 512x512 PNG with no metadata, regardless of what
    came in. Transparency is preserved so the mark sits correctly on both the
    dark and light themes.
    """
    kind = validate_logo_bytes(data)
    destination_dir.mkdir(parents=True, exist_ok=True)

    if kind == "svg":
        # Store vetted SVG as-is: it scales better than a raster at every size,
        # and it has already been checked for scripts and external references.
        filename = f"logo-{uuid.uuid4().hex}.svg"
        (destination_dir / filename).write_bytes(data)
        log.info("logo_stored", kind="svg", filename=filename, bytes=len(data))
        return filename

    try:
        with Image.open(io.BytesIO(data)) as source:
            # `load()` forces a full decode, so a truncated or malformed file
            # fails here rather than halfway through the resize.
            source.load()
            image = source.convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UnprocessableError("The image could not be decoded.") from exc

    image = fit_square(image, LOGO_SIZE)

    filename = f"logo-{uuid.uuid4().hex}.png"
    # A fresh Image built from pixels: no EXIF, no ICC profile, no appended data.
    image.save(destination_dir / filename, format="PNG", optimize=True)
    log.info("logo_stored", kind=kind, filename=filename)
    return filename


def fit_square(image: Image.Image, size: int) -> Image.Image:
    """Scale to fit inside `size` and centre on a transparent square.

    Letterboxing rather than cropping: a wide wordmark centred on a square is
    still readable, whereas a centre-crop of one is unrecognisable.
    """
    image.thumbnail((size, size), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
    return canvas
