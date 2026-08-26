"""Draw the deck.

Fifty-two faces and a back, written as SVG at exactly the aspect the table
draws them at (240 x 336, a real card's 2.5 x 3.5), so nothing is cropped to
fit. Run me from anywhere:

    python gto/tools/make_cards.py

The style is one big index - rank and suit stacked large in the top-left, a
small mirrored repeat bottom-right - because these are read at 40 to 84 pixels
across a felt, where a traditional pip layout is a grey smudge and only the
corner index actually carries. RED/BLACK below is the whole palette; a
four-colour deck is a change to that dict and nothing else.
"""

import os

W, H = 240, 336
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "cards")

INK = "#1d2430"
RED = "#c8323f"
FACE = "#faf9f6"

SUIT_COLOR = {"s": INK, "c": INK, "h": RED, "d": RED}
RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
LABEL = {"T": "10"}

# Each pip is drawn in its own 100 x 100 box and placed by transform.
PIPS = {
    "s": '<path d="M50 8C50 8 14 36 14 58c0 13 9 21 19 21 7 0 12-3 15-8'
         '-1 11-5 18-13 22h30c-8-4-12-11-13-22 3 5 8 8 15 8 10 0 19-8 19-21'
         'C86 36 50 8 50 8z"/>',
    "h": '<path d="M50 89C20 67 8 51 8 35 8 21 19 11 32 11c9 0 15 5 18 11 '
         '3-6 9-11 18-11 13 0 24 10 24 24 0 16-12 32-42 54z"/>',
    "d": '<path d="M50 6 88 50 50 94 12 50z"/>',
    "c": '<g><circle cx="50" cy="30" r="20"/><circle cx="25" cy="61" r="20"/>'
         '<circle cx="75" cy="61" r="20"/>'
         '<path d="M43 94c5-11 7-21 7-33h0c0 12 2 22 7 33z"/></g>',
}

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"


def index_block(rank, suit, color):
    """Rank over pip, drawn from (0, 0) down, so a corner is one translate."""
    text = LABEL.get(rank, rank)
    size = 118 if len(text) == 1 else 98
    return (
        f'<text x="0" y="86" font-family="{FONT}" font-size="{size}" '
        f'font-weight="700" letter-spacing="-3" fill="{color}">{text}</text>'
        f'<g transform="translate(1 100) scale(.56)" fill="{color}">{PIPS[suit]}</g>'
    )


def face(rank, suit):
    color = SUIT_COLOR[suit]
    block = index_block(rank, suit, color)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs><linearGradient id="g" x1="0" y1="0" x2=".35" y2="1">
<stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="{FACE}"/>
</linearGradient>
<clipPath id="c"><rect width="{W}" height="{H}" rx="19"/></clipPath></defs>
<g clip-path="url(#c)">
<rect width="{W}" height="{H}" fill="url(#g)"/>
<g transform="translate(26 30)">{block}</g>
<g transform="translate(214 306) rotate(180) scale(.52)">{block}</g>
</g>
<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="18.25" fill="none"
      stroke="{INK}" stroke-opacity=".16"/>
</svg>
"""


BACK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
<linearGradient id="f" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#2a3550"/><stop offset="1" stop-color="#141a28"/>
</linearGradient>
<pattern id="w" width="24" height="24" patternUnits="userSpaceOnUse"
         patternTransform="rotate(45)">
<path d="M12 0v24M0 12h24" stroke="#d8ae5e" stroke-opacity=".16" stroke-width="1.4"/>
<circle cx="12" cy="12" r="2.6" fill="#d8ae5e" fill-opacity=".2"/>
</pattern>
</defs>
<rect width="{W}" height="{H}" rx="19" fill="url(#f)"/>
<rect x="9" y="9" width="{W - 18}" height="{H - 18}" rx="12" fill="url(#w)"/>
<rect x="9.5" y="9.5" width="{W - 19}" height="{H - 19}" rx="11.5" fill="none"
      stroke="#d8ae5e" stroke-opacity=".45"/>
<circle cx="120" cy="168" r="41" fill="#141a28" stroke="#d8ae5e"
        stroke-opacity=".5" stroke-width="1.5"/>
<g transform="translate(96 144) scale(.48)" fill="#d8ae5e" fill-opacity=".9">{PIPS['s']}</g>
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
