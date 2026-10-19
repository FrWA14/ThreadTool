"""Symétrie / répétitions PartDesign et pièce de révolution à deux portées (freecadcmd tests/test_transform.py)."""
import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD as App
import Part
from threadtool import feature, creation
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


def slab(z1, z2, r=50):
    return Part.makeCylinder(r, z2 - z1, V(0, 0, z1))


def origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def revolved(name):
    """Ø10 sur 21 mm avec un collet Ø14 × 5 au centre, fait par révolution autour de Z."""
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    sk = body.newObject("Sketcher::SketchObject", "Profil")
    sk.AttachmentSupport, sk.MapMode = [(origin(body, "XZ_Plane"), "")], "FlatFace"
    pts = [(0, 0), (5, 0), (5, 8), (7, 8), (7, 13), (5, 13), (5, 21), (0, 21)]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sk.addGeometry(Part.LineSegment(V(a[0], a[1], 0), V(b[0], b[1], 0)))
    rev = body.newObject("PartDesign::Revolution", "Revolution")
    rev.Profile, rev.ReferenceAxis, rev.Angle = sk, (sk, ["V_Axis"]), 360
    doc.recompute()
    return doc, body, rev


def face_at(shape, r, zmid):
    return [("Face%d" % (i + 1)) for i, f in enumerate(shape.Faces) if isinstance(f.Surface, Part.Cylinder)
            and abs(f.Surface.Radius - r) < 1e-6 and abs(f.CenterOfMass.z - zmid) < 1e-6][0]


def thread(body, base, face, side, name="T", des="M10", depth=6):
    t = feature.create(body, name)
    t.FaceName, t.Side, t.Standard, t.Designation, t.Depth = face, side, "ISO", des, depth
    body.Document.recompute()
    return t


# ---------------------------------------------------------------- 1. deux filetages sur la pièce de révolution
doc, body, rev = revolved("R")
base = rev.Shape
t1 = thread(body, base, face_at(base, 5, 17), "high", "Haut")
check(t1.isValid(), "filetage du haut : valide (%s) %s" % (t1.getStatusString(), t1.Messages))
t2 = thread(body, t1.Shape, face_at(t1.Shape, 5, 4), "low", "Bas")
check(t2.isValid(), "filetage du bas : valide (%s) %s" % (t2.getStatusString(), t2.Messages))
r = t2.Shape
check(abs(r.common(slab(8, 13)).Volume - base.common(slab(8, 13)).Volume) < 1e-4, "collet Ø14 intact")
v_top = base.common(slab(13, 21)).Volume - r.common(slab(13, 21)).Volume
v_bot = base.common(slab(0, 8)).Volume - r.common(slab(0, 8)).Volume
check(v_top > 1 and abs(v_top - v_bot) < 1e-3, "même matière enlevée en haut et en bas : %.3f / %.3f mm3" % (v_top, v_bot))
check(t1.TypeId == feature.SUB_TYPE and not t1.AddSubShape.isNull(), "fonction soustractive avec son outil (AddSubShape)")

# ---------------------------------------------------------------- 2. symétrie PartDesign du filetage du haut
doc, body, rev = revolved("M")
base = rev.Shape
t = thread(body, base, face_at(base, 5, 17), "high")
pl = body.newObject("PartDesign::Plane", "Milieu")
pl.AttachmentSupport, pl.MapMode = [(origin(body, "XY_Plane"), "")], "FlatFace"
pl.AttachmentOffset = App.Placement(V(0, 0, 10.5), App.Rotation())
mir = body.newObject("PartDesign::Mirrored", "Symetrie")
mir.Originals = [t]
mir.MirrorPlane = (pl, [""])
mir.Refine = False
doc.recompute()
check(mir.isValid(), "Symétrie : valide (%s)" % mir.getStatusString())
r = mir.Shape
v_top = base.common(slab(13, 21)).Volume - r.common(slab(13, 21)).Volume
v_bot = base.common(slab(0, 8)).Volume - r.common(slab(0, 8)).Volume
check(len(r.Solids) == 1 and v_top > 1 and abs(v_top - v_bot) < 1e-3,
      "Symétrie : filet reproduit en bas (%.3f / %.3f mm3)" % (v_top, v_bot))

