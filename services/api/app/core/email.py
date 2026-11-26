"""Outgoing email over SMTP.

The application's only email path. Uses the standard library, so no new
dependency. Errors raised from here carry a short, safe description: never
the SMTP password, never the message body (which may contain a link).
"""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """The email was not delivered. The message is safe to log."""


class EmailNotConfiguredError(EmailDeliveryError):
    """SMTP_HOST or EMAIL_FROM is not set."""


def is_email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.EMAIL_FROM)


def build_message(
    to_address: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr(
        (settings.EMAIL_FROM_NAME, settings.EMAIL_FROM or "")
    )
    message["To"] = to_address
    message["Subject"] = subject

    domain = (settings.EMAIL_FROM or "localhost").rpartition("@")[2]
    message["Message-ID"] = make_msgid(domain=domain or None)

    message.set_content(text_body)

    if html_body:
        message.add_alternative(html_body, subtype="html")

    return message


def send_email(
    to_address: str,
    subject: str,
    text_body: str,
    html_body: str | None = None,
) -> None:
    """Sends one email or raises EmailDeliveryError. Never reports success
    for a message the server did not accept."""
    if not is_email_configured():
        raise EmailNotConfiguredError("Email is not configured.")

    message = build_message(to_address, subject, text_body, html_body)
    context = ssl.create_default_context()

    try:
        if settings.SMTP_SSL:
            server = smtplib.SMTP_SSL(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
                context=context,
            )
        else:
            server = smtplib.SMTP(
                settings.SMTP_HOST,
                settings.SMTP_PORT,
                timeout=settings.SMTP_TIMEOUT_SECONDS,
            )

        with server:
            if not settings.SMTP_SSL and settings.SMTP_STARTTLS:
                server.starttls(context=context)

            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD.get_secret_value(),
                )

            refused = server.send_message(message)

        if refused:
            raise EmailDeliveryError("The mail server refused the recipient.")

    except EmailDeliveryError:
        raise
    except (smtplib.SMTPException, OSError) as exc:
        # Only the exception class is reported. SMTP exception text can
        # echo server responses, and chaining would carry it into logs.
        raise EmailDeliveryError(
            f"SMTP delivery failed ({type(exc).__name__})."
        ) from None
