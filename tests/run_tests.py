"""Tests sans interface : freecadcmd tests/run_tests.py  (ou depuis la console Python de FreeCAD).

Variable d'environnement facultative THREADTOOL_TESTS="nom1,nom2" pour n'en lancer que certains."""
import os
import sys
import time
import math
import traceback

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("THREADTOOL_LANG", "fr")         # les messages vérifiés sont en français

import FreeCAD as App
import Part
from threadtool.config import ThreadConfig
from threadtool.axis import NotThreadable
from threadtool import detect, builder, standards, thread_data, thread_spec
from threadtool.thread_spec import ThreadSpec

V = App.Vector
cfg = ThreadConfig()          # valeurs d'usine, indépendantes des préférences de l'utilisateur
RESULTS = []


# Console Windows (cp1252) : un caractère comme « → » est remplacé au lieu de faire échouer le test.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def log(*a):
    print(*a)
    sys.stdout.flush()


def find_face(shape, radius, kind=None):
    for i, f in enumerate(shape.Faces):
        s = f.Surface
        if isinstance(s, Part.Cylinder) and abs(s.Radius - radius) < 1e-6:
            return "Face%d" % (i + 1)
    raise AssertionError("face de rayon %s introuvable" % radius)


def test(fn):
    sel = os.environ.get("THREADTOOL_TESTS")
    if sel and fn.__name__ not in sel.split(","):
        return fn
    t = time.time()
    try:
        fn()
        RESULTS.append((fn.__name__, "OK", time.time() - t, ""))
        log("OK    %-28s %5.1fs" % (fn.__name__, time.time() - t))
    except Exception as e:
        RESULTS.append((fn.__name__, "ÉCHEC", time.time() - t, str(e)))
        log("ÉCHEC %-28s %5.1fs  %s" % (fn.__name__, time.time() - t, e))
        traceback.print_exc()
        sys.stdout.flush()
    return fn


def section_radii(shape, a, c, t):
    """Tous les rayons des points d'une coupe perpendiculaire à l'axe."""
    rs = []
    for w in shape.slice(a, a.dot(c) + t):
        for q in detect.wire_points(w, 400):
            d = q - c
            rs.append((d - a * d.dot(a)).Length)
    return rs


def cross_section_radii(shape, a, c, t):
    """Rayons min / max d'une coupe perpendiculaire à l'axe."""
    rs = section_radii(shape, a, c, t)
    return min(rs), max(rs)


def adapter():
    """Cylindre d'adaptation : Ø ext 4 (M4), trou 2,459 (D1 du M3), longueur 12."""
    return Part.makeCylinder(2.0, 12).cut(Part.makeCylinder(2.459 / 2, 12))


# ---------------------------------------------------------------- données
@test
def data_tables():
    assert len(thread_data.ALL) > 250, len(thread_data.ALL)
    m = thread_data.dims(thread_data.get("M3"))
    assert abs(m["minor_int"] - 2.459) < 1e-3 and abs(m["d2"] - 2.675) < 1e-3
    m = thread_data.dims(thread_data.get('1/4"-20 UNC'))
    assert abs(m["minor_ext"] - 4.838) < 1e-3
    m = thread_data.dims(thread_data.get("Tr12×3"))
    assert abs(m["minor_ext"] - 8.5) < 1e-6 and abs(m["d2"] - 10.5) < 1e-6
    m = thread_data.dims(thread_data.get('1/2" NPT'))
    assert abs(m["d2"] - 19.264) < 1e-3


@test
def proposals():
    def first(kind, d, **kw):
        c = ThreadConfig()
        for k, v in kw.items():
            setattr(c, k, v)
        return standards.propose(kind, d, c)[0].entry.name
    assert first("arbre", 4.0) == "M4"
    assert first("arbre", 6.35, units_pref="both") == '1/4"-20 UNC'
    # par défaut, un trou est dessiné au Ø du taraud voulu : Ø3 → M3, Ø4 → M4
    assert first("trou", 3.0) == "M3", first("trou", 3.0)
    assert first("trou", 4.0) == "M4"
    # ancien mode : trou au Ø de perçage
    assert first("trou", 2.5, hole_reference="drill") == "M3"
    assert first("trou", 3.3, hole_reference="drill") == "M4"
    assert first("trou", 11.8, hole_reference="drill") == "G 1/4", first("trou", 11.8, hole_reference="drill")
    assert first("arbre", 10.0, series_pref="fine") == "M10×1.25"


