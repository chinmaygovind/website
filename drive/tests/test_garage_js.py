"""`CarView` built for real, against a stub three.js.

A car is now assembled out of a livery rather than out of a colour, and almost
everything that can go wrong with that is invisible to both of the checks this
project normally leans on. The autopilot never draws anything, so no lap can
notice. A screenshot can notice, but only of the one car in it - and the failures
here are of the shape "the fifth rim style is twenty-four meshes instead of one"
and "the decals are wound the wrong way so they light from underneath", which
either photograph correctly or photograph as something you would have to already
suspect to see.

So the real module runs in QuickJS the way `test_sim.py` runs the physics, and
what is pinned is the *construction*: how many meshes and materials a car costs,
that every material is reachable by `setGhostly`, that a rim is one geometry
shared by four wheels, that a decal clears the panel under it and faces up, and
above all that a car with no livery is the car Drive drew before the garage
existed.
"""

import os

import pytest

import jsrt

pytestmark = pytest.mark.skipif(not jsrt.HAVE_QUICKJS,
                                reason="needs the optional quickjs package")

RENDER_JS = os.path.join(os.path.dirname(__file__), "..", "static", "js",
                         "render.js")

# `render.js` is not in the standard bundle - the simulation does not draw - so
# it is appended here. Nothing in it runs at module scope, and the classes the
# garage does not touch (`Renderer`, `Draft`) only have to parse.
#
# The scene is the stub `Scene`, which is an `Obj3` and therefore records what
# was added to it, which is the whole of what these tests read.
HARNESS = """
var SCENE = new THREE.Scene();

/** Every mesh under a node, the scene graph walked by hand. */
function meshes(o, out) {
  out = out || [];
  if (o.geometry) out.push(o);
  for (const c of o.children || []) meshes(c, out);
  return out;
}

function build(livery, opts) {
  SCENE = new THREE.Scene();
  const v = new CarView(SCENE, livery, opts || {});
  // The shadow is added straight to the scene rather than to the car, so the
  // car's own meshes are the group's plus that one. It is counted as a mesh and
  // its material is deliberately left out of `materials`: the shadow carries
  // its own opacity (`_shadowOpacity`) and is the one thing on a car that
  // `setGhostly` is right not to touch.
  const own = meshes(v.group);
  const all = own.concat([v.shadow]);
  return {
    view: v,
    meshes: all,
    // Distinct material objects, which is the number that matters: two panels
    // sharing one material is one shader, and the two-tone roof is exactly
    // that trick.
    materials: Array.from(new Set(own.map((m) => m.material))),
  };
}

/** A summary safe to hand back to Python. */
function census(livery, opts) {
  const b = build(livery, opts);
  return {
    meshes: b.meshes.length,
    materials: b.materials.length,
    tracked: b.view._mats.length,
    // Every material on a mesh that `setGhostly` would have to reach.
    untracked: b.materials.filter((m) => b.view._mats.indexOf(m) < 0).length,
    geometries: Array.from(new Set(b.meshes.map((m) => m.geometry))).length,
    plate: b.view.plateColor,
    color: b.view.color,
    phong: b.view._mats.filter((m) => m instanceof THREE.MeshPhongMaterial).length,
    lambert: b.view._mats.filter((m) => m instanceof THREE.MeshLambertMaterial).length,
    basic: b.view._mats.filter((m) => m instanceof THREE.MeshBasicMaterial).length,
  };
}
"""


@pytest.fixture(scope="module")
def rt():
    r = jsrt.Runtime()
    r.eval(jsrt._strip_modules(jsrt._read(RENDER_JS)))
    r.eval(HARNESS)
    return r


def census(rt, livery="null", opts="{}"):
    return rt.call(f"census({livery}, {opts})")


# ---------------------------------------------------------------------------
# The car that has always been there
# ---------------------------------------------------------------------------

def test_a_bare_colour_string_is_still_a_livery(rt):
    """The ghost path, a replay saved before the garage, and a rival on a client
    that has not reloaded all hand over a hex string. None of them is going to be
    updated, so a string has to keep meaning exactly what it meant."""
    a = census(rt, "'#e8453c'")
    b = census(rt, "{body: '#e8453c'}")
    assert a == b


def test_a_car_with_no_livery_at_all_still_builds(rt):
    """`null` is what `_livery_for` gives a guest before anything is resolved and
    what an old replay frame carries."""
    assert census(rt, "null") == census(rt, "undefined") == census(rt, "{}")


def test_the_default_car_costs_exactly_what_it_used_to(rt):
    """**The check this whole file exists for.** Fourteen meshes and seven
    materials: chassis, cabin, raked windscreen, headlights, wing, two stays, four
    wheels, two brake lamps and the contact shadow, painted out of body, trim,
    glass, tyre, a material per brake lamp, and one unlit white for the headlights.

    **Fourteen is the same count the car has always had**, which is worth noticing
    rather than being a coincidence: the windscreen replaced the glass box it was
    made out of, and the headlights replaced the bumper slab that came off. The
    seventh material is the lamps' own, and it is the only thing this front costs
    that the old one did not. **A move here has to be a deliberate edit** - the car
    is drawn eight times on a full grid, so a mesh added carelessly to one is eight
    more draw calls on a phone.
    """
    c = census(rt, "null")
    assert c["meshes"] == 14
    assert c["materials"] == 7
    # Matte is `MeshLambertMaterial`, which is what every car was, so the
    # default car has no Phong anywhere on it.
    assert c["phong"] == 0


