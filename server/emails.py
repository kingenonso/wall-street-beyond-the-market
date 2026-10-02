"""Email addresses: working out which mailbox an address really reaches,
confirmation codes, and sending mail."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import smtplib
from email.message import EmailMessage

from server.config import get_settings

log = logging.getLogger("wsbm.email")

CODE_MINUTES = 15
MAX_WRONG_GUESSES = 5

# Services that hand out throwaway mailboxes by the thousand. An account needs a
# lasting address. The list is not complete and never can be; it raises the effort.
_THROWAWAY_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
    "tempmail.com", "temp-mail.org", "yopmail.com", "trashmail.com", "getnada.com", "throwawaymail.com",
    "dispostable.com", "maildrop.cc", "fakeinbox.com", "mintemail.com", "mailnesia.com", "tempr.email",
    "discard.email", "emailondeck.com", "moakt.com", "mohmal.com", "tempmailo.com", "burnermail.io",
})

# Providers that ignore full stops in the name: a.d.a@ and ada@ are one mailbox.
_DOTS_IGNORED = frozenset({"gmail.com"})
_SAME_PROVIDER = {"googlemail.com": "gmail.com"}


class UnusableEmail(ValueError):
    pass


def email_key(email: str) -> str:
    """The mailbox an address really delivers to. Addresses with the same key are
    the same person's inbox, so only one account may exist per key."""
    name, _, domain = email.strip().lower().rpartition("@")
    domain = _SAME_PROVIDER.get(domain, domain)
    name = name.split("+", 1)[0]                 # ada+anything@ is delivered to ada@
    if domain in _DOTS_IGNORED:
        name = name.replace(".", "")
    if not name or not domain:
        raise UnusableEmail("That email address is not valid.")
    if domain in _THROWAWAY_DOMAINS:
        raise UnusableEmail("Please use a lasting email address, not a temporary one.")
    return f"{name}@{domain}"


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(key: str, code: str) -> str:
    """Scramble a code together with the address it was sent to, using the server's
    secret key, so that a copy of the database does not reveal any codes."""
    secret = get_settings().secret_key.encode()
    return hmac.new(secret, f"{key}:{code}".encode(), hashlib.sha256).hexdigest()


def code_matches(key: str, code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_code(key, code), stored_hash)


def shown_on_screen() -> bool:
    """True while no email service is connected (running on your own computer).
    The code is then shown on the sign-up screen instead of being emailed."""
    return get_settings().smtp_host is None


def send(to: str, subject: str, body: str) -> None:
    """Send one plain email. Raises if the email service refuses it."""
    settings = get_settings()
    if settings.smtp_host is None:
        log.info("No email service is connected. Email to %s not sent: %s", to, subject)
        return
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password or "")
        server.send_message(message)


def send_code(to: str, code: str) -> None:
    send(
        to,
        "Your Wall Street: Beyond the Market code",
        f"Your code is {code}\n\n"
        f"Type it into the sign-up page to open your account. It works for {CODE_MINUTES} minutes.\n\n"
        "If you did not ask for this, ignore this email. No account has been opened.",
    )


def send_already_registered(to: str) -> None:
    send(
        to,
        "You already have an account",
        "Somebody tried to open a new Wall Street: Beyond the Market account with this email address.\n\n"
        "You already have an account, and each email address can have only one. "
        "If it was you, log in instead. If it was not you, you need do nothing.",
    )
