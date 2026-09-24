"""Items: who may take one, what a shell does, and who gets told.

The room owns the queue and the shells for the reason in `app.py`: a pose is
one browser's opinion and can be wrong by a metre without anybody minding, but
an item is a discrete shared event - two clients rolling their own result, or
each consuming the same box, disagree permanently.

So what is tested here is the server's half, which is all of the half that has
to be right: the claim rule (`_claim_box`), where a fired shell goes and what
it hits (`_fire`, `_tick_shots`), and the phase gate that keeps qualifying
clean. The browser's half is a shove on a car, which `item_hit` announces and
`physics.js` already knows how to do.

The live room is plain dicts, so it is built here directly rather than driven
through a socket - the same shape `test_race.py` uses and for the same reason.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from conftest import boot_app, close_app        # noqa: E402


@pytest.fixture()
def A():
    mod, path = boot_app()
    yield mod
    mod._rooms.clear()
    close_app(path)


def _room(A, phase="racing"):
    r = A._room("ITEM")
    r["phase"] = phase
    return r


def _car(A, r, pid, at=(0.0, 0.0, 0.0), cp=9, facing=(0.0, 0.0, 0.0, 1.0)):
    c = A._car(r, pid)
    c["p"] = list(at)
    c["q"] = list(facing)
    c["cp"] = cp
    c["ts"] = A._now_ms()
    return c


# ---------------------------------------------------------------------------
# The box
# ---------------------------------------------------------------------------

@pytest.fixture()
def boxes(A, monkeypatch):
    """Two boxes, a long way apart, in place of a track's own."""
    out = [[0.0, 0.0, 0.0], [500.0, 0.0, 0.0]]
    monkeypatch.setattr(A, "_boxes", lambda r: out)
    return out


def test_a_box_fills_one_slot(A, boxes):
    r = _room(A)
    _car(A, r, "a")
    assert A._claim_box(r, "a", 0) in A.RACE_ITEMS
    assert len(A._item_queue(r, "a")) == 1


def test_a_box_is_the_rooms_and_not_the_players(A, boxes):
    """The whole change: one car through it and it is gone for everybody."""
    r = _room(A)
    _car(A, r, "a")
    _car(A, r, "b")
    assert A._claim_box(r, "a", 0)
    assert A._claim_box(r, "b", 0) is None, "the second car got the same box"
    assert A._item_queue(r, "b") == []


def test_the_box_comes_back(A, boxes):
    r = _room(A)
    _car(A, r, "a")
    now = A._now_ms()
    A._claim_box(r, "a", 0, now)
    A._item_queue(r, "a").clear()
    assert A._claim_box(r, "a", 0, now + A.BOX_RESPAWN_MS - 50) is None
    assert A._claim_box(r, "a", 0, now + A.BOX_RESPAWN_MS + 1) in A.RACE_ITEMS


def test_a_box_across_the_track_is_not_yours(A, boxes):
    """The pose is not a scoring authority, but it bounds what can be claimed."""
    r = _room(A)
    _car(A, r, "a")                      # at the origin, box 1 is 500 away
    assert A._claim_box(r, "a", 1) is None
    assert A._item_queue(r, "a") == []


def test_a_box_that_does_not_exist_is_not_a_box(A, boxes):
    r = _room(A)
    _car(A, r, "a")
    assert A._claim_box(r, "a", 99) is None
    assert A._claim_box(r, "a", -1) is None


def test_two_is_the_cap(A, boxes):
    r = _room(A)
    _car(A, r, "a")
    now = A._now_ms()
    for k in range(4):
        A._claim_box(r, "a", 0, now + k * (A.BOX_RESPAWN_MS + 1))
    assert len(A._item_queue(r, "a")) == A.POWERUP_CAP


def test_a_full_queue_leaves_the_box_up(A, boxes):
    """Turned away with both hands full is not the same as having taken it -
    and now that it is everybody's box, the car behind wants it there."""
    r = _room(A)
    _car(A, r, "a")
    _car(A, r, "b")
    now = A._now_ms()
    A._claim_box(r, "a", 0, now)
    A._item_queue(r, "a").extend(["red", "red"])       # both hands full
    A._claim_box(r, "a", 0, now + A.BOX_RESPAWN_MS + 1)
    assert A._claim_box(r, "b", 0, now + A.BOX_RESPAWN_MS + 2) in A.RACE_ITEMS


def test_practice_has_no_blue_shell_or_star(A):
    """Nothing to be last in, so the two items that exist to fix that are out."""
    assert "blue" not in A.PRACTICE_ITEMS and "star" not in A.PRACTICE_ITEMS
    assert set(A.PRACTICE_ITEMS) < set(A.RACE_ITEMS)


# ---------------------------------------------------------------------------
# Where the boxes are
# ---------------------------------------------------------------------------

def _line(n=200, hw=6.5):
    return [{"p": [i * 3.5, 0.0, 0.0], "n": [0.0, 1.0, 0.0],
             "lat": [0.0, 0.0, 1.0], "hw": hw} for i in range(n)]


def test_a_row_of_boxes_every_nine_seconds_of_the_lap(A):
    """Not one per checkpoint: a checkpoint is where the *track* wants a gate,
    which is three on a short lap and none down a long straight."""
    for ideal, rows in ((5.0, 1), (9.0, 1), (20.0, 2), (35.0, 4), (88.0, 10)):
        got = A._boxes_for({"line": _line(), "ideal": ideal})
        assert len(got) == rows * len(A.BOX_LANES), ideal


def test_a_row_lies_across_the_road_and_above_it(A):
    got = A._boxes_for({"line": _line(), "ideal": 35.0})
    row = got[:3]
    assert [b[1] for b in row] == [A.BOX_HEIGHT] * 3, "not lifted off the road"
    assert row[0][2] < row[1][2] < row[2][2], "not spread across the road"
    assert abs(row[1][2]) < 1e-9, "the middle one is not on the line"


def test_a_narrow_road_gets_one_box_and_not_three(A):
    """Three across a four-unit shoulder is three boxes in the scenery."""
    got = A._boxes_for({"line": _line(hw=3.0), "ideal": 35.0})
    assert len(got) == 4 and all(abs(b[2]) < 1e-9 for b in got)


def test_no_box_sits_on_the_start_line_or_the_flag(A):
    got = A._boxes_for({"line": _line(), "ideal": 35.0})
    xs = [b[0] for b in got]
    assert min(xs) > 3.5 and max(xs) < 199 * 3.5


def test_a_track_with_no_ribbon_has_no_boxes(A):
    assert A._boxes_for({"line": [], "ideal": 30.0}) == []