@test
def choices_sorted_and_series():
    iso = sorted([e for e in thread_data.ALL if thread_data.choice_key(e) == "ISO|coarse"], key=lambda e: (e.d, -e.P))
    assert [e.name for e in iso[:4]] == ["M1", "M1.2", "M1.4", "M1.6"], [e.name for e in iso[:4]]
    fine = [e for e in thread_data.ALL if thread_data.choice_key(e) == "ISO|fine"]
    assert all(e.series == "fine" for e in fine) and "M10×1.25" in [e.name for e in fine]
    keys = {k for k, *_ in thread_data.CHOICES}
    assert all(thread_data.choice_key(e) in keys for e in thread_data.ALL)


@test
def pitch_override_M3_04():
    """M3 au pas personnalisé de 0,4 : cotes recalculées avec le nouveau pas."""
    sh = Part.makeCylinder(1.5, 10)
    info = detect.analyse(sh, find_face(sh, 1.5), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("M3"), 0.4)
    assert spec.pitch == 0.4 and spec.entry().P == 0.4
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=6)
    assert res.isValid() and len(res.Solids) == 1
    root = min(r for r in section_radii(res, V(0, 0, 1), V(0, 0, 0), 7.0))
    expect = (3 - 1.226869 * 0.4 - cfg.clearance) / 2
    assert abs(root - expect) < 0.03, (root, expect)


# ---------------------------------------------------------------- détection
@test
def detect_tube():
    sh = adapter()
    i_out = detect.analyse(sh, find_face(sh, 2.0), None, cfg)
    i_in = detect.analyse(sh, find_face(sh, 2.459 / 2), None, cfg)
    assert i_out["kind"] == "arbre", i_out["kind"]
    assert i_in["kind"] == "trou", i_in["kind"]
    assert abs(i_out["diameter"] - 4.0) < 1e-3 and abs(i_in["diameter"] - 2.459) < 1e-3
    assert i_out["ends"]["low"]["free"] and i_out["ends"]["high"]["free"]


@test
def detect_revolution():
    prof = Part.makePolygon([V(1, 0, 0), V(3, 0, 0), V(3, 0, 8), V(1, 0, 8), V(1, 0, 0)])
    sh = Part.Face(prof).revolve(V(0, 0, 0), V(0, 0, 1), 360)
    sh = Part.Solid(Part.Shell(sh.Faces)) if sh.ShapeType != "Solid" else sh
    kinds = sorted(detect.analyse(sh, "Face%d" % (i + 1), None, cfg)["kind"]
                   for i, f in enumerate(sh.Faces) if not isinstance(f.Surface, Part.Plane))
    assert kinds == ["arbre", "trou"], kinds


@test
def detect_cone_refused():
    sh = Part.makeCone(5, 3, 10)
    f = [n for n in ("Face1", "Face2", "Face3") if isinstance(sh.getElement(n).Surface, Part.Cone)][0]
    try:
        detect.analyse(sh, f, None, cfg)
    except NotThreadable as e:
        assert "Cône" in str(e), e
        return
    raise AssertionError("cône accepté")


@test
def detect_taper_1_16():
    L = 16.0
    sh = Part.makeCone(10.0, 10.0 - L / 32, L)
    f = [n for n in ("Face1", "Face2", "Face3") if isinstance(sh.getElement(n).Surface, Part.Cone)][0]
    info = detect.analyse(sh, f, None, cfg)
    assert abs(abs(info["half_angle"]) - detect.TAPER_HALF_ANGLE) < 0.01, info["half_angle"]
    names = [c.entry.name for c in standards.propose("arbre", 20.0, cfg, tapered_face=True)[:4]]
    assert all(thread_data.get(n).taper for n in names), names


@test
def default_face_shaft_on_plate():
    plate = Part.makeBox(30, 30, 5, V(-15, -15, -5))
    shaft = Part.makeCylinder(4, 15)
    sh = plate.fuse(shaft).removeSplitter()
    info, side = detect.find_default(sh, cfg)
    assert info and info["kind"] == "arbre" and abs(info["R"] - 4) < 1e-3, info and info["R"]
    assert side == "high", side
    assert not info["ends"]["low"]["free"]


@test
def default_face_two_free_prefers_positive():
    sh = adapter()
    info, side = detect.find_default(sh, cfg)
    assert side == "high"


