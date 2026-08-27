# Where these cards came from

They are drawn by `gto/tools/make_cards.py` - 52 faces and a back, written as
SVG at exactly the 240 x 336 the table draws them at. **Do not hand-edit an
`.svg` in here**; change the generator and run it.

The deck that used to be here was the public-domain `vector-playing-cards` set
repackaged by [hayeah/playing-cards-assets](https://github.com/hayeah/playing-cards-assets).
It was replaced in August 2026 for two reasons:

- **It did not fit.** Those faces are 167.1 x 242.7pt, an 0.688 aspect, and the
  table draws a real card's 0.714 - so every one of them was being cropped by
  `background-size: cover`.
- **It was 4.7MB**, 630KB of which was one king of clubs. This deck is 86KB in
  total, and the court cards are the same size as the rest.

The style is a jumbo index rather than a pip layout, because these are read at
40 to 84 pixels across a felt, where a traditional face is a grey smudge and
only the corner index is doing any work. The first cut of it was *only* that
index, and it read as a blank card with a letter in the corner; what fills the
rest is a **watermark pip** at a tenth opacity, and on the ace the same pip
printed solid. `SUIT_COLOR` in the generator is the whole palette: a four-colour
deck is a change to that dict and nothing else.