def test_the_default_trim_is_the_body_darkened_and_not_a_colour(rt):
    """`null` and not `#7f2620`. A literal would be indistinguishable today and
    would stop following the body the first time somebody repainted - so the
    check is that it *tracks*: two different bodies give two trims, each the
    x0.55 `render.js` has always used."""
    for body in ("#e8453c", "#3d8bfd", "#17bfa8"):
        assert rt.call(f"liveryOf({{body: '{body}'}}).trim.getHexString()") == \
            rt.call(f"new THREE.Color('{body}').multiplyScalar(0.55)"
                    f".getHexString()")


def test_an_explicit_trim_wins_over_the_darkening(rt):
    assert rt.call("liveryOf({body: '#e8453c', trim: '#123456'})"
                   ".trim.getHexString()") == "123456"


# ---------------------------------------------------------------------------
# setGhostly, which has to reach everything
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("livery", [
    "null",
    "{finish: 'gloss'}",
    "{rim_style: 'forged', rim: '#c9ced6'}",
    "{livery: 'fade', stripe: '#ffffff'}",
    "{badge: 'laurel'}",
    "{body: '#7b6cf6', finish: 'pearl', livery: 'twin', rim_style: 'mesh',"
    " two_tone: true, badge: 'laurel', trim: '#111111', glass: '#446688'}",
])
def test_every_material_on_the_car_is_one_setghostly_can_reach(rt, livery):
    """A car you cannot hit must not look like one you can, and that is one loop
    over `_mats`. A new slot whose material is not pushed onto it is a panel
    that stays solid while the rest of the car goes see-through - which reads as
    a rendering glitch rather than as the bug it is."""
    c = census(rt, livery)
    assert c["untracked"] == 0
    assert c["tracked"] >= 6


def test_a_ghost_is_born_translucent_and_stays_that_way(rt):
    """`_solid` is what "not translucent" means for this car, which for a ghost
    is not opaque - so a phase change must not turn a ghost into a fifth real
    car."""
    assert rt.call("build(null, {ghost: true}).view._solid") == pytest.approx(0.42)
    assert rt.call("build(null, {}).view._solid") == 1
    assert rt.call("(function () {"
                   "  const b = build({finish: 'gloss'}, {ghost: true});"
                   "  return b.view._mats.every((m) => m.transparent === true);"
                   "})()") is True


# ---------------------------------------------------------------------------
# Wheels
# ---------------------------------------------------------------------------

def test_an_unpainted_stock_wheel_is_the_wheel_it_always_was(rt):
    """Stock can be painted now, and this is the half of that which matters: with
    no colour on it there is **no rim face at all**, so the default car is exactly
    the car it was before any of this existed - which is also what keeps a plain
    car at fourteen meshes rather than eighteen, on every rival and every ghost."""
    assert census(rt, "{rim_style: 'stock'}") == census(rt, "null")


def test_a_painted_stock_wheel_grows_a_lip_and_not_five_spokes(rt):
    """The other half. It went wrong in exactly this direction once - the gate was
    on the colour, so `stock` with a colour came out wearing five spokes - so the
    shape is asserted and not just the cost: every vertex of the face is out at the
    rim, which is what makes it a lip. A spoke reaches in to 0.10 and a boss to
    zero, and either would fail this.
    """
    plain = census(rt, "null")
    painted = census(rt, "{rim_style: 'stock', rim: '#ff0000'}")
    assert painted["meshes"] - plain["meshes"] == 4
    assert painted["materials"] - plain["materials"] == 1
    assert painted["geometries"] - plain["geometries"] == 1
    # The rim is built in the wheel's own frame, where x is the axle - so the
    # radius of a vertex is in the other two.
    inner = rt.call("(function () {"
                    "  const g = rimGeometry('stock').attributes.position.array;"
                    "  let min = 1e9;"
                    "  for (let i = 0; i < g.length; i += 3)"
                    "    min = Math.min(min, Math.hypot(g[i + 1], g[i + 2]));"
                    "  return min;"
                    "})()")
    assert inner >= 0.35, "the stock face reaches in to %.3f - that is not a lip" % inner


@pytest.mark.parametrize("style", ["spoke5", "spoke6", "mesh", "dish", "forged"])
def test_a_rim_style_is_one_geometry_shared_by_four_wheels(rt, style):
    """Not a disc plus N spoke meshes. Five spokes drawn separately is twenty-four
    extra meshes on one car and nearly two hundred across a full grid, which is
    real draw-call cost on a phone - so the whole face is accumulated into one
    `MeshBuf` and the four wheels share the buffer and the material."""
    plain, rimmed = census(rt, "null"), census(rt, f"{{rim_style: '{style}'}}")
    assert rimmed["meshes"] - plain["meshes"] == 4        # one per wheel
    assert rimmed["materials"] - plain["materials"] == 1  # one shared material
    assert rimmed["geometries"] - plain["geometries"] == 1


def test_a_rim_spins_with_its_tyre(rt):
    """Parented to the wheel and not to the hub. A rim that stayed still while
    the tyre turned would be the only part of the car that is obviously wrong at
    any speed, and it is one line to get wrong."""
    assert rt.call("(function () {"
                   "  const v = build({rim_style: 'spoke5'}).view;"
                   "  return v.wheels.every((w) => w.children.length === 1);"
                   "})()") is True


