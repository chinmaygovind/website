"""Fetch the US state (and DC) flags from Wikimedia Commons as 256px PNGs.

Country flags come from flag-icons as SVG, which is right for them - a tricolour
is a handful of rectangles. State flags are not like that: most of them are a
state seal on a blue field, and the seal is a page of engraving. As SVG they run
to a quarter of a megabyte each and, at the 20px a leaderboard shows them at,
render as mush. Wikimedia will rasterise on request, so we ask it for a 256px
PNG once and ship that: a few kilobytes, and correct at every size we draw it.
"""

import json
import os
import sys
import time
from urllib import parse, request

OUT = sys.argv[1]
UA = {"User-Agent": "cgovind.com flag vendoring (one-time)"}

# The Commons file name is not always "Flag of <state>.svg".
SPECIAL = {
    "DC": "Flag of the District of Columbia.svg",
}

STATES = {
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
    # Territories, for completeness - people are from them too.
    "PR": "Puerto Rico", "GU": "Guam", "VI": "the United States Virgin Islands",
    "AS": "American Samoa", "MP": "the Northern Mariana Islands",
}


def get(url):
    return request.urlopen(request.Request(url, headers=UA), timeout=30).read()


def thumb_url(title, width=256):
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
           "&prop=imageinfo&iiprop=url&iiurlwidth=%d&titles=%s"
           % (width, parse.quote("File:" + title)))
    pages = json.loads(get(api))["query"]["pages"]
    info = list(pages.values())[0].get("imageinfo")
    if not info:
        return None
    return info[0].get("thumburl") or info[0].get("url")


os.makedirs(OUT, exist_ok=True)
missing = []
for code, name in sorted(STATES.items()):
    dest = os.path.join(OUT, code.lower() + ".png")
    if os.path.exists(dest):
        continue
    title = SPECIAL.get(code, "Flag of %s.svg" % name)
    try:
        url = thumb_url(title)
        if not url:
            missing.append((code, title))
            continue
        blob = get(url)                            # fetch first, then write:
        if not blob.startswith(b"\x89PNG"):        # a half-written file is a
            raise ValueError("not a PNG")          # file the resume skips
        with open(dest, "wb") as f:
            f.write(blob)
        print("%s  %-28s %6d bytes" % (code, name, os.path.getsize(dest)))
    except Exception as exc:                       # noqa: BLE001 - one-time tool
        missing.append((code, "%s (%s)" % (title, exc)))
        time.sleep(20)
    time.sleep(2.0)                                # be polite to Commons

if missing:
    print("\nMISSING:")
    for code, why in missing:
        print(" ", code, why)
    sys.exit(1)
