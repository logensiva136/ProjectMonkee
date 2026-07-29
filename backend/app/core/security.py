"""Password hashing, tokens, TOTP and recovery codes (SPEC §6.1, §6.2).

Everything credential-related lives here so there is exactly one place to audit.
Nothing in this module touches the database; it deals in strings and hashes, and
the services in `app.services.auth` decide what to persist.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import secrets
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type
from jose import JWTError, jwt
from qrcode.image.svg import SvgPathImage
from zxcvbn import zxcvbn

from app.config import get_settings
from app.models.base import utcnow

# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #

# SPEC §6.2 fixes these parameters. 64 MiB of memory per hash is the point of
# Argon2id: it makes GPU-parallel cracking expensive, not just slow.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # KiB, so 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


def hash_password(password: str) -> str:
    """Argon2id hash, salt included in the returned encoded string."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification. False on mismatch, never raises for a bad guess."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current cost parameters.

    Called after a successful login so that raising the cost parameters later
    silently upgrades hashes as users sign in.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# Password policy (SPEC §6.1 step 3)
# --------------------------------------------------------------------------- #

MIN_PASSWORD_LENGTH = 12
MIN_ZXCVBN_SCORE = 3
_TRAILING_DIGITS = re.compile(r"\d+$")


@lru_cache(maxsize=1)
def _common_passwords() -> frozenset[str]:
    """Load the bundled denylist once per process."""
    path = Path(__file__).parent / "data" / "common_passwords.txt"
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip().lower()
        if stripped and not stripped.startswith("#"):
            entries.add(stripped)
    return frozenset(entries)


def _is_common(password: str) -> bool:
    """Match against the denylist, ignoring case and trailing digits.

    "Password123" and "hayabusa2026" are the same weak password as "password"
    and "hayabusa" with a counter bolted on, and users reach for exactly that
    when told to add a number.
    """
    common = _common_passwords()
    lowered = password.lower()
    return lowered in common or _TRAILING_DIGITS.sub("", lowered) in common


def _character_classes(password: str) -> int:
    return sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )


def validate_password(
    password: str,
    *,
    username: str | None = None,
    email: str | None = None,
    full_name: str | None = None,
) -> list[str]:
    """Check a password against SPEC §6.1, returning human-readable problems.

    An empty list means acceptable. The messages are shown to the user verbatim,
    so they say what to do rather than merely what is wrong.

    Personal terms are passed to zxcvbn as `user_inputs` so it also penalises
    passwords *built around* the username, not just ones equal to it.
    """
    problems: list[str] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(
            f"Use at least {MIN_PASSWORD_LENGTH} characters (currently {len(password)})."
        )

    classes = _character_classes(password)
    if classes < 3:
        problems.append(
            f"Mix at least three of: lowercase, uppercase, digits, symbols (currently {classes})."
        )

    if _is_common(password):
        problems.append("This is a commonly used password. Choose something unpredictable.")

    # Substring checks: a password containing the username is trivially guessable
    # by anyone who can see the login form.
    lowered = password.lower()
    personal: list[str] = []
    if username:
        personal.append(username)
    if email:
        personal.append(email.split("@")[0])
    if full_name:
        personal.extend(part for part in full_name.split() if len(part) > 2)

    for term in personal:
        if len(term) >= 3 and term.lower() in lowered:
            problems.append(f"Do not include {term!r} — it is part of your account details.")
            break

    result: dict[str, Any] = zxcvbn(password, user_inputs=[p for p in personal if p])
    if int(result["score"]) < MIN_ZXCVBN_SCORE:
        feedback = result.get("feedback", {}) or {}
        suggestion = (feedback.get("warning") or "").strip()
        if not suggestion:
            suggestions = feedback.get("suggestions") or []
            suggestion = str(suggestions[0]) if suggestions else ""
        problems.append(
            f"Too easy to guess. {suggestion}".strip()
            if suggestion
            else "Too easy to guess. Try a longer passphrase of unrelated words."
        )

    return problems


def password_strength(password: str, *, user_inputs: list[str] | None = None) -> dict[str, Any]:
    """Score a password for the live strength meter (SPEC §6.1 step 3)."""
    result: dict[str, Any] = zxcvbn(password, user_inputs=user_inputs or [])
    feedback = result.get("feedback", {}) or {}
    return {
        "score": int(result["score"]),
        "warning": feedback.get("warning") or "",
        "suggestions": [str(s) for s in (feedback.get("suggestions") or [])],
        "crack_time": str(result["crack_times_display"]["offline_slow_hashing_1e4_per_second"]),
    }


