"""What you are allowed to be called.

Two names, on purpose, and they answer different questions.

The **username** is the login and the URL, and it is permanent. Nothing about a
person should be able to change the address of their own profile: a link
somebody sent last month has to still work, and a name that can be given up is a
name somebody else can pick up and be mistaken for.

The **display name** is what every screen actually shows, and it is theirs to
change. It is unique *case-insensitively* and it may not collide with anybody
else's username either, which is the whole point of enforcing it at all: a
leaderboard with two rows reading "chinmay" on it is not a cosmetic problem.
SQLite's UNIQUE is case-sensitive, so the constraint lives on a folded copy of
the string (``UserProfile.display_name_lc``) and this module is what folds it.
"""

import re

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{1,29}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# A display name is a name, not an identifier, so it is much freer than a
# username - spaces and apostrophes and accents are all fine. What it may not
# contain is anything that would let it lie about the page it is drawn on:
# control characters, and the bidirectional overrides that can make a string
# render as text it does not contain.
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁦-⁩]")

MIN_PASSWORD = 8

# Addresses under /accounts/ that are pages rather than people. A username is
# checked against these at registration so that no account can be created that
# its own profile URL would not reach.
RESERVED = {
    "settings", "forgot", "reset", "login", "logout", "register", "avatar",
    "confirm-email", "confirm", "me", "admin", "api", "static", "new", "edit",
}


def fold(name):
    """The comparison form of a name: lower case, inner runs of space collapsed."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def check_username(name):
    """Return an error message, or None if the username is allowed."""
    name = (name or "").strip()
    if not USERNAME_RE.match(name):
        return ("Username must be 2-30 characters, start with a letter, and use "
                "only letters, numbers, hyphens or underscores.")
    if name.lower() in RESERVED:
        return "That username is reserved. Pick another one."
    return None


def check_display_name(name):
    """Return an error message, or None if the display name is allowed."""
    name = (name or "").strip()
    if len(name) < 2:
        return "Display name must be at least 2 characters."
    if len(name) > 30:
        return "Display name must be 30 characters or fewer."
    if _BAD_CHARS.search(name):
        return "Display name can't contain that character."
    if not any(ch.isalnum() for ch in name):
        return "Display name needs at least one letter or number."
    if fold(name) in RESERVED:
        return "That display name is reserved. Pick another one."
    return None


def check_email(email):
    email = (email or "").strip()
    if not EMAIL_RE.match(email):
        return "Please enter a valid email address."
    if len(email) > 120:
        return "That email address is too long."
    return None


def check_password(password):
    if len(password or "") < MIN_PASSWORD:
        return "Password must be at least %d characters." % MIN_PASSWORD
    return None