# ---------------------------------------------------------------------------
# The phase gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase,live", [("free", True), ("racing", True),
                                        ("qualifying", False),
                                        ("countdown", False), ("results", False)])
def test_items_are_live_in_the_two_phases_contact_is(A, phase, live):
    r = _room(A, phase)
    assert A._powerups_live(r) is live


def test_the_switch_turns_them_off(A):
    r = _room(A, "racing")
    r["settings"]["powerups"] = False
    assert A._powerups_live(r) is False


def test_powerups_is_a_room_setting_the_host_can_set(A):
    assert "powerups" in A.ROOM_DEFAULTS


# ---------------------------------------------------------------------------
# Shells and bananas
# ---------------------------------------------------------------------------

def test_everything_leaves_the_nose_and_backwards_is_the_only_exception(A, bend):
    """One rule for every item: a press throws forwards, `back` throws behind.
    The banana used to be the other way round on its own, which made the one
    control on the pad mean the opposite of itself for one item."""
    r = _room(A)
    _car(A, r, "a")                      # identity quaternion: forward is -Z
    A._fire(r, "a", "green")
    A._fire(r, "a", "banana")
    A._fire(r, "a", "bomb")
    shell, banana, bomb = r["shots"]
    assert shell["p"][2] < 0 and banana["p"][2] < 0 and bomb["p"][2] < 0
    assert shell["v"][2] < 0 and banana["v"][2] < 0 and bomb["v"][2] < 0


def test_a_bomb_is_thrown_past_the_car_that_threw_it(A, bend):
    """`BOMB_SPEED` is 38 and a car does 50, so a bomb thrown at speed used to
    be left behind by the thrower and go off under their own wheels."""
    r = _room(A)
    c = _car(A, r, "a")
    c["v"] = [0.0, 0.0, -48.0]                # flat out, forward is -Z
    A._fire(r, "a", "bomb")
    assert r["shots"][0]["v"][2] < -48.0 - 10


def test_a_bomb_thrown_backwards_is_just_lobbed(A, bend):
    """Behind you it is separating from you already - adding your own speed to
    it would plant it on your own back bumper."""
    r = _room(A)
    c = _car(A, r, "a")
    c["v"] = [0.0, 0.0, -48.0]
    A._fire(r, "a", "bomb", back=True)
    assert r["shots"][0]["v"][2] == A.BOMB_SPEED


def test_a_banana_thrown_backwards_is_a_banana_dropped(A, bend):
    """It is the one item whose backwards is *standing still*: dropping one on
    the road behind you is the whole of what a banana is for."""
    r = _room(A)
    _car(A, r, "a")
    A._fire(r, "a", "banana", back=True)
    A._fire(r, "a", "green", back=True)
    banana, shell = r["shots"]
    assert banana["p"][2] > 0 and banana["v"] == [0.0, 0.0, 0.0]
    assert shell["p"][2] > 0 and shell["v"][2] > 0, "a shell thrown back still flies"


def test_a_shell_thrown_backwards_keeps_its_own_clock(A, bend, monkeypatch):
    """`until` asked `back`, which was the banana's flag by accident - so a
    green thrown backwards lived BANANA_MS and bounced for forty-five
    seconds."""
    r = _room(A)
    _car(A, r, "a")
    # **The clock is frozen because the assertion is about the two lifetimes,
    # not about how long two calls take.** Each `_fire` stamps `until` from its
    # own `_now_ms()`, so if the wall clock ticks between them the difference
    # comes out one millisecond off and this fails - which it did, in CI,
    # reporting -40001 where it wanted -40000. Freezing it is what the test
    # means rather than a tolerance bolted onto the comparison.
    monkeypatch.setattr(A, "_now_ms", lambda: 1_700_000_000_000)
    A._fire(r, "a", "green", back=True)
    A._fire(r, "a", "banana", back=True)
    shell, banana = r["shots"]
    assert shell["until"] - banana["until"] == A.SHELL_MS - A.BANANA_MS


def test_a_shell_hits_the_car_it_reaches(A, bend, monkeypatch):
    r = _room(A)
    # On the ribbon, which runs out along +X: the shell rides the road, so the
    # car it is going to reach has to be *on* the road.
    c = _car(A, r, "a", at=(35.0, 0.0, 0.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]          # pointing along +X
    _car(A, r, "b", at=(75.0, 0.0, 0.0))
    A._fire(r, "a", "green")
    hits = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d, **kw: hits.append((ev, d)))
    now = A._now_ms()
    for step in range(20):
        A._tick_shots(r, now + 300 + step * 50)
    assert ("item_hit", {"item": "green", "pid": "b", "owner": "a"}) in hits
    assert r["shots"] == []              # and it is spent


@pytest.mark.parametrize("item", ["green", "banana"])
def test_a_shot_never_hits_the_car_that_let_it_go(A, item, bend, monkeypatch):
    """A shell leaves three units off the nose and the hit radius is four."""
    r = _room(A)
    _car(A, r, "a", at=(35.0, 0.0, 0.0))
    A._fire(r, "a", item)
    hits = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d, **kw: hits.append((ev, d)))
    now = A._now_ms()
    for step in range(40):
        A._tick_shots(r, now + step * 50)
    assert hits == []


def test_a_shell_that_hits_nothing_gives_up(A, bend):
    r = _room(A)
    _car(A, r, "a", at=(35.0, 0.0, 0.0))
    A._fire(r, "a", "green")
    A._tick_shots(r, A._now_ms() + A.SHELL_MS + 1)
    assert r["shots"] == []


def test_a_red_shell_chases_the_car_in_front_and_not_the_one_behind(A):
    r = _room(A)
    me = _car(A, r, "a")
    me["prog"] = 100.0
    _car(A, r, "ahead")["prog"] = 140.0
    _car(A, r, "behind")["prog"] = 40.0
    assert A._shell_target(r, "a") == "ahead"


def test_a_blue_shell_goes_for_the_leader(A):
    r = _room(A)
    _car(A, r, "a")["prog"] = 10.0
    _car(A, r, "mid")["prog"] = 140.0
    _car(A, r, "lead")["prog"] = 900.0
    assert A._shell_target(r, "a", blue=True) == "lead"


