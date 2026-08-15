# The static site (`site/`)

The web root. `app.py` serves everything under here as static files with
GitHub-Pages-style directory indexes. No build step, no bundler — pages are
self-contained HTML with inline `<style>`/`<script>`.


- `site/index.html` is the landing page: white page, big "hey!" left, welcome line
  and contact links across the top, all in the self-hosted xkcd Script font
  (`site/fonts/xkcd-script.woff`, from ipython/xkcd-font). Below it are **two
  labelled tile rows** — `<section class="tilerow">` each holding an
  `<h2 class="rowlabel">` and its tiles, `ABOUT ME` over resume, poker, whales,
  racing, music, settings and `GAMES` over drive, ttr, ers, kot. Each row is its
  own `repeat(6, --tile)` grid, so the two line up as they did when they shared
  one twelve-slot grid, and **six is still the row width**: a seventh tile in a
  row wraps *within that row* rather than into the row below. **Keep `settings`
  last in the top row** (it's a Wii-menu joke), and add new games to the
  `GAMES` section so the split holds.
  **The labels cost the tiles nothing** — they were added without a single icon
  moving, and there is a check for that: shoot the page before and after and
  diff the pixels (`ImageChops.difference(...).getbbox()`), and the only band
  that differs is the strip the labels are in. That is what `position: absolute`
  on `.rowlabel` buys — it hangs in the margin left over beside six tiles rather
  than taking a column. Two things it needs: the row is `width: max-content;
  margin: 0 auto` so that `right: 100%` means "the left edge of the tiles", and
  the label needs an explicit `width: max-content`, because an absolute box
  positioned entirely outside its containing block gets no available width and
  shrink-to-fit collapses it to its longest word.
  **Below 900px the label goes above its row instead**, back in the flow and
  spanning the grid: `--tile` has bottomed out at its 110px floor there while
  the screen keeps shrinking, so six tiles are already most of the page and
  there is no margin to hang anything in. At 760 and below it stays above the
  row and the grid drops to two columns, which is the phone layout. Drive's tile was pulled for
  a while (Jul 2026) so Chinmay could draw the icon himself, and came back once he
  had — the steering wheel in `assets/icons/drive.{png,gif,xcf}` is his.
- **Adding a tile is one repeating pattern**, all inside `site/index.html` (no
  build step, so everything is inline):
  1. a `--<name>` accent colour in `:root`, then `.modal-<name>` rules for
     `border-color`, `.pane-title` colour, and `.media-img` border;
  2. a `<button class="tile" data-modal="modal-<name>">` with a `.tile-img` whose
     `data-still`/`data-anim` are `assets/icons/<name>.png` / `.gif` — the script
     at the bottom swaps to the gif on hover and preloads it, so **every tile
     needs both files**;
  3. a `.modal` + `.modal-box .modal-<name>` block, left pane = `.pane-title` +
     `.pane-text` (+ `.modal-icon` gif top-right), right pane = `.media` frames
     holding a `.media-img` or a dashed `.placeholder` while art is pending.
  The generic script wires open/close (X, backdrop, Escape) off those classes —
  a new tile needs no JS. Icon sources are GIMP `.xcf` files kept next to the
  exported png/gif in `site/assets/icons/`.
- Two panes are live rather than static: the resume tile's fast facts patch in a
  computed age and the Duolingo streak, and the music tile fills recently-played
  and top-artists from the Spotify proxy, plus a concert carousel driven by
  `site/assets/music/concerts.json` (add a concert by appending to that JSON —
  no code change).
- `site/wii/index.html` is the Wii menu (was `public/wii/index.html`, briefly at
  root). Warning screen fades into a channel grid. The bottom-left gray slot is a
  **Ticket to Ride channel** (`#channel-ttr`) whose click handler navigates to `/ttr`.
  Its `../../images|audio|videos` paths assume it sits at root, so some break at `/wii/`.
- **`site/warning.html` is gone** (deleted in `d0a282b`) but `site/wii/index.html`
  still navigates to `warning.html`, so the Wii menu's "reset" path 404s into the
  Mario game. The `warning.png`/`warning.wav` assets are still there, so restoring
  the page (at `site/wii/warning.html`, since the link is relative) would fix it.
- `site/channels/{mii,music,codebusters}/` - the Wii channel pages. They
  reference shared assets with `../../images|audio|videos/…` (resolves to root).
- `site/home/index.html` - the **projects landing page** (was the site's old `/`).
  Its assets live in `site/home/{images,audio}/` and `Chinmay_Govind_Resume.pdf`.
- `site/{projects,games}/` - standalone project/game pages (astro, ibec, quickcal,
  robot-tour, bridge, flip, klotski), copied unchanged.
- `site/{images,audio,videos}/` - shared media (Wii menu art + channel media).
- `site/404.html`, `favicon.ico`, `robots.txt` at the root.

## Being found

- **`site/sitemap.xml` lists the landing page and nothing else, on purpose.** It
  briefly listed all twelve reachable pages; Chinmay does not want the unlinked
  ones found, so they came out and `robots.txt` disallows them (`/home/`,
  `/projects/`, `/games/`, `/channels/`, `/wii/`). They are **still on disk and
  still answer** if you know the address — this is a decision about what search
  engines are told, not a deletion. It is still hand-kept, so `tests/test_seo.py`
  resolves every URL in it against the tree, fails on a rename, and fails if the
  sitemap ever lists something robots.txt disallows.
- **The four games cannot be in that sitemap and do not need to be.** A sitemap
  may only list URLs on its own host, so a `drive.cgovind.com` entry would
  invalidate the file. They are found the better way: the landing page links to
  all four, and Drive serves its own sitemap from its own host, generated from
  the track pool.
- **`<link rel="canonical">` on the landing page is the www fix.**
  `www.cgovind.com` and `cgovind.com` both answer 200 with no redirect between
  them, so a crawler sees two whole copies of the site. Doing it properly is an
  nginx redirect and **the deploy never touches nginx**, so the canonical settles
  which address is real without a hand-applied config change, and stays right if
  a redirect is ever added.
- **`chinmaygovind.github.io` now redirects here** (2026-08-14). It was live,
  ranking for Chinmay's name, and never mentioned this domain, which was the
  biggest single reason searching his name did not land on `cgovind.com`. It is
  a different repo: GitHub Pages serves its **`gh-pages` branch**, published
  from `public/` by `npm run deploy`, so the redirect had to be committed to
  both or the next deploy there would put the old site back. Pages cannot serve
  a 301, so it is a canonical plus a zero-delay meta refresh plus a
  `location.replace`. Its old pages are left on disk and dropped from the index
  with robots.txt — **but its root is deliberately still crawlable**, because a
  crawler that cannot fetch the redirect cannot follow it either.

## Unlinked pages (nothing on the site links to these)

The landing page's tiles only open modals or point off-site (ttr/ers/kot subdomains,
the resume PDF, YouTube, PennToday). **No internal HTML page is linked from `/` at
all**, so every page below is reachable only by typing its URL:

- **Orphaned outright:** `games/flip/` ("Flip - The Game"), `games/klotski/`
  ("Klotski"), `wii/`, `channels/mii/`, and the local
  `projects/ibec/` copy (7 leftover template pages: committees, contact, events,
  membership, left-/right-/no-sidebar).
- **Orphaned transitively:** `home/index.html` (the old projects page) has no
  inbound links either, so the things only *it* links to are also unreachable:
  `projects/astro/` (AstroGPT), `projects/quickcal/`, `projects/robot-tour/`,
  `games/bridge/` (Penn Bridge sim, plus the `projects/bridge/` redirect stub),
  `channels/music/` and `channels/codebusters/` (+ its `pattern.html`).
- `site/404.html` (Mario game) is by design only reachable via a bad URL.
- **Two stale links to fix if you re-link things:** `home/index.html:591`'s "Wii
  Channel" tile points at `../`, which was the Wii menu when it lived at `/` but is
  now the landing page — it should be `../wii/`. And the Wii menu itself only
  navigates for the TTR slot; the mii/music/codebusters channel pages are not
  wired to any channel tile.
## Conventions / gotchas

- **Links are relative** and assume `site/`-as-root. When adding pages, keep paths
  relative; the only absolute paths are a couple that already encode the page's
  own location (e.g. astro's `/projects/astro/static/…`) and `site/404.html`'s
  `/home/audio/…` (absolute so the 404 game works at any URL).
- This site was lifted from `chinmaygovind.github.io/public`. The Wii menu briefly
  sat at `/` but now lives at `/wii/`; `/` is a simple landing page and the older
  projects page stayed at `/home/`. Dead Create-React-App refs (`%PUBLIC_URL%`,
  `logo192.png`, `manifest.json`) were removed.
