"""Début du filet décalé depuis la face, entrée ramenée au Ø de pied (freecadcmd tests/test_offset.py).

Cas de l'utilisateur : cylindre Ø14 × 37,5, haut réduit à Ø8 sur 12 mm, chanfrein 1 mm,
M10 commencé 2 mm sous la face, sur 3 filets (4,5 mm)."""
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


def radii(shape, z, cx=0.0, cy=0.0, rmax=1e9):
    rs = [math.hypot(q.x - cx, q.y - cy) for w in shape.slice(V(0, 0, 1), z) for e in w.Edges
          for q in e.discretize(Number=120)]
    rs = [r for r in rs if r < rmax]
    return (min(rs), max(rs)) if rs else (0.0, 0.0)


def slab(z1, z2, r=50):
    return Part.makeCylinder(r, z2 - z1, V(0, 0, z1))


def stepped(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    c1 = body.newObject("PartDesign::AdditiveCylinder", "C14")
    c1.Radius, c1.Height = 7, 25.5
    c2 = body.newObject("PartDesign::AdditiveCylinder", "C8")
    c2.Radius, c2.Height = 4, 12
    c2.AttachmentSupport, c2.MapMode = [(xy, "")], "FlatFace"
    c2.AttachmentOffset = App.Placement(V(0, 0, 25.5), App.Rotation())
    doc.recompute()
    top = [("Edge%d" % (i + 1)) for i, e in enumerate(c2.Shape.Edges)
           if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Center.z - 37.5) < 1e-6][0]
    ch = body.newObject("PartDesign::Chamfer", "Chanfrein")
    ch.Base, ch.Size = (c2, [top]), 1
    doc.recompute()
    return doc, body, ch


def cyl_face(shape, r):
    return [("Face%d" % (i + 1)) for i, f in enumerate(shape.Faces)
            if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - r) < 1e-6][0]


m10 = thread_data.dims(thread_data.get("M10"))
root10 = (m10["minor_ext"] - cfg.clearance) / 2

# ---------------------------------------------------------------- A. M10 sur le Ø8, 2 mm sous la face, 3 filets
doc, body, ch = stepped("A")
base = ch.Shape
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation = cyl_face(base, 4), "high", "ISO", "M10"
t.StartOffset, t.Depth = 2.0, 3 * 1.5
doc.recompute()
check(t.isValid(), "A : M10 décalé de 2 mm valide (%s) %s" % (t.getStatusString(), t.Messages))
r = t.Shape
check(len(r.Solids) == 1 and r.isValid(), "A : un solide valide")
# la face cylindrique commence sous le chanfrein (z = 36.5) : filet de z = 34.5 à z = 30
lo, hi = radii(r, 35.5)
check(hi <= root10 + 1e-3, "A : entrée (z = 35.5) Ø %.3f ≤ Ø de pied %.3f (Ø8 > 7.96 avec le jeu : réduit)" % (2 * hi, 2 * root10))
check(abs(r.common(slab(36.5, 40)).Volume - base.common(slab(36.5, 40)).Volume) < 1e-4, "A : chanfrein intact")
lo, hi = radii(r, 32.0)
check(abs(hi - (10 - cfg.clearance) / 2) < 0.03 and abs(lo - root10) < 0.03,
      "A : filet complet (z = 32 : r %.3f – %.3f)" % (lo, hi))
check(abs(r.common(slab(0, 29.99)).Volume - base.common(slab(0, 29.99)).Volume) < 1e-4,
      "A : rien sous la fin du filet (z = 30)")

# ---------------------------------------------------------------- B. M10 sur le Ø14, 2 mm sous l'épaulement
doc, body, ch = stepped("B")
base = ch.Shape
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation = cyl_face(base, 7), "high", "ISO", "M10"
t.StartOffset, t.Depth = 2.0, 4.5
doc.recompute()
check(t.isValid(), "B : M10 sur Ø14 décalé valide (%s)" % t.getStatusString())
log("  messages :", t.Messages)
r = t.Shape
lo, hi = radii(r, 24.5)
check(hi <= root10 + 1e-3 and hi > root10 - 0.05,
      "B : entrée Ø14 (z = 24.5) ramenée au Ø %.3f ≤ pied %.3f" % (2 * hi, 2 * root10))
check("ramenée" in t.Messages, "B : message d'entrée ramenée")
check(abs(r.common(slab(25.5, 40)).Volume - base.common(slab(25.5, 40)).Volume) < 1e-4, "B : portée Ø8 intacte")
lo, hi = radii(r, 21.0)
check(abs(hi - (10 - cfg.clearance) / 2) < 0.03, "B : filet M10 (z = 21 : r max %.3f)" % hi)
check(abs(r.common(slab(0, 18.99)).Volume - base.common(slab(0, 18.99)).Volume) < 1e-4, "B : rien sous z = 19")

