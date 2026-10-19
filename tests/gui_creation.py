"""Trou taraudé / extrusion filetée dans l'interface : freecad tests/gui_creation.py (captures dans THREADTOOL_GUI_OUT)."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_creation.log"), "w", encoding="utf-8")
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


def sketch(body, name, z, geos):
    sk = body.newObject("Sketcher::SketchObject", name)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    for g in geos:
        sk.addGeometry(g)
    return sk


@guard
def step1():
    Gui.getMainWindow().resize(1400, 950)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("Creation")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 30, 30, 20
    sk = sketch(body, "Sk", 20, [Part.Circle(V(8, 8, 0), V(0, 0, 1), 2.5), Part.Circle(V(22, 15, 0), V(0, 0, 1), 2.5)])
    pv = body.newObject("PartDesign::Point", "PtVide")
    pv.MapMode = "Deactivated"
    pv.Placement = App.Placement(V(5, 5, 60), App.Rotation())
    doc.recompute()
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    S["doc"], S["body"] = doc, body
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Body", "Sk.")
    log("1. ESQUISSE SÉLECTIONNÉE (2 cercles Ø5)")
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(5000, step2)


@guard
def step2():
    from threadtool import commands
    p = commands.LAST_PANEL
    panel_state(p)
    shot("cr1_esquisse_panneau")
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread")
    log("  accept :", ok, "| valide :", o.isValid(), o.getStatusString(), "|", o.Designation, o.Depth, "|", o.Messages,
        "| esquisse cachée :", not S["doc"].getObject("Sk").ViewObject.Visibility)
    top = [("Face%d" % (i + 1)) for i, f in enumerate(o.Shape.Faces)
           if isinstance(f.Surface, Part.Plane) and abs(f.CenterOfMass.z - 20) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(S["doc"].Name, "Body", "Thread.%s" % top, 25, 25, 20)
    log("2. FACE PLANE CLIQUÉE en (25, 25, 20) :", top)
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(5000, step3)


@guard
def step3():
    from threadtool import commands
    p = commands.LAST_PANEL
    panel_state(p)
    p.cb_op.setCurrentIndex(p.cb_op.findData("Extrusion filetée"))
    Gui.updateGui()
    QtCore.QTimer.singleShot(3000, step4)


@guard
def step4():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("  -> extrusion :")
    panel_state(p)
    shot("cr2_extrusion_panneau")
    p.reject()
    Gui.Control.closeDialog()
    QtCore.QTimer.singleShot(1000, step5)


@guard
def step5():
    sel = Gui.Selection.getSelectionEx("", 0)
    log("  annuler -> sélection conservée :", [(s.Object.Name, list(s.SubElementNames)) for s in sel])
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(S["doc"].Name, "Body", "PtVide.")
    log("3. POINT DANS LE VIDE")
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(5000, step6)


@guard
def step6():
    from threadtool import commands
    p = commands.LAST_PANEL
    panel_state(p)
    shot("cr3_vide_panneau")
    log("  accept refusé :", p.accept() is False)
    p.reject()
    Gui.Control.closeDialog()
    S["doc"].getObject("Body").ViewObject.Transparency = 0
    Gui.SendMsgToActiveView("ViewFit")
    QtCore.QTimer.singleShot(1500, step7)


@guard
def step7():
    shot("cr4_resultat")
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
