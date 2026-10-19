"""Changement d'opération selon l'appui : freecad tests/gui_support.py (captures dans THREADTOOL_GUI_OUT).

Bloc 30 × 30 × 20 + cylindre Ø10 × 10 posé dessus. Pour chaque sélection, l'outil est lancé puis l'opération
est changée dans le panneau :
- couture et face cylindrique -> « Trou taraudé » doit reprendre le cercle du bout (version 0.6.1) ;
- arête circulaire et face plane du bout : inchangés ;
- point sur le bout du cylindre -> « Fileter la face existante » prend le cylindre ;
- point sur un flanc du bloc -> « Fileter la face existante » refusé (aucun cercle ni arc), OK désactivé ;
  « Extrusion filetée » reste possible."""
import os, sys, tempfile, traceback
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

OUT = os.environ.get("THREADTOOL_GUI_OUT", tempfile.gettempdir())
LOG = open(os.path.join(OUT, "gui_support.log"), "w", encoding="utf-8")
V = App.Vector
S = {}
FAILS = []
EXIST, HOLE, PAD = "Existant", "Trou taraudé", "Extrusion filetée"


def log(*a):
    LOG.write(" ".join(str(x) for x in a) + "\n")
    LOG.flush()


def check(cond, msg):
    log(("  ok   " if cond else "  ÉCHEC ") + msg)
    if not cond:
        FAILS.append(msg)


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


def ok_button():
    bb = [b for b in Gui.getMainWindow().findChildren(QtWidgets.QDialogButtonBox)
          if b.button(QtWidgets.QDialogButtonBox.Ok) and b.isVisible()]
    return bb[0].button(QtWidgets.QDialogButtonBox.Ok) if bb else None


def panel():
    from threadtool import commands
    return commands.LAST_PANEL


def state(p):
    b = ok_button()
    st = dict(op=p.obj.Operation, support=p.lbl_sup.text(), face=p.obj.FaceName, info=p.lbl_faceinfo.text(),
              msg=p.lbl_msg.text(), des=p.cb_des.currentText(), ok=b.isEnabled() if b else None)
    log("   ", st)
    return st


def set_op(p, op):
    p.cb_op.setCurrentIndex(p.cb_op.findData(op))
    Gui.updateGui()


# ------------------------------------------------------------------ déroulé (une étape par minuterie)
STEPS = []


def step(fn):
    STEPS.append(fn)
    return fn


def run_next(delay=300):
    def go():
        if not STEPS:
            return finish()
        fn = STEPS.pop(0)
        try:
            fn()
            run_next(fn.__dict__.get("wait", 2500))
        except Exception:
            log("EXCEPTION", fn.__name__, traceback.format_exc())
            finish()
    QtCore.QTimer.singleShot(delay, go)


def wait(ms):
    def deco(fn):
        fn.wait = ms
        return fn
    return deco


def launch(sub, pnt=(15, 15, 30)):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(S["doc"].Name, "Body", sub, *pnt)
    Gui.runCommand("PartDesign_ThreadTool")


def close():
    panel().reject()
    Gui.Control.closeDialog()


@step
def build():
    Gui.getMainWindow().resize(1400, 950)
    Gui.activateWorkbench("PartDesignWorkbench")
    doc = App.newDocument("Appuis")
    body = doc.addObject("PartDesign::Body", "Body")
    Gui.ActiveDocument.ActiveView.setActiveObject("pdbody", body)
    box = body.newObject("PartDesign::AdditiveBox", "Bloc")
    box.Length, box.Width, box.Height = 30, 30, 20
    cyl = body.newObject("PartDesign::AdditiveCylinder", "Cyl")
    cyl.Radius, cyl.Height = 5, 10
    cyl.Placement = App.Placement(V(15, 15, 20), App.Rotation())
    doc.recompute()
    sh = cyl.Shape
    for i, e in enumerate(sh.Edges):
        if isinstance(e.Curve, Part.Circle) and abs(e.Curve.Radius - 5) < 1e-6 and abs(e.Curve.Center.z - 30) < 1e-6:
            S["circle"] = "Edge%d" % (i + 1)
        if isinstance(e.Curve, Part.Line) and abs(e.BoundBox.ZMin - 20) < 1e-6 and abs(e.BoundBox.ZMax - 30) < 1e-6:
            S["seam"] = "Edge%d" % (i + 1)
    for i, f in enumerate(sh.Faces):
        if isinstance(f.Surface, Part.Plane) and abs(f.CenterOfMass.z - 30) < 1e-6:
            S["top"] = "Face%d" % (i + 1)
        if isinstance(f.Surface, Part.Cylinder):
            S["cyl"] = "Face%d" % (i + 1)
    for name, p in (("PtBout", V(17, 15, 30)), ("PtFlanc", V(0, 15, 10))):
        pt = body.newObject("PartDesign::Point", name)
        pt.MapMode = "Deactivated"
        pt.Placement = App.Placement(p, App.Rotation())
    doc.recompute()
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    S["doc"], S["body"] = doc, body
    log("arêtes / faces :", {k: S[k] for k in ("circle", "seam", "top", "cyl")})


