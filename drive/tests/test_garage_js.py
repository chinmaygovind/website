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
    """**The check this whole file exists for.** Sixteen meshes and seven
    materials is the stock car: chassis, cabin, glass, snout, splitter,
    headlights, wing, two stays, four wheels, two brake lamps and the contact
    shadow, painted out of body, trim, glass, tyre, a material per brake lamp,
    and one unlit white for the headlights.

    It was fourteen and six until the front was given a face. **A number moving
    here has to be a deliberate edit**, which is the whole point of pinning it -
    the car is drawn eight times on a full grid, so a mesh added carelessly to
    one is eight more draw calls on a phone. Two extra is a different order of
    decision from the twenty-four the merged rim geometry was avoiding, and the
    reasoning is in `render.js` beside the boxes.
    """
    c = census(rt, "null")
    assert c["meshes"] == 16
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

def test_stock_wheels_grow_no_rim(rt):
    """The *style* turns a rim on, not the colour. Picking a colour for a wheel
    that has no rim face must not quietly grow one - and it did, once: the gate
    was on the colour and `stock` came out with five spokes on it."""
    assert census(rt, "{rim_style: 'stock', rim: '#ff0000'}") == census(rt, "null")


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


@pytest.mark.parametrize("name", LIVERIES)
def test_a_livery_is_one_mesh_however_many_stripes_it_is(rt, name):
    plain, striped = census(rt, "null"), census(rt, f"{{livery: '{name}'}}")
    assert striped["meshes"] - plain["meshes"] == 1
    assert striped["materials"] - plain["materials"] == 1


def test_the_none_livery_is_no_mesh_at_all(rt):
    assert census(rt, "{livery: 'none', stripe: '#ffffff'}") == census(rt, "null")


@pytest.mark.parametrize("name", LIVERIES)
def test_every_decal_clears_the_panel_it_decorates(rt, name):
    """Coplanar surfaces tear into each other, and at speed that reads as the
    stripe flickering rather than as z-fighting. `LIFT` is a hundredth of a unit,
    which at this scale is invisible and is far more than enough."""
    ys = rt.call(f"liveryMesh(liveryOf({{livery: '{name}'}})).pos"
                 ".filter((_, i) => i % 3 === 1)")
    DECK, ROOF = 0.555, 1.03
    for y in ys:
        on_deck = abs(y - DECK) < 0.05
        assert on_deck or abs(y - ROOF) < 0.05, y
        assert y > (DECK if on_deck else ROOF) + 1e-9, y


@pytest.mark.parametrize("name", LIVERIES)
def test_every_decal_faces_upward(rt, name):
    """Wound anticlockwise seen from above, so `computeVertexNormals` gives an
    upward normal. The obvious winding is the other one and it is **silently**
    wrong - the decal still draws, and it is lit from underneath, so a bright
    stripe comes out as a dark smear on the one surface the sun is hitting.
    The stub's `computeVertexNormals` does nothing, so the cross product is
    taken here from the raw positions."""
    pos = rt.call(f"liveryMesh(liveryOf({{livery: '{name}'}})).pos")
    assert len(pos) % 9 == 0 and pos
    for i in range(0, len(pos), 9):
        a, b, c = (pos[i:i + 3], pos[i + 3:i + 6], pos[i + 6:i + 9])
        u = [b[k] - a[k] for k in range(3)]
        v = [c[k] - a[k] for k in range(3)]
        ny = u[2] * v[0] - u[0] * v[2]        # the y of u x v
        assert ny > 0, f"{name} triangle {i // 9} is wound face-down"


