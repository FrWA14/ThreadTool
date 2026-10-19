"""Captures du README : freecad docs/screenshots.py (images écrites dans docs/images).

Trois exemples, chacun avec le panneau (aperçu) puis le résultat :
1. filetage M10 sur un arbre Ø10 ;
2. trou taraudé M6 avec lamage ISO 4762 dans un bloc (vue en coupe) ;
3. vis CHC M8 : tige filetée + tête ISO 4762 à six pans creux."""
import os
import traceback

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("THREADTOOL_SHOTS", os.path.join(HERE, "images"))
os.makedirs(OUT, exist_ok=True)
LOG = open(os.path.join(OUT, "_screenshots.log"), "w", encoding="utf-8")
V = App.Vector
VIEW_W, VIEW_H = 900, 680
S = {}


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def guard(fn):
    def w():
        try:
            fn()
        except Exception:
            log("EXCEPTION", fn.__name__, traceback.format_exc())
            finish()
    return w


def later(ms, fn):
    QtCore.QTimer.singleShot(ms, guard(fn))


def panel():
    from threadtool import commands
    return commands.LAST_PANEL


def pick(cb, data):
    i = cb.findData(data)
    if i >= 0:
        cb.setCurrentIndex(i)


def view_image(path, w=VIEW_W, h=VIEW_H):
    Gui.updateGui()
    Gui.activeDocument().activeView().saveImage(path, w, h, "Current")
    return QtGui.QImage(path)


def shot_with_panel(name):
    """Vue 3D (avec l'aperçu) à gauche, panneau Tâches à droite, sur une même image."""
    tmp = os.path.join(OUT, "_vue.png")
    view = view_image(tmp)
    os.remove(tmp)
    form = panel().form
    pm = form.grab()
    if pm.height() > VIEW_H:
        pm = pm.scaledToHeight(VIEW_H, QtCore.Qt.SmoothTransformation)
    img = QtGui.QImage(VIEW_W + pm.width() + 12, VIEW_H, QtGui.QImage.Format_RGB32)
    img.fill(QtGui.QColor(255, 255, 255))
    p = QtGui.QPainter(img)
    p.drawImage(0, 0, view)
    p.drawPixmap(VIEW_W + 12, 0, pm)
    p.end()
    img.save(os.path.join(OUT, name + ".png"))
    log("  image", name)


def shot_view(name, w=VIEW_W, h=VIEW_H):
    view_image(os.path.join(OUT, name + ".png"), w, h)
    log("  image", name)


def new_doc(name):
    doc = App.newDocument(name)
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    return doc, body


def fit(iso=True):
    v = Gui.activeDocument().activeView()
    v.viewIsometric() if iso else v.viewAxonometric()
    Gui.SendMsgToActiveView("ViewFit")


def cyl_face(obj, r):
    return [("Face%d" % (i + 1)) for i, f in enumerate(obj.Shape.Faces)
            if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - r) < 1e-6][0]


def accept():
    p = panel()
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    log("  accept", ok, p.obj.Label, p.obj.isValid(), p.obj.Messages)
    return p.obj


# ------------------------------------------------------------------ 1. filetage
def s1():
    Gui.getMainWindow().resize(1400, 1000)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc, body = new_doc("Filetage")
    base = body.newObject("PartDesign::AdditiveCylinder", "Collet")
    base.Radius, base.Height = 10, 6
    shaft = body.newObject("PartDesign::AdditiveCylinder", "Arbre")
    shaft.Radius, shaft.Height = 5, 26
    shaft.Placement = App.Placement(V(0, 0, 6), App.Rotation())
    doc.recompute()
    fit()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Arbre." + cyl_face(shaft, 5))
    log("1. filetage M10")
    Gui.runCommand("PartDesign_ThreadTool")
    later(6000, s1b)


def s1b():
    p = panel()
    pick(p.cb_std, "ISO|coarse")
    pick(p.cb_des, "M10")
    p.sp_depth.setValue(18)
    later(9000, s1c)


def s1c():
    fit()
    later(1500, s1c2)


def s1c2():
    shot_with_panel("filetage_panneau")
    accept()
    fit()
    later(2000, s1d)


def s1d():
    shot_view("filetage_resultat")
    App.closeDocument("Filetage")
    s2()


# ------------------------------------------------------------------ 2. trou taraudé + lamage
def s2():
    doc, body = new_doc("Taraudage")
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 40, 30, 20
    doc.recompute()
    fit()
    top = [("Face%d" % (i + 1)) for i, f in enumerate(box.Shape.Faces) if abs(f.CenterOfMass.z - 20) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Bloc." + top, 20, 15, 20)
    S["doc"] = doc
    log("2. trou taraudé M6 + lamage")
    Gui.runCommand("PartDesign_ThreadTool")
    later(6000, s2b)


def s2b():
    p = panel()
    pick(p.cb_std, "ISO|coarse")
    pick(p.cb_des, "M6")
    p.sp_depth.setValue(16)
    pick(p.cb_head, "ISO 4762")
    later(9000, s2c)


def s2c():
    fit()
    later(1500, s2c2)


def s2c2():
    shot_with_panel("taraudage_lamage_panneau")
    o = accept()
    doc = S["doc"]
    cut = doc.addObject("Part::Feature", "Coupe")            # demi-pièce pour voir le taraudage
    cut.Shape = o.Shape.common(Part.makeBox(40, 15, 30, V(0, 15, -5)))
    doc.recompute()
    o.ViewObject.hide()
    cut.ViewObject.ShapeAppearance = o.ViewObject.ShapeAppearance
    fit()
    later(2000, s2d)


def s2d():
    shot_view("taraudage_lamage_resultat")
    App.closeDocument("Taraudage")
    s3()


# ------------------------------------------------------------------ 3. vis CHC
def s3():
    doc, body = new_doc("Vis")
    shank = body.newObject("PartDesign::AdditiveCylinder", "Tige")
    shank.Radius, shank.Height = 4, 30
    doc.recompute()
    fit()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Tige." + cyl_face(shank, 4))
    log("3. vis CHC M8")
    Gui.runCommand("PartDesign_ThreadTool")
    later(6000, s3b)


def s3b():
    p = panel()
    if p.obj.Side != "low":                                   # filet depuis le bas, tête en haut
        p.flip_side()
    pick(p.cb_std, "ISO|coarse")
    pick(p.cb_des, "M8")
    p.sp_depth.setValue(22)
    pick(p.cb_head, "ISO 4762")
    pick(p.cb_hpos, "Face opposée")
    later(10000, s3c)


def s3c():
    fit()
    later(1500, s3c2)


def s3c2():
    shot_with_panel("vis_chc_panneau")
    accept()
    fit()
    later(2000, s3d)


def s3d():
    shot_view("vis_chc_resultat")
    finish()


def finish():
    log("FIN")
    LOG.close()
    try:
        for d in list(App.listDocuments()):
            App.closeDocument(d)
    except Exception:
        pass
    Gui.getMainWindow().close()


later(3000, s1)