def test_a_rim_is_double_sided_because_the_left_pair_are_mirrored(rt):
    assert rt.call("(function () {"
                   "  const b = build({rim_style: 'dish'});"
                   "  return b.view._mats.some((m) => m.side === THREE.DoubleSide);"
                   "})()") is True


def test_a_rim_sits_inside_the_car(rt):
    """Cosmetics may not reach the simulation, and a rim standing proud of the
    tyre would be the first thing to do it visually - the collision radius is
    1.0 either side and the wheels are at 1.0."""
    xs = rt.call("build({rim_style: 'forged'}).view.wheels"
                 ".map((w) => w.children[0].position.x)")
    assert all(abs(x) < 0.2 for x in xs)


# ---------------------------------------------------------------------------
# Decals
# ---------------------------------------------------------------------------

LIVERIES = ["centre", "twin", "band", "hoop", "halves", "fade", "pinstripe"]

# Every decal on the car, stripes and badges alike, because they share a buffer
# and therefore share every rule about lying on a panel: lifted clear of it,
# wound facing out of the car, and not drawn somewhere nobody can see. A badge is
# a decal on the bonnet in exactly the way a stripe is, and the moment it stopped
# being its own mesh it inherited all of this - so it is checked by the same
# tests rather than by copies of them.
DECALS = ([("livery", n) for n in LIVERIES]
          + [("badge", b) for b in ["laurel", "checkers", "chevrons", "crown",
                                    "podium", "sunburst", "ribbon", "shield"]])


@pytest.mark.parametrize("name", LIVERIES)
def test_a_livery_is_one_mesh_however_many_stripes_it_is(rt, name):
    plain, striped = census(rt, "null"), census(rt, f"{{livery: '{name}'}}")
    assert striped["meshes"] - plain["meshes"] == 1
    assert striped["materials"] - plain["materials"] == 1


def test_the_none_livery_is_no_mesh_at_all(rt):
    assert census(rt, "{livery: 'none', stripe: '#ffffff'}") == census(rt, "null")


# The three surfaces a decal may lie on, and which way is *out* of each. Taken
# from the chassis boxes: the `lower` box's top is 0.555 and its sides are at
# ±0.95, and the cabin's top is 1.03. The flanks are the third, added when `hoop`
# and `halves` were rebuilt - a hoop that stops at the roofline is not a hoop.
DECK, ROOF, FLANK = 0.555, 1.03, 0.95


def _panel(tri):
    """Which panel this triangle is on, how far it is proud of it, and the axis
    and sign that point out of the car.

    Decided **per triangle and not per vertex**, because a vertex alone is
    ambiguous: the widest deck stripes reach x ±0.94, which is within a
    hair of the flank plane at ±0.96, and the flanks run up to y 0.53, which is
    within a hair of the deck plane at 0.565. Every decal quad is axis-aligned,
    so the flat axis is the panel: all three x equal is a side, all three y equal
    is a top surface.

    A triangle on no panel at all is a stripe floating in the air, and one on the
    wrong side of its own panel is a stripe inside the bodywork. Both used to be
    expressible, and one of them shipped.
    """
    xs, ys = [v[0] for v in tri], [v[1] for v in tri]
    if max(xs) - min(xs) < 1e-9:
        return ("flank", 0, 1 if xs[0] > 0 else -1, abs(xs[0]) - FLANK)
    if max(ys) - min(ys) < 1e-9:
        y = ys[0]
        top = "roof" if abs(y - ROOF) < abs(y - DECK) else "deck"
        return (top, 1, 1, y - (ROOF if top == "roof" else DECK))
    return (None, None, None, None)


@pytest.mark.parametrize("slot,name", DECALS)
def test_every_decal_clears_the_panel_it_decorates(rt, slot, name):
    """Coplanar surfaces tear into each other, and at speed that reads as the
    stripe flickering rather than as z-fighting. `LIFT` is a hundredth of a unit,
    which at this scale is invisible and is far more than enough.

    Panel-aware since the flanks arrived: this used to require every vertex to be
    within 0.05 of the deck or the roof, which is a rule a vertical quad cannot
    satisfy at all - it spans y.
    """
    pos = rt.call(f"decalMesh(liveryOf({{{slot}: '{name}'}})).pos")
    assert len(pos) % 9 == 0 and pos, name
    for i in range(0, len(pos), 9):
        tri = [pos[i:i + 3], pos[i + 3:i + 6], pos[i + 6:i + 9]]
        panel, _axis, _sign, clear = _panel(tri)
        assert panel, f"{name}: triangle {i // 9} lies on no panel of the car"
        assert clear > 1e-9, \
            f"{name}: triangle {i // 9} is level with or inside the {panel}"
        assert clear < 0.05, \
            f"{name}: triangle {i // 9} floats {clear:.3f} off the {panel}"