# ---------------------------------------------------------------- génération
def _check_thread(sh, info, res, p, expect_min, expect_max):
    """Coupe au milieu de la zone filetée : rayons attendus (à 0,03 mm près)."""
    a, c = info["axis"], info["center"]
    t = p.t0 + p.u * min(p.depth / 2, p.depth - p.lead)
    rmin, rmax = cross_section_radii(res, a, c, t)
    return rmin, rmax


@test
def shaft_M4():
    sh = adapter()
    info = detect.analyse(sh, find_face(sh, 2.0), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("M4"))
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=8)
    assert res.isValid()
    a, c = info["axis"], info["center"]
    m = thread_data.dims(thread_data.get("M4"))
    rmin, rmax = None, 0
    radii = []
    for k in range(6):
        t = 12 - 2 - k * 0.11
        radii += section_radii(res, a, c, t)
    outer = max(radii)
    assert abs(outer - (4 - cfg.clearance) / 2) < 0.02, outer
    # le fond du filet (au rayon > trou intérieur) doit être proche de d3 - jeu
    root = min(r for r in radii if r > 1.5)
    assert abs(root - (m["minor_ext"] - cfg.clearance) / 2) < 0.05, root
    # le bas (non fileté, z < 4) garde son Ø
    assert abs(cross_section_radii(res, a, c, 1.0)[1] - 2.0) < 1e-3


@test
def hole_M3():
    sh = adapter()
    info = detect.analyse(sh, find_face(sh, 2.459 / 2), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("M3"))
    res, p = builder.build(sh, info, spec, cfg, side="low", depth=6)
    assert res.isValid() and len(res.Solids) == 1
    a, c = info["axis"], info["center"]
    radii = []
    for k in range(6):
        radii += section_radii(res, a, c, 3 + k * 0.09)
    inner = min(radii)
    assert abs(inner - (2.459 + cfg.clearance) / 2) < 0.02, inner
    root = max(r for r in radii if r < 1.9)
    assert abs(root - (3.0 + cfg.clearance) / 2) < 0.05, root


@test
def oblique_truncation():
    cyl = Part.makeCylinder(5, 20)
    # plan oblique à 30°, coupe le haut
    n = V(0, math.sin(math.radians(30)), math.cos(math.radians(30)))
    box = Part.makeBox(100, 100, 100, V(-50, -50, 0))
    box.rotate(V(0, 0, 0), V(1, 0, 0), -30)
    box.translate(V(0, 0, 15))
    sh = cyl.cut(box)
    info = detect.analyse(sh, find_face(sh, 5), None, cfg)
    assert info["kind"] == "arbre"

    spec = thread_spec.from_entry(thread_data.get("M10"))
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=8)
    assert res.isValid() and len(res.Solids) == 1
    # le filet ne dépasse pas : la pièce filetée est contenue dans l'originale
    assert res.cut(sh).Volume < 1e-4, res.cut(sh).Volume
    assert info["ends"]["high"]["free"], "bout oblique non reconnu comme libre"


@test
def add_material_clipped():
    """Arbre Ø 3,7 fileté en M4 : ajout de matière découpé par le plan oblique."""
    cyl = Part.makeCylinder(1.85, 12)
    box = Part.makeBox(50, 50, 50, V(-25, -25, 0))
    box.rotate(V(0, 0, 0), V(1, 0, 0), -30)
    box.translate(V(0, 0, 11))
    sh = cyl.cut(box)
    info = detect.analyse(sh, find_face(sh, 1.85), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("M4"))
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=6)
    assert res.isValid() and len(res.Solids) == 1
    # rien au-delà du plan oblique d'origine ni du dessus
    assert res.common(box).Volume < 1e-4, res.common(box).Volume
    assert res.optimalBoundingBox().ZMax <= sh.BoundBox.ZMax + 1e-3, res.optimalBoundingBox().ZMax
    assert info["ends"]["high"]["free"], "bout tronqué non reconnu comme libre"
    c2 = ThreadConfig()
    c2.allow_add_material = False
    try:
        builder.build(sh, info, spec, c2, side="high", depth=6)
    except NotThreadable:
        pass
    else:
        raise AssertionError("ajout de matière non refusé")


@test
def tr12_left_hand():
    sh = Part.makeCylinder(6, 20)
    info = detect.analyse(sh, find_face(sh, 6), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("Tr12×3"))
    spec.left_hand = True
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=12)
    assert res.isValid() and len(res.Solids) == 1


