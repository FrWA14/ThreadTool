"""Test de la fonction paramétrique dans un document (freecadcmd tests/test_feature.py)."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("THREADTOOL_LANG", "fr")         # les messages vérifiés sont en français
import FreeCAD as App
import Part
from threadtool import feature, detect, standards
from threadtool.config import ThreadConfig


# Console Windows (cp1252) : un caractère comme « → » est remplacé au lieu de faire échouer le test.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")


def log(*a):
    print(*a); sys.stdout.flush()


cfg = ThreadConfig()
doc = App.newDocument("ThreadTest")
body = doc.addObject("PartDesign::Body", "Body")
cyl = body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
cyl.Radius, cyl.Height = 3.0, 15.0
hole = body.newObject("PartDesign::SubtractiveCylinder", "Hole")
hole.Radius, hole.Height = 1.25, 15.0
doc.recompute()
info, side = detect.find_default(body.Tip.Shape, cfg)
log("défaut :", info["face_name"], info["kind"], round(info["diameter"], 3), side)
obj = feature.create(body)
obj.FaceName = info["face_name"]
obj.Side = side
c = standards.propose(info["kind"], info["diameter"], cfg)[0]
obj.Standard, obj.Designation = c.entry.standard, c.entry.name
obj.Depth = 8
doc.recompute()
log("valide :", obj.isValid(), obj.getStatusString(), "| tip :", body.Tip.Name, "| ", obj.Designation,
    "| vol", round(cyl.Shape.Volume, 2), "->", round(obj.Shape.Volume, 2), "| msg:", obj.Messages)
assert obj.isValid() and obj.Shape.Volume < hole.Shape.Volume
# modification d'une fonction antérieure : le nom de face peut changer, la face est retrouvée
cyl.Height = 20.0
doc.recompute()
log("après modif :", obj.isValid(), obj.FaceName, round(obj.Shape.Volume, 2))
assert obj.isValid()
# taraudage du trou central, pas à gauche, M3
t2 = feature.create(body, "Thread2")
inner = [i for i in range(len(obj.BaseFeature.Shape.Faces))]
sh = obj.Shape
fn = [("Face%d" % (i + 1)) for i, f in enumerate(sh.Faces)
      if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 1.25) < 1e-6][0]
t2.FaceName = fn
t2.Side = "low"
t2.Standard, t2.Designation, t2.LeftHanded = "ISO", "M3", True
t2.Depth = 6
doc.recompute()
log("taraudage :", t2.isValid(), t2.getStatusString(), round(t2.Shape.Volume, 2))
assert t2.isValid()
path = os.path.join(tempfile.gettempdir(), "threadtool_test.FCStd")
doc.saveAs(path)
App.closeDocument(doc.Name)
d2 = App.openDocument(path)
o2 = d2.getObject("Thread")
o2.Depth = 5
o2.touch()
d2.recompute()
log("réouvert :", o2.isValid(), type(o2.Proxy).__name__, round(o2.Shape.Volume, 2))
assert o2.isValid()
log("FEATURE OK")

# corps déplacé et tourné : le filet doit rester sur la pièce (pas de double placement)
doc3 = App.newDocument("Moved")
b3 = doc3.addObject("PartDesign::Body", "Body")
b3.Placement = App.Placement(App.Vector(50, -20, 10), App.Rotation(App.Vector(1, 1, 0), 40))
c3 = b3.newObject("PartDesign::AdditiveCylinder", "Cylinder")
c3.Radius, c3.Height = 4.0, 20.0
c3.Placement = App.Placement(App.Vector(5, 5, 0), App.Rotation(App.Vector(0, 1, 0), 90))
doc3.recompute()
info, side = detect.find_default(b3.Tip.Shape, cfg)
t3 = feature.create(b3)
t3.FaceName, t3.Side, t3.Standard, t3.Designation, t3.Depth = info["face_name"], side, "ISO", "M8", 10
doc3.recompute()
bb0, bb1 = c3.Shape.optimalBoundingBox(), t3.Shape.optimalBoundingBox()
log("corps déplacé :", t3.isValid(), t3.getStatusString(), "| centres", bb0.Center, bb1.Center)
assert t3.isValid() and (bb0.Center - bb1.Center).Length < 0.6, (bb0.Center, bb1.Center)
# plan de référence : plan YZ de l'Origin (perpendiculaire à l'axe du cylindre couché) à x = 0
yz = [o for o in b3.Origin.OriginFeatures if o.Role == "YZ_Plane"][0]
t3.HeightReference = (yz, [])
t3.Side = "high"                          # volontairement le mauvais côté : doit être corrigé seul
t3.Depth = 6
doc3.recompute()
log("plan de référence :", t3.isValid(), t3.getStatusString(), round(t3.Shape.Volume, 2))
assert t3.isValid()
log("FEATURE 2 OK")
