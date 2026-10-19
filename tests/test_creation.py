"""Trou taraudé / extrusion filetée créés sur un appui (freecadcmd tests/test_creation.py) — section 13 du cahier.

Bloc 30 × 30 × 20 ; esquisses sur le dessus (z = 20) ou dans le vide (z = 50), point de référence,
face plane cliquée, face d'extrémité d'un cylindre."""
import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD as App
import Part
from threadtool import feature, creation, thread_data
from threadtool.config import ThreadConfig

V = App.Vector
cfg = ThreadConfig()
FAILS = []


# Console Windows (cp1252) : un caractère comme « → » est remplacé au lieu de faire échouer le test.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def log(*a):
    print(*a)
    sys.stdout.flush()


def check(cond, msg):
    log(("  ok   " if cond else "  ÉCHEC ") + msg)
    if not cond:
        FAILS.append(msg)


def sketch(body, name, z, geos):
    sk = body.newObject("Sketcher::SketchObject", name)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    for g in geos:
        sk.addGeometry(g)
    return sk


def new_body(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 30, 30, 20
    doc.recompute()
    return doc, body, box


def thread_op(body, op, support, des="M5", depth=10.0, picked=None):
    t = feature.create(body, "T", op)
    t.Operation = op
    t.Support = support
    if picked is not None:
        t.SupportPoint = picked
    t.Standard, t.Designation, t.Depth = "ISO", des, depth
    body.Document.recompute()
    return t


def radii(shape, z, cx, cy):
    rs = []
    for w in shape.slice(V(0, 0, 1), z):
        for e in w.Edges:
            for q in e.discretize(Number=90):
                rs.append(math.hypot(q.x - cx, q.y - cy))
    return rs


HOLE, PAD = creation.OPERATIONS[1], creation.OPERATIONS[2]
m5 = thread_data.dims(thread_data.get("M5"))

# ------------------------------------------------------------ 1. esquisse 2 cercles Ø5 sur le dessus : trous M5
doc, body, box = new_body("C1")
sk = sketch(body, "Sk", 20, [Part.Circle(V(8, 8, 0), V(0, 0, 1), 2.5), Part.Circle(V(22, 15, 0), V(0, 0, 1), 2.5)])
t = thread_op(body, HOLE, (sk, []))
check(t.isValid(), "trous taraudés M5 sur 2 cercles valides (%s)" % t.getStatusString())
log("  messages :", t.Messages)
r = t.Shape
check(len(r.Solids) == 1 and r.isValid(), "un seul solide valide")
check(abs(r.common(Part.makeBox(30, 30, 9.99)).Volume - 30 * 30 * 9.99) < 1e-4, "rien sous le fond des trous (z = 10)")
for cx, cy in ((8, 8), (22, 15)):
    rs = [x for x in radii(r, 15, cx, cy) if x < 4]
    check(rs and abs(max(rs) - (5 + cfg.clearance) / 2) < 0.03 and abs(min(rs) - (m5["minor_int"] + cfg.clearance) / 2) < 0.03,
          "trou (%g, %g) : r min %.3f / max %.3f" % (cx, cy, min(rs or [0]), max(rs or [0])))
check(feature.ViewProviderThread.claimChildren(type("VP", (), {"Object": t})()) == [sk], "esquisse rangée sous la fonction")

# ------------------------------------------------------------ 2. même esquisse : extrusions M5 de 8 mm
doc, body, box = new_body("C2")
sk = sketch(body, "Sk", 20, [Part.Circle(V(8, 8, 0), V(0, 0, 1), 2.5), Part.Circle(V(22, 15, 0), V(0, 0, 1), 2.5)])
t2 = thread_op(body, PAD, (sk, []), depth=8.0)
check(t2.isValid(), "extrusions filetées M5 valides (%s)" % t2.getStatusString())
r2 = t2.Shape
above = r2.common(Part.makeBox(30, 30, 10, V(0, 0, 28.001))).Volume
check(len(r2.Solids) == 1 and above < 1e-9 and r2.common(Part.makeBox(30, 30, 0.5, V(0, 0, 27.4))).Volume > 1,
      "un solide, extrusions jusqu'à z = 28 (au-delà : %.2e mm3)" % above)
check(abs(r2.common(Part.makeBox(30, 30, 20)).Volume - 30 * 30 * 20) < 1e-4, "bloc intact sous les extrusions")
rs = [x for x in radii(r2, 24, 8, 8) if x < 4]
check(rs and abs(max(rs) - (5 - cfg.clearance) / 2) < 0.03, "extrusion : r max %.3f" % max(rs or [0]))

# ------------------------------------------------------------ 3. dans le vide
sk_void = sketch(body, "SkVide", 50, [Part.Circle(V(15, 15, 0), V(0, 0, 1), 2.5)])
for op, msg in ((HOLE, creation.VOID_HOLE), (PAD, creation.VOID_PAD)):
    tv = feature.create(body, "Vide")
    tv.Operation, tv.Support, tv.Designation, tv.Depth = op, (sk_void, []), "M5", 10
    tv.BaseFeature = box
    try:
        feature.creation_context(tv, box.Shape, cfg)
        got = "aucune erreur"
    except Exception as e:
        got = str(e)
    check(got.startswith(msg), "%s dans le vide : « %s »" % (op, got))

# ------------------------------------------------------------ 4. cercles de Ø différents
sk_mix = sketch(body, "SkMix", 20, [Part.Circle(V(8, 8, 0), V(0, 0, 1), 2.5), Part.Circle(V(22, 22, 0), V(0, 0, 1), 3)])
tm = feature.create(body, "Mix")
tm.Operation, tm.Support, tm.Designation = HOLE, (sk_mix, []), "M5"
tm.BaseFeature = box
try:
    feature.creation_context(tm, box.Shape, cfg)
    got = ""
except Exception as e:
    got = str(e)
check("Ø différents" in got, "Ø différents refusés : « %s »" % got)

# ------------------------------------------------------------ 5. face plane cliquée + point de référence
doc, body, box = new_body("C5")
top = [("Face%d" % (i + 1)) for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 20) < 1e-9][0]
t5 = thread_op(body, HOLE, (box, [top]), des="M6", depth=12, picked=V(10, 20, 20))
check(t5.isValid(), "face plane cliquée : trou M6 valide (%s)" % t5.getStatusString())
rs = [x for x in radii(t5.Shape, 14, 10, 20) if x < 5]
check(rs and abs(max(rs) - (6 + cfg.clearance) / 2) < 0.03, "trou centré sur le point cliqué (r max %.3f)" % max(rs or [0]))
pt = body.newObject("PartDesign::Point", "Pt")
pt.MapMode = "Deactivated"
pt.Placement = App.Placement(V(5, 5, 0), App.Rotation())        # sur la face du dessous
doc.recompute()
t6 = thread_op(body, HOLE, (pt, []), des="M4", depth=6)
check(t6.isValid(), "point de référence sur la face du dessous : trou M4 (%s)" % t6.getStatusString())
check(abs(t6.Shape.common(Part.makeBox(30, 30, 20, V(0, 0, 0))).Volume - t5.Shape.Volume) > 1, "matière enlevée")
check(abs(t6.Shape.common(Part.makeBox(30, 30, 13.99, V(0, 0, 6.01))).Volume -
          t5.Shape.common(Part.makeBox(30, 30, 13.99, V(0, 0, 6.01))).Volume) < 1e-4, "trou vers le haut, arrêté à z = 6")
