"""Têtes : lamage / fraisage d'un taraudage, tête de vis + empreinte d'un filetage (freecadcmd tests/test_heads.py)."""
import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("THREADTOOL_LANG", "fr")         # les messages vérifiés sont en français

import FreeCAD as App
import Part
from threadtool import feature, creation, heads, thread_data
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


def radii(shape, z, cx=0.0, cy=0.0, rmax=1e9):
    rs = [math.hypot(q.x - cx, q.y - cy) for w in shape.slice(V(0, 0, 1), z) for e in w.Edges
          for q in e.discretize(Number=180)]
    rs = [r for r in rs if r < rmax]
    return (min(rs), max(rs)) if rs else (0.0, 0.0)


def sketch(body, name, z, geos):
    sk = body.newObject("Sketcher::SketchObject", name)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport, sk.MapMode = [(xy, "")], "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    for g in geos:
        sk.addGeometry(g)
    return sk


def block_with_hole(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 30, 30, 20
    pk = body.newObject("PartDesign::Pocket", "Poche")
    pk.Profile = sketch(body, "Sk", 20, [Part.Circle(V(15, 15, 0), V(0, 0, 1), 2.5)])
    pk.Length = 15
    doc.recompute()
    return doc, body, pk


def cyl_face(shape, r):
    return [("Face%d" % (i + 1)) for i, f in enumerate(shape.Faces)
            if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - r) < 1e-6][0]


# ---------------------------------------------------------------- 1. lamage ISO 4762 sur un M5 existant
doc, body, pk = block_with_hole("L")
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation, t.Depth = cyl_face(pk.Shape, 2.5), "high", "ISO", "M5", 8
t.HoleHead = "ISO 4762"
doc.recompute()
check(t.isValid(), "lamage ISO 4762 : valide (%s) %s" % (t.getStatusString(), t.Messages))
check(abs(t.HeadDiameter.Value - 10) < 1e-9 and abs(t.HeadHeight.Value - 5.4) < 1e-9,
      "cotes du Perçage FreeCAD : Ø %.1f × %.1f" % (t.HeadDiameter.Value, t.HeadHeight.Value))
lo, hi = radii(t.Shape, 17.0, 15, 15, 8)
check(abs(lo - 5.0) < 1e-3, "z = 17 : lamage Ø %.3f" % (2 * lo))
lo, hi = radii(t.Shape, 12.0, 15, 15, 8)
m5 = thread_data.dims(thread_data.get("M5"))
check(abs(lo - (m5["minor_int"] + cfg.clearance) / 2) < 0.03 and hi < 2.7,
      "z = 12 : taraudage sous le lamage (r %.3f – %.3f)" % (lo, hi))
check(len(t.Shape.Solids) == 1 and t.Shape.isValid(), "un solide valide")

# ---------------------------------------------------------------- 2. fraisage ISO 10642
t.HoleHead = "ISO 10642"
doc.recompute()
check(t.isValid(), "fraisage ISO 10642 : valide (%s)" % t.getStatusString())
lo, hi = radii(t.Shape, 19.999, 15, 15, 8)
check(abs(lo - 11.2 / 2) < 0.01, "Ø du fraisage à la face : %.3f (11.2)" % (2 * lo))
lo, hi = radii(t.Shape, 18.0, 15, 15, 8)
check(abs(lo - (11.2 / 2 - 2.0)) < 0.01, "cône à 90° : 2 mm sous la face r = %.3f (3.6)" % lo)

# ---------------------------------------------------------------- 3. filet hors norme : pas de tête
t.Standard = "custom"
t.CustomDiameter, t.CustomPitch = 5.0, 0.8
doc.recompute()
check(t.isValid() and heads.NEED_STANDARD in t.Messages, "hors norme : tête ignorée, message « %s »" % t.Messages)