# ---------------------------------------------------------------- 2b. répétition circulaire 180° (garde le pas à droite)
doc, body, rev = revolved("P")
base = rev.Shape
t = thread(body, base, face_at(base, 5, 17), "high")
ax = body.newObject("PartDesign::Line", "AxeMilieu")
ax.AttachmentSupport, ax.MapMode = [(origin(body, "X_Axis"), "")], "ObjectXY"
ax.MapMode = "Deactivated"
ax.Placement = App.Placement(V(0, 0, 10.5), App.Rotation(V(0, 1, 0), 90))
pp = body.newObject("PartDesign::PolarPattern", "Circulaire")
pp.Originals = [t]
pp.Axis = (ax, [""])
pp.Angle, pp.Occurrences = 360, 2
pp.Refine = False
doc.recompute()
r = pp.Shape
v_top = base.common(slab(13, 21)).Volume - r.common(slab(13, 21)).Volume
v_bot = base.common(slab(0, 8)).Volume - r.common(slab(0, 8)).Volume
check(pp.isValid() and len(r.Solids) == 1 and abs(v_top - v_bot) < 1e-3,
      "Répétition circulaire 180° : filet reproduit en bas, pas à droite conservé (%.3f / %.3f mm3)" % (v_top, v_bot))

# ---------------------------------------------------------------- 3. répétition linéaire Poche + taraudage (perçage Ø4.2, M5)
doc = App.newDocument("L")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Plaque")
box.Length, box.Width, box.Height = 40, 20, 10
sk = body.newObject("Sketcher::SketchObject", "Sk")
sk.AttachmentSupport, sk.MapMode = [(origin(body, "XY_Plane"), "")], "FlatFace"
sk.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
sk.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 2.1))
pk = body.newObject("PartDesign::Pocket", "Poche")
pk.Profile, pk.Type = sk, "ThroughAll"
doc.recompute()
f = [("Face%d" % (i + 1)) for i, x in enumerate(pk.Shape.Faces)
     if isinstance(x.Surface, Part.Cylinder) and abs(x.Surface.Radius - 2.1) < 1e-6][0]
t = thread(body, pk.Shape, f, "high", des="M5", depth=8)
check(t.isValid() and feature.WARN_SUB not in t.Messages, "M5 dans un perçage Ø4.2 : valide, rien d'ajouté (%s)" % t.Messages)
lp = body.newObject("PartDesign::LinearPattern", "Repetition")
lp.Originals = [pk, t]
lp.Direction = (origin(body, "X_Axis"), [""])
lp.Length, lp.Occurrences = 20, 2
lp.Refine = False
doc.recompute()
check(lp.isValid(), "Répétition linéaire : valide (%s)" % lp.getStatusString())
r = lp.Shape
one = box.Shape.Volume - t.Shape.Volume
check(len(r.Solids) == 1 and abs((box.Shape.Volume - r.Volume) - 2 * one) < 1e-3,
      "Répétition : 2 trous taraudés identiques (%.3f = 2 × %.3f mm3)" % (box.Shape.Volume - r.Volume, one))

# ---------------------------------------------------------------- 4. trou au Ø nominal : rebouchage => avertissement
doc = App.newDocument("N")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Plaque")
box.Length, box.Width, box.Height = 20, 20, 10
sk = body.newObject("Sketcher::SketchObject", "Sk")
sk.AttachmentSupport, sk.MapMode = [(origin(body, "XY_Plane"), "")], "FlatFace"
sk.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
sk.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 2.5))
pk = body.newObject("PartDesign::Pocket", "Poche")
pk.Profile, pk.Length = sk, 8
doc.recompute()
f = [("Face%d" % (i + 1)) for i, x in enumerate(pk.Shape.Faces)
     if isinstance(x.Surface, Part.Cylinder) and abs(x.Surface.Radius - 2.5) < 1e-6][0]
