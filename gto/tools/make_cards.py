"""Draw the deck.

Fifty-two faces and a back, written as SVG at exactly the aspect the table
draws them at (240 x 336, a real card's 2.5 x 3.5), so nothing is cropped to
fit. Run me from anywhere:

    python gto/tools/make_cards.py

The style is a jumbo index - rank over pip in two opposite corners, at the same
size in both, the way a casino deck is printed - because these are read at 40 to
84 pixels across a felt, where a traditional pip layout is a grey smudge and
only the corner index actually carries.

Two things keep that from reading as a blank card with a letter on it. There is
a **watermark pip** filling the middle, at a tenth opacity: too faint to compete
with the index, strong enough that the suit is a colour and a shape at forty
pixels rather than a symbol you have to find. And the **ace prints that pip
solid**, which is both the classic face and the one distinction worth making at
a poker table, where the ace is the card you are scanning for.

SUIT_COLOR below is the whole palette; a four-colour deck is a change to that
dict and nothing else.
"""

import os

W, H = 240, 336
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "cards")

INK = "#12181f"
RED = "#bf2233"
FACE = "#f8f6f0"

SUIT_COLOR = {"s": INK, "c": INK, "h": RED, "d": RED}
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
LABEL = {"T": "10"}

# Each pip is drawn in its own 100 x 100 box and placed by transform, so the
# corner pip, the watermark and the back's medallion are one path at three
# scales.
PIPS = {
    "s": '<path d="M50 7C50 7 13 37 13 60c0 13 9 22 20 22 7 0 13-3 16-9'
         '-1 12-5 20-11 24-3 2-7 4-11 5v2h46v-2c-4-1-8-3-11-5-6-4-10-12-11-24'
         ' 3 6 9 9 16 9 11 0 20-9 20-22C87 37 50 7 50 7z"/>',
    "h": '<path d="M50 93C20 70 9 53 9 36 9 22 19 11 33 11c8 0 14 5 17 12'
         ' 3-7 9-12 17-12 14 0 24 11 24 25 0 17-11 34-41 57z"/>',
    "d": '<path d="M50 4 87 50 50 96 13 50z"/>',
    "c": '<g><circle cx="50" cy="28" r="20"/><circle cx="23" cy="60" r="20"/>'
         '<circle cx="77" cy="60" r="20"/>'
         '<path d="M50 60c0 15-4 27-11 36 7-3 15-3 22 0-7-9-11-21-11-36z"/></g>',
}

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"


def index_block(rank, suit, color):
    """Rank over pip, both centred on x=30, drawn downward from the origin.

    Placing a corner is then one translate, and the bottom-right one is the
    same translate with a rotate - which is what makes the two indices the same
    size, as they are on a real card and were not here.
    """
    text = LABEL.get(rank, rank)
    two = len(text) > 1
    return (
        f'<text x="31" y="68" text-anchor="middle" font-family="{FONT}" '
        f'font-size="{74 if two else 92}" font-weight="700" '
        f'letter-spacing="{-5 if two else -2}" fill="{color}">{text}</text>'
        f'<g transform="translate(11 72) scale(.40)" fill="{color}">{PIPS[suit]}</g>'
    )


def face(rank, suit):
    color = SUIT_COLOR[suit]
    block = index_block(rank, suit, color)
    ace = rank == "A"
    mark = (
        f'<g transform="translate(75 126) scale(.90)" fill="{color}"'
        f' fill-opacity=".93">{PIPS[suit]}</g>'
        if ace else
        f'<g transform="translate(45 97) scale(1.50)" fill="{color}"'
        f' fill-opacity="{.11 if color == RED else .075}">{PIPS[suit]}</g>'
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs><linearGradient id="g" x1="0" y1="0" x2=".3" y2="1">
<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="{FACE}"/>
</linearGradient>
<clipPath id="c"><rect width="{W}" height="{H}" rx="19"/></clipPath></defs>
<g clip-path="url(#c)">
<rect width="{W}" height="{H}" fill="url(#g)"/>
<rect x="8.5" y="8.5" width="{W - 17}" height="{H - 17}" rx="12" fill="none"
      stroke="{color}" stroke-opacity=".18"/>
{mark}
<g transform="translate(20 22)">{block}</g>
<g transform="translate(220 314) rotate(180)">{block}</g>
</g>
<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="18.25" fill="none"
      stroke="{INK}" stroke-opacity=".22"/>
</svg>
"""


BACK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
<linearGradient id="f" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#8f1d2a"/><stop offset="1" stop-color="#4a0e16"/>
</linearGradient>
<pattern id="w" width="26" height="26" patternUnits="userSpaceOnUse"
         patternTransform="rotate(45)">
<path d="M13 0v26M0 13h26" stroke="#f0d49a" stroke-opacity=".22" stroke-width="1.6"/>
<circle cx="13" cy="13" r="3.2" fill="none" stroke="#f0d49a"
        stroke-opacity=".3" stroke-width="1.6"/>
</pattern>
<radialGradient id="v" cx=".5" cy=".42" r=".75">
<stop offset=".55" stop-color="#000000" stop-opacity="0"/>
<stop offset="1" stop-color="#000000" stop-opacity=".45"/>
</radialGradient>
</defs>
<rect width="{W}" height="{H}" rx="19" fill="url(#f)"/>
<rect x="10" y="10" width="{W - 20}" height="{H - 20}" rx="12" fill="url(#w)"/>
<rect width="{W}" height="{H}" rx="19" fill="url(#v)"/>
<rect x="7.5" y="7.5" width="{W - 15}" height="{H - 15}" rx="14" fill="none"
      stroke="#f0d49a" stroke-opacity=".75" stroke-width="2"/>
<rect x="14.5" y="14.5" width="{W - 29}" height="{H - 29}" rx="9" fill="none"
      stroke="#f0d49a" stroke-opacity=".38"/>
<circle cx="120" cy="168" r="46" fill="#5c1119" stroke="#f0d49a"
        stroke-opacity=".8" stroke-width="2"/>
<circle cx="120" cy="168" r="39" fill="none" stroke="#f0d49a" stroke-opacity=".4"/>
<g transform="translate(94 142) scale(.52)" fill="#f0d49a">{PIPS['s']}</g>
<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="18.25" fill="none"
      stroke="#000000" stroke-opacity=".35"/>
</svg>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for suit in "shdc":
        for rank in RANKS:
            with open(os.path.join(OUT, f"{rank}{suit}.svg"), "w") as fh:
                fh.write(face(rank, suit))
    with open(os.path.join(OUT, "back.svg"), "w") as fh:
        fh.write(BACK)
    print(f"wrote 52 faces and a back to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
