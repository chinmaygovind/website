"""The scenery sandbox, and the spec that makes it usable by somebody else's AI.

Three separable things are checked here and they fail for different reasons:

* **the boundary.** A player's scenery may add `KIND.WALL` and `KIND.OFFROAD`
  to the collider and nothing else. This is the one real vulnerability in the
  whole feature: the anti-cheat re-drives submitted laps against this exact
  collider, so a user-emitted `BOOST` quad would be a speed hack that arrives
  with a certificate of authenticity. Whitelisted on the numbers, at the
  validator - never on trust in the code that produced them.
* **no second copies.** `sceneryContext`, `shade` and `mulberry` are injected
  into the sandbox as *source*, off the live `trackmesh.js` exports, so the four
  helpers a player writes against are the four the engine draws Silverstone's
  hangars with. The first hand-written `shade` in the worker was a multiplier
  where the real one takes an amount - a function that looks right and darkens
  everything it touches - which is why this is pinned rather than trusted.
* **the examples run.** They are real functions, and they are executed here
  against a real ribbon through QuickJS. A spec whose examples do not work
  teaches a model to write something that fails, and the model has no other
  source for this API to correct itself from.
"""

import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))

JS = os.path.join(HERE, "..", "static", "js")


def _js(name):
    with open(os.path.join(JS, name)) as f:
        return f.read()


# --------------------------------------------------------------- the boundary

def test_the_sandbox_allows_two_collider_kinds_and_no_others():
    """Whitelist, not blacklist, and on the numbers.

    BOOST is a pad baked into the road. BOUNCE is the same trick with a
    trampoline. ROAD is worse in a quieter way: fake surface the ground probe
    picks up, which the car drives on with no ribbon under it.
    """
    src = _js("scenery_worker.js")
    m = re.search(r"KIND_OK = new Set\(\[([^\]]*)\]\)", src)
    assert m, "the collider whitelist is gone"
    allowed = {t.strip() for t in m.group(1).split(",") if t.strip()}
    assert allowed == {"KIND.WALL", "KIND.OFFROAD"}, allowed


def test_the_iframe_is_created_without_same_origin():
    """The omission *is* the isolation.

    A Worker started from the main page inherits the page's origin, so a
    stranger's scenery could fetch our own API with the reader's cookies
    attached. `allow-scripts` alone makes the frame's origin opaque and the
    Worker inherits that: no cookies, no storage, and a request back to the site
    is a credential-less cross-origin request the site does not answer.
    """
    src = _js("make.js")
    m = re.search(r"setAttribute\('sandbox',\s*'([^']*)'\)", src)
    assert m, "the sandbox attribute is gone"
    tokens = set(m.group(1).split())
    assert tokens == {"allow-scripts"}, (
        "the sandbox frame gained a permission: %r. allow-same-origin in "
        "particular would hand untrusted code this site's cookies." % tokens)


def test_the_editor_page_declares_who_it_may_talk_to():
    """`connect-src` on /make only, and it makes that page *more* restricted.

    With no `connect-src` and no `default-src` a browser permits every
    destination there is, so this is the backstop under the sandbox: if
    untrusted scenery ever did escape its frame, there is nowhere to post what
    it found.
    """
    import app as A
    with A.app.test_client() as c:
        editor = c.get("/make").headers["Content-Security-Policy"]
        assert "connect-src 'self'" in editor
        for host in A.AI_HOSTS:
            assert host in editor, host
        # and nowhere else, because every other page here talks only to itself
        for path in ("/", "/solo/sunrise", "/leaderboard"):
            other = c.get(path).headers.get("Content-Security-Policy", "")
            assert "connect-src" not in other, path
            assert other.startswith("frame-ancestors "), path


def test_the_hosts_in_the_policy_are_the_providers_in_the_picker():
    """One list would drift from the other, and the failure is a provider that
    is offered in the menu and blocked by the page."""
    import app as A
    src = _js("make.js")
    for host in A.AI_HOSTS:
        assert host in src, "%s is in the CSP and in no provider" % host
    for m in re.finditer(r"https://[a-z0-9.]+\.(?:com|googleapis\.com)", src):
        if "api." in m.group(0) or "googleapis" in m.group(0):
            assert m.group(0) in A.AI_HOSTS, (
                "%s is called from make.js and not in AI_HOSTS, so the page "
                "policy will refuse it" % m.group(0))


