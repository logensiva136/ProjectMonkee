"""Deterministic SVG monogram avatars (SPEC §6.1 step 2).

When an organisation uploads no logo, the console still needs a mark. Rather
than a generic placeholder, derive one from the name: initials on a background
colour computed from a hash of that name.

Deterministic matters. The same organisation name always yields the same colour,
so the avatar does not change between the wizard's live preview and what the top
bar renders afterwards, and it survives a database restore.
"""

from __future__ import annotations

import hashlib
import re

# Corporate suffixes that carry no identity. "Maybank Berhad" should give "M",
# not "MB" — the "B" says nothing about which company it is.
_NOISE_WORDS = frozenset(
    {
        "sdn",
        "bhd",
        "sdn.",
        "bhd.",
        "berhad",
        "inc",
        "inc.",
        "ltd",
        "ltd.",
        "limited",
        "llc",
        "llp",
        "plc",
        "gmbh",
        "corp",
        "corp.",
        "corporation",
        "company",
        "co",
        "co.",
        "group",
        "holdings",
        "holding",
        "pte",
        "pty",
        "the",
        "and",
        "of",
        "&",
    }
)

_WORD = re.compile(r"[A-Za-z0-9]+")

# Backgrounds picked to hold white text at WCAG AA and to sit alongside the
# SPEC §9.1 palette without clashing with the cyan accent.
_PALETTE = (
    "#0E7490",
    "#4338CA",
    "#6D28D9",
    "#9D174D",
    "#B45309",
    "#15803D",
    "#0F766E",
    "#7C2D12",
    "#1D4ED8",
    "#A21CAF",
    "#374151",
    "#065F46",
)


def derive_initials(name: str, *, max_length: int = 3) -> str:
    """Initials for an organisation or person.

    "Test Bank Sdn Bhd" -> "TB". "logen" -> "LO". Falls back to the first two
    characters when there is only one meaningful word, because a single letter
    reads as an error rather than a monogram.
    """
    # Annotated because `re.findall` is typed as returning `list[Any]`, which
    # would make every `.upper()` below an untyped expression.
    all_words: list[str] = _WORD.findall(name)
    words = [word for word in all_words if word.lower() not in _NOISE_WORDS]

    if not words:
        # Everything was noise — fall back to the raw string.
        if not all_words:
            return "?"
        return all_words[0][:2].upper()

    if len(words) == 1:
        return words[0][:2].upper()

    return "".join(word[0] for word in words[:max_length]).upper()


def derive_color(seed: str) -> str:
    """Pick a palette entry from a hash of the name.

    SHA-256 rather than Python's `hash()`: the built-in is salted per process,
    so the colour would change on every restart.
    """
    digest = hashlib.sha256(seed.strip().lower().encode("utf-8")).digest()
    return _PALETTE[digest[0] % len(_PALETTE)]


def render_monogram_svg(name: str, *, size: int = 512, initials: str | None = None) -> str:
    """Render a square SVG monogram.

    Self-contained: no external font reference, no embedded raster. It can be
    served directly, inlined into a page, or written to disk.
    """
    text = (initials or derive_initials(name)).strip() or "?"
    background = derive_color(name)

    # Shrink the glyphs as the initials get longer so three letters still fit
    # inside the square with breathing room.
    font_size = {1: 0.46, 2: 0.38, 3: 0.29}.get(len(text), 0.26) * size

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" role="img" aria-label="{text}">'
        f'<rect width="{size}" height="{size}" rx="{round(size * 0.18)}" fill="{background}"/>'
        f'<text x="50%" y="50%" fill="#FFFFFF" '
        f'font-family="Inter, ui-sans-serif, system-ui, sans-serif" '
        f'font-size="{font_size:.0f}" font-weight="600" letter-spacing="{size * 0.01:.1f}" '
        f'text-anchor="middle" dominant-baseline="central">{text}</text>'
        f"</svg>"
    )
