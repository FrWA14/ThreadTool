"""Commande PartDesign_ThreadTool : crée la fonction et ouvre le panneau Tâches."""
import FreeCAD as App
import FreeCADGui as Gui
import Part

from .axis import NotThreadable
from .config import ThreadConfig
from . import detect, builder, standards, feature, creation

CMD_NAME = "PartDesign_ThreadTool"
LAST_PANEL = None          # dernier panneau ouvert (utile pour les tests de l'interface)


def _message(text):
    from PySide import QtWidgets
    QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "Filetage / taraudage", text)


def _active_body(sel):
    view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
    body = view.getActiveObject("pdbody") if view and hasattr(view, "getActiveObject") else None
    if body is None:
        for s in sel:
            b = s.Object.getParentGeoFeatureGroup() if hasattr(s.Object, "getParentGeoFeatureGroup") else None
            if s.Object.isDerivedFrom("PartDesign::Body"):
                b = s.Object
            if b is not None and b.isDerivedFrom("PartDesign::Body"):
                body = b
                break
    return body


def _preselected_face(sel, body, tip_shape):
    from .task_panel import to_local, match_face
    for s in sel:
        for sub in s.SubElementNames:
            leaf = sub.split(".")[-1]
            if not leaf.startswith(("Face", "Edge")):
                continue
            try:
                g = Part.getShape(s.Object, sub, needSubElement=True)
            except Exception:
                continue
            if leaf.startswith("Edge"):                # couture d'un cylindre : sa face (un cercle reste un appui)
                if g.Edges and not isinstance(g.Edges[0].Curve, Part.Circle):
                    name = _face_of_edge(tip_shape, to_local(g.Edges[0], body))
                    if name:
                        return name
                continue
            if not g.Faces or not isinstance(g.Faces[0].Surface, (Part.Cylinder, Part.Cone)):
                continue
            name = match_face(tip_shape, to_local(g.Faces[0], body))
            if name:
                return name
    return None


def _face_of_edge(shape, edge):
    """Face cylindrique ou conique de shape qui porte toute l'arête (couture, génératrice), ou None."""
    pts = [Part.Vertex(edge.valueAt(t)) for t in (edge.FirstParameter, (edge.FirstParameter + edge.LastParameter) / 2,
                                                  edge.LastParameter)]
    for i, f in enumerate(shape.Faces):
        if isinstance(f.Surface, (Part.Cylinder, Part.Cone)) and all(f.distToShape(p)[0] < 1e-6 for p in pts):
            return "Face%d" % (i + 1)
    return None


def _leaf(top, sub):
    """Objet réellement cliqué et son sous-élément (« Body.Sketch.Edge3 » -> Sketch, « Edge3 »)."""
    leaf_sub = sub.split(".")[-1] if sub else ""
    path = sub[:len(sub) - len(leaf_sub)]
    leaf = top.getSubObject(path, retType=1) if path else top
    if isinstance(leaf, tuple):
        leaf = leaf[0]
    return leaf, leaf_sub


def coaxial_face(shape, anchor):
    """Face cylindrique de shape qui s'appuie sur le cercle de l'appui (bout d'arbre, entrée de trou)."""
    if anchor.radius is None:
        return None
    c, n, r = anchor.centers[0], anchor.normal, anchor.radius
    from .axis import radial
    for i, f in enumerate(shape.Faces):
        s = f.Surface
        if isinstance(s, Part.Cylinder) and abs(s.Radius - r) < 1e-6 and App.Vector(s.Axis).cross(n).Length < 1e-6 \
                and radial(App.Vector(s.Center), c, n).Length < 1e-6 and f.distToShape(Part.Vertex(c))[0] <= r + 1e-6:
            return "Face%d" % (i + 1)
    return None


def external_point(top, sub, body):
    """Point (sommet, point Part / Draft…) hors du corps actif : sa forme, ou None si ce n'en est pas un."""
    if top is body or top.getParentGeoFeatureGroup() is body:
        return None
    try:
        g = Part.getShape(top, sub, needSubElement=True) if sub else Part.getShape(top)
    except Exception:
        return None
    return g if not g.isNull() and len(g.Vertexes) == 1 and not g.Edges else None


