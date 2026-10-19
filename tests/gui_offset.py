"""Début décalé dans l'interface : freecad tests/gui_offset.py (captures dans THREADTOOL_GUI_OUT)."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_offset.log"), "w", encoding="utf-8")
V = App.Vector
S = {}


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def shot(name):
    Gui.updateGui()
    mw = Gui.getMainWindow()
    img = mw.grab()
    if sys.platform == "win32":
        # Sous Windows, grab() ne relit pas la vue 3D (OpenGL) : elle est rendue à part
        # (saveImage, hors écran) puis collée à sa place dans la capture.
        gd = Gui.activeDocument()
        gl = [w for w in mw.findChildren(QtWidgets.QWidget) if w.inherits("QOpenGLWidget") and w.isVisible()]
        if gd and gl:
            w = max(gl, key=lambda w: w.width() * w.height())
            tmp = os.path.join(OUT, "_vue3d.png")
            gd.activeView().saveImage(tmp, w.width(), w.height(), "Current")
            p = QtGui.QPainter(img)
            p.drawImage(QtCore.QRect(w.mapTo(mw, QtCore.QPoint(0, 0)), w.size()), QtGui.QImage(tmp))
            # Panneaux superposés à la vue 3D (Tâches, Modèle… en mode « overlay ») : redessinés par-dessus.
            for o in mw.findChildren(QtWidgets.QWidget):
                if o.isVisible() and "OverlayTabWidget" in o.metaObject().className():
                    p.drawPixmap(o.mapTo(mw, QtCore.QPoint(0, 0)), o.grab())
            p.end()
            os.remove(tmp)
    img.save(os.path.join(OUT, name + ".png"))


def guard(fn):
    def w():
        try:
            fn()
        except Exception:
            log("EXCEPTION", fn.__name__, traceback.format_exc())
            finish()
    return w


def ok_button():
    bb = [b for b in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox) if b.button(QtWidgets.QDialogButtonBox.Ok)
          and b.isVisible()]
    return bb[0].button(QtWidgets.QDialogButtonBox.Ok) if bb else None


def panel_state(p):
    log("  opération :", p.cb_op.currentText(), "| appui :", p.lbl_sup.text() or "[gris] " + p.lbl_sup.placeholderText(),
        "| face visible :", p.lbl_face.isVisible())
    log("  info      :", p.lbl_faceinfo.text(), "| longueur :", p.lbl_len.text())
    log("  désignation :", p.cb_des.currentText(), "| profondeur :", p.sp_depth.value(), "| message :", p.lbl_msg.text())
    b = ok_button()
    log("  aperçu : cylindres", p.preview.shape_sep.getNumChildren(), "| surlignage", p.preview.hl_sep.getNumChildren(),
        "| OK actif :", b.isEnabled() if b else "?")



@guard
def step1():
    Gui.getMainWindow().resize(1400, 950)
    Gui.activateWorkbench("PartDesignWorkbench")
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()))
    doc = App.newDocument("Decalage")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
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
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    S["doc"] = doc
    f14 = [("Face%d" % (i + 1)) for i, f in enumerate(ch.Shape.Faces)
           if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 7) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Chanfrein.%s" % f14)
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(4000, step2)


@guard
def step2():
    from threadtool import commands
    p = commands.LAST_PANEL
    p.cb_std.setCurrentIndex(p.cb_std.findData("ISO|coarse"))
    for i in range(p.cb_des.count()):
        if p.cb_des.itemData(i) == "M10":
            p.cb_des.setCurrentIndex(i)
    p.sp_offset.setValue(2.0)
    p.sp_depth.setValue(4.5)
    QtCore.QTimer.singleShot(8000, step3)


@guard
def step3():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("M10 SUR Ø14, DÉCALAGE 2 mm, 3 FILETS")
    log("  face :", p.lbl_face.text(), "| début :", p.lbl_ref.text() or p.lbl_ref.placeholderText())
    log("  désignation :", p.cb_des.currentText(), "| décalage :", p.sp_offset.value(), "| profondeur :",
        p.sp_depth.value(), "|", p.lbl_turns.text())
    log("  message :", p.lbl_msg.text(), "| aperçu : solides", p.preview.shape_sep.getNumChildren())
    shot("off1_panneau")
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread")
    log("  accept :", ok, "| valide :", o.isValid(), "|", o.Messages)
    QtCore.QTimer.singleShot(1500, step4)


@guard
def step4():
    Gui.SendMsgToActiveView("ViewFit")
    shot("off2_resultat")
    finish()


def finish():
    log("FIN")
    LOG.close()
    try:
        for d in list(App.listDocuments()):
            App.closeDocument(d)
    except Exception:
        pass
    QtCore.QTimer.singleShot(200, QtWidgets.QApplication.instance().quit)


QtCore.QTimer.singleShot(3000, step1)