@pytest.mark.parametrize("slot,name", DECALS)
def test_no_decal_is_hidden_under_the_cabin(rt, slot, name):
    """The cabin stands on the deck from z -0.15 to 0.9, so a deck decal that lives
    entirely inside that footprint has been drawn into the dark. A full-length
    stripe *passing* under the cabin is fine and unavoidable; being wholly under it
    is not.

    **This would not have caught the `hoop` bug**, and it is worth saying so. That
    band was full width, and the cabin is 1.55 against the body's 1.9, so two
    strips 0.175 wide did show either side of the roof - not invisible, just
    pointless. The test below is the one that catches it, by asking whether a
    livery is the shape its name claims. This one is here for the strict case,
    which is still a thing that can be written by accident.
    """
    CX, CZ0, CZ1 = 0.775, -0.15, 0.9         # the cabin box, from the chassis
    pos = rt.call(f"decalMesh(liveryOf({{{slot}: '{name}'}})).pos")
    for i in range(0, len(pos), 9):
        tri = [pos[i:i + 3], pos[i + 3:i + 6], pos[i + 6:i + 9]]
        panel, _a, _s, _c = _panel(tri)
        if panel != "deck":
            continue
        xs, zs = [v[0] for v in tri], [v[2] for v in tri]
        buried = (max(abs(x) for x in xs) < CX
                  and min(zs) > CZ0 and max(zs) < CZ1)
        assert not buried, (
            f"{name}: triangle {i // 9} is on the deck but entirely under the "
            f"cabin (x <= {max(abs(x) for x in xs):.2f}, "
            f"z {min(zs):.2f}..{max(zs):.2f}) - nobody can see it")


def _panels_of(rt, name):
    """Which panels a livery actually puts paint on."""
    pos = rt.call(f"decalMesh(liveryOf({{livery: '{name}'}})).pos")
    out = set()
    for i in range(0, len(pos), 9):
        out.add(_panel([pos[i:i + 3], pos[i + 3:i + 6], pos[i + 6:i + 9]])[0])
    return out


@pytest.mark.parametrize("name,want", [
    # The two that need the sides to be themselves at all. A hoop that stops at
    # the roofline is a painted roof, and a car split front-to-back along a line
    # only visible from above is not painted in halves. Both were exactly that.
    ("hoop", {"roof", "flank"}),
    ("halves", {"deck", "flank"}),
    # And the five that are stripes along the top, which is what they are. Named
    # here so that "add the flanks to everything" is a deliberate edit rather than
    # something that happens to one livery while nobody is looking.
    ("centre", {"deck", "roof"}),
    ("twin", {"deck", "roof"}),
    ("band", {"deck", "roof"}),
    ("pinstripe", {"deck", "roof"}),
    ("fade", {"deck"}),
])
def test_a_livery_is_on_the_panels_its_name_needs(rt, name, want):
    """The test that would have caught `hoop`. Every geometric assertion here
    passed on the old one - it was valid, wound right and properly lifted - and it
    still was not a hoop, because a hoop goes *round* something and that one only
    ever touched the top of the car."""
    assert _panels_of(rt, name) == want


@pytest.mark.parametrize("slot,name", DECALS)
def test_every_decal_faces_away_from_the_car(rt, slot, name):
    """Wound so `computeVertexNormals` points the decal outward. The obvious
    winding is the other one and it is **silently** wrong - the decal still draws,
    and it is lit from behind, so a bright stripe comes out as a dark smear on the
    one surface the sun is hitting.

    Two flanks make this sharper than it was. They are mirror images, so the
    winding that lights the right one correctly lights the left one from inside
    the bodywork: one order cannot serve both, and the old test could not see
    either - it only ever asked about the y of the normal, which a vertical quad
    has none of however it is wound.

    The stub's `computeVertexNormals` does nothing, so the cross product is taken
    here from the raw positions.
    """
    pos = rt.call(f"decalMesh(liveryOf({{{slot}: '{name}'}})).pos")
    assert len(pos) % 9 == 0 and pos
    for i in range(0, len(pos), 9):
        a, b, c = (pos[i:i + 3], pos[i + 3:i + 6], pos[i + 6:i + 9])
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        n = [u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0]]
        panel, axis, sign, _ = _panel([a, b, c])
        assert panel, f"{name}: triangle {i // 9} is on no panel"
        assert n[axis] * sign > 0, (
            f"{name} triangle {i // 9} on the {panel} is wound facing inward")


def test_a_fade_is_a_colour_ramp_in_the_vertices(rt):
    """The reason the decals go through `MeshBuf` at all: a per-vertex colour
    makes a gradient a lerp written into the attribute. A texture would have
    been the only other way, in a renderer whose whole look is having none."""
    cols = rt.call("decalMesh(liveryOf({livery: 'fade', body: '#000000',"
                   " stripe: '#ffffff'})).col")
    reds = cols[0::3]
    assert reds[0] == pytest.approx(1.0, abs=0.02)     # nose: the stripe colour
    assert reds[-1] == pytest.approx(0.0, abs=0.02)    # tail: the body's
    assert len(set(round(r, 2) for r in reds)) > 3     # and a ramp between them


def test_a_stripe_defaults_to_the_trim_colour(rt):
    assert rt.call("liveryOf({body: '#e8453c'}).stripe.getHexString()") == \
        rt.call("liveryOf({body: '#e8453c'}).trim.getHexString()")


# ---------------------------------------------------------------------------
# Finish, two-tone, badge
# ---------------------------------------------------------------------------

def test_matte_is_the_material_every_car_already_had(rt):
    """Which is why it is the only finish that may be the default: anything else
    would be a restyle of everybody who never opened the garage."""
    assert census(rt, "{finish: 'matte'}") == census(rt, "null")


@pytest.mark.parametrize("finish", ["gloss", "metallic", "pearl"])
def test_a_shiny_finish_is_phong_and_only_on_the_paint(rt, finish):
    """Glass, tyres and the lamps stay matte whatever the car is wearing: a
    shiny tyre is not a thing, and a glossy lamp lens fights the one signal on
    the car that has to be unambiguous."""
    c = census(rt, f"{{finish: '{finish}'}}")
    assert c["meshes"] == 14 and c["materials"] == 7   # costs no geometry
    assert c["phong"] == 2                             # body and trim
    assert rt.call(f"(function () {{"
                   f"  const b = build({{finish: '{finish}'}});"
                   f"  const glass = b.view._mats.filter("
                   f"    (m) => !(m instanceof THREE.MeshPhongMaterial));"
                   f"  return glass.length;"
                   f"}})()") >= 3


