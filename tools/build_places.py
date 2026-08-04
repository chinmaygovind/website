"""Regenerate ``accounts/places.py`` from the vendored flag art.

Run from the repo root, with flag-icons' ``country.json`` to hand:

    python3 tools/build_places.py path/to/flag-icons/country.json > accounts/places.py

The lists are derived from the directories rather than hand-written, so a code
can never be offered without a flag behind it. See ``accounts/places.py``'s own
docstring for what is deliberately left out and why.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COUNTRY_DIR = os.path.join(ROOT, "site", "assets", "flags", "country")
US_DIR = os.path.join(ROOT, "site", "assets", "flags", "us")

# Not ISO 3166-1, but all of them ordinary answers to "where are you from?"
# with a flag anybody would know.
EXTRA = {"gb-eng": "England", "gb-sct": "Scotland", "gb-wls": "Wales",
         "gb-nir": "Northern Ireland", "xk": "Kosovo"}

# Shortened from the vendored names, which are the formal ones. A profile puts
# this next to a person's name, where "United States of America" takes the line.
RENAME = {
    "us": "United States", "gb": "United Kingdom", "kr": "South Korea",
    "kp": "North Korea", "ru": "Russia", "cd": "DR Congo", "cg": "Congo",
    "sy": "Syria", "ir": "Iran", "la": "Laos", "bo": "Bolivia",
    "ve": "Venezuela", "tz": "Tanzania", "va": "Vatican City",
    "fm": "Micronesia", "vg": "British Virgin Islands",
    "vi": "US Virgin Islands", "cz": "Czechia", "mo": "Macao",
    "sh": "Saint Helena", "gs": "South Georgia",
    "um": "US Outlying Islands",
}

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "AS": "American Samoa", "GU": "Guam", "MP": "Northern Mariana Islands",
    "PR": "Puerto Rico", "VI": "U.S. Virgin Islands",
}


def main(country_json):
    data = json.load(open(country_json))
    have = {os.path.splitext(f)[0] for f in os.listdir(COUNTRY_DIR)
            if f.endswith(".svg")}
    countries = {}
    for entry in data:
        code = entry["code"]
        if code not in have:
            continue
        if entry.get("iso"):
            countries[code] = RENAME.get(code, entry["name"])
        elif code in EXTRA:
            countries[code] = EXTRA[code]

    have_states = {os.path.splitext(f)[0].upper() for f in os.listdir(US_DIR)
                   if f.endswith(".png")}
    # By name, not by code: sorted by code the picker opens on Alaska,
    # Alabama, Arkansas, which is nobody's idea of alphabetical.
    states = sorted(((k, v) for k, v in US_STATES.items() if k in have_states),
                    key=lambda r: r[1])

    print("COUNTRIES = [")
    for code, name in sorted(countries.items(), key=lambda r: r[1]):
        print("    (%r, %r)," % (code, name))
    print("]\n")
    print("US_STATES = [")
    for code, name in states:
        print("    (%r, %r)," % (code, name))
    print("]")
    print("\n# Paste the module docstring and the two helpers back on - this "
          "script only\n# regenerates the lists.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