# --------------------------------------------------------------------------- #
# JWT access and MFA tokens
# --------------------------------------------------------------------------- #

ALGORITHM = "HS256"
TokenType = Literal["access", "mfa"]


class TokenError(Exception):
    """A JWT was absent, malformed, expired, or of the wrong type."""


def _create_token(subject: str, token_type: TokenType, expires_in: dt.timedelta) -> str:
    now = utcnow()
    claims = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        # A unique ID per token, so a specific token can be denylisted later
        # without invalidating every token for that user.
        "jti": str(uuid.uuid4()),
    }
    token: str = jwt.encode(claims, get_settings().app_secret_key, algorithm=ALGORITHM)
    return token


def create_access_token(user_id: uuid.UUID | str) -> str:
    """Short-lived bearer token, held only in browser memory (SPEC §6.2).

    Deliberately carries no roles or permissions. Embedding them would make a
    revoked role keep working until the token expired; looking them up per
    request costs one indexed query and makes revocation immediate.
    """
    settings = get_settings()
    return _create_token(
        str(user_id), "access", dt.timedelta(minutes=settings.access_token_ttl_minutes)
    )


def create_mfa_token(user_id: uuid.UUID | str) -> str:
    """Five-minute token proving the password step passed (SPEC §6.2).

    It is NOT an access token: `decode_token` refuses to accept it where an
    access token is required, so presenting it to an API route cannot bypass the
    second factor.
    """
    return _create_token(str(user_id), "mfa", dt.timedelta(minutes=5))


def decode_token(token: str, *, expect: TokenType) -> str:
    """Validate a JWT and return its subject. Raises TokenError otherwise."""
    try:
        claims = jwt.decode(token, get_settings().app_secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise TokenError(str(exc)) from exc

    if claims.get("type") != expect:
        raise TokenError(f"expected a {expect} token, got {claims.get('type')!r}")

    subject = claims.get("sub")
    if not subject:
        raise TokenError("token has no subject")
    return str(subject)


# --------------------------------------------------------------------------- #
# Refresh tokens
# --------------------------------------------------------------------------- #


def generate_refresh_token() -> str:
    """A 256-bit opaque token. Opaque, not a JWT: it must be revocable."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """SHA-256 of a refresh token, for storage.

    Plain SHA-256 rather than Argon2 on purpose. The token is 256 bits of
    machine-generated randomness, so there is no dictionary to attack and no
    need for a slow KDF — and refresh happens on a hot path where a 64 MiB hash
    per call would be felt.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# TOTP (SPEC §6.1 step 4)
# --------------------------------------------------------------------------- #

TOTP_ISSUER = "HAYABUSA"
# One step of tolerance either side, so a user typing a code as it rolls over is
# not rejected. Wider windows meaningfully extend the replay window.
TOTP_VALID_WINDOW = 1


def generate_totp_secret() -> str:
    """A fresh Base32 secret, shown once during onboarding."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, username: str) -> str:
    """`otpauth://` URI for the authenticator app QR code (SPEC §6.1)."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit code against the secret."""
    cleaned = code.strip().replace(" ", "")
    if not cleaned.isdigit() or len(cleaned) != 6:
        return False
    return bool(pyotp.TOTP(secret).verify(cleaned, valid_window=TOTP_VALID_WINDOW))


def totp_qr_svg(uri: str) -> str:
    """Render the provisioning URI as an inline SVG.

    SVG rather than PNG so it can be embedded in a JSON response as text and
    scales crisply — and so the response contains no base64 image blob.
    """
    code = qrcode.QRCode(box_size=10, border=2)
    code.add_data(uri)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    return image.to_string(encoding="unicode")  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# Recovery codes (SPEC §6.1 step 4, §6.2)
# --------------------------------------------------------------------------- #

RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no O/0, I/1, easily misread


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-transcribable single-use codes, formatted `XXXXX-XXXXX`.

    The alphabet omits characters that are misread when copied off a screen or a
    printout, which is exactly how these get used.
    """
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalize_recovery_code(code: str) -> str:
    """Canonical form for comparison: uppercase, hyphens and spaces removed."""
    return re.sub(r"[\s-]", "", code).upper()


def hash_recovery_code(code: str) -> str:
    """Argon2id hash of the normalised code.

    Argon2 here, unlike refresh tokens: a recovery code is only ~50 bits of
    entropy and is typed by a human, so it deserves a slow hash.
    """
    return _hasher.hash(normalize_recovery_code(code))


def verify_recovery_code(code: str, code_hash: str) -> bool:
    try:
        return _hasher.verify(code_hash, normalize_recovery_code(code))
    except (VerifyMismatchError, InvalidHashError):
        return False
