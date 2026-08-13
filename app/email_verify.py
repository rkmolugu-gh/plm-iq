"""Email verification & password-reset helpers.

Provides stateless signed tokens (itsdangerous, valid ``VERIFY_TOKEN_MAX_AGE_*``)
and a thin wrapper over the SMTP sender. When SMTP is disabled the callers show
the generated link on the page / log it (dev fallback).
"""

import logging
from typing import Optional

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import SECRET_KEY, VERIFY_TOKEN_MAX_AGE_MINUTES
from app.notifications import _send_email_safe

logger = logging.getLogger(__name__)

_SALT = "plm-verify"


def make_token(uid: int, email: str) -> str:
    """Return a signed, expiring token embedding the user id + email."""
    s = URLSafeTimedSerializer(SECRET_KEY, salt=_SALT)
    return s.dumps({"uid": uid, "email": email})


def read_token(token: str, max_age_minutes: Optional[int] = None):
    """Validate a token; return (uid, email) or None on any failure.

    Returns None for invalid, expired, or tampered tokens (never raises).
    """
    age = (max_age_minutes or VERIFY_TOKEN_MAX_AGE_MINUTES) * 60
    s = URLSafeTimedSerializer(SECRET_KEY, salt=_SALT)
    try:
        data = s.loads(token, max_age=age)
    except (BadSignature, SignatureExpired, Exception):  # noqa: BLE001
        return None
    return data.get("uid"), data.get("email")


def verification_link(request, uid: int, email: str) -> str:
    """Build the absolute verification URL for a user."""
    token = make_token(uid, email)
    base = str(request.base_url).rstrip("/")
    return f"{base}/verify/{token}"


_PURPOSE_COPY = {
    "register": (
        "[PLM-IQ] Verify your email",
        "Welcome to PLM-IQ! Verify your email and set a password to activate "
        "your tenant admin account.\n\nOpen this link (valid 1 hour):\n{link}",
    ),
    "invite": (
        "[PLM-IQ] You've been invited",
        "You've been invited to PLM-IQ. Verify your email and set a password "
        "to activate your account.\n\nOpen this link (valid 1 hour):\n{link}",
    ),
    "reset": (
        "[PLM-IQ] Reset your password",
        "A password reset was requested. Open this link to set a new password "
        "(valid 1 hour):\n{link}",
    ),
}


def send_verification_email(request, user, purpose: str) -> str:
    """Send a purpose-appropriate verification email; return the link.

    When SMTP is disabled ``_send_email_safe`` returns False and no email is
    sent — the returned link is shown by the caller (dev fallback).
    """
    link = verification_link(request, user.user_id, user.email)
    subject, body_tmpl = _PURPOSE_COPY.get(
        purpose, _PURPOSE_COPY["reset"]
    )
    sent = _send_email_safe(user.email, subject, body_tmpl.format(link=link))
    if not sent:
        logger.info("verify email (SMTP off) for '%s': %s", user.email, link)
    return link


def send_generic_email(to: str, subject: str, body: str) -> bool:
    """Send an arbitrary email; never raises (SMTP-enabled guard inside)."""
    return _send_email_safe(to, subject, body)
