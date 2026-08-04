"""The signed links, and the property that makes them safe without a table.

The claim under test is that **using a link destroys it**, and that it is
destroyed by the thing it was for rather than by a cleanup job: a reset link
dies when the password is set, an address-change link dies when the address
moves. Everything else here is the ordinary tampering.
"""

import pytest

from accounts import tokens
from accounts.models import User

SECRET = "test-secret"


class FakeUser:
    """Enough of a user for the token module, which only reads three fields."""
    def __init__(self, uid=1, email="a@example.com", password="one"):
        self.id = uid
        self.email = email
        self.password_hash = None
        self.set_password(password)

    def set_password(self, pw):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(pw)


def lookup_for(*users):
    by_id = {u.id: u for u in users}
    return lambda uid: by_id.get(uid)


# --- password reset ---------------------------------------------------------

def test_a_fresh_link_names_its_user():
    user = FakeUser()
    token = tokens.make_reset(SECRET, user)
    assert tokens.read_reset(SECRET, token, lookup_for(user)) is user


def test_setting_the_password_kills_the_link():
    """This is what "single use" means here: the link is signed over the hash
    it is allowed to replace, so replacing it is what invalidates the link.
    No table of spent tokens, and it survives a restore from backup."""
    user = FakeUser()
    token = tokens.make_reset(SECRET, user)
    user.set_password("something new")

    with pytest.raises(ValueError, match="already been used"):
        tokens.read_reset(SECRET, token, lookup_for(user))


def test_setting_the_same_password_still_kills_the_link():
    """Werkzeug salts, so the hash moves even when the password does not -
    which matters, because otherwise a reset to the existing password would
    leave the link live."""
    user = FakeUser(password="same")
    token = tokens.make_reset(SECRET, user)
    user.set_password("same")

    with pytest.raises(ValueError):
        tokens.read_reset(SECRET, token, lookup_for(user))


def test_changing_the_email_kills_the_link_too():
    """A reset link is a key to whoever holds that mailbox. If the account has
    moved to a different mailbox since, the old one no longer speaks for it."""
    user = FakeUser()
    token = tokens.make_reset(SECRET, user)
    user.email = "somewhere-else@example.com"

    with pytest.raises(ValueError):
        tokens.read_reset(SECRET, token, lookup_for(user))


def test_an_expired_link_says_so_rather_than_failing_the_signature():
    user = FakeUser()
    token = tokens.make_reset(SECRET, user)
    with pytest.raises(ValueError, match="expired"):
        tokens.read_reset(SECRET, token, lookup_for(user), max_age=-1)


def test_a_tampered_or_foreign_link_is_refused():
    user = FakeUser()
    token = tokens.make_reset(SECRET, user)

    with pytest.raises(ValueError, match="not valid"):
        tokens.read_reset("a different secret", token, lookup_for(user))
    with pytest.raises(ValueError, match="not valid"):
        tokens.read_reset(SECRET, token[:-3] + "aaa", lookup_for(user))
    with pytest.raises(ValueError, match="not valid"):
        tokens.read_reset(SECRET, token, lambda uid: None)   # user deleted


def test_the_link_carries_no_secret_of_its_own():
    """It is signed, not encrypted, so anyone can read the payload. Sixteen
    characters of a salted hash is far too little to attack it with, and the
    password itself is nowhere near it."""
    import base64
    user = FakeUser(password="correct horse battery staple")
    token = tokens.make_reset(SECRET, user)
    payload = token.split(".")[0]
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
    assert "correct horse" not in raw
    assert user.password_hash not in raw


# --- email change -----------------------------------------------------------

def test_an_address_change_confirms_once():
    user = FakeUser(email="old@example.com")
    token = tokens.make_email_change(SECRET, user, "New@Example.com")

    got_user, new_email = tokens.read_email_change(SECRET, token, lookup_for(user))
    assert got_user is user
    assert new_email == "new@example.com"           # folded on the way in

    user.email = new_email                          # as the route would
    with pytest.raises(ValueError, match="out of date"):
        tokens.read_email_change(SECRET, token, lookup_for(user))


def test_changing_the_address_any_other_way_kills_links_in_flight():
    """Two requests out, one confirmed: the other has to be dead, or the second
    click silently moves the account somewhere the owner did not choose."""
    user = FakeUser(email="old@example.com")
    first = tokens.make_email_change(SECRET, user, "one@example.com")
    second = tokens.make_email_change(SECRET, user, "two@example.com")

    tokens.read_email_change(SECRET, first, lookup_for(user))
    user.email = "one@example.com"

    with pytest.raises(ValueError):
        tokens.read_email_change(SECRET, second, lookup_for(user))


def test_a_reset_link_is_not_an_email_change_link():
    """Different salts, so one cannot be presented as the other."""
    user = FakeUser()
    reset = tokens.make_reset(SECRET, user)
    with pytest.raises(ValueError):
        tokens.read_email_change(SECRET, reset, lookup_for(user))

    change = tokens.make_email_change(SECRET, user, "new@example.com")
    with pytest.raises(ValueError):
        tokens.read_reset(SECRET, change, lookup_for(user))


def test_it_works_against_the_real_user_model(db):
    """The fake above only has three attributes; this is the real one."""
    user = User(username="real", email="real@example.com")
    user.set_password("hunter2hunter2")
    db.session.add(user)
    db.session.commit()

    token = tokens.make_reset(SECRET, user)
    assert tokens.read_reset(SECRET, token, lambda uid: db.session.get(User, uid)).id == user.id

    user.set_password("a new one entirely")
    db.session.commit()
    with pytest.raises(ValueError):
        tokens.read_reset(SECRET, token, lambda uid: db.session.get(User, uid))