def test_a_blue_shell_goes_for_the_leader_on_the_road_not_the_winner(A):
    """A finisher keeps rolling and its progress keeps climbing past the flag.

    So the moment anybody is home, every blue in the room went after a car that
    was parked on the far side of the line - most of a lap away, which the
    homing clock runs out long before, and from the seat that is a blue shell
    that simply got lost. The same rule the catch-up boost already follows:
    a car that is already home is not the one being chased.
    """
    r = _room(A)
    _car(A, r, "a")["prog"] = 10.0
    _car(A, r, "second")["prog"] = 500.0
    home = _car(A, r, "winner")
    home["prog"] = 3000.0
    home["ms"] = 61000
    assert A._shell_target(r, "a", blue=True) == "second"
    # A retirement is not a target either, and with nobody left still racing it
    # falls back rather than returning nothing - a blue has to go somewhere.
    _car(A, r, "out")["prog"] = 4000.0
    r["cars"]["out"]["dnf"] = True
    assert A._shell_target(r, "a", blue=True) == "second"


def test_out_in_front_there_is_nothing_to_aim_at(A):
    r = _room(A)
    _car(A, r, "a")["prog"] = 900.0
    _car(A, r, "b")["prog"] = 10.0
    assert A._shell_target(r, "a") is None


def test_the_shots_ride_the_pose_snapshot(A, bend):
    """A shell nobody can see is a hit out of nowhere - and it carries an id,
    because a browser has to tell this shell from the one beside it."""
    r = _room(A)
    _car(A, r, "a")
    A._fire(r, "a", "banana", back=True)          # dropped: it sits where it lands
    shots = A._snapshot(r)["shots"]
    assert shots == [["banana", 0.0, 0.0, 4.0, r["shots"][0]["id"]]]
    A._fire(r, "a", "green")
    ids = [sh[4] for sh in A._snapshot(r)["shots"]]
    assert len(set(ids)) == 2, "two shots with one id"


def test_a_new_race_starts_with_no_shells_or_items_in_it(A):
    r = _room(A)
    _car(A, r, "a")
    r.setdefault("items", {})["a"] = ["red"]
    r.setdefault("box_until", {})[0] = A._now_ms() + 5000
    A._fire(r, "a", "banana")
    A._reset_race(r)
    assert r["shots"] == [] and r["items"] == {} and r["box_until"] == {}


# ---------------------------------------------------------------------------
# Over the wire
# ---------------------------------------------------------------------------

def _seated(A, code="WIRE", phase="free"):
    """A room with one seated player, and a socket client for them."""
    with A.app.app_context():
        game = A.DriveGame(code=code, track="sunrise", status="waiting")
        A.db.session.add(game)
        A.db.session.commit()
        me = A.DrivePlayer(game_id=game.id, user_id=None, session_key="sk-i",
                           name="racer", color="#fff", seat_order=0, is_host=True)
        A.db.session.add(me)
        A.db.session.commit()
        pid = me.pid
    fc = A.app.test_client()
    with fc.session_transaction() as s:
        s["session_key"], s["guest_name"] = "sk-i", "racer"
    cl = A.socketio.test_client(A.app, flask_test_client=fc)
    cl.emit("join_room_", {"code": code})
    cl.get_received()
    r = A._room(code)
    r["phase"] = phase
    A._car(r, pid)["cp"] = 5
    return cl, r, pid


def _drain(cl):
    """Everything the client has been sent, by event name.

    One call, because `get_received` *empties* the queue - asking it twice for
    two different events throws the second one away.
    """
    out = {}
    for e in cl.get_received():
        out.setdefault(e["name"], []).append(e["args"][0])
    return out


def test_a_box_and_then_using_it_both_come_back_over_the_socket(A, monkeypatch):
    cl, r, pid = _seated(A)
    monkeypatch.setattr(A, "_boxes", lambda _r: [[0.0, 0.0, 0.0]])
    cl.emit("item_box", {"i": 0})
    got = _drain(cl)
    assert len(got["items"][-1]["slots"]) == 1
    assert got["item_box_taken"][-1]["i"] == 0
    assert got["item_box_taken"][-1]["pid"] == pid
    item = got["items"][-1]["slots"][0]

    cl.emit("use_item", {})
    got = _drain(cl)
    assert got["item_used"][-1]["pid"] == pid
    assert got["item_used"][-1]["item"] == item
    # What a box gives is random, and the boost is the one item a press does
    # not spend - it opens a window and stays in the slot. Both are the wire's
    # contract, so both are asserted rather than one being engineered away.
    if item == "boost":
        assert got["item_used"][-1]["until"], "a boost with no window"
        assert A._item_queue(r, pid) == ["boost"]
    else:
        assert got["items"][-1]["slots"] == []


def test_a_boost_is_a_window_and_every_tap_inside_it_is_another_burst(A):
    """Mario's golden mushroom: the press does not spend it, the clock does."""
    cl, r, pid = _seated(A, code="GOLD")
    A._item_queue(r, pid).append("boost")
    cl.get_received()

    cl.emit("use_item", {})
    got = _drain(cl)
    first = got["item_used"][-1]
    assert first["item"] == "boost" and first["until"], "no window on the wire"
    assert A._item_queue(r, pid) == ["boost"], "the tap spent the item"

    cl.emit("use_item", {})
    again = _drain(cl)["item_used"][-1]
    assert again["until"] == first["until"], "the second tap re-opened the window"
    assert A._item_queue(r, pid) == ["boost"]

    A._tick_items(r, A._now_ms() + A.BOOST_WINDOW_MS + 1)
    assert A._item_queue(r, pid) == [], "the window closed and left the item"
    assert _drain(cl)["items"][-1] == {"pid": pid, "slots": []}


def test_the_client_cannot_write_its_own_slots(A):
    """The only thing a browser may say is *which box*, and it is checked."""
    cl, r, pid = _seated(A)
    cl.emit("item_box", {"i": 900})        # no such box
    cl.emit("item_box", {"i": "star"})     # not a box at all
    cl.emit("item_box", {})
    cl.emit("use_item", {})                # nothing held: nothing happens
    got = _drain(cl)
    assert "items" not in got, "a made-up claim filled a slot"
    # A refusal is answered rather than ignored, because the browser has
    # already hidden the box it asked about - see `on_item_box`.
    assert [d["why"] for d in got.get("item_box_miss", [])] == ["gone"]
    assert A._item_queue(r, pid) == []


def test_qualifying_hands_out_nothing(A, monkeypatch):
    cl, r, pid = _seated(A, code="QUAL", phase="qualifying")
    monkeypatch.setattr(A, "_boxes", lambda _r: [[0.0, 0.0, 0.0]])
    cl.emit("item_box", {"i": 0})
    assert _drain(cl) == {}
    assert A._item_queue(r, pid) == []


# ---------------------------------------------------------------------------
# The bots
# ---------------------------------------------------------------------------