def point_binder(body, top, sub):
    """Lien de forme (SubShapeBinder) vers un point hors du corps, créé dans le corps (comme PartDesign
    pour toute référence extérieure) : le point reste paramétrique. Retourne l'appui (binder, [])."""
    b = body.newObject("PartDesign::SubShapeBinder", "PointLie")
    b.Support = [(top, (sub,) if sub else ("",))]
    b.recompute()
    if b.ViewObject:
        b.ViewObject.hide()
    return (b, [])


def selection_support(sel, body, base_shape):
    """Appui d'un trou / extrusion dans la présélection : esquisse, point, cercle, face plane.

    Retourne dict(link, picked, anchor) ou None (face cylindrique ou rien d'utilisable).
    Un point hors du corps donne dict(external=(objet, sous-élément)) : son lien de forme est créé ensuite,
    dans la transaction de la fonction."""
    from .task_panel import to_local
    inv = body.getGlobalPlacement().inverse()
    for s in sel:
        subs = list(s.SubElementNames) or [""]
        pts = list(getattr(s, "PickedPoints", [])) or [None] * len(subs)
        for sub, pnt in zip(subs, pts + [None] * (len(subs) - len(pts))):
            try:
                leaf, leaf_sub = _leaf(s.Object, sub)
            except Exception:
                continue
            if leaf is not None and external_point(s.Object, sub, body) is not None:
                return dict(external=(s.Object, sub), picked=None)
            if leaf is None or leaf.getParentGeoFeatureGroup() is not body:
                continue
            if leaf_sub.startswith("Face"):
                g = Part.getShape(s.Object, sub, needSubElement=True)
                if not g.Faces or not isinstance(g.Faces[0].Surface, Part.Plane):
                    continue                                   # face cylindrique : cas « existant »
            elif not (leaf.isDerivedFrom("Sketcher::SketchObject") or leaf_sub.startswith(("Edge", "Vertex"))
                      or leaf.isDerivedFrom("PartDesign::Point")):
                continue
            link = (leaf, [leaf_sub] if leaf_sub else [])
            picked = inv.multVec(App.Vector(pnt)) if pnt is not None else None
            try:
                anchor = creation.resolve(link, base_shape, picked)
            except NotThreadable:
                continue
            return dict(link=link, picked=picked, anchor=anchor)
    return None


def init_creation(obj, sup, cfg):
    """Trou taraudé / extrusion filetée par défaut sur l'appui présélectionné (section 13)."""
    shape = obj.BaseFeature.Shape
    a = sup["anchor"]
    obj.Support = sup["link"]
    if sup["picked"] is not None:
        obj.SupportPoint = sup["picked"]
    obj.HintAxis = a.normal
    face = coaxial_face(shape, a)
    if face:                                       # cylindre attenant : le fileter / tarauder est proposé
        obj.FaceName = face
        obj.HintRadius = 0.0
        obj.Operation = "Existant"
        try:
            info = detect.analyse(shape, face, None, cfg)
            t = (a.centers[0] - info["center"]).dot(info["axis"])
            obj.Side = "low" if abs(t - info["t_min"]) < abs(t - info["t_max"]) else "high"
            cands = standards.propose(info["kind"], info["diameter"], cfg, tapered_face=bool(info["half_angle"]))
            if cands:
                obj.Standard, obj.Designation = cands[0].entry.standard, cands[0].entry.name
            length = builder.make_plan(shape, info, feature.spec_of(obj), cfg, side=obj.Side, depth=0.001).available
            obj.Depth = builder.default_depth(length, cfg)
            return
        except Exception:
            pass
    obj.Operation = creation.OPERATIONS[1]
    diam = 2 * a.radius if a.radius else cfg.create_diameter
    cands = [c for c in standards.propose("trou", diam, cfg) if not c.entry.taper]
    if cands:
        obj.Standard, obj.Designation = cands[0].entry.standard, cands[0].entry.name
    obj.Depth = cfg.default_depth
    try:
        p = creation.plan(a, shape, obj.Operation, feature.spec_of(obj).d / 2, cfg.default_depth, False)
        obj.Depth = builder.default_depth(p.thickness, cfg) if p.thickness else cfg.default_depth
    except NotThreadable:
        pass


def _other_bodies(doc, body):
    from .task_panel import to_local
    out = []
    for o in doc.Objects:
        if o is body or not getattr(o, "Visibility", False):
            continue
        if o.isDerivedFrom("PartDesign::Body") or (o.isDerivedFrom("Part::Feature") and
                                                    o.getParentGeoFeatureGroup() is None):
            try:
                s = Part.getShape(o)
                if not s.isNull() and s.Solids:
                    out.append(to_local(s, body))
            except Exception:
                pass
    return out


