"""Test de l'interface : freecad tests/gui_test.py (ouvre FreeCAD, fait des captures, se ferme)."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_test.log"), "w", encoding="utf-8")


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
    log("capture", name)


S = {}


def guard(fn):
    def w():
        try:
            fn()
        except Exception:
            log("EXCEPTION dans", fn.__name__, traceback.format_exc())
            finish()
    return w


@guard
def step1():
    Gui.getMainWindow().resize(1400, 900)
    Gui.activateWorkbench("PartDesignWorkbench")
    Gui.updateGui()
    mw = Gui.getMainWindow()
    tbs = [tb.objectName() for tb in mw.findChildren(QtWidgets.QToolBar)
           if any(a.objectName() == "PartDesign_ThreadTool" for a in tb.actions())]
    log("barres d'outils contenant la commande :", tbs)
    menus = [m.title() for m in mw.findChildren(QtWidgets.QMenu)
             if any(a.objectName() == "PartDesign_ThreadTool" for a in m.actions())]
    log("menus contenant la commande :", menus)
    hole_tbs = [tb.objectName() for tb in mw.findChildren(QtWidgets.QToolBar)
                if any(a.objectName() == "PartDesign_Hole" for a in tb.actions())]
    log("barres d'outils contenant Perçage :", hole_tbs)
    doc = App.newDocument("GuiTest")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    cyl = body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
    cyl.Radius, cyl.Height = 2.0, 12.0
    hole = body.newObject("PartDesign::SubtractiveCylinder", "Hole")
    hole.Radius, hole.Height = 2.459 / 2, 12.0
    doc.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    Gui.activeDocument().activeView().viewIsometric()
    Gui.runCommand("PartDesign_ThreadTool")
    S["doc"] = doc
    QtCore.QTimer.singleShot(2500, step2)


@guard
def step2():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("dialogue actif :", Gui.Control.activeDialog(), "| panneau :", type(p).__name__)
    log("face :", p.lbl_face.text())
    log("référence :", p.lbl_ref.text())
    log("norme :", p.cb_std.currentText(), "| désignation :", p.cb_des.currentText())
    log("info :", p.lbl_info.text())
    log("profondeur :", p.sp_depth.value(), "| jeu :", p.sp_clr.value(), "| aperçu :", p.ck_preview.isChecked())
    log("type :", "taraudage" if p.rb_tap.isChecked() else "filetage", "| message :", p.lbl_msg.text())
    log("noeuds d'aperçu :", p.preview.shape_sep.getNumChildren(), "| axe :", p.preview.axis_sep.getNumChildren())
    log("objets du document :", [o.Name for o in S["doc"].Objects])
    shot("1_panneau")
    # clic simulé : plan XY de l'Origin comme référence de hauteur
    doc = S["doc"]
    p.btn_ref.setChecked(True)
    Gui.Selection.addSelection(doc.Name, "Body", "Origin.XY_Plane.")
    Gui.updateGui()
    log("référence après clic :", p.lbl_ref.text(), "| côté :", p.obj.Side, "| message :", p.lbl_msg.text())
    p.clear_ref()
    p.flip_side() if p.obj.Side != "high" else None
    # clic simulé : face du trou -> doit devenir un taraudage
    import Part
    base = doc.getObject("Hole").Shape
    fn = [("Face%d" % (i + 1)) for i, f in enumerate(base.Faces)
          if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 2.459 / 2) < 1e-6][0]
    p.btn_face.setChecked(True)
    Gui.Selection.addSelection(doc.Name, "Body", "Hole." + fn)
    Gui.updateGui()
    log("face du trou après clic :", p.lbl_face.text(), "| désignation :", p.cb_des.currentText(),
        "| type :", "taraudage" if p.rb_tap.isChecked() else "filetage")
    QtCore.QTimer.singleShot(4000, step2b)


@guard
def step2b():
    from threadtool import commands
    import Part
    p = commands.LAST_PANEL
    doc = S["doc"]
    base = doc.getObject("Hole").Shape
    shot("1b_trou")
    # retour à la face extérieure
    fo = [("Face%d" % (i + 1)) for i, f in enumerate(base.Faces)
          if isinstance(f.Surface, Part.Cylinder) and abs(f.Surface.Radius - 2.0) < 1e-6][0]
    p.btn_face.setChecked(True)
    Gui.Selection.addSelection(doc.Name, "Body", "Hole." + fo)
    Gui.updateGui()
    log("retour face extérieure :", p.lbl_face.text())
    # bascule vers taraudage puis retour, pas à gauche
    p.rb_left.setChecked(True)
    p.cb_std.setCurrentIndex(p.cb_std.findData("custom"))
    Gui.updateGui()
    log("personnalisé visible :", p.grp_custom.isVisible())
    p.cb_std.setCurrentIndex(p.cb_std.findData("ISO|coarse"))
    Gui.updateGui()
    log("ISO -> désignation :", p.cb_des.currentText())
    QtCore.QTimer.singleShot(1500, step3)


@guard
def step3():
    from threadtool import commands
    p = commands.LAST_PANEL
    shot("2_iso")
    ok = p.accept()
    log("accept ->", ok, "| message :", p.lbl_msg.text())
    if ok:
        Gui.Control.closeDialog()
    doc = S["doc"]
    obj = doc.getObject("Thread")
    log("fonction :", obj and obj.isValid(), obj and obj.getStatusString(), "| tip :", doc.getObject("Body").Tip.Name,
        "| désignation :", obj and obj.Designation, "| gauche :", obj and obj.LeftHanded)
    log("objets du document :", [o.Name for o in doc.Objects])
    QtCore.QTimer.singleShot(1000, step4)


@guard
def step4():
    shot("3_resultat")
    doc = S["doc"]
    Gui.ActiveDocument.setEdit("Thread", 0)
    QtCore.QTimer.singleShot(2000, step5)


@guard
def step5():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("édition rouverte :", Gui.Control.activeDialog(), "| désignation :", p.cb_des.currentText())
    shot("4_edition")
    p.reject()
    Gui.Control.closeDialog()
    doc = S["doc"]
    log("après annulation :", doc.getObject("Thread").isValid(), doc.getObject("Thread").Designation)
    # nouvelle fonction annulée : ne doit rien laisser
    Gui.runCommand("PartDesign_ThreadTool")
    QtCore.QTimer.singleShot(1500, step6)


@guard
def step6():
    from threadtool import commands
    p = commands.LAST_PANEL
    log("2e fonction, face par défaut :", p.lbl_face.text())
    p.reject()
    Gui.Control.closeDialog()
    log("objets après annulation :", [o.Name for o in S["doc"].Objects])
    from threadtool.preferences import ThreadPreferencePage
    pg = ThreadPreferencePage()
    pg.loadSettings()
    pg.form.resize(520, 560)
    pg.form.show()
    Gui.updateGui()
    pg.form.grab().save(os.path.join(OUT, "5_preferences.png"))
    pg.form.close()
    log("page de préférences OK")
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