# ---------------------------------------------------------------- 4. vis : tige Ø5 + tête CHC ISO 4762 en face opposée
doc = App.newDocument("V")
body = doc.addObject("PartDesign::Body", "Body")
c = body.newObject("PartDesign::AdditiveCylinder", "Tige")
c.Radius, c.Height = 2.5, 20
doc.recompute()
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation, t.Depth = cyl_face(c.Shape, 2.5), "high", "ISO", "M5", 12
t.ScrewHead, t.Drive = "ISO 4762", "Six pans creux"
doc.recompute()
check(t.isValid(), "vis CHC M5 : valide (%s) %s" % (t.getStatusString(), t.Messages))
r = t.Shape
check(len(r.Solids) == 1 and r.isValid(), "vis : un solide valide")
bb = r.BoundBox
check(abs(bb.ZMin + 5) < 1e-3, "tête sous la tige (face opposée) : z min %.3f (−5)" % bb.ZMin)
lo, hi = radii(r, -4.0)            # l'empreinte est sur le dessus de la tête (z = −5 à −2.5)
check(abs(hi - 4.25) < 1e-3 and abs(lo - 2.0) < 1e-2, "z = −4 : tête Ø %.2f, six pans creux de 4 (r min %.3f)" % (2 * hi, lo))
lo, hi = radii(r, -1.0)
check(lo > 4.2, "empreinte de 2.5 mm de profondeur : tête pleine à z = −1 (r min %.3f)" % lo)

# ---------------------------------------------------------------- 5. tête hexagonale sur la face de début
t.ScrewHead, t.HeadPosition, t.Drive = "ISO 4017", "Face de début", heads.NONE
doc.recompute()
check(t.isValid(), "tête H ISO 4017 face de début : valide (%s)" % t.getStatusString())
bb = t.Shape.BoundBox
check(abs(bb.ZMax - 23.5) < 1e-3, "tête au-dessus de la face de début : z max %.3f (23.5)" % bb.ZMax)
lo, hi = radii(t.Shape, 20.5)
check(abs(lo - 4.0) < 1e-2 and hi > 4.4, "z = 20.5 : sur plats 8 (r min %.3f, r max %.3f)" % (lo, hi))

# ---------------------------------------------------------------- 6. chaque empreinte
for drive in heads.DRIVES[1:]:
    h = heads.screw_head("ISO 4762", 6.0, drive)
    s = heads.screw_solid(h, 6.0, V(0, 0, 0), V(0, 0, 1))
    full = heads.screw_solid(dict(h, drive=heads.NONE), 6.0, V(0, 0, 0), V(0, 0, 1))
    check(s.isValid() and len(s.Solids) == 1 and s.Volume < full.Volume - 1e-3,
          "empreinte %-15s %-14s : %.2f mm3 enlevés" % (drive, h["drive_label"], full.Volume - s.Volume))
for name in heads.SCREW_HEADS:
    h = heads.screw_head(name, 8.0)
    s = heads.screw_solid(h, 8.0, V(0, 0, 0), V(0, 0, 1))
    check(s.isValid() and len(s.Solids) == 1, "tête %-10s M8 : %s, %s" % (name, heads.SCREW_HEADS[name][0], h["drive_label"] or "sans empreinte"))

# ---------------------------------------------------------------- 7. équivalence d'une autre norme
e = thread_data.get('1/4"-20 UNC') if any(x.name == '1/4"-20 UNC' for x in thread_data.ALL) else None
d = e.d if e else 6.35
cb = heads.hole_cut("ISO 4762", d)
check(11.0 < cb["diameter"] < 15.0, "1/4\" (Ø %.2f) : lamage en équivalence Ø %.2f × %.2f" % (d, cb["diameter"], cb["depth"]))

# ---------------------------------------------------------------- 8. trou taraudé créé + lamage
doc = App.newDocument("C")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Bloc")
box.Length, box.Width, box.Height = 30, 30, 20
sk = sketch(body, "Sk", 20, [Part.Circle(V(10, 10, 0), V(0, 0, 1), 3)])
doc.recompute()
t = feature.create(body, "T")
t.Operation, t.Support = creation.OPERATIONS[1], (sk, [])
t.Standard, t.Designation, t.Depth, t.HoleHead = "ISO", "M6", 15, "ISO 4762"
doc.recompute()
check(t.isValid(), "trou taraudé créé M6 + lamage : valide (%s) %s" % (t.getStatusString(), t.Messages))
lo, hi = radii(t.Shape, 17.0, 10, 10, 9)
check(abs(lo - 5.5) < 1e-3, "lamage Ø %.2f (11)" % (2 * lo))
lo, hi = radii(t.Shape, 10.0, 10, 10, 9)
check(lo < 2.7, "taraudage sous le lamage (r min %.3f)" % lo)

log("\nTÊTES : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
