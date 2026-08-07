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

# Every colour a car may be *wearing*, which is the offered ten plus the eight the
# palette dropped: a retired colour is still on the road, so every rule below has
# to keep holding for it. Checking `PALETTE` alone would let a retired colour drift
# into being invisible against snow with nobody noticing, on a car that exists.
def _worn():
    return sorted(garage.BODY_OK)


def test_no_two_body_colours_are_confusable():
    """The point of choosing a colour is being told apart by it.

    Checked as CIELAB distance rather than by eye because two colours that are
    plainly different on a swatch chart are a different question from two cars
    thirty metres up the road with motion blur on them.
    """
    worn = _worn()
    worst, pair = 1e9, None
    for i, a in enumerate(worn):
        for b in worn[i + 1:]:
            d = _de(a, b)
            if d < worst:
                worst, pair = d, (a, b)
    assert worst >= garage.DELTA_E_MIN, f"{pair} are only {worst:.1f} apart"


def test_no_body_colour_hides_against_the_world():
    """A car has to be visible against everything it is driven over and under."""
    for c in _worn():
        for name, bg in garage.BACKDROPS.items():
            d = _de(c, bg)
            assert d >= garage.BACKDROP_MIN, f"{c} is {d:.1f} from {name}"


def test_every_body_colour_is_inside_the_luminance_band():
    """Nothing near-black (a hole in the road) or near-white (a kerb)."""
    for c in _worn():
        L = _lab(c)[0]
        assert garage.L_MIN <= L <= garage.L_MAX, f"{c} has L* {L:.1f}"


def test_the_palette_is_well_formed_and_has_no_duplicates():
    assert len(set(garage.PALETTE)) == len(garage.PALETTE)
    assert not (set(garage.PALETTE) & set(garage.RETIRED)), "offered and retired"
    for c in _worn():
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
                 {"future_slot": "spoiler"},
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


# ---------------------------------------------------------------------------
# What the detail slots offer, which is not what the body offers
# ---------------------------------------------------------------------------

def test_a_retired_body_colour_is_still_worn_by_whoever_chose_it():
    """The palette went from eighteen to ten so a row fits on one line, and this is
    the half of that which matters: **dropping a colour from the offered list must
    not repaint the car of anybody wearing it.** `validate` checks `BODY_OK`, so a
    retired colour round-trips; it is simply no longer suggested."""
    for c in garage.RETIRED:
        assert c not in garage.PALETTE, c
        assert garage.validate({"body": c})["body"] == c, c
    # And a colour that was never offered at all is still refused.
    assert garage.validate({"body": "#123456"})["body"] is None


def test_every_swatch_row_fits_on_one_line():
    """Ten is the bar, and it is a layout claim made executable: eighteen and
    twenty-four wrapped to two rows, which reads as a paint chart rather than as a
    choice - and made the options bar taller on some tabs than others, so switching
    tabs walked the car up and down the screen behind it."""
    for name, colours in list(garage.SWATCHES.items()) + [("body", garage.PALETTE)]:
        assert len(colours) <= 10, "%s offers %d" % (name, len(colours))


def test_every_free_hex_slot_has_swatches_of_its_own():
    """Each of the four is a different question, and they all used to be answered
    with the body's eighteen. `FREE_HEX` is the list of slots that take any hex, so
    it is also the list that needs somewhere to offer *from*."""
    assert set(garage.SWATCHES) == set(garage.FREE_HEX)
    for slot, colours in garage.SWATCHES.items():
        assert colours, slot
        assert len(set(colours)) == len(colours), "%s repeats a colour" % slot
        for c in colours:
            assert garage._HEX.match(c) and c == c.lower(), (slot, c)


def test_white_and_black_are_offered_where_a_car_may_not_be_painted_them():
    """The point of splitting the lists. The body is held to a luminance band and
    a distance from kerbs and snow, because it is the shape somebody picks you out
    by at thirty metres. A stripe is not that thing, and a white stripe is the most
    ordinary stripe there is - there was no white anywhere in the garage."""
    for slot in ("trim", "stripe", "rim"):
        assert "#ffffff" in garage.SWATCHES[slot], slot
        assert "#101216" in garage.SWATCHES[slot], slot
    # And the body still refuses both, by the rules two sections up.
    assert garage.validate({"body": "#ffffff"})["body"] is None