class _FakeWorld:
    """Stands in for `botsim.World`, which needs QuickJS and a built track."""

    def __init__(self):
        self.used = []
        self.hit_ = []

    def use(self, pid, item):
        self.used.append((pid, item))

    def hit(self, pid):
        self.hit_.append(pid)


@pytest.fixture()
def world(A, monkeypatch):
    w = _FakeWorld()
    monkeypatch.setattr(A, "_bot_world", lambda r, create=False: w)
    return w


def _bot(A, r, pid="b1", **kw):
    r.setdefault("bots", {})[pid] = "medium"
    return _car(A, r, pid, **kw)


def test_a_bot_takes_a_box_by_driving_through_it(A, boxes):
    """Same function, same reach: a bot cannot take one from further off."""
    r = _room(A)
    _bot(A, r, at=(1.0, 0.0, 0.0))
    A._tick_bot_boxes(r, A._now_ms())
    assert len(A._item_queue(r, "b1")) == 1


def test_a_bot_nowhere_near_a_box_gets_nothing(A, boxes):
    r = _room(A)
    _bot(A, r, at=(60.0, 0.0, 0.0))
    A._tick_bot_boxes(r, A._now_ms())
    assert A._item_queue(r, "b1") == []


def test_a_bot_sits_on_an_item_and_then_uses_it(A, world):
    r = _room(A)
    _bot(A, r)
    A._item_queue(r, "b1").append("shield")
    now = A._now_ms()
    A._tick_bot_items(r, now)                  # first sight: sets the clock
    A._tick_bot_items(r, now + 1)
    assert A._item_queue(r, "b1") == ["shield"], "used it the instant it collected"
    A._tick_bot_items(r, now + max(A.BOT_ITEM_WAIT) + 1)
    assert A._item_queue(r, "b1") == []
    assert world.used == [("b1", "shield")], "the bot's own car never got it"


def test_a_bot_keeps_tapping_a_boost_until_its_window_closes(A, world):
    """The item is not spent by being used, so the bot stays on it - which is
    what a person does with the same item."""
    r = _room(A)
    _bot(A, r)
    A._item_queue(r, "b1").append("boost")
    now = A._now_ms()
    A._tick_bot_items(r, now)
    now += max(A.BOT_ITEM_WAIT) + 1
    A._tick_bot_items(r, now)
    assert A._item_queue(r, "b1") == ["boost"], "a boost is not spent by a press"
    for _ in range(3):
        now += A.BOT_BOOST_TAP + 1
        A._tick_bot_items(r, now)
    assert len(world.used) >= 4, "tapped once and then sat on it"
    A._tick_items(r, now + A.BOOST_WINDOW_MS + 1)
    assert A._item_queue(r, "b1") == [], "the window closed and left the item"


def test_a_bot_holds_a_shell_it_has_nothing_to_aim_at(A, world, bend):
    r = _room(A)
    _bot(A, r)["prog"] = 900.0                 # out in front on its own
    A._item_queue(r, "b1").append("red")
    now = A._now_ms()
    A._tick_bot_items(r, now)
    A._tick_bot_items(r, now + max(A.BOT_ITEM_WAIT) + 1)
    assert A._item_queue(r, "b1") == ["red"]
    # Somebody to aim at, and the same tick fires it.
    _car(A, r, "human")["prog"] = 1200.0
    A._tick_bot_items(r, now + max(A.BOT_ITEM_WAIT) + 2)
    assert A._item_queue(r, "b1") == []
    assert r["shots"] and r["shots"][0]["target"] == "human"


def test_a_bot_does_not_fire_a_green_shell_into_qualifying(A, world):
    r = _room(A, "qualifying")
    _bot(A, r)
    A._item_queue(r, "b1").append("green")
    A._tick_bot_items(r, A._now_ms() + 10 ** 6)
    assert A._item_queue(r, "b1") == ["green"] and r["shots"] == []


def test_a_shell_that_reaches_a_bot_shoves_the_bot(A, world, bend, monkeypatch):
    """A bot has no browser to give its own car the hit, so the server does."""
    r = _room(A)
    _bot(A, r, at=(75.0, 0.0, 0.0))
    c = _car(A, r, "human", at=(35.0, 0.0, 0.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]          # pointing along the road
    A._fire(r, "human", "green")
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **kw: None)
    now = A._now_ms()
    for step in range(20):
        A._tick_shots(r, now + 300 + step * 50)
    assert world.hit_ == ["b1"]


@pytest.mark.skipif(not __import__("botsim").available(),
                    reason="needs a JS runtime")
def test_a_real_bot_world_takes_a_boost_and_a_hit(A):
    """The two calls above, through QuickJS on a real track.

    Everything else about the bots here runs against a stand-in world, which
    cannot tell a working `BotWorld.use` from a typo in one - so this is the
    test that actually reads the JS.
    """
    import botsim
    w = botsim.world("JSIT", "sunrise", create=True)
    try:
        w.add("b1", "medium", seed=3)
        now = 1000
        for _ in range(60):
            now += 33
            w.tick(0.033, [], now, "free", None)
        w.use("b1", "boost")            # one tap's worth, not the whole window
        assert w.rt.ctx.eval("WORLDS['JSIT'].get('b1').car.itemBoost") == 1.1
        w.use("b1", "shield")
        w.hit("b1")                      # spends the shield instead of spinning
        assert w.rt.ctx.eval("WORLDS['JSIT'].get('b1').car.shield") == 0
        w.hit("b1")                      # and now it lands
        assert w.rt.ctx.eval("WORLDS['JSIT'].get('b1').car.bumpSlip") > 0
        w.use("b1", "green")             # a thrown item is not the car's business
        assert w.rt.ctx.eval("WORLDS['JSIT'].get('b1').car.star") == 0
    finally:
        botsim.drop("JSIT")


# ---------------------------------------------------------------------------
# The pump
# ---------------------------------------------------------------------------

def test_a_tick_that_throws_does_not_freeze_the_room(A, monkeypatch):
    """The whole room used to stop, with every socket still connected.

    `_pump` holds its greenlet in `r["loop"]`, so a greenlet that died took
    `_ensure_pump` with it - nothing ever started another, no snapshot ever
    went out again, and every client carried on driving against cars that had
    stopped where they were.
    """
    r = _room(A)
    _car(A, r, "a")
    boom = {"n": 0}

    def _explode(room):
        boom["n"] += 1
        raise RuntimeError("bad tick")

    monkeypatch.setattr(A, "_tick_bots", _explode)
    monkeypatch.setattr(A, "_rooms", {"ITEM": r})
    sleeps = {"n": 0}

    def _sleep(_):
        sleeps["n"] += 1
        if sleeps["n"] > 3:
            r["loop_stop"] = True

    monkeypatch.setattr(A.eventlet, "sleep", _sleep)
    A._pump("ITEM")                     # returns rather than dying
    assert boom["n"] >= 3, "the pump gave up after the first bad tick"
    assert r["loop"] is None, "a stopped pump must let the next one start"