def test_a_fade_is_a_colour_ramp_in_the_vertices(rt):
    """The reason the decals go through `MeshBuf` at all: a per-vertex colour
    makes a gradient a lerp written into the attribute. A texture would have
    been the only other way, in a renderer whose whole look is having none."""
    cols = rt.call("liveryMesh(liveryOf({livery: 'fade', body: '#000000',"
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
    assert c["meshes"] == 16 and c["materials"] == 7   # costs no geometry
    assert c["phong"] == 2                             # body and trim
    assert rt.call(f"(function () {{"
                   f"  const b = build({{finish: '{finish}'}});"
                   f"  const glass = b.view._mats.filter("
                   f"    (m) => !(m instanceof THREE.MeshPhongMaterial));"
                   f"  return glass.length;"
                   f"}})()") >= 3


def test_a_shiny_finish_is_not_standard_material(rt):
    """`MeshStandardMaterial` needs an environment map to read as metal and goes
    flat and dark without one, and there is no env map here on purpose. Pinned
    because it is the obvious thing to reach for when a finish looks
    disappointing, and the disappointment would get worse rather than better."""
    assert "new THREE.MeshStandardMaterial" not in jsrt._read(RENDER_JS)
    assert rt.call("typeof THREE.MeshStandardMaterial") == "undefined"


def test_two_tone_puts_the_cabin_in_the_trim_and_costs_nothing(rt):
    """One material either way, so it is a choice of which existing one the roof
    gets rather than a seventh material."""
    assert census(rt, "{two_tone: true}")["materials"] == census(rt, "null")["materials"]

    def roof(spec):
        """[body colour, cabin colour], read off the materials themselves."""
        return rt.call("(function () {"
                       f"  const b = build({spec});"
                       "  return [b.meshes[0], b.meshes[1]].map("
                       "    (m) => '#' + m.material.color.getHexString());"
                       "})()")

    body = "#7b6cf6"
    trim = "#" + rt.call(f"new THREE.Color('{body}').multiplyScalar(0.55)"
                         f".getHexString()")
    assert roof(f"{{body: '{body}'}}") == [body, body]
    assert roof(f"{{body: '{body}', two_tone: true}}") == [body, trim]
    # And with a trim of its own, the roof follows that rather than the
    # darkening - which is the combination that makes it a two-tone rather than
    # a shaded roof.
    assert roof(f"{{body: '{body}', trim: '#f2c94c', two_tone: true}}") == \
        [body, "#f2c94c"]


def test_the_badge_is_a_nose_flash_and_a_green_nameplate(rt):
    """The plate is most of the point: a decal on a low-poly car is invisible at
    the distance you actually see rivals from, and the name over it is legible
    from anywhere."""
    plain, badged = census(rt, "null"), census(rt, "{badge: 'laurel'}")
    assert badged["meshes"] - plain["meshes"] == 1
    assert badged["plate"] == "#55e08a"
    assert plain["plate"] == plain["color"]


def test_the_badge_green_is_the_records_own_green(rt):
    """Kept in step with `garage.RECORD_GREEN` from the other side by
    `test_garage.py`. A badge about the record in a different green from the
    record is a badge about nothing."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import garage
    assert rt.call("'#' + new THREE.Color(0x55e08a).getHexString()") == \
        garage.RECORD_GREEN


# ---------------------------------------------------------------------------
# The whole thing at once
# ---------------------------------------------------------------------------

def test_a_fully_loaded_car_is_still_a_cheap_car(rt):
    """Every slot filled: 22 meshes against the plain car's 16. A full eight-car
    grid is therefore ~176 meshes, which is the budget the merged rim geometry
    buys and the reason it is merged - drawn the obvious way, the rims alone
    would have been another 160 on top."""
    c = census(rt, "{body: '#7b6cf6', trim: '#111111', glass: '#446688',"
                   " rim: '#c9ced6', stripe: '#ffffff', finish: 'pearl',"
                   " livery: 'twin', rim_style: 'forged', two_tone: true,"
                   " badge: 'laurel'}")
    assert c["meshes"] == 22
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
    assert len(plain) == 15                # chassis + front + 4 hubs + lamps
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

def test_the_headlights_are_one_mesh_and_not_two(rt):
    """Unlike the brake lamps, which change colour independently every time
    somebody touches the brakes, these never change at all - so they are one
    `MeshBuf` and one material rather than a mesh each. Two per car is four
    across a grid of eight, which is the sort of saving that only exists if
    somebody takes it."""
    # Every livery, because the front is not a slot and must cost the same on
    # all of them.
    for livery in ("null", "{finish: 'pearl'}", "{rim_style: 'mesh'}",
                   "{livery: 'band'}", "{badge: 'laurel'}"):
        n = rt.call(f"(function () {{"
                    f"  const b = build({livery});"
                    f"  return b.meshes.filter((m) => m.material"
                    f"    && m.material instanceof THREE.MeshBasicMaterial"
                    f"    && m.material.color.getHexString() === 'ffeccc').length;"
                    f"}})()")
        assert n == 1, livery


def test_the_headlights_are_never_the_drivers_colour(rt):
    """The rule the brake lamps already follow, asserted rather than trusted:
    the lamps are the only thing another driver reads off your car, which is why
    the amber drift state was taken out again. Nothing in a livery may reach
    them - not the trim, not the body, and not a finish."""
    base = rt.call("'#' + (function () {"
                   "  const b = build(null);"
                   "  return b.view._mats.find((m) =>"
                   "    m instanceof THREE.MeshBasicMaterial"
                   "    && m.color.getHexString() === 'ffeccc');"
                   "})().color.getHexString()")
    assert base == "#ffeccc"
    for livery in ("{trim: '#000000'}", "{body: '#17bfa8'}", "{finish: 'pearl'}",
                   "{two_tone: true, trim: '#ff0000'}", "{glass: '#000000'}"):
        got = rt.call(f"(function () {{"
                      f"  const b = build({livery});"
                      f"  const m = b.view._mats.find((x) =>"
                      f"    x instanceof THREE.MeshBasicMaterial"
                      f"    && x.color.getHexString() === 'ffeccc');"
                      f"  return m ? '#' + m.color.getHexString() : null;"
                      f"}})()")
        assert got == "#ffeccc", livery


def test_the_headlight_lens_fades_with_a_ghost(rt):
    """It is on `_mats`, so `setGhostly` reaches it. A lamp that stayed solid
    while the car around it went see-through would be two bright rectangles
    floating in the air."""
    assert rt.call("(function () {"
                   "  const b = build(null, {ghost: true});"
                   "  const m = b.view._mats.find((x) =>"
                   "    x instanceof THREE.MeshBasicMaterial"
                   "    && x.color.getHexString() === 'ffeccc');"
                   "  return !!m && m.transparent === true;"
                   "})()") is True


def test_the_splitter_reaches_the_corners_of_the_car(rt):
    """The old nose was 1.7 wide against a 1.9 body, so it stopped 0.1 short of
    each flank - and a bumper that does not reach the corners of the car reads
    as a bumper lying on top of one. Being flush is half of why the front stopped
    looking bolted on, and it is a number somebody could round off without
    noticing what it was for."""
    parts = rt.call("build(null).view.group.children[0].children"
                    ".filter((c) => c.geometry && c.geometry.parameters)"
                    ".map((c) => [c.position.z, c.geometry.parameters.width])")
    body = max(w for z, w in parts)                      # the chassis box
    assert body == 1.9
    front = [w for z, w in parts if z < -1.5]
    assert front, "nothing is drawn ahead of the front axle"
    assert max(front) == body, "the splitter is not flush with the flanks"


def test_the_car_did_not_get_longer(rt):
    """A cosmetic may not change what the car *is*. The collision radius lives in
    `tuning.py` and has not moved, so a nose drawn further forward than the old
    one would have the car looking like it should have hit something before it
    does. The old slab reached z = -2.2; nothing may reach past it by more than
    the blade's own few centimetres.
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
    assert -2.30 <= reach <= -2.15, reach


def test_the_snout_is_as_deep_as_the_car_is(rt):
    """At 0.30 tall it met the bonnet deck correctly and left its underside a
    quarter of a unit above the floor, so between the body's front face and the
    splitter there was a slot of open air you could see daylight through -
    which looks worse than the slab it replaced, and looks *fine* from every
    angle except the two that matter."""
    parts = rt.call("build(null).view.group.children[0].children"
                    ".filter((c) => c.geometry && c.geometry.parameters"
                    "               && c.position.z < -1.5)"
                    ".map((c) => [c.position.y, c.geometry.parameters.height])")
    # The lowest point of the tallest thing up front, against the chassis floor.
    tall = max(parts, key=lambda p: p[1])
    assert tall[0] - tall[1] / 2 < 0.12, "the snout leaves a slot under it"


def test_the_record_badge_is_on_the_nose_and_not_inside_it(rt):
    """It used to sit at z -1.86, which was clear air in front of the old slab
    and is the middle of the snout now - so rebuilding the front drew the badge
    entirely inside the bodywork, where it was invisible from every angle and
    from every screenshot. Nothing about it errored and nothing about it looked
    wrong; it was simply not there.

    So: it has to be at least as far forward as the frontmost bodywork.
    """
    front = rt.call("(function () {"
                    "  const parts = build({badge: 'laurel'}).view.group"
                    "    .children[0].children"
                    "    .filter((c) => c.geometry && c.geometry.parameters)"
                    "    .map((c) => [c.position.z - c.geometry.parameters.depth / 2,"
                    "                 c.geometry.parameters.width]);"
                    "  return parts;"
                    "})()")
    plain = rt.call("(function () {"
                    "  return build(null).view.group.children[0].children"
                    "    .filter((c) => c.geometry && c.geometry.parameters)"
                    "    .map((c) => c.position.z - c.geometry.parameters.depth / 2);"
                    "})()")
    # The badge is the box the loaded car has and the plain one does not.
    badge = [z for z, w in front if abs(w - 1.5) < 1e-9]
    assert len(badge) == 1, "the nose flash is gone"
    assert badge[0] <= min(plain) + 0.02, "the badge is buried in the bodywork"