pv = body.newObject("PartDesign::Point", "PtVide")
pv.MapMode = "Deactivated"
pv.Placement = App.Placement(V(5, 5, 100), App.Rotation())
doc.recompute()
tv = feature.create(body, "PtV")
tv.Operation, tv.Support, tv.Designation = HOLE, (pv, []), "M4"
tv.BaseFeature = t6
try:
    a = creation.resolve(tv.Support, t6.Shape)
    check(abs(a.normal.z) > 0.999, "point dans le vide : axe Z")
    feature.creation_context(tv, t6.Shape, cfg)
    got = ""
except Exception as e:
    got = str(e)
check(got.startswith(creation.VOID_HOLE), "point dans le vide : « %s »" % got)

# ------------------------------------------------------------ 6. face d'extrémité d'un cylindre (centre du cercle)
doc, body, box = new_body("C6")
skc = sketch(body, "SkD10", 20, [Part.Circle(V(15, 15, 0), V(0, 0, 1), 5)])
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile, pad.Length = skc, 15
doc.recompute()
end = [("Face%d" % (i + 1)) for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 35) < 1e-9][0]
a = creation.resolve((pad, [end]), pad.Shape, V(17, 16, 35))
check(abs(a.centers[0].x - 15) < 1e-9 and abs(a.centers[0].y - 15) < 1e-9 and abs(a.radius - 5) < 1e-9,
      "face bordée d'un cercle : centre du cercle, Ø 10 proposé")