def test_glass_is_offered_glass_colours_and_nothing_else():
    """The one list that *replaces* the palette rather than extending it. Glass is
    dark and neutral or it is not glass, so eighteen body colours here were
    eighteen wrong answers - the tint could be pink."""
    glass = garage.SWATCHES["glass"]
    assert not (set(glass) & set(garage.PALETTE)), "a body colour is on the glass"
    # Every one of them is dark: a window you cannot see out of is still a window,
    # a bright one is a hole. Measured, because "looks like glass" is not checkable.
    for c in glass:
        assert _lab(c)[0] <= 62.0, "%s is too light to be glass (L* %.1f)" % (
            c, _lab(c)[0])
    # Including the tint render.js falls back to when nobody has chosen, so the
    # chip for today's car is in the row rather than reading as a custom colour.
    assert "#2b3240" in glass


def test_the_swatches_reach_the_page():
    """They are a shortcut for the UI and not a rule, but a shortcut nobody is
    sent is no shortcut. `palette` stays exactly the body's list beside them."""
    data = garage.payload(None, {}, set())
    assert data["swatches"]["glass"] == list(garage.SWATCHES["glass"])
    assert data["palette"] == list(garage.PALETTE)
    assert "#ffffff" not in data["palette"]


def test_a_swatch_is_a_shortcut_and_not_a_rule():
    """`validate` is unchanged: these slots take any hex, and the picker is right
    there. Offering a list must not quietly become enforcing one, or the custom
    colour every one of these slots supports would stop round-tripping."""
    off_list = "#7f3d19"
    assert off_list not in garage.SWATCHES["trim"]
    assert garage.validate({"trim": off_list})["trim"] == off_list


def test_storage_keeps_only_what_was_changed():
    """So a default that moves later moves the cars of everybody who never
    touched that slot, which is what a default is for."""
    assert garage.dumps({}) == "{}"
    assert garage.dumps({"finish": "matte"}) == "{}"
    assert garage.loads(garage.dumps({"finish": "gloss", "roof": "#101216"})) == \
        dict(garage.DEFAULTS, finish="gloss", roof="#101216")


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
    assert out["roof"] is None and out["badge"] == "none"
    assert out["badge_color"] is None


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
    """`shield` is one of nine badges: locking the item must not lock the slot, or
    earning nothing would mean choosing nothing.

    There are no gated *finishes* any more - the pearl gate moved to a badge when
    metallic and pearl went - so every finish is free and the slot to check is the
    badge."""
    for f in garage.FINISHES:
        assert garage.resolve({"finish": f}, "x", set())["finish"] == f
    assert garage.resolve({"badge": "shield"}, "x", set())["badge"] == "none"
    assert garage.resolve({"badge": "none"}, "x", set())["badge"] == "none"


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
    assert got["shield"]["got"] is False
    assert got["shield"]["text"] == garage.GATES["shield"]["text"]
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
        assert garage.earned(u, holders={}) == set()
        _stats(env, uid, golds=2)
        env.db.session.expire_all()
        assert "shield" not in garage.earned(env.User.query.get(uid), holders={})
        env.User.query.get(uid).drive.golds = 3
        env.db.session.commit()
        got = garage.earned(env.User.query.get(uid), holders={})
        assert got == {"shield"}
        env.User.query.get(uid).drive.golds = n
        env.db.session.commit()
        # `sunburst` on purpose: it shares `pinstripe`'s condition, because a gold
        # on every track is the thing the badge was asked for and two items are
        # allowed to want the same achievement.
        assert garage.earned(env.User.query.get(uid), holders={}) == \
            {"shield", "pinstripe", "sunburst"}