# ---------------------------------------------------------------------------
# A homing shell follows the road
# ---------------------------------------------------------------------------

def _bend():
    """A ribbon that turns ninety degrees, so 'along the road' and 'straight at
    it' are visibly different answers."""
    import math
    line = []
    for i in range(60):                       # a straight out along +X
        line.append({"p": [i * 3.5, 0.0, 0.0], "n": [0.0, 1.0, 0.0],
                     "lat": [0.0, 0.0, 1.0], "hw": 6.5})
    for k in range(1, 40):                    # then a quarter circle
        a = k * (math.pi / 2) / 40
        line.append({"p": [59 * 3.5 + math.sin(a) * 60, 0.0, 60 - math.cos(a) * 60],
                     "n": [0.0, 1.0, 0.0],
                     "lat": [math.sin(a), 0.0, math.cos(a)], "hw": 6.5})
    return {"slug": "bend", "line": line, "station": 3.5, "ideal": 30.0}


@pytest.fixture()
def bend(A, monkeypatch):
    track = _bend()
    monkeypatch.setattr(A, "_hot_track", lambda r: track)
    return track


def test_a_red_shell_is_launched_onto_the_ribbon(A, bend):
    r = _room(A)
    c = _car(A, r, "a", at=(35.0, 0.0, 2.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]          # pointing along the road
    _car(A, r, "b", at=(105.0, 0.0, 0.0))["prog"] = 200.0
    A._fire(r, "a", "red", "b")
    shot = r["shots"][0]
    # Station 10 is x=35, and it leaves five units in front of the car.
    assert "si" in shot and 10 <= shot["si"] <= 13, "not put on the road ahead"
    assert abs(shot["lat"] - 2.0) < 1.0, "not put in the lane it was fired from"


def test_a_red_shell_goes_round_the_corner_instead_of_through_it(A, bend, monkeypatch):
    """The point of the whole thing: the car it is chasing is round a bend, and
    the road is the only way there."""
    r = _room(A)
    c = _car(A, r, "a", at=(0.0, 0.0, 0.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]          # pointing along the road
    # A target on the far side of the ninety-degree turn.
    far = bend["line"][-1]["p"]
    _car(A, r, "b", at=tuple(far))["prog"] = 900.0
    A._fire(r, "a", "red", "b")
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    now = A._now_ms()
    seen = []
    for step in range(1, 240):
        A._tick_shots(r, now + step * 33)
        if r["shots"]:
            seen.append(list(r["shots"][0]["p"]))
        else:
            break
    assert seen, "the shell never moved"
    # Every point it visited is on the road: within a half width of a station.
    # The hint walks with it, which is what `nearest_station` is built for - a
    # cold hint only ever looks at the first forty stations.
    hint = 0
    for p in seen:
        d2, hint = A.runcheck.nearest_station(bend, p, hint)
        assert d2 <= 8.0 ** 2, "left the road at %s" % (p,)
    assert max(p[2] for p in seen) > 20, "never took the corner at all"


def test_a_shell_that_runs_out_of_road_gives_up(A, bend, monkeypatch):
    r = _room(A)
    _car(A, r, "a", at=tuple(bend["line"][-3]["p"]))
    A._fire(r, "a", "red", None)
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    now = A._now_ms()
    for step in range(1, 30):
        A._tick_shots(r, now + step * 33)
    assert r["shots"] == []


def test_a_green_rides_the_road_but_chases_nobody(A, bend):
    """Both kinds of shell are on the ribbon; only one of them is hunting."""
    r = _room(A)
    _car(A, r, "a", at=(35.0, 0.0, 0.0))
    _car(A, r, "b", at=(105.0, 0.0, 0.0))["prog"] = 900.0
    A._fire(r, "a", "green")
    shot = r["shots"][0]
    assert "si" in shot and shot["target"] is None
    assert "along" in shot and "across" in shot


# ---------------------------------------------------------------------------
# The bomb
# ---------------------------------------------------------------------------

def test_a_bomb_is_in_both_pools(A):
    assert "bomb" in A.PRACTICE_ITEMS and "bomb" in A.RACE_ITEMS


def test_a_bomb_lands_and_then_sits(A, monkeypatch):
    """Thrown at a place rather than at a car: it is a mine once it lands."""
    r = _room(A)
    _car(A, r, "a")
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._fire(r, "a", "bomb")
    now = A._now_ms()
    start = list(r["shots"][0]["p"])
    for step in range(1, 40):                 # up to and past where it lands
        A._tick_shots(r, now + step * 33)
    landed = list(r["shots"][0]["p"])
    assert landed != start, "never moved"
    for step in range(40, 70):
        A._tick_shots(r, now + step * 33)
    assert r["shots"][0]["p"] == landed, "still travelling after it landed"


def test_a_bomb_goes_off_on_its_own_fuse_and_catches_everyone_near_it(A, monkeypatch):
    r = _room(A)
    _car(A, r, "a")                                   # the one who threw it
    _car(A, r, "near", at=(-2.0, 0.0, -6.0))
    _car(A, r, "far", at=(90.0, 0.0, 0.0))
    seen = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d, **k: seen.append((ev, d)))
    A._fire(r, "a", "bomb")
    now = A._now_ms()
    A._tick_shots(r, now + A.BOMB_FLY_MS + A.BOMB_FUSE_MS + 1)
    hit = {d["pid"] for ev, d in seen if ev == "item_hit"}
    assert "near" in hit, "missed a car standing next to it"
    assert "far" not in hit, "caught a car on the other side of the track"
    assert any(ev == "item_blast" for ev, d in seen), "no flash and no bang"
    assert r["shots"] == [], "a bomb that goes off is still there"


def test_a_bomb_catches_the_car_that_threw_it(A, monkeypatch):
    """The whole of what makes it a bet rather than a slow shell."""
    r = _room(A)
    _car(A, r, "a")
    seen = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d, **k: seen.append((ev, d)))
    A._fire(r, "a", "bomb")
    A._blast(r, r["shots"][0], A._now_ms())
    assert {d["pid"] for ev, d in seen if ev == "item_hit"} == {"a"}