def existing_then_hole(key, label):
    @step
    def open_():
        log("== %s (Cyl:%s)" % (label, S[key]))
        launch("Cyl.%s" % S[key])

    @step
    def to_hole():
        p = panel()
        st = state(p)
        check(st["op"] == EXIST and st["face"] == S["cyl"], "%s : filetage de la face %s proposé" % (label, S["cyl"]))
        set_op(p, HOLE)

    @step
    @wait(800)
    def after():
        st = state(panel())
        check(st["support"].startswith("Cyl:") and "Ø 10.000" in st["info"] and "Choisis" not in st["msg"]
              and st["ok"], "%s -> trou taraudé : appui au cercle Ø10 du bout (%s)" % (label, st["support"]))
        close()


existing_then_hole("seam", "couture du cylindre")
existing_then_hole("cyl", "face cylindrique")
existing_then_hole("circle", "arête circulaire")
existing_then_hole("top", "face plane du bout")


@step
def point_end():
    log("== point sur le bout du cylindre")
    launch("PtBout.", (17, 15, 30))


@step
def point_end_exist():
    p = panel()
    st = state(p)
    check(st["op"] == HOLE and "cercle Ø 10.000" in st["info"], "point sur le bout : trou taraudé par défaut, "
          "cercle trouvé (%s)" % st["info"])
    set_op(p, EXIST)


@step
@wait(800)
def point_end_check():
    st = state(panel())
    check(st["face"] == S["cyl"] and st["ok"] and "aucun cercle" not in st["msg"],
          "point sur le bout -> fileter la face existante : %s" % st["face"])
    shot("sup1_point_bout_existant")
    close()


@step
def point_side():
    log("== point sur un flanc du bloc")
    launch("PtFlanc.", (0, 15, 10))


@step
def point_side_exist():
    p = panel()
    st = state(p)
    check(st["op"] == HOLE and "aucun cercle ni arc" in st["info"] and st["ok"],
          "point sur un flanc : trou taraudé par défaut (%s)" % st["info"])
    set_op(p, EXIST)


@step
@wait(800)
def point_side_refused():
    p = panel()
    st = state(p)
    check("aucun cercle ou arc pouvant être fileté" in st["msg"] and st["ok"] is False and not st["face"],
          "point sur un flanc -> fileter la face existante refusé, OK désactivé")
    check(p.accept() is False, "OK refusé")
    shot("sup2_point_flanc_refus")
    set_op(p, PAD)


@step
@wait(800)
def point_side_pad():
    st = state(panel())
    check(st["op"] == PAD and st["ok"], "point sur un flanc -> extrusion filetée possible")
    close()


@step
def external_point():
    log("== point Part hors du corps, sur un flanc du bloc (0.6.2)")
    doc = S["doc"]
    v = doc.addObject("Part::Vertex", "PointPart")
    v.X, v.Y, v.Z = 0, 10, 8
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "PointPart")
    Gui.runCommand("PartDesign_ThreadTool")


@step
def external_exist():
    p = panel()
    st = state(p)
    check(st["op"] == HOLE and st["support"].startswith("PointLie") and "aucun cercle ni arc" in st["info"]
          and st["ok"], "point extérieur : trou taraudé par défaut, lien de forme créé (%s)" % st["info"])
    set_op(p, EXIST)


@step
@wait(800)
def external_refused():
    p = panel()
    st = state(p)
    check("aucun cercle ou arc" in st["msg"] and st["ok"] is False, "point extérieur -> face existante refusé")
    set_op(p, HOLE)


@step
@wait(800)
def external_back():
    st = state(panel())
    check(st["op"] == HOLE and st["support"].startswith("PointLie") and st["ok"] and not st["msg"].startswith("<span style=\"color:#c00000\""),
          "point extérieur : retour au trou taraudé, point et face conservés")
    shot("sup3_point_exterieur")
    close()


@step
@wait(800)
def external_cancel():
    left = [o.Name for o in S["doc"].Objects if o.Name.startswith("PointLie")]
    check(not left, "Annuler supprime aussi le lien de forme (%s)" % left)


def finish():
    log("\nAPPUIS : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
    log("FIN")
    LOG.close()
    try:
        for d in list(App.listDocuments()):
            App.closeDocument(d)
    except Exception:
        pass
    QtCore.QTimer.singleShot(200, QtWidgets.QApplication.instance().quit)


run_next(3000)
