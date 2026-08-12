"""In-app notifications + optional email delivery.

In-app notifications are always recorded. Email is sent only when ``SMTP_ENABLED`` is
true in config; failures are logged and swallowed so a missing mail server never breaks
an approval. ``notify()`` is called inside a DB session that the caller commits.
"""

import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from sqlalchemy.orm import Session

from app.config import SMTP_ENABLED, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS
from app.models import Notification
from app.settings import STATUS_PENDING

logger = logging.getLogger(__name__)


def _send_email_safe(to: str, subject: str, body: str) -> bool:
    """Send one email via SMTP; never raise — log and return False on failure."""
    if not SMTP_ENABLED or not SMTP_HOST or not to:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 - mail must never break the request
        logger.warning("Email send failed to %s: %s", to, e)
        return False


def notify(
    db: Session,
    user,
    ntype: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    email: bool = True,
    background=None,
) -> Notification:
    """Record an in-app notification for ``user`` and optionally queue an email.

    ``background`` is a FastAPI ``BackgroundTasks`` instance; when provided the email
    is sent after the response returns, otherwise synchronously (still failure-safe).
    """
    notif = Notification(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        tenant_key=getattr(user, 'tenant_key', ''),
        type=ntype,
        title=title,
        message=message,
        link=link,
        is_read=False,
        created_at=_today(),
    )
    db.add(notif)

    if email and SMTP_ENABLED and getattr(user, "email", None):
        subject = f"[PLM-IQ] {title}"
        body = f"{message}\n\n{('Open: ' + link) if link else ''}"
        if background is not None:
            background.add_task(_send_email_safe, user.email, subject, body)
        else:
            _send_email_safe(user.email, subject, body)
    return notif


def inbox_counts(db: Session, user) -> tuple[int, int]:
    """Return (pending_task_count, unread_notification_count) for ``user``."""
    from app.models import WorkflowTask

    tasks = (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.assigned_to == user.user_id,
            WorkflowTask.tenant_id == user.tenant_id,
            WorkflowTask.status == STATUS_PENDING,
        )
        .count()
    )
    unread = (
        db.query(Notification)
        .filter(
            Notification.user_id == user.user_id,
            Notification.tenant_id == user.tenant_id,
            Notification.is_read == False,  # noqa: E712
        )
        .count()
    )
    return tasks, unread


def _today() -> str:
    import datetime
    return datetime.date.today().isoformat()