def test_a_bomb_does_not_go_off_in_the_thrower_s_face(A, monkeypatch):
    """Contact sets it off - but not contact with the car it just left."""
    r = _room(A)
    _car(A, r, "a")
    seen = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d, **k: seen.append((ev, d)))
    A._fire(r, "a", "bomb")
    A._tick_shots(r, A._now_ms() + 30)
    assert seen == [] and r["shots"], "went off on the way out"


# ---------------------------------------------------------------------------
# Thrown backwards, and bounced off the walls
# ---------------------------------------------------------------------------

def test_a_bomb_pressed_normally_actually_goes_out(A, monkeypatch):
    """It is `_spend_item` that throws things, and the bomb was not in the list
    it throws - so the item existed, made its noise and did nothing."""
    r = _room(A)
    _car(A, r, "a")
    A._item_queue(r, "a").append("bomb")
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._spend_item(r, "a")
    assert [sh["item"] for sh in r["shots"]] == ["bomb"]


@pytest.mark.parametrize("item", ["green", "red", "bomb"])
def test_the_handbrake_throws_it_out_behind_you(A, bend, monkeypatch, item):
    r = _room(A)
    _car(A, r, "a", at=(35.0, 0.0, 0.0))     # identity quaternion: forward is -Z
    _car(A, r, "b", at=(105.0, 0.0, 0.0))["prog"] = 900.0
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._item_queue(r, "a").append(item)
    A._spend_item(r, "a", back=True)
    shot = r["shots"][0]
    assert shot["p"][2] > 0, "left the car forwards"
    assert shot["target"] is None, "a shell thrown backwards still went hunting"


def test_a_banana_is_thrown_by_default_and_dropped_on_request(A, monkeypatch):
    """The same sign as every other item, through the press rather than the
    `_fire` call: holding the throttle throws it, letting go drops it."""
    r = _room(A)
    _car(A, r, "a")
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._item_queue(r, "a").extend(["banana", "banana"])
    A._spend_item(r, "a")                     # lobbed ahead
    A._spend_item(r, "a", back=True)          # dropped behind
    lobbed, dropped = r["shots"]
    assert lobbed["p"][2] < 0 and dropped["p"][2] > 0
    assert dropped["v"] == [0.0, 0.0, 0.0], "a dropped banana should sit still"


def test_a_green_shell_bounces_off_the_wall_instead_of_leaving(A, bend, monkeypatch):
    """Aimed across the road, it comes back off the far side."""
    import math
    r = _room(A)
    # Pointing about 25 degrees across the road, which on this ribbon is +Z.
    a = math.radians(25)
    c = _car(A, r, "a", at=(35.0, 0.0, 0.0))
    c["q"] = [0.0, math.sin(a / 2), 0.0, math.cos(a / 2)]
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._fire(r, "a", "green")
    shot = r["shots"][0]
    assert "across" in shot and abs(shot["across"]) > 1, "never aimed across"
    now = A._now_ms()
    sign0 = 1 if shot["across"] > 0 else -1
    lats, turned = [], False
    for step in range(1, 90):
        A._tick_shots(r, now + step * 33)
        if not r["shots"]:
            break
        live = r["shots"][0]
        lats.append(live["lat"])
        if (1 if live["across"] > 0 else -1) != sign0:
            turned = True
    assert lats, "the shell never moved"
    assert max(abs(v) for v in lats) <= 6.5, "left the road"
    assert turned, "ran into the wall and kept going"


# ---------------------------------------------------------------------------
# What a box gives depends on where you are
# ---------------------------------------------------------------------------

def _field(A, r, progs):
    for i, prog in enumerate(progs):
        _car(A, r, "p%d" % i)["prog"] = prog
    return ["p%d" % i for i in range(len(progs))]


def test_the_leader_never_draws_a_star_or_a_blue(A):
    """A leader who could draw one has nothing to fear and nothing to catch."""
    r = _room(A, "racing")
    pids = _field(A, r, [900.0, 600.0, 300.0, 10.0])
    got = {A._roll_item(r, pids[0]) for _ in range(400)}
    assert "star" not in got and "blue" not in got, got
    assert got <= set(A.ITEM_ODDS["front"])


def test_the_back_of_the_field_is_where_the_star_lives(A):
    r = _room(A, "racing")
    pids = _field(A, r, [900.0, 600.0, 300.0, 10.0])
    rolls = [A._roll_item(r, pids[-1]) for _ in range(600)]
    assert rolls.count("star") > 40, "a last place that never gets a star"
    assert "banana" not in set(rolls), "handed the one item that defends a lead"


def test_the_band_is_the_running_order(A):
    r = _room(A, "racing")
    pids = _field(A, r, [900.0, 600.0, 300.0, 10.0])
    bands = [A._race_band(r, p) for p in pids]
    assert bands[0] == "front" and bands[-1] == "back"
    assert "mid" in bands


def test_practice_is_flat_and_has_neither(A):
    r = _room(A, "free")
    got = {A._roll_item(r, "a") for _ in range(300)}
    assert got == set(A.PRACTICE_ITEMS)


# ---------------------------------------------------------------------------
# Holding one behind you
# ---------------------------------------------------------------------------

