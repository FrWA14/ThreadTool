"""Têtes dans l'interface : freecad tests/gui_heads.py (captures dans THREADTOOL_GUI_OUT)."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_heads.log"), "w", encoding="utf-8")
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



def hstate(p):
    log("  type :", "taraudage" if p.rb_tap.isChecked() else "filetage", "| tête :", p.cb_head.currentText(),
        "| actif :", p.cb_head.isEnabled(), "| empreinte :", p.cb_drive.currentText() if p.cb_drive.isVisible() else "-",
        "| position :", p.cb_hpos.currentText() if p.cb_hpos.isVisible() else "-")
    log("  info tête :", p.lbl_head.text(), "| message :", p.lbl_msg.text(),
        "| aperçu : solides", p.preview.shape_sep.getNumChildren())


def pick(cb, data):
    cb.setCurrentIndex(cb.findData(data))


@guard
def step1():
    Gui.getMainWindow().resize(1400, 1000)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("Tetes")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 30, 30, 20
    c = body.newObject("PartDesign::AdditiveCylinder", "Tige")
    c.Radius, c.Height = 2.5, 20
    c.Placement = App.Placement(V(15, 15, 20), App.Rotation())
    doc.recompute()
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    S["doc"] = doc
    f = [("Face%d" % (i + 1)) for i, f in enumerate(c.Shape.Faces)
         if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 2.5) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Tige.%s" % f)
    log("1. FILETAGE M5 SUR LA TIGE + TÊTE CHC")
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(4000, step2)


@guard
def step2():
    from threadtool import commands
    p = commands.LAST_PANEL
    pick(p.cb_std, "ISO|coarse")
    for i in range(p.cb_des.count()):
        if p.cb_des.itemData(i) == "M5":
            p.cb_des.setCurrentIndex(i)
    p.sp_depth.setValue(12)
    pick(p.cb_head, "ISO 4762")
    pick(p.cb_hpos, "Face de début")
    Gui.updateGui()
    hstate(p)
    pick(p.cb_drive, "Torx")
    QtCore.QTimer.singleShot(6000, step3)


@guard
def step3():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("  -> Torx :")
    hstate(p)
    shot("h1_vis_panneau")
    pick(p.cb_std, "custom")
    Gui.updateGui()
    log("  -> hors norme :")
    hstate(p)
    pick(p.cb_std, "ISO|coarse")
    for i in range(p.cb_des.count()):
        if p.cb_des.itemData(i) == "M5":
            p.cb_des.setCurrentIndex(i)
    Gui.updateGui()
    QtCore.QTimer.singleShot(5000, step4)


@guard
def step4():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("  -> retour ISO :")
    hstate(p)
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread")
    log("  accept :", ok, "| valide :", o.isValid(), o.getStatusString(), "|", o.ScrewHead, o.Drive, "|", o.Messages)
    top = [("Face%d" % (i + 1)) for i, f in enumerate(o.Shape.Faces)
           if isinstance(f.Surface, Part.Plane) and abs(f.CenterOfMass.z - 20) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(S["doc"].Name, "Body", "Thread.%s" % top, 5, 5, 20)
    log("2. TROU TARAUDÉ M6 + LAMAGE SUR LA FACE CLIQUÉE")
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(5000, step5)


@guard
def step5():
    from threadtool import commands
    p = commands.LAST_PANEL
    hstate(p)
    pick(p.cb_head, "ISO 4762")
    p.sp_depth.setValue(15)
    QtCore.QTimer.singleShot(6000, step6)


@guard
def step6():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("  -> lamage :")
    hstate(p)
    shot("h2_lamage_panneau")
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread001")
    log("  accept :", ok, "| valide :", o.isValid(), o.getStatusString(), "|", o.HoleHead, o.HeadDiameter, o.HeadHeight,
        "|", o.Messages)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.SendMsgToActiveView("ViewFit")
    QtCore.QTimer.singleShot(1500, step7)


@guard
def step7():
    shot("h3_resultat")
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
