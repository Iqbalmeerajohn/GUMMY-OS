"""Outbound mail for auth flows — console by default, SMTP if configured.

There was no email layer in this project before password reset needed one, and
a local-first app must not require an email account to run. So delivery is a
mode, not a dependency:

* ``console`` (default) — the message is written to the backend log, reset link
  and all. The whole flow is then testable on a laptop with no provider, no
  credentials, and no outbound network.
* ``smtp`` — a real send, configured entirely from the environment.

The one thing this module will not do is pretend. If SMTP is selected and the
send fails, that is an error the caller sees; it never logs "sent" for a message
that was not sent. Console mode is honest in the other direction: it says
plainly that it is a local-development delivery.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)

CONSOLE = "console"
SMTP = "smtp"


@dataclass(frozen=True)
class Message:
    """One outbound email."""

    to: str
    subject: str
    body: str


class MailDeliveryError(RuntimeError):
    """An SMTP send failed. Never raised in console mode."""


def _deliver_to_console(message: Message) -> None:
    """Write the message where a developer will actually see it.

    Deliberately multi-line and prefixed: this competes with SQL echo and
    request logs, and a reset link folded into a single log line is a link
    nobody can find.
    """
    logger.info(
        "\n"
        "==================== [GUMMY AUTH] ====================\n"
        "Local development delivery — no email was actually sent.\n"
        "To: %s\n"
        "Subject: %s\n"
        "\n"
        "%s\n"
        "======================================================",
        message.to,
        message.subject,
        message.body,
    )


def _deliver_over_smtp(message: Message, settings: Settings) -> None:
    if not settings.smtp_host:
        raise MailDeliveryError("AUTH_EMAIL_MODE=smtp but SMTP_HOST is not configured.")

    email = EmailMessage()
    email["From"] = settings.smtp_from or settings.smtp_username or "gummy@localhost"
    email["To"] = message.to
    email["Subject"] = message.subject
    email.set_content(message.body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
            client.ehlo()
            if settings.smtp_use_tls:
                client.starttls()
                client.ehlo()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(email)
    except (smtplib.SMTPException, OSError) as exc:
        # The exception text can carry the server's response, which for some
        # providers echoes the username. Log the type and the host, not the body.
        logger.error(
            "SMTP delivery failed: %s via %s:%s",
            type(exc).__name__,
            settings.smtp_host,
            settings.smtp_port,
        )
        raise MailDeliveryError("Could not deliver the email.") from exc

    logger.info("SMTP delivery ok: to=%s subject=%s", message.to, message.subject)


def send(message: Message, *, settings: Settings) -> None:
    """Deliver a message using the configured mode."""
    if settings.auth_email_mode == SMTP:
        _deliver_over_smtp(message, settings)
        return
    _deliver_to_console(message)