def test_an_old_author_medal_still_counts_as_a_gold(env):
    """`author` was retired above gold and `medal_shown` already renders one as
    a gold, so a gate that ignored the column would take a medal off somebody
    for a change they had nothing to do with."""
    uid = _user(env)
    _stats(env, uid, golds=1, authors=2)
    with env.app.app_context():
        assert "shield" in garage.earned(env.User.query.get(uid), holders={})


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
        assert "forged" not in garage.earned(u, holders={})
    _time(env, uid, pool[-1], 30000)
    with env.app.app_context():
        assert "forged" in garage.earned(env.User.query.get(uid), holders={})


def test_holding_a_record_earns_the_badge_and_losing_it_does_not_take_it(env):
    """The one gate anybody can take off you, so it is earned once and kept -
    which is why its wording is past tense. Persisted by `_earned_for` the
    moment it is true, which is also what makes a backfill unnecessary: every
    current holder qualifies the first time anything asks about them."""
    a, b = _user(env, "alice"), _user(env, "bob")
    _time(env, a, "sunrise", 30000)
    with env.app.app_context():
        holders = garage.records_held()
        assert holders == {a: 1}
        env._earned_for(env.User.query.get(a))          # writes it down
        assert env._garage_row(env.User.query.get(a)).earned == {"laurel"}

    with env.app.app_context():                          # and she puts it on
        env._garage_row(env.User.query.get(a)).livery_json = \
            garage.dumps({"badge": "laurel"})
        env.db.session.commit()

    _time(env, b, "sunrise", 25000)                     # bob takes the record
    with env.app.app_context():
        assert garage.records_held() == {b: 1}
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
        assert garage.records_held() == {a: 1}


def test_reading_a_strangers_livery_leaves_no_row_behind(env):
    """Same rule `_stats(create=False)` follows: a passer-by looking at a board
    must not create a garage row for everybody on it."""
    uid = _user(env)
    with env.app.app_context():
        env._livery_for(env.User.query.get(uid))
        assert env.DriveGarage.query.count() == 0


# ---------------------------------------------------------------------------
# Progress, for the line that says what is left to earn
# ---------------------------------------------------------------------------

def test_the_payload_still_works_without_progress():
    """`prog` is optional, and that is load-bearing rather than lazy: `payload`
    is called here against a user with no database behind it, and `progress`
    runs two queries. Made unconditional it would turn every caller into one
    that needs a session."""

    class U:
        username = "x"

    data = garage.payload(U(), {}, set())
    assert {g["id"] for g in data["gates"]} == set(garage.GATES)
    assert all(g["need"] == 0 for g in data["gates"]), "no numbers, no lies"


def test_progress_counts_toward_each_gate(env):
    uid = _user(env)
    n = len(tracks_mod.TRACKS)
    _stats(env, uid, golds=4)
    pool = [t["slug"] for t in tracks_mod.TRACKS]
    for slug in pool[:9]:
        _time(env, uid, slug, 30000)
    with env.app.app_context():
        p = garage.progress(env.User.query.get(uid), holders={})
        # Pearl is already earned, so it reads full rather than 4/3 - a bar past
        # its own end is a bar somebody has to explain.
        assert p["shield"] == (3, 3)
        assert p["pinstripe"] == (4, n)
        assert p["forged"] == (9, n)
        assert p["laurel"] == (0, 1)


def test_the_record_badge_has_no_count_worth_showing(env):
    """It is a thing you have done or have not, so it is 0 or 1 out of 1 - and
    the garage hides a `need` of 1, because "0/1 records" is a worse sentence
    than the text already on the chip."""
    uid = _user(env)
    _time(env, uid, "sunrise", 30000)
    with env.app.app_context():
        assert garage.progress(env.User.query.get(uid))["laurel"] == (1, 1)


def test_progress_and_the_gate_agree(env):
    """The count and the check are built from the same helpers, so a gate can
    never read `12/12` next to a chip that is still locked."""
    uid = _user(env)
    n = len(tracks_mod.TRACKS)
    _stats(env, uid, golds=n)
    with env.app.app_context():
        u = env.User.query.get(uid)
        got = garage.earned(u, holders={})
        prog = garage.progress(u, holders={})
        for gid in garage.GATES:
            have, need = prog[gid]
            assert (have >= need) == (gid in got), gid


def test_progress_of_a_stranger_is_nothing(env):
    assert garage.progress(None) == {}