t = thread(body, pk.Shape, f, "high", des="M5", depth=6)
check(t.isValid() and feature.WARN_SUB in t.Messages, "trou Ø5 rebouché : avertissement pour la symétrie / répétition")

# ---------------------------------------------------------------- 5. trou taraudé créé : soustractif pur ; extrusion : additive
doc = App.newDocument("C")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Plaque")
box.Length, box.Width, box.Height = 30, 20, 10
sk = body.newObject("Sketcher::SketchObject", "Sk")
sk.AttachmentSupport, sk.MapMode = [(origin(body, "XY_Plane"), "")], "FlatFace"
sk.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
sk.addGeometry(Part.Circle(V(22, 10, 0), V(0, 0, 1), 3))
doc.recompute()
t = feature.create(body, "Trou")
t.Operation, t.Support, t.Standard, t.Designation, t.Depth = creation.OPERATIONS[1], (sk, []), "ISO", "M6", 8
doc.recompute()
check(t.isValid() and feature.WARN_SUB not in t.Messages, "trou taraudé créé : percé au Ø d'alésage, rien d'ajouté (%s)" % t.Messages)
sk2 = body.newObject("Sketcher::SketchObject", "Sk2")
sk2.AttachmentSupport, sk2.MapMode = [(origin(body, "XY_Plane"), "")], "FlatFace"
sk2.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
sk2.addGeometry(Part.Circle(V(5, 10, 0), V(0, 0, 1), 3))
body.Tip = t
doc.recompute()
e = feature.create(body, "Ext")                               # créée soustractive, puis passée en extrusion
e.Operation, e.Support, e.Standard, e.Designation, e.Depth = creation.OPERATIONS[2], (sk2, []), "ISO", "M6", 8
e.Reversed = False
e = feature.ensure_type(e)
doc.recompute()
check(e.TypeId == feature.ADD_TYPE and body.Tip == e and e.BaseFeature == t,
      "changement d'opération : fonction recréée additive à la même place (%s)" % e.TypeId)
check(e.isValid() and feature.WARN_ADD not in e.Messages, "extrusion filetée additive : valide (%s) %s" % (e.getStatusString(), e.Messages))
lp = body.newObject("PartDesign::LinearPattern", "RepExt")
lp.Originals = [e]
lp.Direction = (origin(body, "X_Axis"), [""])
lp.Length, lp.Occurrences = 14, 2
lp.Refine = False
doc.recompute()
added = e.Shape.Volume - t.Shape.Volume
check(lp.isValid() and len(lp.Shape.Solids) == 1 and abs((lp.Shape.Volume - t.Shape.Volume) - 2 * added) < 1e-3,
      "Répétition de l'extrusion filetée : 2 extrusions identiques (%.3f = 2 × %.3f mm3)" % (lp.Shape.Volume - t.Shape.Volume, added))

# ---------------------------------------------------------------- 6. fonction d'une version 0.5 (FeaturePython) convertie
from threadtool.feature import ThreadFeature
doc, body, rev = revolved("Mig")
base = rev.Shape
old = body.newObject("PartDesign::FeaturePython", "Ancien")          # fonction d'une version 0.5
ThreadFeature(old)
old.FaceName, old.Side, old.Standard, old.Designation, old.Depth = face_at(base, 5, 17), "high", "ISO", "M10", 6
doc.recompute()
nxt = thread(body, old.Shape, face_at(old.Shape, 5, 4), "low", "Suivant")
v0 = nxt.Shape.Volume
new = feature.ensure_type(old)
doc.recompute()
check(new.TypeId == feature.SUB_TYPE and new.BaseFeature == rev and nxt.BaseFeature == new and body.Tip == nxt,
      "migration en milieu d'arbre : %s, base %s, suivant -> %s" % (new.TypeId, new.BaseFeature.Name, nxt.BaseFeature.Name))
check(new.isValid() and nxt.isValid() and abs(nxt.Shape.Volume - v0) < 1e-6, "résultat identique après migration")

log("\nSYMÉTRIE / RÉPÉTITION : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
