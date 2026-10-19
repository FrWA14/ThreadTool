"""Exercice de référence (freecadcmd tests/test_exercise.py).

Cube 10×10×10 ; sur une face, esquisse cercle Ø10 + protrusion 20 mm ; sur la face circulaire,
esquisse cercle Ø5 + poche 10 mm.
  1. Filetage M10 demandé sur 22 mm : limité aux 20 mm du cylindre, ne touche pas le cube,
     le fond de gorge atteint les deux plans d'extrémité du cylindre (z = 10 et z = 30).
  2. Taraudage M5 demandé sur 11 mm : limité aux 10 mm de la poche, rien sous le fond (z = 20).
"""
import os
import sys
import math

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("THREADTOOL_LANG", "fr")         # les messages vérifiés sont en français

import FreeCAD as App
import Part
from threadtool import feature, detect, thread_data
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


def circle_sketch(body, name, z, r):
    sk = body.newObject("Sketcher::SketchObject", name)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    sk.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), r))
    return sk


def slab(z1, z2, r=50):
    return Part.makeCylinder(r, z2 - z1, V(5, 5, z1))


def section_radii(shape, z):
    rs = []
    for w in shape.slice(V(0, 0, 1), z):
        for q in detect.wire_points(w, 720):
            rs.append(math.hypot(q.x - 5, q.y - 5))
    return rs


doc = App.newDocument("Exercice")
body = doc.addObject("PartDesign::Body", "Body")
cube = body.newObject("PartDesign::AdditiveBox", "Cube")
cube.Length = cube.Width = cube.Height = 10
sk1 = circle_sketch(body, "SketchD10", 10, 5)
pad = body.newObject("PartDesign::Pad", "Pad")
pad.Profile = sk1
pad.Length = 20
sk2 = circle_sketch(body, "SketchD5", 30, 2.5)
pocket = body.newObject("PartDesign::Pocket", "Pocket")
pocket.Profile = sk2
pocket.Length = 10
doc.recompute()
base = pocket.Shape
log("pièce :", base.isValid(), round(base.Volume, 3), base.BoundBox)


def cyl_face(shape, r):
    return [("Face%d" % (i + 1)) for i, f in enumerate(shape.Faces)
            if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - r) < 1e-6][0]


# ------------------------------------------------------------- 1. filetage M10 sur 22 mm demandés
info, side = detect.find_default(base, cfg)
log("face par défaut :", info["face_name"], info["kind"], round(info["diameter"], 3), side)
check(info["kind"] == "arbre" and abs(info["diameter"] - 10) < 1e-6, "face par défaut = cylindre Ø10 (arbre)")
t1 = feature.create(body, "ThreadM10")
t1.FaceName, t1.Side, t1.Standard, t1.Designation, t1.Depth = cyl_face(base, 5), "high", "ISO", "M10", 22
doc.recompute()
check(t1.isValid(), "filetage M10 valide (%s)" % t1.getStatusString())
src = feature.source_feature(t1, detect.analyse(base, cyl_face(base, 5), None, cfg))
check(src is not None and src["obj"] is pad and abs(src["length"] - 20) < 1e-9,
      "longueur reprise de la fonction : %s.%s = %s" % (src and src["label"], src and src["prop"], src and src["length"]))
log("  messages :", t1.Messages)
r1 = t1.Shape
cube_before = base.common(slab(0, 10)).Volume
cube_after = r1.common(slab(0, 10)).Volume
check(abs(cube_before - cube_after) < 1e-4, "cube intact (Δ = %.2e mm3)" % (cube_before - cube_after))
check(r1.common(slab(30, 60)).Volume < 1e-9, "rien au-delà du bout libre")
m = thread_data.dims(thread_data.get("M10"))
root = (m["minor_ext"] - cfg.clearance) / 2
for z, name in ((10.001, "début (contre le cube)"), (29.999, "fin (bout libre)")):
    rs = [r for r in section_radii(r1, z) if r > 3.0]           # contour extérieur (pas le trou Ø5)
    check(abs(min(rs) - root) < 0.02 and abs(max(rs) - (10 - cfg.clearance) / 2) < 0.02,
          "fond de gorge au plan %s : r min %.3f (fond théorique %.3f), r max %.3f" % (name, min(rs), root, max(rs)))

# ------------------------------------------------------------- 2. taraudage M5 sur 11 mm demandés
t2 = feature.create(body, "TapM5")
t2.FaceName, t2.Side, t2.Standard, t2.Designation, t2.Depth = cyl_face(r1, 2.5), "high", "ISO", "M5", 11
doc.recompute()
check(t2.isValid(), "taraudage M5 valide (%s)" % t2.getStatusString())
log("  messages :", t2.Messages)
r2 = t2.Shape
below_before = r1.common(slab(0, 20)).Volume
below_after = r2.common(slab(0, 20)).Volume
check(abs(below_before - below_after) < 1e-4, "rien sous le fond de la poche (Δ = %.2e mm3)" % (below_before - below_after))
m5 = thread_data.dims(thread_data.get("M5"))
for z, name in ((20.001, "fond de la poche"), (29.999, "entrée")):
    rs = [r for r in section_radii(r2, z) if r < 3.0]           # contour du trou
    check(abs(max(rs) - (5 + cfg.clearance) / 2) < 0.03 and abs(min(rs) - (m5["minor_int"] + cfg.clearance) / 2) < 0.03,
          "fond de gorge au plan %s : r max %.3f (théorique %.3f), r min %.3f" % (
              name, max(rs), (5 + cfg.clearance) / 2, min(rs)))
check(len(r2.Solids) == 1 and r2.isValid(), "résultat : un solide valide")

log("\nEXERCICE : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