t7 = thread_op(body, HOLE, (pad, [end]), des="M5", depth=10)
check(t7.isValid() and len(t7.Shape.Solids) == 1, "trou M5 au centre de l'extrusion Ø10 (%s)" % t7.getStatusString())

# ------------------------------------------------------------ 7. point : étude de la face de contact (0.6.1)
def shaft_body(name):
    """Bloc 30 × 30 × 20 + extrusion Ø10 de z = 20 à z = 35, centrée en (15, 15)."""
    doc, body, box = new_body(name)
    skc = sketch(body, "SkD10", 20, [Part.Circle(V(15, 15, 0), V(0, 0, 1), 5)])
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile, pad.Length = skc, 15
    doc.recompute()
    return doc, body, pad


def datum(body, name, p):
    pt = body.newObject("PartDesign::Point", name)
    pt.MapMode = "Deactivated"
    pt.Placement = App.Placement(p, App.Rotation())
    body.Document.recompute()
    return pt


def cyl_face(shape, r):
    return [("Face%d" % (i + 1)) for i, f in enumerate(shape.Faces)
            if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - r) < 1e-9][0]


doc, body, pad = shaft_body("C7")
shaft = cyl_face(pad.Shape, 5)
ct = creation.contact(pad.Shape, V(17, 15, 35))
check(ct and ct.thread_face == shaft and ct.arc is not None, "point sur le bout de l'arbre : cercle → %s (%s)" %
      (shaft, ct.desc if ct else None))
ct = creation.contact(pad.Shape, V(0, 15, 10))
check(ct and ct.thread_face is None and abs(abs(ct.normal.x) - 1) < 1e-9, "point sur un flanc du bloc : aucun cercle, "
      "normale X (%s)" % (ct.desc if ct else None))
ct = creation.contact(pad.Shape, V(20, 15, 25))
check(ct and ct.thread_face == shaft and abs(abs(ct.normal.x) - 1) < 1e-9, "point sur la face cylindrique : "
      "elle-même, normale radiale")
check(creation.contact(pad.Shape, V(5, 5, 60)) is None, "point dans le vide : pas de face de contact")

p_end = datum(body, "PtBout", V(17, 15, 35))
t = thread_op(body, "Existant", (p_end, []), des="M10", depth=8)
check(t.isValid() and t.FaceName == shaft and t.DetectedKind == "arbre" and abs(t.DetectedDiameter.Value - 10) < 1e-6,
      "point sur le bout de l'arbre, « fileter la face existante » : M10 sur %s (%s)" % (t.FaceName, t.getStatusString()))

doc, body, pad = shaft_body("C7b")
p_side = datum(body, "PtFlanc", V(0, 15, 10))
t = thread_op(body, "Existant", (p_side, []), des="M5", depth=6)
check(not t.isValid() and creation.NO_ARC in t.getStatusString(),
      "point sur un flanc, « fileter la face existante » refusé : %s" % t.getStatusString())
doc, body, pad = shaft_body("C7c")
p_side = datum(body, "PtFlanc", V(0, 15, 10))
t = thread_op(body, HOLE, (p_side, []), des="M5", depth=6)
check(t.isValid() and len(t.Shape.Solids) == 1 and t.Shape.Volume < pad.Shape.Volume - 50,
      "point sur un flanc : trou taraudé M5 perpendiculaire au flanc (%s)" % t.getStatusString())
doc, body, pad = shaft_body("C7d")
p_side = datum(body, "PtFlanc", V(0, 15, 10))
t = thread_op(body, PAD, (p_side, []), des="M5", depth=6)
check(t.isValid() and len(t.Shape.Solids) == 1 and t.Shape.BoundBox.XMin < -5.9,
      "point sur un flanc : extrusion filetée M5 vers l'extérieur (%s)" % t.getStatusString())

doc, body, pad = shaft_body("C7e")
skp = sketch(body, "SkPt", 20, [Part.Point(V(5, 25, 0))])
skp.setConstruction(0, True)
doc.recompute()
a = creation.resolve((skp, []), pad.Shape)
check(a.radius is None and "point de construction" in a.desc and a.contact is not None,
      "esquisse avec un point de construction : appui ponctuel étudié (%s)" % a.desc)
t = thread_op(body, HOLE, (skp, []), des="M4", depth=8)
check(t.isValid() and t.Shape.Volume < pad.Shape.Volume - 50, "point de construction : trou taraudé M4 (%s)" %
      t.getStatusString())

log("\nCRÉATION : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