def _body_paint(rt, spec):
    """The colour the *body material* came out, which is not `L.body`."""
    return rt.call("(function () {"
                   "  const b = build(%s);"
                   "  return b.view._mats[0].color.getHexString();"
                   "})()" % spec)


@pytest.mark.parametrize("finish,shine,spec", [
    ("gloss", 110, 0x8b9096),
])
def test_each_finish_reaches_the_material_it_names(rt, finish, shine, spec):
    """The half of a finish that is lighting. Pinned because nothing did: the four
    could be given identical numbers and every test still passed."""
    got = rt.call("(function () {"
                  "  const m = build({finish: '%s'}).view._mats[0];"
                  "  return [m.shininess, m.specular];"
                  "})()" % finish)
    assert got == [shine, spec]


def test_a_finish_paints_itself_and_not_only_lights_itself(rt):
    """The reason the finishes were indistinguishable. The car is `flatShading`
    boxes lit by one sun, so a specular on a face is *constant across it* - nothing
    travels and nothing reflects, and the whole of what a shiny finish did was make
    a sunlit panel slightly lighter.

    There are two finishes now rather than four, and gloss carries the shiny idea
    alone - so it has to be a visible difference on its own, in the albedo as well
    as in the lighting. Wet paint is deeper and richer than dry, which is what
    `darken` and `saturate` say.
    """
    body = "#3d8bfd"
    matte = _body_paint(rt, "{body: '%s'}" % body)
    assert matte == body[1:], "matte is the colour you picked, exactly"
    wet = _body_paint(rt, "{body: '%s', finish: 'gloss'}" % body)
    gap = sum(abs(int(wet[i:i + 2], 16) - int(matte[i:i + 2], 16))
              for i in (0, 2, 4))
    assert gap >= 40, "gloss %s and matte %s are the same paint" % (wet, matte)
    # Deeper and not paler. Paler is what metallic was, and the two would have been
    # one finish under two names - which is the trap the whole finish table fell
    # into the first time.
    assert sum(int(wet[i:i + 2], 16) for i in (0, 2, 4)) \
        < sum(int(matte[i:i + 2], 16) for i in (0, 2, 4)), "gloss went lighter"


def test_a_retired_finish_still_draws_the_car_it_was_driven_in(rt):
    """`metallic` and `pearl` left the vocabulary - `garage.FINISHES` is two, so
    `validate` turns a posted one into matte - and they are **still in the renderer
    on purpose**. A stored replay carries the livery it was driven in and is never
    re-validated, so deleting them would repaint every car in every race recorded
    before they went. Same rule that stores a replay's livery with it rather than
    looking it up."""
    for gone in ("metallic", "pearl"):
        c = census(rt, "{body: '#3d8bfd', finish: '%s'}" % gone)
        assert c["phong"] == 2, gone
        assert _body_paint(rt, "{body: '#3d8bfd', finish: '%s'}" % gone) != "3d8bfd"


def test_a_finish_nobody_has_ever_heard_of_is_a_matte_car(rt):
    """`FINISH[x]` is undefined for anything not in the table, so `paintOf` and
    `mat` both have to survive being handed one - a client from after the next
    deploy, or a corrupt row."""
    c = census(rt, "{body: '#3d8bfd', finish: 'sparkle'}")
    assert c["meshes"] == 14 and c["phong"] == 0
    assert _body_paint(rt, "{body: '#3d8bfd', finish: 'sparkle'}") == "3d8bfd"


def test_the_finish_never_changes_the_colour_you_chose(rt):
    """`L.body` is what the garage swatch, the minimap dot and the nameplate are
    drawn from, so a finish that wrote back into it would answer "what colour is
    my car" with the colour the finish made of it. The transform lives on the way
    into the material and nowhere else."""
    assert rt.call("liveryOf({body: '#3d8bfd', finish: 'metallic'})"
                   ".body.getHexString()") == "3d8bfd"
    assert rt.call("build({body: '#3d8bfd', finish: 'pearl'}).view"
                   ".plateColor") == "#3d8bfd"


def test_a_finish_does_not_tint_the_stripes(rt):
    """The decal material is painted too - a stripe on a glossy car is glossy -
    but it is `0xffffff` with `vertexColors`, so a pearl tint applied there would
    multiply every stripe and every badge on the car by a lilac. That is why the
    paint half is applied at the two call sites and not inside `mat`."""
    deco = ("(function () {"
            "  const b = build({finish: 'pearl', livery: 'twin', stripe: '#ffffff'});"
            "  const m = b.view._mats.filter((x) => x.vertexColors)[0];"
            "  return m.color.getHexString();"
            "})()")
    assert rt.call(deco) == "ffffff"


def test_a_shiny_finish_is_not_standard_material(rt):
    """`MeshStandardMaterial` needs an environment map to read as metal and goes
    flat and dark without one, and there is no env map here on purpose. Pinned
    because it is the obvious thing to reach for when a finish looks
    disappointing, and the disappointment would get worse rather than better."""
    assert "new THREE.MeshStandardMaterial" not in jsrt._read(RENDER_JS)
    assert rt.call("typeof THREE.MeshStandardMaterial") == "undefined"


