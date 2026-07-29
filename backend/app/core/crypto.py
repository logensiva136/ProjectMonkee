"""Symmetric encryption for secrets at rest (SPEC §4).

Telegram bot tokens, TOTP secrets and source credentials are stored encrypted
with AES-256-GCM under `APP_ENCRYPTION_KEY`. GCM is authenticated: tampering
with stored ciphertext produces a decryption failure rather than silently
different plaintext.

Wire format, base64url encoded:

    [ 12-byte nonce ][ ciphertext ][ 16-byte GCM tag ]

The nonce is random per encryption and stored alongside the ciphertext. It is
not secret — but it must never repeat under the same key, which is why it is
generated fresh on every call and never derived from the plaintext.

**Key rotation destroys existing ciphertext.** There is no key-id envelope yet,
so changing `APP_ENCRYPTION_KEY` orphans every stored secret; they must be
re-entered. This is stated in the README runbook.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings
from app.core.errors import AppError

NONCE_BYTES = 12  # 96 bits, the size GCM is specified for


class DecryptionError(AppError):
    """Ciphertext could not be decrypted — wrong key, or it was tampered with."""

    status_code = 500
    title = "Decryption Failed"
    problem_type = "decryption-failed"


def _cipher() -> AESGCM:
    return AESGCM(get_settings().encryption_key_bytes)


def encrypt(plaintext: str) -> str:
    """Encrypt a string, returning base64url of nonce||ciphertext||tag."""
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _cipher().encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    """Reverse `encrypt`. Raises DecryptionError on a bad key or tampering."""
    try:
        raw = base64.urlsafe_b64decode(token)
    except (ValueError, TypeError) as exc:
        raise DecryptionError("Stored secret is not valid base64.") from exc

    if len(raw) <= NONCE_BYTES:
        raise DecryptionError("Stored secret is truncated.")

    nonce, ciphertext = raw[:NONCE_BYTES], raw[NONCE_BYTES:]
    try:
        return _cipher().decrypt(nonce, ciphertext, None).decode("utf-8")
    except InvalidTag as exc:
        # Either APP_ENCRYPTION_KEY changed, or the row was modified. Both are
        # operational faults, and neither should leak detail to the caller.
        raise DecryptionError(
            "Stored secret could not be decrypted. The encryption key may have changed."
        ) from exc


def mask_secret(secret: str, *, head: int = 12, tail: int = 3) -> str:
    """Render a secret for display without disclosing it (SPEC §4).

    A Telegram bot token becomes `123456789:AAE••••••••xyz` — enough to tell two
    bots apart at a glance, not enough to use.

    Short secrets are masked entirely rather than mostly-revealed, which is the
    failure mode a naive slice would have.
    """
    if len(secret) <= head + tail:
        return "•" * 12
    return f"{secret[:head]}{'•' * 8}{secret[-tail:]}"