@test
def custom_lid_pair():
    """Pot Ø 70 (filet extérieur, Ø gardé) et couvercle dessiné avec 0,8 mm de jeu (Ø nominal 70 saisi).

    L'emboîtement est vérifié sur une tranche centrale, loin des fins de filet."""
    pot = Part.makeCylinder(35, 30).cut(Part.makeCylinder(32, 30, V(0, 0, 2)))
    lid = Part.makeCylinder(39, 20).cut(Part.makeCylinder(35.4, 18))
    sp = ThreadSpec(pitch=4, starts=2, flank_a=45, flank_b=45, depth=1.6, d=0)
    sl = ThreadSpec(pitch=4, starts=2, flank_a=45, flank_b=45, depth=1.6, d=70)
    ip = detect.analyse(pot, find_face(pot, 35), None, cfg)
    il = detect.analyse(lid, find_face(lid, 35.4), None, cfg)
    assert ip["kind"] == "arbre" and il["kind"] == "trou"
    rp, pp = builder.build(pot, ip, sp, cfg, side="high", depth=26)
    rl, pl = builder.build(lid, il, sl, cfg, side="low", depth=16)
    assert rp.isValid() and rl.isValid() and len(rl.Solids) == 1
    rmin_lid = min(section_radii(rl, V(0, 0, 1), V(0, 0, 0), 8.0))
    assert rmin_lid < 35 - 1.0, rmin_lid                   # couvercle rebouché puis taraudé
    slab = Part.makeCylinder(50, 6, V(0, 0, 15))
    pot_s = rp.common(slab)

    def inter(angle):
        l2 = rl.copy()
        l2.rotate(V(0, 0, 0), V(0, 0, 1), angle)
        l2.translate(V(0, 0, 10))
        return pot_s.common(l2).Volume
    vals = {k * 15.0: inter(k * 15.0) for k in range(12)}      # motif périodique de 180° (2 filets)
    worst = max(vals.values())
    a0 = min(vals, key=vals.get)
    for step in (3.0, 0.5):
        for k in range(-5, 6):
            ang = a0 + k * step
            if ang not in vals:
                vals[ang] = inter(ang)
        a0 = min(vals, key=vals.get)
    best = vals[a0]
    log("  ->  interférence pot / couvercle (tranche centrale) : min %.4f (à %.1f°), max %.2f mm3" % (best, a0, worst))
    assert best < 1e-3, best        # il existe une position où ça se visse
    assert worst > 1.0, worst       # et les filets s'emboîtent vraiment


@test
def custom_profile_error():
    sh = Part.makeCylinder(5, 10)
    info = detect.analyse(sh, find_face(sh, 5), None, cfg)
    spec = ThreadSpec(pitch=1, flank_a=30, flank_b=30, depth=2.0, d=0)
    try:
        builder.build(sh, info, spec, cfg, side="high", depth=5)
    except NotThreadable as e:
        assert "Profil impossible" in str(e)
        return
    raise AssertionError("profil impossible accepté")


@test
def npt_on_cylinder():
    sh = Part.makeCylinder(21.336 / 2, 25)
    info = detect.analyse(sh, find_face(sh, 21.336 / 2), None, cfg)
    spec = thread_spec.from_entry(thread_data.get('1/2" NPT'))
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=13.5)
    assert res.isValid() and len(res.Solids) == 1
    a, c = info["axis"], info["center"]
    # Ø de sommet plus petit au bout libre qu'au fond du filet (conique)
    r_top = cross_section_radii(res, a, c, 25 - 1.0)[1]
    r_low = cross_section_radii(res, a, c, 25 - 12.0)[1]
    assert r_low - r_top > 0.25, (r_top, r_low)


@test
def blind_hole_in_block():
    blk = Part.makeBox(20, 20, 15).cut(Part.makeCylinder(3.4, 10, V(10, 10, 5)))
    info, side = detect.find_default(blk, cfg)
    assert info["kind"] == "trou", info["kind"]
    assert side == "high" and info["ends"]["high"]["free"] and not info["ends"]["low"]["free"]
    spec = thread_spec.from_entry(thread_data.get(standards.propose("trou", info["diameter"], cfg)[0].entry.name))
    res, p = builder.build(blk, info, spec, cfg, side=side)
    assert res.isValid() and len(res.Solids) == 1
    log("  ->  trou Ø %.2f → %s, profondeur %.1f" % (info["diameter"], spec.name, p.depth))