def test_no_provider_sends_a_temperature():
    """On claude-opus-5 and claude-sonnet-5, `temperature`, `top_p` and `top_k`
    are rejected with a 400. They are gone, not deprecated - so a sampling knob
    here is not a tuning choice, it is a panel that cannot send a message."""
    src = _js("make.js")
    body = src[src.index("const PROVIDERS = {"):src.index("const CTX_API = [")]
    # Comments stripped, because the comment saying why there is no temperature
    # is not a temperature.
    body = re.sub(r"//[^\n]*", "", body)
    for knob in ("temperature", "top_p", "top_k", "topP", "topK"):
        assert knob not in body, "the AI panel sends %s" % knob


def test_the_key_never_reaches_this_server():
    """The whole design, and the reason to say it in the code as well as the UI.

    The tempting shortcut is a small proxy here that "just adds the key", which
    is an open model endpoint on this box's account holding a worker for the
    length of every call. There is no route here that takes a key, and there
    must never be one.
    """
    import app as A
    routes = [str(r) for r in A.app.url_map.iter_rules()]
    for r in routes:
        assert "gemini" not in r.lower(), r
    src = open(os.path.join(HERE, "..", "app.py")).read()
    for bad in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "x-api-key"):
        assert bad not in src, "app.py handles an AI key: %s" % bad


# ------------------------------------------------------------- no second copies

@pytest.mark.parametrize("fn", ["sceneryContext", "shade", "mulberry"])
def test_the_primitives_are_injected_and_not_copied(fn):
    """Injected by source off the live export, so the two cannot drift."""
    mesh, make, worker = (_js("trackmesh.js"), _js("make.js"),
                          _js("scenery_worker.js"))
    assert "export function %s(" % fn in mesh, (
        "%s is no longer exported, so it cannot be injected" % fn)
    assert "%s.toString()" % fn in make, (
        "%s is no longer injected into the sandbox" % fn)
    assert "function %s(" % fn not in worker, (
        "the worker carries its own %s again. That is the drift this whole "
        "arrangement exists to prevent - the first hand-written copy of shade "
        "had it as a multiplier instead of an amount." % fn)


def test_scenerycontext_closes_over_nothing():
    """Which is what makes injecting it by source legitimate rather than a trick.

    Every input arrives as a parameter. If it ever closed over a module-level
    binding, the injected copy would reference a name the sandbox does not have
    and the failure would be a ReferenceError inside somebody else's scenery.
    """
    src = _js("trackmesh.js")
    i = src.index("export function sceneryContext(")
    body = src[i:src.index("\n}", i)]
    params = re.search(r"sceneryContext\(([^)]*)\)", body).group(1)
    names = {p.strip() for p in params.split(",")}
    assert names == {"solid", "track", "pal", "terrain", "groundY", "drop"}
    # Nothing from trackmesh's module scope. GRASS_DROP in particular is a local
    # of buildTrack and is passed in as `drop` for exactly this reason.
    for leaked in ("GRASS_DROP", "KIND", "CELL", "MeshBuf", "hsl("):
        assert leaked not in body, (
            "sceneryContext reaches module scope for %s, so the injected copy "
            "would not resolve it" % leaked)


def test_the_helpers_reach_the_engines_own_scenery():
    """They are on the context the five hand-written files receive too, which is
    the point: one API, whether the caller is a player or the engine."""
    src = _js("trackmesh.js")
    i = src.index("sc.props({")
    assert "...sctx," in src[i:i + 400], (
        "the shared helpers are no longer handed to the pool's own scenery")


# ---------------------------------------------------------------- the examples

