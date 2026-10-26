"""Filet fendu : une fente traverse le taraudage de part en part (freecadcmd tests/test_slot.py).

Bossage Ø16 × 15, trou Ø10 de 12 mm depuis le dessus (z = 15), M10 sur 10 mm, fente de 2 mm le long de X
depuis le dessus, de 6 mm (le filet reste entier sous la fente) ou de 14 mm (le trou est coupé en deux
moitiés). La fente est faite avant ou après le filet : le filet doit toujours aller de z = 5 à z = 15."""
import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("THREADTOOL_LANG", "fr")         # les messages vérifiés sont en français

import FreeCAD as App
import Part
from threadtool import feature, creation, detect
from threadtool.config import ThreadConfig

V = App.Vector
cfg = ThreadConfig()
FAILS = []
EXISTING, HOLE = creation.OPERATIONS[0], creation.OPERATIONS[1]
THIN = "paroi peut-être trop fine"


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


def boss(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    c = body.newObject("PartDesign::AdditiveCylinder", "Bossage")
    c.Radius, c.Height = 8, 15
    doc.recompute()
    return doc, body


def slot(body, depth, width=2.0):
    b = body.newObject("PartDesign::SubtractiveBox", "Fente")
    b.Length, b.Width, b.Height = 40, width, depth
    b.Placement = App.Placement(V(-20, -width / 2, 15 - depth), App.Rotation())
    body.Document.recompute()
    return b


def bore(body):
    b = body.newObject("PartDesign::SubtractiveCylinder", "Trou")
    b.Radius, b.Height = 5, 12
    b.Placement = App.Placement(V(0, 0, 3), App.Rotation())
    body.Document.recompute()
    return b


def bore_face(shape):
    """Face du trou Ø10 qui monte jusqu'à l'entrée (comme un clic près du dessus)."""
    faces = [i for i, f in enumerate(shape.Faces) if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 5) < 1e-6]
    return "Face%d" % (max(faces, key=lambda i: shape.Faces[i].BoundBox.ZMax) + 1)


def thread_existing(body):
    shape = body.Tip.Shape
    t = feature.create(body, "T", EXISTING)
    t.FaceName = bore_face(shape)
    e = detect.analyse(shape, t.FaceName, None, cfg)["ends"]
    t.Side = "high" if e["high"]["free"] or not e["low"]["free"] else "low"
    t.Standard, t.Designation, t.Depth = "ISO", "M10", 10
    body.Document.recompute()
    return t


def tapped_hole(body):
    doc = body.Document
    sk = body.newObject("Sketcher::SketchObject", "Esquisse")
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, 15), App.Rotation())
    sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5))
    doc.recompute()
    t = feature.create(body, "T", HOLE)
    t.Support = (sk, [])
    t.Standard, t.Designation, t.Depth = "ISO", "M10", 10
    doc.recompute()
    return t