def init_defaults(obj, body, face_name, cfg):
    """Face, côté, profondeur et désignation par défaut d'une nouvelle fonction (section 9.4)."""
    shape = obj.BaseFeature.Shape
    if face_name:
        info = detect.analyse(shape, face_name, None, cfg)
        e = info["ends"]
        side = "high" if e["high"]["free"] or not e["low"]["free"] else "low"
    else:
        info, side = detect.find_default(shape, cfg, _other_bodies(obj.Document, body))
        if info is None:
            raise NotThreadable("Aucune face cylindrique filetable trouvée : sélectionne une face")
    obj.FaceName = info["face_name"]
    obj.HintCenter, obj.HintAxis, obj.HintRadius = info["center"], info["axis"], info["R"]
    obj.Side = side
    cands = standards.propose(info["kind"], info["diameter"], cfg, tapered_face=bool(info["half_angle"]))
    if cands:
        obj.Standard = cands[0].entry.standard
        obj.Designation = cands[0].entry.name
    try:                                   # longueur réellement disponible (fond, épaulement, marge)
        length = builder.make_plan(shape, info, feature.spec_of(obj), cfg, side=side, depth=0.001).available
    except Exception:
        length = info["t_max"] - info["t_min"]
    obj.Depth = builder.default_depth(length, cfg)
    return info


class CommandThread:
    def GetResources(self):
        return {"Pixmap": feature.ICON,
                "MenuText": "Filetage / taraudage",
                "ToolTip": "Crée un filetage (arbre) ou un taraudage (trou) sur une face cylindrique.\n"
                           "Norme ISO, impériale, conique, trapézoïdale ou dimensions personnalisées."}

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        doc = App.ActiveDocument
        sel = Gui.Selection.getSelectionEx()
        body = _active_body(sel)
        if body is None:
            _message("Active d'abord un corps PartDesign (double-clic sur le corps).")
            return
        tip = body.Tip
        if tip is None or tip.Shape.isNull() or not tip.Shape.Solids:
            _message("Le corps actif ne contient pas encore de solide à fileter.")
            return
        cfg = ThreadConfig.load()
        sel0 = Gui.Selection.getSelectionEx("", 0)
        restore = [(doc.Name, s.Object.Name, sub) for s in sel0 for sub in (s.SubElementNames or [""])]
        face_name = _preselected_face(sel0, body, tip.Shape)
        sup = None if face_name else selection_support(sel0, body, tip.Shape)
        doc.openTransaction("Filetage")
        if sup and "external" in sup:                  # point hors du corps : lien de forme dans le corps
            try:
                sup["link"] = point_binder(body, *sup["external"])
                sup["anchor"] = creation.resolve(sup["link"], tip.Shape)
            except Exception as e:
                App.Console.PrintWarning("ThreadTool : point extérieur non utilisable : %s\n" % e)
                sup = None
        obj = feature.create(body)
        try:
            if sup:
                init_creation(obj, sup, cfg)
            else:
                init_defaults(obj, body, face_name, cfg)
        except NotThreadable as e:
            App.Console.PrintWarning("ThreadTool : %s\n" % e)
        except Exception as e:
            App.Console.PrintError("ThreadTool : %s\n" % e)
        Gui.Selection.clearSelection()
        from .task_panel import ThreadTaskPanel
        global LAST_PANEL
        LAST_PANEL = ThreadTaskPanel(obj, new=True, restore=restore)
        Gui.Control.showDialog(LAST_PANEL)


def register():
    if CMD_NAME not in Gui.listCommands():
        Gui.addCommand(CMD_NAME, CommandThread())


class ThreadToolManipulator:
    """Place la commande à côté de PartDesign_Hole (juste avant dans la barre d'outils, juste après dans le menu)."""

    def modifyToolBars(self):
        return [{"insert": CMD_NAME, "toolItem": "PartDesign_Hole"}]

    def modifyMenuBar(self):
        return [{"append": CMD_NAME, "menuItem": "PartDesign_Hole"}]


_MANIPULATOR = None


def setup_gui():
    global _MANIPULATOR
    from . import preferences
    register()
    Gui.addPreferencePage(preferences.ThreadPreferencePage, "Part/Part Design")
    if _MANIPULATOR is None:
        _MANIPULATOR = ThreadToolManipulator()
        Gui.addWorkbenchManipulator(_MANIPULATOR)