# ---------------------------------------------------------------- C. plan de référence décalé (sans décalage)
doc, body, ch = stepped("C")
base = ch.Shape
xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
pl = body.newObject("PartDesign::Plane", "Plan")
pl.AttachmentSupport, pl.MapMode = [(xy, "")], "FlatFace"
pl.AttachmentOffset = App.Placement(V(0, 0, 23.5), App.Rotation())
doc.recompute()
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation, t.Depth = cyl_face(base, 7), "high", "ISO", "M10", 4.5
t.HeightReference = (pl, [])
doc.recompute()
check(t.isValid(), "C : plan de référence à 2 mm valide (%s)" % t.getStatusString())
lo, hi = radii(t.Shape, 24.5)
check(hi <= root10 + 1e-3, "C : entrée entre la face et le plan ramenée au Ø %.3f" % (2 * hi))

# ---------------------------------------------------------------- D. trou taraudé M6 créé, 2 mm sous la face
doc = App.newDocument("D")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Bloc")
box.Length, box.Width, box.Height = 20, 20, 20
doc.recompute()
top = [("Face%d" % (i + 1)) for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 20) < 1e-9][0]
t = feature.create(body, "T")
t.Operation, t.Support, t.SupportPoint = creation.OPERATIONS[1], (box, [top]), V(10, 10, 20)
t.Standard, t.Designation, t.Depth, t.StartOffset = "ISO", "M6", 10, 2
doc.recompute()
check(t.isValid(), "D : trou taraudé M6 décalé valide (%s) %s" % (t.getStatusString(), t.Messages))
m6 = thread_data.dims(thread_data.get("M6"))
lo, hi = radii(t.Shape, 19.0, 10, 10, 5)
check(lo >= (6 + cfg.clearance) / 2 - 1e-3, "D : entrée alésée au Ø %.3f ≥ pied du taraudage %.3f" % (2 * lo, 6 + cfg.clearance))
lo, hi = radii(t.Shape, 14.0, 10, 10, 5)
check(abs(lo - (m6["minor_int"] + cfg.clearance) / 2) < 0.03, "D : taraudage sous l'entrée (z = 14 : r min %.3f)" % lo)
check(abs(t.Shape.common(Part.makeBox(20, 20, 9.99)).Volume - 20 * 20 * 9.99) < 1e-4, "D : rien sous le fond (z = 10)")

# ---------------------------------------------------------------- E. dernier filet complet (protrusion Ø14 × 10, M16, décalage 4)
def per_pitch(shape, zs, P, r, outside):
    """Matière d'un côté du Ø moyen, pas par pas : identique sur chaque pas si le filet est complet."""
    out = []
    for z1 in zs:
        c = Part.makeCylinder(r, P, V(0, 0, z1))
        tool = Part.makeCylinder(40, P, V(0, 0, z1)).cut(c) if outside else c
        out.append(shape.common(tool).Volume)
    return out


doc = App.newDocument("E")
body = doc.addObject("PartDesign::Body", "Body")
xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
sk = body.newObject("Sketcher::SketchObject", "Sk")
sk.AttachmentSupport, sk.MapMode = [(xy, "")], "FlatFace"
sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 7))
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile, pad.Length = sk, 10
doc.recompute()
t = feature.create(body, "T")
t.FaceName, t.Side, t.Standard, t.Designation, t.StartOffset, t.Depth = cyl_face(pad.Shape, 7), "high", "ISO", "M16", 4, 6
doc.recompute()
check(t.isValid(), "E : M16 sur Ø14, décalage 4 : valide (%s)" % t.getStatusString())
m16 = thread_data.dims(thread_data.get("M16"))
v = per_pitch(t.Shape, (0.0, 2.0, 4.0), 2.0, m16["d2"] / 2, True)
check(max(v) - min(v) < 1e-3, "E : dernier filet complet, matière par pas %s mm3" % ", ".join("%.3f" % x for x in v))
check(t.Shape.common(slab(-5, 0)).Volume < 1e-9, "E : rien sous le bout de l'extrusion")

# ---------------------------------------------------------------- F. dernier filet complet d'un trou borgne (M8 × 12)
doc = App.newDocument("F")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Bloc")
box.Length, box.Width, box.Height = 20, 20, 20
box.Placement = App.Placement(V(-10, -10, 0), App.Rotation())
doc.recompute()
top = [("Face%d" % (i + 1)) for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 20) < 1e-9][0]
t = feature.create(body, "T")
t.Operation, t.Support, t.SupportPoint = creation.OPERATIONS[1], (box, [top]), V(0, 0, 20)
t.Standard, t.Designation, t.Depth = "ISO", "M8", 12
doc.recompute()
check(t.isValid(), "F : trou taraudé M8 × 12 : valide (%s)" % t.getStatusString())
m8 = thread_data.dims(thread_data.get("M8"))
v = per_pitch(t.Shape, (8.0, 8.0 + 1.25, 14.0), 1.25, m8["d2"] / 2, False)
check(max(v) - min(v) < 1e-3, "F : dernier filet complet au fond, matière par pas %s mm3" % ", ".join("%.3f" % x for x in v))
check(abs(t.Shape.common(Part.makeBox(20, 20, 7.99, V(-10, -10, 0))).Volume - 20 * 20 * 7.99) < 1e-4,
      "F : rien sous le fond (z = 8)")

log("\nDÉCALAGE : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