def test_a_held_item_takes_the_hit_and_is_gone(A, bend, monkeypatch):
    r = _room(A)
    c = _car(A, r, "a", at=(35.0, 0.0, 0.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]             # along the road
    _car(A, r, "b", at=(75.0, 0.0, 0.0))
    A._item_queue(r, "b").append("banana")
    r.setdefault("held", {})["b"] = "banana"
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    A._fire(r, "a", "green")
    now = A._now_ms()
    for step in range(1, 60):
        A._tick_shots(r, now + step * 33)
        if not r["shots"]:
            break
    kinds = [ev for ev, d in seen]
    assert "item_blocked" in kinds, "the held item did nothing"
    assert "item_hit" not in kinds, "hit anyway, holding or not"
    assert r["shots"] == [], "the shell survived being blocked"
    assert A._item_queue(r, "b") == [] and not r["held"].get("b")


def test_only_a_thing_on_the_road_can_be_held(A):
    """A boost is not an object; there is nothing to put behind you."""
    assert set(A.HOLDABLE) == {"banana", "green", "red"}
    assert not set(A.HOLDABLE) & {"boost", "shield", "star", "blue", "bomb"}


# ---------------------------------------------------------------------------
# A star is a weapon
# ---------------------------------------------------------------------------

def test_driving_into_somebody_with_a_star_spins_them(A, monkeypatch):
    r = _room(A)
    star = _car(A, r, "a")
    star["flags"] = A.racecheck.FLAG_STAR
    _car(A, r, "b", at=(2.0, 0.0, 0.0))
    _car(A, r, "far", at=(80.0, 0.0, 0.0))
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    now = A._now_ms()
    A._tick_stars(r, now)
    hit = [d for ev, d in seen if ev == "item_hit"]
    assert [d["pid"] for d in hit] == ["b"]
    assert hit[0]["owner"] == "a" and hit[0]["item"] == "star"
    # And not again on the very next tick, or contact would be a machine gun.
    seen.clear()
    A._tick_stars(r, now + 100)
    assert seen == []
    A._tick_stars(r, now + A.STAR_AGAIN_MS + 1)
    assert [d["pid"] for ev, d in seen if ev == "item_hit"] == ["b"]


def test_two_stars_pass_through_each_other(A, monkeypatch):
    r = _room(A)
    for pid, x in (("a", 0.0), ("b", 2.0)):
        _car(A, r, pid, at=(x, 0.0, 0.0))["flags"] = A.racecheck.FLAG_STAR
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    A._tick_stars(r, A._now_ms())
    assert seen == []


# ---------------------------------------------------------------------------
# The watchdog
# ---------------------------------------------------------------------------

def test_the_watchdog_only_speaks_when_the_loop_is_late(A, monkeypatch):
    """A stall leaves no trace - it is the absence of everything - so the one
    thing that can catch it is something asking for a second and reporting how
    long it actually got."""
    clock = {"t": 0.0}
    naps = {"n": 0}

    def _sleep(_):
        naps["n"] += 1
        # On time, then five seconds late, then on time again - and then stop.
        clock["t"] += 1.0 if naps["n"] != 2 else 6.0
        if naps["n"] >= 3:
            raise KeyboardInterrupt

    said = []
    monkeypatch.setattr(A.eventlet, "sleep", _sleep)
    monkeypatch.setattr(A.time, "monotonic", lambda: clock["t"])
    monkeypatch.setattr(A.app.logger, "warning", lambda *a, **k: said.append(a))
    with pytest.raises(KeyboardInterrupt):
        A._hub_watchdog()
    assert len(said) == 1, "said nothing, or said it about an on-time tick"
    assert "%.1fs" in said[0][0] and said[0][1] >= 4.9, said


def test_running_into_a_trailed_item_spins_you_and_destroys_it(A, monkeypatch):
    """The other half of holding one: a banana behind your car is a banana on
    the road for the driver sitting in your bumper."""
    r = _room(A)
    me = _car(A, r, "a")                       # identity quaternion: forward -Z
    A._item_queue(r, "a").append("banana")
    r.setdefault("held", {})["a"] = "banana"
    # Right where the held item rides, which is behind the car.
    _car(A, r, "b", at=(0.0, 0.0, A.HELD_BACK))
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    A._tick_held(r, A._now_ms())
    hit = [d for ev, d in seen if ev == "item_hit"]
    assert [d["pid"] for d in hit] == ["b"] and hit[0]["owner"] == "a"
    assert not r["held"].get("a"), "the item survived being run into"
    assert A._item_queue(r, "a") == []


def test_your_own_trailed_item_cannot_hit_you(A, monkeypatch):
    r = _room(A)
    _car(A, r, "a")
    A._item_queue(r, "a").append("green")
    r.setdefault("held", {})["a"] = "green"
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    A._tick_held(r, A._now_ms())
    assert seen == [] and r["held"]["a"] == "green"


def test_two_trailed_items_take_each_other_out(A, monkeypatch):
    """Neither driver is hit: the two objects met, not the two cars."""
    r = _room(A)
    _car(A, r, "a")
    _car(A, r, "b", at=(0.0, 0.0, A.HELD_BACK))
    for pid in ("a", "b"):
        A._item_queue(r, pid).append("banana")
        r.setdefault("held", {})[pid] = "banana"
    seen = []
    monkeypatch.setattr(A.socketio, "emit", lambda ev, d, **k: seen.append((ev, d)))
    A._tick_held(r, A._now_ms())
    assert not [d for ev, d in seen if ev == "item_hit"], "somebody got hit"
    assert r["held"] == {}


def test_the_leader_rarely_draws_a_shield(A):
    """Defence is the leader's theme, but a shield defends *by existing* - at
    one box in four they have one nearly all the time, and hitting them stops
    being a thing you can do. A banana only defends if you put it somewhere."""
    r = _room(A, "racing")
    pids = _field(A, r, [900.0, 600.0, 300.0, 10.0])
    # **Twenty thousand rolls, not a thousand, and the count is load bearing.**
    # The leader's shield is 14 of 100 by weight, against a ceiling here of 16.
    # At n=1000 the standard error is 0.011, so the true value sits 1.8 sd
    # below the bound and this fails about one run in twenty-nine - which it
    # duly did, in CI, on the commit that moved the weight from 10 to 14. At
    # n=20000 the error is 0.0025 and 0.14 is eight sd clear, so the assertion
    # tests the weights rather than the weather. Raise the ceiling only if the
    # *weight* is meant to go up; it is cheap to sample instead.
    rolls = [A._roll_item(r, pids[0]) for _ in range(20000)]
    share = rolls.count("shield") / float(len(rolls))
    assert 0.04 < share < 0.16, share
    assert rolls.count("banana") > rolls.count("shield") * 2


def _ring():
    """A closed circuit: the last station lands back beside the first."""
    import math
    n = 120
    line = []
    for i in range(n):
        a = i * 2 * math.pi / n
        line.append({"p": [math.cos(a) * 200, 0.0, math.sin(a) * 200],
                     "n": [0.0, 1.0, 0.0],
                     "lat": [math.cos(a), 0.0, math.sin(a)], "hw": 6.5})
    return {"slug": "ring", "line": line, "station": 10.5, "ideal": 60.0,
            "closed": True}


def test_a_blue_shell_runs_round_a_closed_circuit(A, monkeypatch):
    """Spa, Silverstone, Monaco and Monza finish where they start, and the
    leader is regularly 'ahead' only the long way round - so a shell that
    stopped at the end of the array died on the pit straight every time."""
    track = _ring()
    monkeypatch.setattr(A, "_hot_track", lambda r: track)
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    r = _room(A)
    _car(A, r, "a", at=tuple(track["line"][110]["p"]))["prog"] = 100.0
    _car(A, r, "lead", at=tuple(track["line"][10]["p"]))["prog"] = 900.0
    A._fire(r, "a", "blue", "lead")
    assert r["shots"], "never left"
    now = A._now_ms()
    wrapped = False
    last = r["shots"][0]["si"]
    for step in range(1, 120):
        A._tick_shots(r, now + step * 33)
        if not r["shots"]:
            break
        si = r["shots"][0]["si"]
        if si < last:
            wrapped = True                    # went round the join
        last = si
    assert wrapped, "gave up at the end of the ribbon instead of going round"


def test_a_blue_shell_is_the_quick_one(A, bend, monkeypatch):
    """It is sent from the back to the front, which is most of a lap of road."""
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    r = _room(A)
    c = _car(A, r, "a", at=(35.0, 0.0, 0.0))
    c["q"] = [0.0, -0.7071, 0.0, 0.7071]
    _car(A, r, "lead", at=(200.0, 0.0, 0.0))["prog"] = 900.0
    now = A._now_ms()
    got = {}
    for item in ("green", "blue"):
        r["shots"] = []
        r.pop("shots_t", None)
        A._fire(r, "a", item, "lead" if item == "blue" else None)
        # Burn the arming ticks first, at no elapsed time, so this measures the
        # flight and not the two ticks every shot now spends standing still.
        for _ in range(A.SHOT_ARM_TICKS):
            A._tick_shots(r, now)
        start = r["shots"][0]["si"]
        A._tick_shots(r, now)                 # the first tick has no interval
        A._tick_shots(r, now + 100)
        # How far it *travelled*, not where it ended up: both leave from the
        # same place, and the launch offset would drown the difference.
        got[item] = r["shots"][0]["si"] - start if r["shots"] else 0
    assert got["blue"] > got["green"] * 1.4, got


# ---------------------------------------------------------------------------
# Counting what the items do
# ---------------------------------------------------------------------------

def test_every_item_event_is_counted(A, bend, monkeypatch, boxes):
    """Four numbers per item, and between them they answer the only questions
    anybody asks of an item table: is it handed out as often as the odds say,
    is it used when it is, does it land, and does holding one work."""
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._item_tally.clear()
    r = _room(A, "free")
    _car(A, r, "a")
    A._claim_box(r, "a", 0)
    given = [i for i, c in A._item_tally.items() if c["given"]]
    assert len(given) == 1, A._item_tally

    A._item_queue(r, "a").clear()
    A._item_queue(r, "a").append("green")
    A._spend_item(r, "a")
    assert A._item_tally["green"]["used"] == 1

    r.setdefault("held", {})["a"] = "banana"
    A._item_queue(r, "a").append("banana")
    A._drop_held(r, "a")
    assert A._item_tally["banana"]["blocked"] == 1


def test_a_boost_counts_once_however_many_times_it_is_tapped(A, monkeypatch):
    """It is one item out of one box; the window is how it is spent, not how
    many of them you had."""
    monkeypatch.setattr(A.socketio, "emit", lambda *a, **k: None)
    A._item_tally.clear()
    r = _room(A, "free")
    _car(A, r, "a")
    A._item_queue(r, "a").append("boost")
    for _ in range(5):
        A._spend_item(r, "a")
    assert A._item_tally["boost"]["used"] == 1


def test_the_stats_endpoint_adds_what_has_not_been_written_yet(A, monkeypatch):
    """A minute of counting lives in the process, and a page that showed only
    what had been flushed would sit still for a minute at a time."""
    A._item_tally.clear()
    A._tally("red", "used", 3)
    got = A.app.test_client().get("/api/item-stats").get_json()["items"]
    red = [row for row in got if row["item"] == "red"]
    assert red and red[0]["used"] == 3


# ---------------------------------------------------------------------------
# Being able to see the thing that hits you
# ---------------------------------------------------------------------------

def _snapshots(A, r, ticks=4):
    """What the room would have fanned out, tick by tick.

    `_tick` does `_tick_shots` and then `_snapshot`, so this is that order.
    """
    out = []
    now = A._now_ms()
    for step in range(ticks):
        A._tick_shots(r, now + step * 33)
        out.append(A._snapshot(r)["shots"])
    return out


@pytest.mark.parametrize("item", ["green", "banana", "bomb"])
def test_nothing_hits_a_car_that_was_never_sent_a_frame_of_it(A, item, bend, monkeypatch):
    """The point-blank hit out of nowhere.

    `_fire` runs in a socket handler; `_tick_shots` runs at the top of the next
    tick and `_snapshot` at the bottom of it. So a shot thrown at somebody
    inside about nine units - the five it leaves the nose at plus the four of
    `SHOT_HIT_R2`, which is the range anybody actually throws one at - was
    born, moved and spent before it had ever been in a snapshot. Nothing was
    drawn, nothing appeared on the minimap and `shellWarning` never pinged:
    from the seat it was being spun over by thin air.
    """
    r = _room(A)
    _car(A, r, "a", at=(0.0, 0.0, 0.0))
    _car(A, r, "b", at=(0.0, 0.0, -6.0))          # six units up the road
    hits = []
    monkeypatch.setattr(A.socketio, "emit",
                        lambda ev, d=None, **kw: hits.append((ev, d)))
    A._fire(r, "a", item)
    snaps = _snapshots(A, r)
    said = [d for ev, d in hits if ev == "item_hit"]
    # A bomb catches whoever threw it too, which is the item; what has to be
    # true for all three is that the car it was thrown at is still hit.
    assert "b" in [d["pid"] for d in said], "the hit itself has to still land"
    assert snaps[0], "the shot was spent before a single snapshot carried it"


def test_an_arming_shot_does_not_wander_off_its_target(A, bend):
    """Frozen for those two ticks, not merely forbidden to hit.

    A shell allowed to fly for 66ms before it may do anything is five units
    past a point-blank target by the time it arms - which would trade a hit
    nobody saw for a shell that goes straight through somebody, and that is not
    the better game. It stands still instead, so every hit that landed before
    still lands.
    """
    r = _room(A)
    _car(A, r, "a", at=(0.0, 0.0, 0.0))
    A._fire(r, "a", "banana")
    where = r["shots"][0]["p"][:]
    now = A._now_ms()
    for step in range(A.SHOT_ARM_TICKS):
        A._tick_shots(r, now + step * 33)
    assert r["shots"][0]["p"] == where


def test_the_browser_empties_its_slots_whenever_the_room_does():
    """`_open_race` and `_reset_race` wipe every queue without a message, so a
    browser that kept last session's items would refuse boxes ("both full") and
    spend nothing. Each phase that follows one of them must call `clearItems`."""
    import re
    js = open(os.path.join(os.path.dirname(__file__), "..", "static/js/game.js")).read()
    for start in ("function onQualCountdown(", "function onRaceStart(",
                  "socket.on('race_reset'", "socket.on('race_abort'"):
        i = js.index(start)
        body = js[i:i + 1500]
        end = re.search(r"\n\}|\n  \}\);", body).start()
        assert "clearItems()" in body[:end], start
