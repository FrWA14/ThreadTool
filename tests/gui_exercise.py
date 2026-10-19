"""Exercice de référence dans l'interface : freecad tests/gui_exercise.py (captures dans THREADTOOL_GUI_OUT)."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_exercise.log"), "w", encoding="utf-8")
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


def panel_state(p):
    for name in ("lbl_face", "lbl_axis", "lbl_ref", "lbl_len"):
        le = getattr(p, name)
        log("  %-9s : %s" % (name[4:], le.text() or "[gris] " + le.placeholderText()))
    log("  info      :", p.lbl_faceinfo.text())
    log("  désignation :", p.cb_des.currentText(), "| profondeur :", p.sp_depth.value(),
        "| type :", "taraudage" if p.rb_tap.isChecked() else "filetage", "| message :", p.lbl_msg.text())
    log("  aperçu : sillons", p.preview.shape_sep.getNumChildren(), "| surlignage", p.preview.hl_sep.getNumChildren())


def circle_sketch(body, name, z, r):
    sk = body.newObject("Sketcher::SketchObject", name)
    xy = [o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
    sk.AttachmentSupport = [(xy, "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    sk.addGeometry(Part.Circle(V(5, 5, 0), V(0, 0, 1), r))
    return sk


@guard
def step1():
    Gui.getMainWindow().resize(1400, 950)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("Exercice")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    cube = body.newObject("PartDesign::AdditiveBox", "Cube")
    cube.Length = cube.Width = cube.Height = 10
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile = circle_sketch(body, "SketchD10", 10, 5)
    pad.Length = 20
    pocket = body.newObject("PartDesign::Pocket", "Pocket")
    pocket.Profile = circle_sketch(body, "SketchD5", 30, 2.5)
    pocket.Length = 10
    doc.recompute()
    for o in (doc.getObject("SketchD10"), doc.getObject("SketchD5")):
        o.ViewObject.hide()
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    S["doc"], S["body"] = doc, body
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(5000, step2)


@guard
def step2():
    from threadtool import commands
    p = commands.LAST_PANEL
    p.sp_depth.setValue(22.0)                      # 22 mm demandés
    QtCore.QTimer.singleShot(5000, step3)


@guard
def step3():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("FILETAGE (22 mm demandés)")
    panel_state(p)
    shot("ex1_filetage_panneau")
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread")
    log("  accept :", ok, "| valide :", o.isValid(), o.getStatusString(), "| profondeur :", o.Depth, "|", o.Messages)
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(4000, step4)


@guard
def step4():
    from threadtool import commands
    p = commands.LAST_PANEL
    doc = S["doc"]
    base = doc.getObject("Thread").Shape
    fn = [("Face%d" % (i + 1)) for i, f in enumerate(base.Faces)
          if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 2.5) < 1e-6][0]
    p.lbl_face.setText("%s:%s" % (doc.getObject("Thread").Label, fn))   # saisie au clavier
    p.lbl_face.editingFinished.emit()
    Gui.updateGui()
    log("SAISIE « %s:%s » -> %s" % (doc.getObject("Thread").Label, fn, p.lbl_faceinfo.text()))
    p.lbl_ref.setText(""); p.lbl_ref.editingFinished.emit()           # effacé : début automatique
    items = [p.cb_des.itemData(i) for i in range(p.cb_des.count())]
    idx = p.cb_std.findData("ISO|coarse")
    p.cb_std.setCurrentIndex(idx)
    Gui.updateGui()
    log("LISTE ISO pas gros :", [p.cb_des.itemData(i) for i in range(min(8, p.cb_des.count()))])
    for i in range(p.cb_des.count()):
        if p.cb_des.itemData(i) == "M5":
            p.cb_des.setCurrentIndex(i)
    p.sp_depth.setValue(11.0)                      # 11 mm demandés
    QtCore.QTimer.singleShot(6000, step5)


@guard
def step5():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("TARAUDAGE (11 mm demandés)")
    panel_state(p)
    shot("ex2_taraudage_panneau")
    ok = p.accept()
    if ok:
        Gui.Control.closeDialog()
    o = S["doc"].getObject("Thread001")
    log("  accept :", ok, "| valide :", o and o.isValid(), o and o.getStatusString(), "| profondeur :", o and o.Depth,
        "|", o and o.Messages)
    S["doc"].getObject("Body").ViewObject.Transparency = 0
    QtCore.QTimer.singleShot(1500, step6)


@guard
def step6():
    Gui.SendMsgToActiveView("ViewFit")
    shot("ex3_resultat")
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
