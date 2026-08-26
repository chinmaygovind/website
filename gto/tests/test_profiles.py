"""The five of them, and the two axes that make them different people."""

import pytest

import profiles
import ranges
from profiles import BASE_TASTE, FRIENDS, STRANGERS, Profile, features, taste_score


def test_there_are_five_friends_and_five_strangers():
    assert len(FRIENDS) == 5
    assert len(STRANGERS) == 5
    assert {p.key for p in FRIENDS} == {"ronit", "aarav", "bell", "apurva", "sanjay"}


def test_no_stranger_carries_a_photograph_or_a_real_name():
    """The repo is public and these are photographs of real people."""
    real = {p.name for p in FRIENDS}
    for s in STRANGERS:
        assert s.avatar is None
        assert s.name not in real


def test_strangers_keep_the_tendencies_they_stand_in_for():
    """The tendencies are the interesting part and they are not private."""
    for friend, stranger in zip(FRIENDS, STRANGERS):
        assert stranger.vpip == friend.vpip
        assert stranger.discipline == friend.discipline
        assert stranger.taste == friend.taste


def test_table_hands_out_copies_not_the_originals():
    """A session tunes its own opponents; it must not tune everybody's."""
    a = profiles.table()[0]
    a.vpip = 99
    assert profiles.table()[0].vpip != 99


@pytest.mark.parametrize("p", FRIENDS, ids=lambda p: p.key)
def test_a_player_cannot_raise_more_hands_than_they_play(p):
    assert p.pfr <= p.vpip


def test_the_described_pecking_order_holds():
    """The friends were described by how they play; the numbers must agree."""
    by_key = {p.key: p for p in FRIENDS}
    nits = (by_key["ronit"], by_key["aarav"])
    casual = (by_key["bell"], by_key["apurva"])
    wild = by_key["sanjay"]

    for n in nits:
        for c in casual:
            assert n.vpip < c.vpip
            assert n.discipline > c.discipline
        assert n.vpip < wild.vpip
    for c in casual:
        assert c.vpip < wild.vpip
        assert c.discipline > wild.discipline


def test_a_bad_profile_is_rejected_rather_than_played():
    with pytest.raises(ValueError, match="pfr"):
        Profile("x", "X", "", vpip=10, pfr=20, three_bet=5, fold_to_three_bet=50,
                cbet=50, fold_to_cbet=50, wtsd=25, aggression=1.0, bluff=1.0,
                limp=0, squeeze=5, call_down=1.0, discipline=0.5,
                tilt_speed="none", tilt_effect=0.1, timing=profiles.timing(1, 2, 0.1))


def test_an_unknown_field_is_a_typo_not_a_setting():
    with pytest.raises(ValueError, match="unknown"):
        Profile("x", "X", "", vpip=10, pfr=8, three_bet=5, fold_to_three_bet=50,
                cbet=50, fold_to_cbet=50, wtsd=25, aggression=1.0, bluff=1.0,
                limp=0, squeeze=5, call_down=1.0, discipline=0.5,
                tilt_speed="none", tilt_effect=0.1,
                timing=profiles.timing(1, 2, 0.1), agression=1.0)


def test_a_profile_survives_a_round_trip():
    for p in FRIENDS:
        assert Profile.from_dict(p.to_dict()).to_dict() == p.to_dict()


# ---------------------------------------------------------------- taste


def test_features_are_all_between_zero_and_one():
    for cls in ranges.CLASSES:
        for k, v in features(cls).items():
            assert 0.0 <= v <= 1.0, (cls, k, v)


def test_a_pair_is_read_as_a_pair_and_nothing_else():
    f = features("77")
    assert f["pair"] == 1.0
    assert f["suited"] == f["connected"] == f["ace"] == 0.0


def test_suitedness_and_connectedness_are_seen():
    assert features("87s")["suited"] == 1.0
    assert features("87o")["suited"] == 0.0
    assert features("87s")["connected"] == 1.0
    assert features("83s")["connected"] < features("87s")["connected"]


def test_taste_is_what_looks_good_not_what_is_good():
    """The gap is the model. A pretty hand can outscore a better ugly one."""
    sanjay = next(p for p in FRIENDS if p.key == "sanjay")
    assert taste_score("A4s", sanjay.taste) > taste_score("99", sanjay.taste)


def test_the_nits_prefer_the_connector_and_the_loose_players_prefer_the_ace():
    """The tell is in the tail, not at the top - everybody likes AKs.

    ``A3o`` against ``76s`` is the whole difference between these players in one
    comparison. Ronit wants the hand that flops well; Sanjay wants the ace. Both
    hands are somewhere near the edge of a 30% range, so which one a person
    reaches for says what kind of player they are.
    """
    by_key = {p.key: p for p in FRIENDS}

    def ace_pull(key):
        """How much more this person likes the offsuit ace than the connector."""
        t = by_key[key].taste
        return taste_score("A3o", t) - taste_score("76s", t)

    # Both nits reach for the hand that flops well.
    assert ace_pull("ronit") < 0
    assert ace_pull("aarav") < 0
    # Sanjay reaches for the ace, harder than anybody else at the table.
    assert ace_pull("sanjay") > 0
    assert ace_pull("sanjay") == max(ace_pull(k) for k in by_key)

    # Apurva also prefers the connector, and that is on purpose rather than an
    # accident of tuning: he is the sharper of the two casual players, and his
    # profile says so with a high `connected` weight. Bell is the one who plays
    # any ace.
    assert ace_pull("apurva") < 0 < ace_pull("bell")


def test_the_looser_the_player_the_higher_a_weak_ace_ranks():
    def rank_of(key, cls):
        p = next(x for x in FRIENDS if x.key == key)
        order = sorted(ranges.CLASSES, key=lambda c: -taste_score(c, p.taste))
        return order.index(cls)

    assert rank_of("sanjay", "A3o") < rank_of("bell", "A3o") < rank_of("ronit", "A3o")


def test_nobody_likes_the_worst_hand_in_poker():
    for p in FRIENDS:
        worst = min(ranges.CLASSES, key=lambda c: taste_score(c, p.taste))
        assert worst in ("72o", "82o", "73o", "32o", "62o", "63o", "83o", "92o")