def test_a_roof_colour_is_the_one_thing_that_costs_a_material(rt):
    """`two_tone` was a boolean that put the roof in the *trim* colour, so a
    two-tone was always spoiler-coloured and a white roof on a red car with a black
    wing could not be asked for. The roof is its own colour now - which does cost a
    material, and it is the only slot on the car that costs one, so it is worth
    saying out loud: no colour means the cabin shares `bodyMat`, which is the common
    case and the free one.
    """
    assert census(rt, "null")["materials"] == 7
    assert census(rt, "{roof: '#ffffff'}")["materials"] == 8

    def panels(spec):
        """[body colour, cabin colour], read off the materials themselves."""
        return rt.call("(function () {"
                       f"  const b = build({spec});"
                       "  return [b.meshes[0], b.meshes[1]].map("
                       "    (m) => '#' + m.material.color.getHexString());"
                       "})()")

    body = "#7b6cf6"
    assert panels(f"{{body: '{body}'}}") == [body, body]
    assert panels(f"{{body: '{body}', roof: '#ffffff'}}") == [body, "#ffffff"]
    # And the roof is independent of the spoiler, which is the whole reason it is a
    # slot: a black wing and a white roof at once.
    assert panels(f"{{body: '{body}', trim: '#101216', roof: '#ffffff'}}") == \
        [body, "#ffffff"]


def test_two_tone_is_gone_and_says_nothing(rt):
    """It was removed rather than kept as an alias, which was the call: a car
    wearing it goes back to a body-coloured roof. So the key has to be *inert* -
    a stored `two_tone: true` must not throw and must not paint anything."""
    assert census(rt, "{two_tone: true}") == census(rt, "null")



BADGES = ["laurel", "checkers", "chevrons", "crown", "podium", "sunburst",
          "ribbon", "shield"]


@pytest.mark.parametrize("badge", BADGES)
def test_a_badge_costs_no_mesh_and_no_material(rt, badge):
    """**The whole reason a badge can be a case of seven rather than one.** It used
    to be its own mesh with its own material, which is a full draw call for a shape
    the size of a hand, on every car on the grid. Folded into the decal buffer it is
    free: a badge *is* a decal on the bonnet in exactly the way a stripe is."""
    striped = census(rt, "{livery: 'twin'}")
    both = census(rt, f"{{livery: 'twin', badge: '{badge}'}}")
    assert both["meshes"] == striped["meshes"]
    assert both["materials"] == striped["materials"]


@pytest.mark.parametrize("badge", BADGES + ["none"])
def test_the_nameplate_is_the_cars_colour_whatever_badge_is_on_it(rt, badge):
    """The plate used to go record green for the laurel, which was worth it while
    the badge was a bar on the bumper nothing could see. With seven badges, green
    would mean "wearing one of the three green ones" - not a fact worth a colour -
    and a plate per badge takes away the one thing a plate is good at, which is
    being that driver's colour."""
    c = census(rt, f"{{body: '#3d8bfd', badge: '{badge}'}}")
    assert c["plate"] == "#3d8bfd"


def test_the_record_badges_green_is_the_records_own_green(rt):
    """Kept in step with `garage.RECORD_GREEN` from the other side by
    `test_garage.py`. A badge about the record in a different green from the record
    is a badge about nothing - and three of the seven are about records."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import garage
    assert rt.call("'#' + new THREE.Color(0x55e08a).getHexString()") == \
        garage.RECORD_GREEN
    for badge in ("laurel", "crown", "chevrons"):
        assert rt.call(f"BADGE_COLOR['{badge}'] === 0x55e08a") is True


def test_every_badge_in_the_vocabulary_has_a_colour_and_a_shape(rt):
    """Two lists in two languages, and a value in one and not the other is a badge
    that either draws nothing or draws in the fallback green - both silent."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import garage
    for badge in garage.BADGES:
        if badge == "none":
            continue
        assert rt.call(f"BADGE_COLOR['{badge}'] !== undefined") is True, badge
        n = rt.call(f"decalMesh(liveryOf({{badge: '{badge}'}})).pos.length")
        assert n and n % 9 == 0, f"{badge} draws {n} floats"


def test_the_badges_are_told_apart_by_their_colours(rt):
    """Its own colour each, so the mark says what *kind* of thing was earned and
    not merely that something was: gold for having won everything, bronze for
    having been on a lot of podiums, the record's green for the record ones."""
    seen = {}
    for badge in BADGES:
        seen[badge] = rt.call(f"BADGE_COLOR['{badge}']")
    assert seen["sunburst"] != seen["podium"] != seen["ribbon"]
    # green x3, gold, bronze, road grey, silver, and the checkers' near-black.
    assert len(set(seen.values())) == 6


# ---------------------------------------------------------------------------
# The whole thing at once
# ---------------------------------------------------------------------------

def test_a_fully_loaded_car_is_still_a_cheap_car(rt):
    """Every slot filled, and this spec is deliberately the *current* vocabulary
    rather than a historical one: **19** meshes against the plain car's 14 - the four
    rims and one decal mesh carrying the stripes and the badge together. A full
    eight-car grid is therefore ~150 meshes, which is the budget the merged rim
    geometry buys and the reason it is merged: drawn the obvious way the rims alone
    would have been another 160 on top.

    It was 20 while the badge was its own mesh. Nineteen is the badge becoming free,
    which is what made a case of eight of them affordable.

    **Ten materials, not nine**, and the tenth is the roof: it is the only slot on
    the car that costs one, because a differently painted cabin cannot share
    `bodyMat`. Everything else here is a colour written into a material that already
    existed or a vertex colour in the decal buffer.
    """
    c = census(rt, "{body: '#7b6cf6', trim: '#111111', roof: '#ffffff',"
                   " glass: '#446688', rim: '#c9ced6', stripe: '#ffffff',"
                   " finish: 'gloss', livery: 'twin', rim_style: 'forged',"
                   " badge: 'laurel', badge_color: '#e8c34a'}")
    assert c["meshes"] == 19
    assert c["materials"] == 10
    assert c["untracked"] == 0


