"""Sending the four emails this site sends.

Plain ``smtplib`` over the box's existing Gmail app password - the same account
Ticket to Ride has been sending from for months - because adding a mail provider
for four transactional emails would be more moving parts than the whole accounts
feature. Configuration is the usual ``SMTP_*`` block in the box's ``.env``.

**Unconfigured is a supported state, not an error.** With no ``SMTP_HOST`` there
is no mail server in a development checkout and there is not going to be, so
``send`` prints the message - link and all - to the log and reports success.
That keeps the reset flow walkable locally, and it means a misconfigured box
degrades to "the link is in the journal" rather than to a 500 in front of
somebody who has forgotten their password.

Sending is best-effort by design: the routes that call this never tell the
visitor whether it worked, because saying so would answer "does an account with
this address exist?" to anyone who asks.
"""

import os
import smtplib
import sys
from email.message import EmailMessage
from email.utils import formataddr


def _config():
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", 587))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    # TTR's own SMTP_FROM says "Ticket to Ride", which is the wrong signature on
    # a letter about a cgovind.com account, so this has its own default.
    sender = os.environ.get("ACCOUNTS_SMTP_FROM") or (
        formataddr(("cgovind.com", user)) if user else None)
    return host, port, user, password, sender


def send(to, subject, body):
    """Send one plain-text email. Returns True if it went, False if it did not."""
    host, port, user, password, sender = _config()

    if not (host and user and password):
        print("[accounts] no SMTP configured; would have sent to %s:\n"
              "  Subject: %s\n%s" % (to, subject, _indent(body)),
              file=sys.stderr, flush=True)
        return True

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True
    except Exception as exc:                             # noqa: BLE001
        print("[accounts] could not send mail to %s: %s" % (to, exc),
              file=sys.stderr, flush=True)
        return False


def _indent(text):
    return "\n".join("  " + line for line in text.splitlines())


# --- the letters themselves -------------------------------------------------
#
# Short, plain text, and each one says what to do if it was not you - which for
# a reset email is the only part that matters to the person who did not ask
# for it.

def password_reset(to, name, link):
    return send(
        to, "Reset your cgovind.com password",
        "Hi %s,\n\n"
        "Someone asked to reset the password on your cgovind.com account - the "
        "one you use for Ticket to Ride, Egyptian Rat Screw, King of Tokyo and "
        "Drive.\n\n"
        "Set a new password here:\n%s\n\n"
        "The link works once and expires in an hour.\n\n"
        "If this wasn't you, you can ignore this email. Your password has not "
        "changed and the link above is useless to anyone who doesn't get it.\n"
        % (name, link))


def confirm_new_email(to, name, link):
    return send(
        to, "Confirm your new cgovind.com email address",
        "Hi %s,\n\n"
        "This address was given as the new email for your cgovind.com account. "
        "Confirm it here:\n%s\n\n"
        "The link expires in a day. Until you use it, the account keeps its old "
        "address.\n\n"
        "If you weren't expecting this, ignore it - nothing has changed.\n"
        % (name, link))


def email_changed_notice(to, name, new_email):
    """To the *old* address, after the change goes through.

    The one email here that nobody asked for, and the important one: if an
    account is taken over, changing the address is the first thing that
    happens, and this is the only warning the person who owns it would get.
    """
    return send(
        to, "Your cgovind.com email address was changed",
        "Hi %s,\n\n"
        "The email address on your cgovind.com account has been changed to "
        "%s.\n\n"
        "If you did this, there is nothing to do.\n\n"
        "If you did not, reply to this email straight away - somebody else has "
        "your password.\n" % (name, new_email))


def password_changed_notice(to, name):
    return send(
        to, "Your cgovind.com password was changed",
        "Hi %s,\n\n"
        "The password on your cgovind.com account has just been changed.\n\n"
        "If that was you, there is nothing to do. If it wasn't, reply to this "
        "email.\n" % (name,))