def _removed_beyond(orig, res, a, c, t_plane, toward):
    """Volume enlevé au-delà du plan t = t_plane (toward = +1 : côté t croissant)."""
    big = 200.0
    if toward > 0:
        box = Part.makeCylinder(big, big, c + a * t_plane, a)
    else:
        box = Part.makeCylinder(big, big, c + a * (t_plane - big), a)
    return orig.common(box).Volume - res.common(box).Volume


@test
def screw_head_not_cut():
    """Vis : tige Ø6 sur tête Ø10. Filet « jusqu'au bout » : rien n'est enlevé dans la tête."""
    sh = Part.makeCylinder(5, 4).fuse(Part.makeCylinder(3, 16, V(0, 0, 4))).removeSplitter()
    info = detect.analyse(sh, find_face(sh, 3), None, cfg)
    spec = thread_spec.from_entry(thread_data.get("M6"))
    p0 = builder.make_plan(sh, info, spec, cfg, side="high", depth=0.001)
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=p0.available)
    a, c = V(0, 0, 1), V(0, 0, 0)          # plans repérés en z absolu
    head = _removed_beyond(sh, res, a, c, 4.0, -1)
    log("  ->  longueur %.3f, matière enlevée dans la tête : %.6f mm3" % (p0.available, head))
    assert abs(p0.available - 16.0) < 1e-3, p0.available
    assert head < 1e-4, head
    # le filet atteint bien le bout libre (premier pas sous la face d'extrémité)
    assert _removed_beyond(sh, res, a, c, 20.0 - spec.pitch, +1) > 0.05


@test
def blind_hole_cone_not_cut():
    """Perçage borgne Ø6,8 avec pointe à 118° : le taraud M8 s'arrête au raccord cylindre / cône."""
    r, depth = 3.4, 12.0
    cone_h = r / math.tan(math.radians(59))
    blk = Part.makeBox(20, 20, 20, V(-10, -10, 0))
    drill = Part.makeCylinder(r, depth, V(0, 0, 20 - depth)).fuse(
        Part.makeCone(0, r, cone_h, V(0, 0, 20 - depth - cone_h)))
    sh = blk.cut(drill).removeSplitter()
    info = detect.analyse(sh, find_face(sh, r), None, cfg)
    assert info["kind"] == "trou" and info["ends"]["high"]["free"] and not info["ends"]["low"]["free"]
    spec = thread_spec.from_entry(thread_data.get("M8"))
    p0 = builder.make_plan(sh, info, spec, cfg, side="high", depth=0.001)
    res, p = builder.build(sh, info, spec, cfg, side="high", depth=p0.available)
    a, c = V(0, 0, 1), V(0, 0, 0)          # plans repérés en z absolu
    bottom = _removed_beyond(sh, res, a, c, 20 - depth, -1)
    log("  ->  longueur %.3f, matière enlevée sous le raccord : %.6f mm3" % (p0.available, bottom))
    assert abs(p0.available - depth) < 1e-3, p0.available
    assert bottom < 1e-4, bottom
    assert _removed_beyond(sh, res, a, c, 20 - spec.pitch, +1) > 0.05     # filet jusqu'à la face d'entrée


@test
def blind_hole_flat_bottom_margin():
    """Perçage borgne à fond plat + marge de fin 1 mm : le taraud s'arrête 1 mm avant le fond."""
    blk = Part.makeBox(20, 20, 15, V(-10, -10, 0)).cut(Part.makeCylinder(3.4, 10, V(0, 0, 5)))
    info = detect.analyse(blk, find_face(blk, 3.4), None, cfg)
    c2 = ThreadConfig()
    c2.end_margin = 1.0
    spec = thread_spec.from_entry(thread_data.get("M8"))
    p0 = builder.make_plan(blk, info, spec, c2, side="high", depth=0.001)
    res, p = builder.build(blk, info, spec, c2, side="high", depth=50)
    a, c = V(0, 0, 1), V(0, 0, 0)          # plans repérés en z absolu
    assert abs(p.depth - 9.0) < 1e-3, p.depth
    assert _removed_beyond(blk, res, a, c, 6.0, -1) < 1e-6
    assert _removed_beyond(blk, res, a, c, 7.0, -1) > 1e-3       # le filet descend bien jusqu'à ~6


def summary():
    ok = sum(1 for r in RESULTS if r[1] == "OK")
    log("\n%d / %d tests réussis" % (ok, len(RESULTS)))
    for n, s, t, m in RESULTS:
        if s != "OK":
            log("  %s : %s" % (n, m))


summary()
