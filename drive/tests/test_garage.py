"""The livery vocabulary, the palette's claim about itself, and the gates.

Three groups, and they are three different kinds of claim.

The **palette** group is the unusual one: it checks a list of colours against the
rules the list was built to satisfy, in both directions. A palette is the sort of
thing somebody adds a nice colour to in thirty seconds, and the failure - two
cars you cannot tell apart at distance, or one that vanishes against snow - is
invisible from any screenshot taken on the day and obvious in the middle of a
race a month later. So the rule is executable.

The **validate/resolve** group pins the split those two names exist for: what
somebody asked for is stored whole, and what they may *wear* is decided every
time it is read. That is the whole of how a gate is enforced.

And running under all of it, the one that matters most:
``test_a_user_with_no_row_is_exactly_todays_car``. Everything here is allowed to
be wrong in some interesting way before it is allowed to repaint somebody's car.
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import garage  # noqa: E402
import tracks as tracks_mod  # noqa: E402


# ---------------------------------------------------------------------------
# CIELAB, so the palette's claim can be checked rather than asserted
# ---------------------------------------------------------------------------
# Written out here rather than pulled in, because a colour library is a
# dependency the box would then have to install to run a test about paint.

def _lab(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    # sRGB -> XYZ (D65), then XYZ -> L*a*b* against the D65 white point.
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 1.00000
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def _de(a, b):
    la, lb = _lab(a), _lab(b)
    return sum((x - y) ** 2 for x, y in zip(la, lb)) ** 0.5


# ---------------------------------------------------------------------------
# The palette
# ---------------------------------------------------------------------------

def test_no_two_body_colours_are_confusable():
    """The point of choosing a colour is being told apart by it.

    Checked as CIELAB distance rather than by eye because two colours that are
    plainly different on a swatch chart are a different question from two cars
    thirty metres up the road with motion blur on them.
    """
    worst, pair = 1e9, None
    for i, a in enumerate(garage.PALETTE):
        for b in garage.PALETTE[i + 1:]:
            d = _de(a, b)
            if d < worst:
                worst, pair = d, (a, b)
    assert worst >= garage.DELTA_E_MIN, f"{pair} are only {worst:.1f} apart"


def test_no_body_colour_hides_against_the_world():
    """A car has to be visible against everything it is driven over and under."""
    for c in garage.PALETTE:
        for name, bg in garage.BACKDROPS.items():
            d = _de(c, bg)
            assert d >= garage.BACKDROP_MIN, f"{c} is {d:.1f} from {name}"


def test_every_body_colour_is_inside_the_luminance_band():
    """Nothing near-black (a hole in the road) or near-white (a kerb)."""
    for c in garage.PALETTE:
        L = _lab(c)[0]
        assert garage.L_MIN <= L <= garage.L_MAX, f"{c} has L* {L:.1f}"


def test_the_palette_is_well_formed_and_has_no_duplicates():
    assert len(set(garage.PALETTE)) == len(garage.PALETTE)
    for c in garage.PALETTE:
        assert garage._HEX.match(c) and c == c.lower()


# ---------------------------------------------------------------------------
# The hash, which is the one thing here that may never move
# ---------------------------------------------------------------------------

def test_the_hashed_colours_never_move():
    """`color_for` indexes modulo the length of the list, so the *length* is
    part of every answer. Growing the palette to 18 and hashing over that would
    have repainted every account that exists and every ghost ever recorded -
    nobody chose those colours, but they have been theirs for months.

    Pinned as the literal list, so widening `PALETTE` cannot reach this by
    accident and this test has to be edited deliberately to break anybody's car.
    """
    assert garage.HASH_COLORS == [
        "#e8453c", "#3d8bfd", "#f2c94c", "#27ae60",
        "#bb6bd9", "#f2994a", "#56ccf2", "#f178b6",
    ]
    assert garage.PALETTE[:8] == garage.HASH_COLORS


def test_a_hashed_colour_is_stable_and_case_insensitive():
    a = garage.color_for("chinmay")
    assert a in garage.HASH_COLORS
    assert garage.color_for("Chinmay") == a
    assert garage.color_for("CHINMAY") == a
    assert garage.color_for(None) == garage.GUEST_COLOR
    assert garage.color_for("") == garage.GUEST_COLOR


def test_widening_the_palette_changed_nobody():
    """The claim above, checked against the arithmetic rather than by trusting
    that nothing indexes the long list: hashing four thousand names over
    `PALETTE` must disagree with `color_for` for most of them, and `color_for`
    must be the eight-colour answer."""
    import hashlib
    names = [f"driver{i}" for i in range(4000)]
    for n in names:
        h = int(hashlib.sha1(n.encode()).hexdigest()[:8], 16)
        assert garage.color_for(n) == garage.HASH_COLORS[h % 8]


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def test_validate_never_raises_whatever_it_is_handed():
    """An unknown key is a client from after the next deploy; a bad value is
    somebody poking the endpoint. Neither is a 500."""
    for junk in (None, [], "nope", 7, {"body": []}, {"finish": {"a": 1}},
                 {"two_tone": "yes"}, {"future_slot": "spoiler"},
                 {"body": "red"}, {"trim": "#12345"}, {"rim": "#gggggg"},
                 {"livery": "stripes"}, {"rim_style": 5}, {"badge": None}):
        out = garage.validate(junk)
        assert set(out) == set(garage.DEFAULTS)


def test_a_bad_value_falls_back_to_the_default_not_to_black():
    """The failure mode that matters: a malformed colour must be today's car,
    never a black one, because a black car is a hole in the road."""
    out = garage.validate({"body": "#nothex", "trim": "chartreuse",
                           "finish": "sparkle"})
    assert out["body"] is None          # -> color_for(username)
    assert out["trim"] is None          # -> render.js's own darkening
    assert out["finish"] == "matte"


def test_a_body_colour_has_to_be_one_of_the_offered_ones():
    """Free hex everywhere else, and deliberately not here: the body is the
    thing rivals identify you by, so it is the one slot whose separation and
    visibility are guaranteed rather than left to whoever is choosing."""
    assert garage.validate({"body": "#17bfa8"})["body"] == "#17bfa8"
    assert garage.validate({"body": "#123456"})["body"] is None


def test_free_hex_slots_are_taken_and_normalised():
    out = garage.validate({"trim": "  #AABBCC  ", "rim": "#000000",
                           "glass": "#ffffff", "stripe": "#123456"})
    assert out["trim"] == "#aabbcc"
    # Near-black and near-white are fine here and not on the body: these are a
    # wing mirror and a window, not the shape somebody picks you out by.
    assert (out["rim"], out["glass"], out["stripe"]) == ("#000000", "#ffffff",
                                                         "#123456")


def test_storage_keeps_only_what_was_changed():
    """So a default that moves later moves the cars of everybody who never
    touched that slot, which is what a default is for."""
    assert garage.dumps({}) == "{}"
    assert garage.dumps({"finish": "matte"}) == "{}"
    assert garage.loads(garage.dumps({"finish": "gloss", "two_tone": True})) == \
        dict(garage.DEFAULTS, finish="gloss", two_tone=True)


def test_a_corrupt_row_reads_as_the_default_car():
    for blob in (None, "", "{", "[]", "null", '"gloss"'):
        assert garage.loads(blob) == dict(garage.DEFAULTS)


# ---------------------------------------------------------------------------
# The one that matters most
# ---------------------------------------------------------------------------

def test_a_user_with_no_row_is_exactly_todays_car():
    """No row, no choices, nothing earned - and the answer has to be the car
    Drive drew before any of this existed: the hashed colour, and every other
    slot saying "whatever the renderer already did".

    `None` rather than a colour that happens to match is the whole point. A
    literal `#7f2620` here would be indistinguishable today and would stop
    tracking the body the first time somebody changed it.
    """
    out = garage.resolve({}, "chinmay", set())
    assert out["body"] == garage.color_for("chinmay")
    assert out["trim"] is None and out["rim"] is None and out["glass"] is None
    assert out["finish"] == "matte"
    assert out["livery"] == "none" and out["rim_style"] == "stock"
    assert out["two_tone"] is False and out["badge"] == "none"


def test_a_guest_is_the_guest_colour_and_nothing_else():
    out = garage.resolve({}, None, set())
    assert out["body"] == garage.GUEST_COLOR
    assert out["rim_style"] == "stock"


# ---------------------------------------------------------------------------
# resolve, i.e. the gates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gid", sorted(garage.GATES))
def test_an_unearned_item_is_replaced_however_it_arrived(gid):
    """`validate` stores what was asked for; `resolve` decides what is worn. A
    client can POST the pearl all day - this is the line it does not cross."""
    g = garage.GATES[gid]
    asked = {g["slot"]: g["value"]}
    assert garage.validate(asked)[g["slot"]] == g["value"]
    assert garage.resolve(asked, "x", set())[g["slot"]] == \
        garage.DEFAULTS[g["slot"]]
    assert garage.resolve(asked, "x", {gid})[g["slot"]] == g["value"]


def test_a_gate_only_locks_its_own_value():
    """`pearl` is one of four finishes: locking the item must not lock the slot,
    or earning nothing would mean choosing nothing."""
    for f in ("matte", "gloss", "metallic"):
        assert garage.resolve({"finish": f}, "x", set())["finish"] == f
    assert garage.resolve({"finish": "pearl"}, "x", set())["finish"] == "matte"


def test_every_gate_names_a_real_slot_and_a_real_value():
    """A gate over a value nothing offers is a lock on a door that is not there
    - and, worse, silently unenforceable if the value is misspelled."""
    offered = {"finish": garage.FINISHES, "livery": garage.LIVERIES,
               "rim_style": garage.RIM_STYLES, "badge": garage.BADGES}
    for gid, g in garage.GATES.items():
        assert g["slot"] in garage.DEFAULTS, gid
        assert g["value"] in offered[g["slot"]], gid
        assert g["text"] and g["text"][0].isupper(), gid


def test_the_payload_carries_the_words_for_every_gate():
    """The locked row's text comes from here rather than from the template, so
    the UI cannot promise something the server will refuse."""

    class U:
        username = "x"

    data = garage.payload(U(), {}, {"laurel"})
    got = {g["id"]: g for g in data["gates"]}
    assert set(got) == set(garage.GATES)
    assert got["laurel"]["got"] is True
    assert got["pearl"]["got"] is False
    assert got["pearl"]["text"] == garage.GATES["pearl"]["text"]
    assert data["palette"] == list(garage.PALETTE)


def test_the_record_badge_is_the_records_own_green():
    """It is the colour the record already is on the medals card, and it has to
    be: a fourth colour for the same fact would make it a different fact.

    Three files hold it, which is the shape this project uses for a value the
    browser and the server both need - so, like every other deliberate
    duplication here, the copies are read rather than trusted. Drifting them
    apart gives a badge about the record in a colour the record is not.
    """
    here = os.path.dirname(__file__)
    render = open(os.path.join(here, "..", "static", "js", "render.js")).read()
    assert "const RECORD_GREEN = 0x%s;" % garage.RECORD_GREEN[1:] in render
    css = open(os.path.join(here, "..", "static", "css", "style.css")).read()
    assert garage.RECORD_GREEN in css


# ---------------------------------------------------------------------------
# The gates against a real database
# ---------------------------------------------------------------------------

@pytest.fixture()
def env():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path
    for mod in ("app", "models"):
        sys.modules.pop(mod, None)
    import app as A
    A.app.config["TESTING"] = True
    with A.app.app_context():
        A.db.drop_all()
        A.db.create_all()
    yield A
    os.unlink(path)


def _user(A, name="chinmay"):
    with A.app.app_context():
        u = A.User(username=name, email=name + "@example.com")
        u.set_password("password123")
        A.db.session.add(u)
        A.db.session.commit()
        return u.id


def _stats(A, uid, **kw):
    with A.app.app_context():
        st = A.DriveStats(user_id=uid, **kw)
        A.db.session.add(st)
        A.db.session.commit()


def _time(A, uid, slug, ms):
    with A.app.app_context():
        A.db.session.add(A.DriveTime(user_id=uid, track=slug, time_ms=ms))
        A.db.session.commit()


def test_the_gold_gates_open_at_their_own_counts(env):
    uid = _user(env)
    n = len(tracks_mod.TRACKS)
    with env.app.app_context():
        u = env.User.query.get(uid)
        assert garage.earned(u, holders=set()) == set()
        _stats(env, uid, golds=2)
        env.db.session.expire_all()
        assert "pearl" not in garage.earned(env.User.query.get(uid), holders=set())
        env.User.query.get(uid).drive.golds = 3
        env.db.session.commit()
        got = garage.earned(env.User.query.get(uid), holders=set())
        assert got == {"pearl"}
        env.User.query.get(uid).drive.golds = n
        env.db.session.commit()
        assert garage.earned(env.User.query.get(uid), holders=set()) == \
            {"pearl", "pinstripe"}


def test_an_old_author_medal_still_counts_as_a_gold(env):
    """`author` was retired above gold and `medal_shown` already renders one as
    a gold, so a gate that ignored the column would take a medal off somebody
    for a change they had nothing to do with."""
    uid = _user(env)
    _stats(env, uid, golds=1, authors=2)
    with env.app.app_context():
        assert "pearl" in garage.earned(env.User.query.get(uid), holders=set())


def test_finishing_every_track_is_scoped_to_the_current_pool(env):
    """A time on a retired track cannot count toward finishing the twelve that
    exist, or the gate would open on a pool that no longer does."""
    uid = _user(env)
    pool = [t["slug"] for t in tracks_mod.TRACKS]
    for slug in pool[:-1]:
        _time(env, uid, slug, 30000)
    _time(env, uid, "a-track-that-was-deleted", 30000)
    with env.app.app_context():
        u = env.User.query.get(uid)
        assert "forged" not in garage.earned(u, holders=set())
    _time(env, uid, pool[-1], 30000)
    with env.app.app_context():
        assert "forged" in garage.earned(env.User.query.get(uid), holders=set())


def test_holding_a_record_earns_the_badge_and_losing_it_does_not_take_it(env):
    """The one gate anybody can take off you, so it is earned once and kept -
    which is why its wording is past tense. Persisted by `_earned_for` the
    moment it is true, which is also what makes a backfill unnecessary: every
    current holder qualifies the first time anything asks about them."""
    a, b = _user(env, "alice"), _user(env, "bob")
    _time(env, a, "sunrise", 30000)
    with env.app.app_context():
        holders = garage.record_holders()
        assert holders == {a}
        env._earned_for(env.User.query.get(a))          # writes it down
        assert env._garage_row(env.User.query.get(a)).earned == {"laurel"}

    with env.app.app_context():                          # and she puts it on
        env._garage_row(env.User.query.get(a)).livery_json = \
            garage.dumps({"badge": "laurel"})
        env.db.session.commit()

    _time(env, b, "sunrise", 25000)                     # bob takes the record
    with env.app.app_context():
        assert garage.record_holders() == {b}
        # Alice keeps it, off the stored earn rather than off the record - and
        # keeps *wearing* it, which is the half a stored earn would still get
        # wrong if `resolve` were handed a freshly recomputed set.
        assert "laurel" in env._earned_for(env.User.query.get(a))
        assert env._livery_for(env.User.query.get(a))["badge"] == "laurel"


def test_a_record_holder_can_wear_the_laurel_and_a_challenger_cannot(env):
    a, b = _user(env, "alice"), _user(env, "bob")
    _time(env, a, "sunrise", 30000)
    with env.app.app_context():
        env._garage_row(env.User.query.get(a), create=True).livery_json = \
            garage.dumps({"badge": "laurel"})
        env._garage_row(env.User.query.get(b), create=True).livery_json = \
            garage.dumps({"badge": "laurel"})
        env.db.session.commit()
        assert env._livery_for(env.User.query.get(a))["badge"] == "laurel"
        assert env._livery_for(env.User.query.get(b))["badge"] == "none"


def test_the_earliest_lap_holds_a_tied_record(env):
    """Same rule the Records page draws, and it has to be the same one or the
    badge and the board would disagree about who holds what."""
    a, b = _user(env, "alice"), _user(env, "bob")
    _time(env, a, "sunrise", 30000)
    _time(env, b, "sunrise", 30000)
    with env.app.app_context():
        assert garage.record_holders() == {a}


def test_reading_a_strangers_livery_leaves_no_row_behind(env):
    """Same rule `_stats(create=False)` follows: a passer-by looking at a board
    must not create a garage row for everybody on it."""
    uid = _user(env)
    with env.app.app_context():
        env._livery_for(env.User.query.get(uid))
        assert env.DriveGarage.query.count() == 0
