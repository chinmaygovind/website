"""The signed links that arrive by email.

There is no table of outstanding tokens here, and that is deliberate: a token
carries a fingerprint of the very thing it is allowed to change, so **using it
destroys it**. A password-reset link is signed over the current password hash,
so the moment the password is set the link stops validating - which is what
"single use" actually has to mean. An email-change link is signed over the
address it is replacing, so confirming it, or changing the address by any other
route, kills every link still in flight.

That property is worth more than a table would give: it also survives the
database being restored from a backup, and it means a leaked link is dead the
moment the account moves on rather than the moment a cleanup job runs.

Both are additionally time-limited by ``itsdangerous`` itself - an hour for a
reset, a day for an address confirmation, which is longer because confirming an
address is a thing people do when they get round to it and being timed out of it
costs them their account's contact details.
"""

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

RESET_MAX_AGE = 60 * 60             # an hour
EMAIL_MAX_AGE = 24 * 60 * 60        # a day

_RESET_SALT = "cgovind-accounts-password-reset"
_EMAIL_SALT = "cgovind-accounts-email-change"


def _serializer(secret, salt):
    return URLSafeTimedSerializer(secret, salt=salt)


def _fingerprint(user):
    """Enough of the password hash to notice it changing, and none of it to leak.

    A werkzeug hash is salted, so its tail moves whenever the password is set -
    even to the same password. Sixteen characters is far too little to attack
    the hash with and far more than enough to tell two of them apart.
    """
    return (user.password_hash or "")[-16:]


# --- password reset ---------------------------------------------------------

def make_reset(secret, user):
    return _serializer(secret, _RESET_SALT).dumps(
        {"u": user.id, "h": _fingerprint(user), "e": (user.email or "").lower()})


def read_reset(secret, token, lookup, max_age=RESET_MAX_AGE):
    """Return the user this token is for, or raise ``ValueError`` saying why.

    ``lookup`` takes a user id and returns the user, so this stays free of the
    session and can be tested without one.
    """
    try:
        data = _serializer(secret, _RESET_SALT).loads(token, max_age=max_age)
    except SignatureExpired:
        raise ValueError("That link has expired. Ask for a new one.")
    except BadSignature:
        raise ValueError("That link is not valid. Ask for a new one.")
    user = lookup(data.get("u"))
    if user is None:
        raise ValueError("That link is not valid. Ask for a new one.")
    if _fingerprint(user) != data.get("h") or (user.email or "").lower() != data.get("e"):
        # The password or the address has moved on since the link was sent,
        # which includes the case of this very link having already been used.
        raise ValueError("That link has already been used. Ask for a new one.")
    return user


# --- email change -----------------------------------------------------------

def make_email_change(secret, user, new_email):
    return _serializer(secret, _EMAIL_SALT).dumps(
        {"u": user.id, "old": (user.email or "").lower(), "new": new_email.lower()})


def read_email_change(secret, token, lookup, max_age=EMAIL_MAX_AGE):
    """Return ``(user, new_email)``, or raise ``ValueError`` saying why not."""
    try:
        data = _serializer(secret, _EMAIL_SALT).loads(token, max_age=max_age)
    except SignatureExpired:
        raise ValueError("That confirmation link has expired. Try changing your "
                         "email address again.")
    except BadSignature:
        raise ValueError("That confirmation link is not valid.")
    user = lookup(data.get("u"))
    if user is None:
        raise ValueError("That confirmation link is not valid.")
    if (user.email or "").lower() != data.get("old"):
        raise ValueError("That confirmation link is out of date - this account's "
                         "email address has changed since it was sent.")
    return user, data["new"]