def test_no_livery_moves_anything_the_simulation_reads(rt):
    """The hard rule of this whole feature: a cosmetic that changed how the car
    drives would make every time on the board mean something different depending
    on what its driver was wearing, and the boards would quietly stop being
    comparable. `CarView` holds no collision state - the radius and the ride
    height are `tuning.py`'s - so what is checkable here is that nothing a
    livery does moves the drawn car's own frame: the wheels stay on their axles
    and the chassis stays where it sits, whatever is bolted to it.
    """
    FRAME = "build(%s).view.group.children[0].children.map("\
            "(c) => [c.position.x, c.position.y, c.position.z])"
    plain = rt.call(FRAME % "null")
    assert len(plain) == 13                       # chassis + 4 hubs + lamps
    for livery in ("{finish: 'pearl'}", "{two_tone: true}", "{rim_style: 'forged'}",
                   "{livery: 'band', stripe: '#ffffff'}",
                   "{rim_style: 'mesh', livery: 'fade', badge: 'laurel',"
                   " finish: 'metallic', two_tone: true}"):
        got = rt.call(FRAME % livery)
        # A livery may *add* to the car - a decal, a nose flash - and may never
        # move any of it. Compared as a multiset rather than as a prefix,
        # because the decal is inserted after the wheels and before the lamps
        # rather than appended.
        from collections import Counter
        a, b = (Counter(map(tuple, plain)), Counter(map(tuple, got)))
        assert not (a - b), livery


# ---------------------------------------------------------------------------
# The front
# ---------------------------------------------------------------------------
# Three rebuilds of the front were tried and reverted, and their tests went with
# them - a test for a splitter, a rake or a headlight is a test for geometry that
# is not there, and leaving it green by accident is worse than not having it.
#
# What is left is the two things that stayed true through all of it: the drawn car
# may not outgrow the collision radius, and the record badge has to be visible.
# The badge is here because it is the one part of the front that moved every time
# the rest of it did, and one of those moves drew it entirely inside the bodywork
# where nothing errored, nothing looked wrong, and the badge was simply absent.

def test_the_car_did_not_get_longer(rt):
    """A cosmetic may not change what the car *is*. The collision radius lives in
    `tuning.py` and has not moved, so anything drawn further forward than the
    body's own front face would have the car looking like it should have hit
    something before it does - and with the bumper gone, the body's front face is
    the front of the car. The lamps and the badge stand 0.01 proud of it, which is
    the least a coplanar face can stand off without z-fighting.
    """
    reach = rt.call("(function () {"
                    "  let z = 0;"
                    "  for (const c of build(null).view.group.children[0].children) {"
                    "    if (!c.geometry || !c.geometry.parameters) continue;"
                    "    const f = c.position.z - c.geometry.parameters.depth / 2;"
                    "    if (f < z) z = f;"
                    "  }"
                    "  return z;"
                    "})()")
    assert -1.72 <= reach <= -1.69, reach


@pytest.mark.parametrize("badge", BADGES)
def test_a_badge_is_on_the_clear_bonnet_and_nothing_stands_on_it(rt, badge):
    """It used to be a bar across the front bumper line, and it had to move every
    time the front of the car did - one of those moves put it at a z that was clear
    air under the old design and solid bodywork under the new one, so the badge was
    drawn *inside* the car. Nothing errored, nothing looked wrong from any angle,
    and it was simply not there.

    On the bonnet it cannot be buried by a box any more, so the question changes to
    the one that can still go wrong: is it on the stretch of bonnet you can
    actually see? The windscreen's foot is at z -0.75 and the cabin stands on the
    deck from there back, so a badge drifting past it disappears under the glass -
    which is the same failure with a different lid on it.

    The other panels are checked in the decal tests above, which the badge goes
    through too: it is on the deck plane, lifted, and wound to face up.
    """
    pos = rt.call(f"decalMesh(liveryOf({{badge: '{badge}'}})).pos")
    assert pos, badge
    xs = pos[0::3]
    zs = pos[2::3]
    NOSE, SCREEN, HALF_W = -1.7, -0.75, 0.94
    assert min(zs) >= NOSE, f"{badge} runs {min(zs):.3f} off the front of the car"
    assert max(zs) <= SCREEN, \
        f"{badge} reaches z {max(zs):.3f}, under the windscreen at {SCREEN}"
    assert max(abs(x) for x in xs) <= HALF_W, \
        f"{badge} is {max(abs(x) for x in xs):.3f} wide - past the edge of the deck"


