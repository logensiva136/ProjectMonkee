"""Create a local `.env` from `.env.example`, generating the two secrets.

Idempotent: an existing `.env` is never overwritten, and any secret already set
in it is left alone. Run via `make secrets` / `./make.ps1 secrets`.

APP_SECRET_KEY     signs JWTs (SPEC §4).
APP_ENCRYPTION_KEY is the AES-GCM key protecting bot tokens and source
                   credentials at rest; it must be exactly 32 bytes, urlsafe
                   base64 encoded, because that is what `cryptography`'s AESGCM
                   accepts for AES-256.
"""

from __future__ import annotations

import base64
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"

# Keys we fill in when they are present but empty.
GENERATORS = {
    "APP_SECRET_KEY": lambda: secrets.token_urlsafe(48),
    "APP_ENCRYPTION_KEY": lambda: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
}


def fill(line: str) -> tuple[str, str | None]:
    """Return (possibly rewritten line, name of the key we generated)."""
    match = re.match(r"^(?P<key>[A-Z0-9_]+)=(?P<value>[^#\n]*)(?P<comment>#.*)?$", line.rstrip("\n"))
    if not match:
        return line, None

    key = match.group("key")
    value = match.group("value").strip()
    if key not in GENERATORS or value:
        return line, None

    comment = match.group("comment")
    rewritten = f"{key}={GENERATORS[key]()}"
    if comment:
        rewritten = f"{rewritten}  {comment}"
    return rewritten + "\n", key


def main() -> int:
    if not EXAMPLE.exists():
        print(f"error: {EXAMPLE} not found", file=sys.stderr)
        return 1

    if TARGET.exists():
        print(f".env already exists at {TARGET} — leaving it untouched.")
        missing = [
            key
            for key in GENERATORS
            if re.search(rf"^{key}=\s*(#.*)?$", TARGET.read_text(encoding="utf-8"), re.MULTILINE)
        ]
        if missing:
            print(f"warning: these are still empty and must be set: {', '.join(missing)}")
            return 1
        return 0

    generated: list[str] = []
    out: list[str] = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines(keepends=True):
        rewritten, key = fill(line)
        out.append(rewritten)
        if key:
            generated.append(key)

    TARGET.write_text("".join(out), encoding="utf-8")
    print(f"wrote {TARGET}")
    for key in generated:
        print(f"  generated {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