def _run_example(name):
    """Run one spec example against a real ribbon, in QuickJS.

    The same engine the anti-cheat re-drives laps in, so `trackmesh.js` and its
    exports are already loadable there. What is added is the recorder - a stub
    with the sandbox's surface - and the whitelist, so a kind the sandbox would
    refuse fails here too.
    """
    import jsrt
    if not jsrt.HAVE_QUICKJS:
        pytest.skip("needs the optional quickjs package")
    ex = jsrt._strip_modules(_js("scenery_examples.js"))
    harness = r"""
    var _out = null;
    function _runExample(name) {
      var solidTris = 0, colTris = 0, kinds = {};
      function Rec() {}
      Rec.prototype.tri = function (a, b, c) {
        for (var _i = 0, ps = [a, b, c]; _i < 3; _i++) {
          var p = ps[_i];
          if (!p || p.length < 3 || !isFinite(p[0]) || !isFinite(p[1])
              || !isFinite(p[2])) throw new Error('not a point: ' + JSON.stringify(p));
        }
        solidTris++;
      };
      Rec.prototype.quad = function (a, b, c, d, k) {
        this.tri(a, b, c, k); this.tri(a, c, d, k);
      };
      Rec.prototype.box = function (cx, cy, cz, hx, hy, hz, k) {
        if (![cx, cy, cz, hx, hy, hz].every(isFinite))
          throw new Error('box with a non-finite argument');
        for (var f = 0; f < 6; f++) this.quad([0,0,0],[0,0,0],[0,0,0],[0,0,0], k);
      };
      var solid = new Rec(), bright = new Rec();
      var col = { addQuad: function (a, b, c, d, kind) {
        if (kind !== 1 && kind !== 2) throw new Error('refused kind ' + kind);
        kinds[kind] = (kinds[kind] || 0) + 1; colTris += 2;
      } };
      // `load_tuning_and_tracks` pushes the pool as `TRACKS`, a list.
      var t = null;
      for (var _k = 0; _k < TRACKS.length; _k++)
        if (TRACKS[_k].slug === 'spa') t = TRACKS[_k];
      if (!t) throw new Error('spa is not in the pool');
      var ctx = sceneryContext(solid, t, t.pal, null, t.ground, 1.2);
      ctx.solid = solid; ctx.bright = bright; ctx.col = col;
      ctx.track = t; ctx.pal = t.pal;
      ctx.KIND = { WALL: 1, OFFROAD: 2 };
      ctx.shade = shade; ctx.mulberry = mulberry;
      (name === 'sheds' ? sheds : insideBarrier)(ctx);
      _out = JSON.stringify({ solid: solidTris, col: colTris, kinds: kinds });
    }
    """
    rt = jsrt.Runtime(extra=(ex, harness))
    rt.load_tuning_and_tracks()
    rt.eval("_runExample(%s);" % json.dumps(name))
    return json.loads(rt.call("_out"))


@pytest.mark.parametrize("name,wants_collider", [
    ("sheds", False),
    ("insideBarrier", True),
])
def test_every_spec_example_actually_runs(name, wants_collider):
    got = _run_example(name)
    assert got["solid"] > 0, "%s drew nothing" % name
    if wants_collider:
        assert got["col"] > 0, "%s adds no collider" % name
        assert set(got["kinds"]) <= {"1", "2"}, got["kinds"]
    else:
        assert got["col"] == 0


def test_the_spec_lists_everything_the_sandbox_hands_over():
    """`CTX_API` is what a model is told it has. The sandbox is what it gets.

    A key on one and not the other is the failure this whole panel exists to
    avoid: a model confidently writing against something that is not there.
    """
    make, worker = _js("make.js"), _js("scenery_worker.js")
    table = make[make.index("const CTX_API = ["):make.index("\n];", make.index(
        "const CTX_API = ["))]
    api = worker[worker.index("const api = {"):worker.index(
        "\n    };", worker.index("const api = {"))]
    # what the worker puts on the object, minus the four from sceneryContext
    # (which arrive by spread and are listed in the table individually)
    keys = set(re.findall(r"(\w+)\s*:", api)) | {"at", "spot", "ground", "face"}
    keys -= {"height", "WALL", "OFFROAD"}          # nested, not top level
    missing = [k for k in keys if k not in table]
    assert not missing, (
        "the sandbox hands over %r and the spec does not mention it, so a model "
        "will not know it exists" % missing)