@pytest.mark.parametrize("badge,heavy", [
    # Only the two whose silhouette is genuinely lopsided *by vertex count*, which
    # is a stricter filter than "looks lopsided". A chevron and the ribbon point
    # clearly one way to the eye and yet have as many corners at one end as the
    # other, so counting ink says nothing about them; the laurel, the sunburst and
    # the checkers are radially or fully symmetric and cannot be flipped at all; and
    # the podium's three pips are centred, so its halves match whichever way round
    # it is. Those six are covered by the mapping test directly below, which is the
    # only thing that *can* speak for them - a test that cannot fail is worse than
    # no test, so they are not listed here with a no-op expectation.
    ("crown", "bottom"),     # a full-width band, with three thin points off it
    ("shield", "top"),       # flat across the top, one point at the bottom
])
def test_a_badge_reads_from_in_front_of_the_car(rt, badge, heavy):
    """A badge on a bonnet is read by somebody standing **in front** of the car, the
    way every real one is - so the top of the icon has to be the end nearest the
    windscreen. It pointed at the nose instead, which put all of them upside down
    from the only angle a hood badge is really for.

    Checked as where the ink is rather than by naming a coordinate: the half of the
    badge with more triangles in it is the heavy end, and for a crown that is the
    band, which has to be the end furthest from the windscreen.
    """
    pos = rt.call(f"decalMesh(liveryOf({{badge: '{badge}'}})).pos")
    zs = pos[2::3]
    mid = (min(zs) + max(zs)) / 2
    # +z is toward the tail, so "toward the windscreen" is the larger z.
    near_screen = sum(1 for z in zs if z > mid)
    near_nose = sum(1 for z in zs if z < mid)
    if heavy == "top":
        assert near_screen > near_nose, (
            f"{badge}: its heavy end is toward the nose, so it is upside down")
    else:
        assert near_nose > near_screen, (
            f"{badge}: its heavy end is toward the windscreen, so it is flipped")


def test_the_top_of_a_badge_is_the_end_nearest_the_windscreen(rt):
    """The mapping every badge shares, checked once and directly rather than through
    seven silhouettes. `+z` is toward the tail of the car, so an icon coordinate that
    means "up" has to come out at a larger z than one that means "down" - and it did
    not: it was `BADGE_Z - v`, which pointed every badge at the nose.
    """
    src = jsrt._read(RENDER_JS)
    assert "BADGE_Z + v * STRETCH" in src, "the icon mapping is not tail-up"
    # And the same thing read off real geometry, so the constant above cannot be
    # right while the shape that uses it is wrong. The shield's one point is its
    # lowest coordinate, so it must be its most nose-ward vertex.
    pos = rt.call("decalMesh(liveryOf({badge: 'shield'})).pos")
    zs = pos[2::3]
    xs = pos[0::3]
    tip = min(range(len(zs)), key=lambda i: zs[i])
    assert abs(xs[tip]) < 0.02, "the most nose-ward point of a shield is not its tip"


def test_the_badge_winding_is_decided_in_world_space(rt):
    """`tri2` picks a winding so every decal faces up. It used to do that from the
    **icon-space** cross product, which depends on which way the mapping sends `v` -
    so turning the badges round to face the front silently inverted every one of
    them, and a decal wound face-down draws as a dark smear rather than as a badge.

    Pinned by reading the source, because the failure is a sign flip in a formula
    that is correct-looking either way: the test above would catch it, but only
    because these two were written together.
    """
    src = jsrt._read(RENDER_JS)
    body = src[src.index("function badgeShape"):]
    body = body[:body.index("\n}")]
    assert "const A = P(a)" in body, "tri2 no longer maps before deciding"
    assert "B[2] - A[2]" in body, "the winding test is not on world coordinates"


@pytest.mark.parametrize("badge", BADGES)
def test_a_badge_is_big_enough_to_read_and_small_enough_to_fit(rt, badge):
    """A shape drawn at the wrong scale is the one failure a screenshot of the
    garage will not show, because the garage frames the car: at 0.05 units it is a
    speck on the road and at 1.5 it is off the side of the bonnet, and both look
    deliberate from a camera three metres away."""
    pos = rt.call(f"decalMesh(liveryOf({{badge: '{badge}'}})).pos")
    w = max(pos[0::3]) - min(pos[0::3])
    d = max(pos[2::3]) - min(pos[2::3])
    assert 0.3 <= w <= 0.9, f"{badge} is {w:.2f} across"
    assert 0.3 <= d <= 0.9, f"{badge} is {d:.2f} long"


def test_the_decals_reach_the_ends_of_the_panels_they_are_on(rt):
    """The bonnet and the roof have each changed length once and changed back, and
    every stripe range that had a length written into it as a literal ran off the
    end of its own panel when they did - the roof stripes hung half a unit past the
    front of the roof, floating in the air over the windscreen. `decalMesh` names
    them for that reason; this walks every livery's vertices against the panels.
    """
    BONNET, ROOF = (-1.7, 1.7), (-0.15, 0.9)
    for name in ("centre", "twin", "band", "pinstripe", "fade", "halves"):
        pos = rt.call(f"decalMesh(liveryOf({{livery: '{name}'}})).pos")
        zs = [(pos[i + 1], pos[i + 2]) for i in range(0, len(pos), 3)]
        deck = [z for y, z in zs if abs(y - 0.565) < 1e-6]
        roof = [z for y, z in zs if abs(y - 1.04) < 1e-6]
        assert deck, name
        assert min(deck) >= BONNET[0] - 1e-9, f"{name} runs past the nose"
        assert max(deck) <= BONNET[1] + 1e-9, f"{name} runs past the tail"
        if roof:
            assert min(roof) >= ROOF[0] - 1e-9, f"{name} hangs off the roof front"
            assert max(roof) <= ROOF[1] + 1e-9, f"{name} hangs off the roof back"
