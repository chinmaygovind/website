"""The flag lists, and the one rule about which flag flies."""

import os

from accounts import places

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTRY_DIR = os.path.join(ROOT, "site", "assets", "flags", "country")
US_DIR = os.path.join(ROOT, "site", "assets", "flags", "us")


def test_every_offered_place_has_a_flag_on_disk():
    """The picker is generated from the directories, so this can only fail if
    somebody deletes art without regenerating - which would put a broken image
    next to a person's name on every leaderboard on the site."""
    for code, name in places.COUNTRIES:
        assert os.path.isfile(os.path.join(COUNTRY_DIR, code + ".svg")), \
            "%s (%s) is offered with no flag" % (code, name)
    for code, name in places.US_STATES:
        assert os.path.isfile(os.path.join(US_DIR, code.lower() + ".png")), \
            "%s (%s) is offered with no flag" % (code, name)


def test_no_flag_on_disk_is_left_unofferable():
    """The other direction: art nobody can pick is dead weight in the repo."""
    offered = {c for c, _ in places.COUNTRIES}
    on_disk = {os.path.splitext(f)[0] for f in os.listdir(COUNTRY_DIR)
               if f.endswith(".svg")}
    assert on_disk == offered, "unofferable flags: %s" % sorted(on_disk - offered)


def test_the_lists_are_sorted_by_name():
    """Which is the order the picker shows them in, and the only order anybody
    can find their own country in."""
    assert [n for _, n in places.COUNTRIES] == sorted(n for _, n in places.COUNTRIES)
    assert [n for _, n in places.US_STATES] == sorted(n for _, n in places.US_STATES)


def test_the_fifty_states_are_all_there():
    codes = {c for c, _ in places.US_STATES}
    assert len(codes) == 56                      # 50 + DC + five territories
    for expected in ("CA", "NY", "TX", "PA", "DC", "PR"):
        assert expected in codes


def test_a_state_flag_needs_the_us_and_a_state_and_the_asking():
    """Three conditions, and the whole point is that all three are checked in
    one place. A stale ``flag_pref`` left behind by somebody moving country
    must not fly a state flag over another country's name."""
    assert places.flag_of("us", "CA", True)[0] == "/assets/flags/us/ca.png"

    # asked, but not in the US any more
    assert places.flag_of("gb", "CA", True)[0] == "/assets/flags/country/gb.svg"
    # in the US with a state, but did not ask
    assert places.flag_of("us", "CA", False)[0] == "/assets/flags/country/us.svg"
    # asked, in the US, but no state chosen
    assert places.flag_of("us", None, True)[0] == "/assets/flags/country/us.svg"


def test_no_country_means_no_flag_rather_than_a_placeholder():
    assert places.flag_of(None) is None
    assert places.flag_of("") is None
    assert places.flag_of("zz") is None              # not a code we have art for


def test_flag_of_does_not_care_how_a_stored_code_is_cased():
    """Five services write this column; only one of them is the settings form."""
    assert places.flag_of("US")[0] == "/assets/flags/country/us.svg"
    assert places.flag_of("us", "ca", True)[0] == "/assets/flags/us/ca.png"


def test_place_name_reads_as_an_address():
    assert places.place_name("us", "CA") == "California, United States"
    assert places.place_name("us") == "United States"
    assert places.place_name("in") == "India"
    assert places.place_name("gb", "CA") == "United Kingdom"   # a state is US-only
    assert places.place_name(None) is None


def test_the_long_formal_names_were_shortened():
    """These sit next to a person's name in a hero and on a card, where the
    formal form takes the whole line."""
    names = dict(places.COUNTRIES)
    assert names["us"] == "United States"
    assert names["gb"] == "United Kingdom"
    assert names["kr"] == "South Korea"
    assert max(len(n) for n in names.values()) <= 34


def test_the_organisations_are_not_offered_as_nationalities():
    """flag-icons ships the EU, the UN, ASEAN and a few pseudo-codes. They are
    flags; they are not answers to "where are you from?"."""
    codes = {c for c, _ in places.COUNTRIES}
    for not_a_country in ("eu", "un", "arab", "asean", "cefta", "xx", "es-ct"):
        assert not_a_country not in codes


def test_the_home_nations_and_kosovo_are_offered_even_though_they_are_not_iso():
    codes = {c for c, _ in places.COUNTRIES}
    for code in ("gb-eng", "gb-sct", "gb-wls", "gb-nir", "xk"):
        assert code in codes
