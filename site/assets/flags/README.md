# Flags

Two sets, in two formats, because they are two different kinds of picture.

- **`country/<cc>.svg`** — 271 flags keyed by ISO 3166-1 alpha-2, lifted from
  [flag-icons](https://github.com/lipis/flag-icons) 7.5.0 (MIT). Most national
  flags are a handful of rectangles, so they are tiny as vectors (4KB median)
  and stay crisp from the 18px on a leaderboard to the 40px in a profile hero.

- **`us/<st>.png`** — the 50 states, DC and five territories, rendered at ~330px
  wide by Wikimedia Commons' thumbnailer from the Commons SVGs (US government
  flags: public domain). These are *not* shipped as vectors on purpose. Most
  state flags are a state seal on a blue field, and a seal is a page of
  engraving — Kansas is 246KB of SVG, California 165KB, and neither survives
  being drawn 20px wide. A rasterised 330px PNG is a few kilobytes and is
  correct at every size the site draws it.

Both sets are served by the main website (`cgovind.com/assets/flags/…`) and
referenced from the game subdomains by absolute URL, so there is one copy rather
than four. `accounts/places.py` is the list of what exists; anything it does not
name has no file here.

Re-fetching the state set: `tools/fetch_state_flags.py` (resumable, and polite
to Commons — it will 429 you if you rush it).