def pocket(body):
    """Poche « à travers tout », symétrique, depuis une esquisse sur XZ : fente de 2 mm de z = 5 à z = 20."""
    sk = body.newObject("Sketcher::SketchObject", "EsquisseFente")
    xz = [o for o in body.Origin.OriginFeatures if o.Role == "XZ_Plane"][0]
    sk.AttachmentSupport = [(xz, "")]
    sk.MapMode = "FlatFace"
    pts = [V(-1, 5), V(1, 5), V(1, 20), V(-1, 20)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
    pk = body.newObject("PartDesign::Pocket", "Poche")
    pk.Profile, pk.Type, pk.Midplane = sk, "ThroughAll", True
    body.Document.recompute()
    return pk


def threaded_range(shape):
    """(z min, z max) des coupes où la paroi du trou est filetée (hors de la fente)."""
    out = []
    for k in range(1, 30):
        z = k * 0.5
        pts = [q for w in shape.slice(V(0, 0, 1), z) for q in detect.wire_points(w, 400)]
        rs = [math.hypot(q.x, q.y) for q in pts if abs(q.y) > 1.05]
        rs = [r for r in rs if r < 6.5]
        if rs and max(rs) > 5.1 and min(rs) < 5.6:
            out.append(z)
    return (min(out), max(out)) if out else None


def verify(name, body, t):
    tip = body.Tip
    ok = t.isValid() and tip.isValid() and tip.Shape.isValid() and len(tip.Shape.Solids) == 1
    rng = threaded_range(tip.Shape) if ok else None
    check(ok and rng is not None and rng[0] <= 5.5 and rng[1] >= 14.5,
          "%s : filet de z = 5 à 15 (%s ; %s)" % (name, rng, t.getStatusString()))
    check("Profondeur ramenée" not in t.Messages and "Trou débouchant" not in t.Messages and THIN not in t.Messages,
          "%s : pas d'avertissement dû à la fente (« %s »)" % (name, t.Messages))


# fente avant le filet : ses bords ne sont pas des extrémités de la face
for d in (6, 14):
    doc, body = boss("Ends%d" % d)
    bore(body)
    slot(body, d)
    sh = body.Tip.Shape
    info = detect.analyse(sh, bore_face(sh), None, cfg)
    e = info["ends"]
    zs = [round(v.Point.z, 3) for side in ("low", "high") for x in e[side]["edges"] for v in x.Vertexes]
    check(e["high"]["free"] and not e["low"]["free"] and set(zs) <= {3.0, 15.0},
          "fente de %d mm : extrémités = fond (z 3) et entrée (z 15) seulement (z des bords : %s)" % (d, sorted(set(zs))))

for name, steps in [
        ("trou, filet, fente de 6", lambda b: (bore(b), thread_existing(b), slot(b, 6))),
        ("trou, filet, fente de 14", lambda b: (bore(b), thread_existing(b), slot(b, 14))),
        ("trou, filet, poche à travers tout", lambda b: (bore(b), thread_existing(b), pocket(b))),
        ("trou, fente de 6, filet", lambda b: (bore(b), slot(b, 6), thread_existing(b))),
        ("trou, fente de 14, filet", lambda b: (bore(b), slot(b, 14), thread_existing(b))),
        ("fente de 6, trou taraudé", lambda b: (slot(b, 6), tapped_hole(b))),
        ("fente de 14, trou taraudé", lambda b: (slot(b, 14), tapped_hole(b)))]:
    doc, body = boss("Fente")
    out = steps(body)
    t = [o for o in out if o is not None and hasattr(o, "Messages")][0]
    verify(name, body, t)
    App.closeDocument(doc.Name)

# filet mâle fendu : arbre Ø10 × 15 sur une embase Ø20 × 3, fente de 2 mm depuis le bout
def shaft(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    b = body.newObject("PartDesign::AdditiveCylinder", "Embase")
    b.Radius, b.Height = 10, 3
    s = body.newObject("PartDesign::AdditiveCylinder", "Arbre")
    s.Radius, s.Height = 5, 15
    s.Placement = App.Placement(V(0, 0, 3), App.Rotation())
    doc.recompute()
    return doc, body


def shaft_slot(body, depth):
    b = body.newObject("PartDesign::SubtractiveBox", "Fente")
    b.Length, b.Width, b.Height = 40, 2, depth
    b.Placement = App.Placement(V(-20, -1, 18 - depth), App.Rotation())
    body.Document.recompute()
    return b


def shaft_range(shape):
    """(z min, z max) des coupes où l'arbre est fileté (hors de la fente)."""
    out = []
    for k in range(7, 36):
        z = k * 0.5
        pts = [q for w in shape.slice(V(0, 0, 1), z) for q in detect.wire_points(w, 400)]
        rs = [math.hypot(q.x, q.y) for q in pts if abs(q.y) > 1.05]
        rs = [r for r in rs if r < 6]
        if rs and min(rs) < 4.9:
            out.append(z)
    return (min(out), max(out)) if out else None


for d in (8, 15):
    for after in (False, True):
        doc, body = shaft("Arbre")
        if not after:
            shaft_slot(body, d)
        shape = body.Tip.Shape
        faces = [i for i, f in enumerate(shape.Faces) if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 5) < 1e-6]
        t = feature.create(body, "T", EXISTING)
        t.FaceName = "Face%d" % (max(faces, key=lambda i: shape.Faces[i].BoundBox.ZMax) + 1)
        t.Side = "high"
        t.Standard, t.Designation, t.Depth = "ISO", "M10", 10
        doc.recompute()
        if after:
            shaft_slot(body, d)
        tip = body.Tip
        rng = shaft_range(tip.Shape) if t.isValid() and tip.isValid() else None
        name = "arbre M10, fente de %d mm %s le filet" % (d, "après" if after else "avant")
        check(rng is not None and rng[0] <= 8.5 and rng[1] >= 17.5 and len(tip.Shape.Solids) == 1,
              "%s : filet de z = 8 à 18 (%s ; %s)" % (name, rng, t.getStatusString()))
        check("Profondeur ramenée" not in t.Messages and THIN not in t.Messages,
              "%s : pas d'avertissement dû à la fente (« %s »)" % (name, t.Messages))
        App.closeDocument(doc.Name)

# « Affiner » sur une fonction placée après le filet : signalé (il abîme le solide fileté)
doc, body = boss("Affiner")
bore(body)
t = thread_existing(body)
pk = pocket(body)
for on in (True, False):
    pk.Refine = on
    t.touch()
    doc.recompute()
    warned = "Affiner" in t.Messages and pk.Label in t.Messages
    check(warned == on, "« Affiner » %s sur la poche : avertissement %s (« %s »)" %
          ("activé" if on else "désactivé", "présent" if warned else "absent", t.Messages))
check(feature.refined_after_thread(t) == [], "« Affiner » de la fonction Filetage elle-même ignoré")
App.closeDocument(doc.Name)

# l'épaisseur d'un trou taraudé dont l'axe tombe dans la fente se mesure à côté de l'axe
doc, body = boss("Epaisseur")
slot(body, 6)
sh = body.Tip.Shape
th = creation.thickness(sh, V(0, 0, 15), V(0, 0, -1), 5.0)
check(abs(th - 15) < 1e-3, "épaisseur sous l'entrée fendue : %.3f mm (15 attendus)" % th)

log("\nFENTE : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
