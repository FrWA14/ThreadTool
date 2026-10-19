"""Fonction paramétrique PartDesign « Filetage » (PartDesign::FeaturePython)."""
import os
import FreeCAD as App
import Part

from .axis import NotThreadable, radial
from .config import ThreadConfig
from . import detect, builder, thread_data, thread_spec, creation, heads
from .thread_spec import ThreadSpec

ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "Resources", "icons", "ThreadTool.svg")
STD_ENUM = thread_data.STANDARDS + ["custom"]
MODE_ENUM = ["Auto", "Taraudage", "Filetage"]
SIDE_ENUM = ["high", "low"]


def _add(obj, typ, name, group, doc, default=None):
    if name not in obj.PropertiesList:
        obj.addProperty(typ, name, group, doc)
        if default is not None:
            setattr(obj, name, default)


class ThreadFeature:
    def __init__(self, obj):
        obj.Proxy = self
        self.setup(obj)

    def setup(self, obj):
        cfg = ThreadConfig.load()
        G, C, R = "Filetage", "Personnalisé", "Référence"
        _add(obj, "App::PropertyEnumeration", "Operation", G,
             "Existant = fileter / tarauder une face cylindrique ; Trou taraudé / Extrusion filetée = créés sur l'appui")
        cur = obj.getEnumerationsOfProperty("Operation")
        if cur != creation.OPERATIONS:                       # liste absente ou ancienne (« Tenon fileté »)
            idx = cur.index(obj.Operation) if cur and obj.Operation in cur else 0
            obj.Operation = creation.OPERATIONS
            obj.Operation = creation.OPERATIONS[idx]
        _add(obj, "App::PropertyLinkSub", "Support", R, "Appui d'un trou / extrusion : esquisse, point, cercle ou face plane")
        _add(obj, "App::PropertyVector", "SupportPoint", R, "Point cliqué sur la face d'appui (repère du corps)")
        _add(obj, "App::PropertyBool", "Reversed", R, "Trou / extrusion : inverser le sens automatique", False)
        _add(obj, "App::PropertyString", "FaceName", R, "Face cylindrique de la fonction précédente (FaceN)")
        _add(obj, "App::PropertyVector", "HintCenter", R, "Point de l'axe (pour retrouver la face si son nom change)")
        _add(obj, "App::PropertyVector", "HintAxis", R, "Direction de l'axe (idem)")
        _add(obj, "App::PropertyFloat", "HintRadius", R, "Rayon de la face (idem)")
        _add(obj, "App::PropertyEnumeration", "Side", R, "Extrémité de départ : high = côté +axe, low = côté -axe")
        if not obj.getEnumerationsOfProperty("Side"):
            obj.Side = SIDE_ENUM
        _add(obj, "App::PropertyLinkSub", "HeightReference", R, "Plan ou face plane d'où se mesure la profondeur")
        _add(obj, "App::PropertyLinkSub", "AxisReference", R, "Axe imposé (facultatif)")
        _add(obj, "App::PropertyLength", "StartOffset", R,
             "Décalage du début du filet depuis la face (ou le plan) de début ; l'entrée est ramenée au Ø de pied", 0.0)
        _add(obj, "App::PropertyEnumeration", "Standard", G, "Norme (custom = personnalisé)")
        if not obj.getEnumerationsOfProperty("Standard"):
            obj.Standard = STD_ENUM
        _add(obj, "App::PropertyString", "Designation", G, "Désignation normalisée (M4, 1/4\"-20 UNC, G 1/2…)", "M4")
        _add(obj, "App::PropertyLength", "Depth", G, "Longueur filetée", cfg.default_depth)
        _add(obj, "App::PropertyBool", "LeftHanded", G, "Pas à gauche", cfg.default_left_hand)
        _add(obj, "App::PropertyLength", "PitchOverride", G, "Pas personnalisé pour la norme choisie (0 = pas normalisé)", 0.0)
        _add(obj, "App::PropertyEnumeration", "Mode", G, "Taraudage / filetage (Auto = détecté)")
        if not obj.getEnumerationsOfProperty("Mode"):
            obj.Mode = MODE_ENUM
        _add(obj, "App::PropertyLength", "Clearance", G, "Jeu sur le diamètre (impression 3D)", cfg.clearance)
        _add(obj, "App::PropertyLength", "CustomDiameter", C, "Ø nominal ; 0 = garder le Ø de la face", 0.0)
        _add(obj, "App::PropertyLength", "CustomPitch", C, "Pas", 2.0)
        _add(obj, "App::PropertyInteger", "CustomStarts", C, "Nombre de filets", 1)
        _add(obj, "App::PropertyAngle", "CustomFlankA", C, "Demi-angle flanc 1", 30.0)
        _add(obj, "App::PropertyAngle", "CustomFlankB", C, "Demi-angle flanc 2 (différent = dent de scie)", 30.0)
        _add(obj, "App::PropertyLength", "CustomDepth", C, "Profondeur du filet ; 0 = auto", 0.0)
        _add(obj, "App::PropertyLength", "CustomCrest", C, "Méplat de sommet ; 0 = auto", 0.0)
        _add(obj, "App::PropertyBool", "CustomTaper", C, "Conique 1:16", False)
        H = "Tête"
        _add(obj, "App::PropertyEnumeration", "HoleHead", H, "Taraudage : lamage / fraisage pour noyer la tête de vis")
        if not obj.getEnumerationsOfProperty("HoleHead"):
            obj.HoleHead = heads.HOLE_HEADS
        _add(obj, "App::PropertyEnumeration", "ScrewHead", H, "Filetage : tête de vis ajoutée à une extrémité")
        if not obj.getEnumerationsOfProperty("ScrewHead"):
            obj.ScrewHead = heads.SCREW_HEAD_NAMES
        _add(obj, "App::PropertyEnumeration", "HeadPosition", H, "Filetage : extrémité qui reçoit la tête")
        if not obj.getEnumerationsOfProperty("HeadPosition"):
            obj.HeadPosition = heads.POSITIONS
        _add(obj, "App::PropertyEnumeration", "Drive", H, "Empreinte creusée au centre de la tête de vis")
        if not obj.getEnumerationsOfProperty("Drive"):
            obj.Drive = heads.DRIVES
        _add(obj, "App::PropertyBool", "HeadCustom", H, "Cotes de tête personnalisées (sinon celles de la norme)", False)
        _add(obj, "App::PropertyLength", "HeadDiameter", H, "Ø du lamage / fraisage, ou Ø (sur plats) de la tête", 0.0)
        _add(obj, "App::PropertyLength", "HeadHeight", H, "Profondeur du lamage, ou hauteur de la tête", 0.0)
        _add(obj, "App::PropertyAngle", "HeadAngle", H, "Angle du fraisage", 90.0)
        _add(obj, "App::PropertyLength", "DriveSize", H, "Taille de l'empreinte (sur plats, largeur, Ø)", 0.0)
        _add(obj, "App::PropertyLength", "DriveDepth", H, "Profondeur de l'empreinte", 0.0)
        _add(obj, "App::PropertyString", "DetectedKind", "Résultat", "Type détecté")
        _add(obj, "App::PropertyLength", "DetectedDiameter", "Résultat", "Ø mesuré de la face")
        _add(obj, "App::PropertyString", "Messages", "Résultat", "Avertissements du dernier calcul")
        for p in ("DetectedKind", "DetectedDiameter", "Messages", "HintCenter", "HintAxis", "HintRadius"):
            obj.setEditorMode(p, 1)

    def onDocumentRestored(self, obj):
        self.setup(obj)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads

    def execute(self, obj):
        base = obj.BaseFeature
        if base is None or base.Shape.isNull():
            raise NotThreadable("Aucune fonction précédente dans le corps")
        shape = base.Shape.copy()
        cfg = ThreadConfig.load()
        if creating(obj):
            cc = creation_context(obj, shape, cfg)
            h, hmsg = head_of(obj, cc["spec"], cc["plan"].kind)
            off = obj.StartOffset.Value
            if h and h.get("type") == "lamage":
                off = max(off, h["depth"])                    # le filet commence sous le lamage
            res, msgs, cuts, adds = creation.build(shape, cc["plan"], cc["spec"], cfg, obj.Clearance.Value, off, head=h)
            if h and h.get("type") == "lamage":
                msgs = [m for m in msgs if not m.startswith("Entrée de")]
            msgs += [hmsg] if hmsg else []
            msgs += set_addsub(obj, shape, res, cuts, adds)
            obj.DetectedKind = cc["plan"].kind
            obj.DetectedDiameter = 2 * cc["plan"].r
            obj.Messages = " ; ".join(msgs)
            obj.Shape = res
            return
        ctx = context(obj, shape, cfg)
        info, spec, kw = ctx["info"], ctx["spec"], ctx["kw"]
        kind = kw["kind"] or info["kind"]
        h, hmsg = head_of(obj, spec, kind)
        if h and h.get("type") == "lamage" and kw["ref_t"] is None:
            kw["start_offset"] = max(kw["start_offset"], h["depth"])   # le filet commence sous le lamage
        res, plan = builder.build(shape, info, spec, cfg, **kw)
        msgs = [m for m in plan.messages if not (h and h.get("type") == "lamage" and m.startswith("Entrée de"))]
        msgs += [hmsg] if hmsg else []
        cuts = list(plan.cut_tools)
        adds = [plan.add_tool] if plan.add_tool is not None else []
        if h:
            base, direction = head_frame(plan, info, h)
            res, m, tool = heads.apply(res, h, spec.d or 2 * plan.R, kind, base, direction)
            (cuts if kind == "trou" else adds).append(tool)
            msgs += [m] if m else []
        msgs += set_addsub(obj, shape, res, cuts, adds)
        obj.DetectedKind = info["kind"]
        obj.DetectedDiameter = info["diameter"]
        obj.Messages = " ; ".join(msgs)
        obj.Shape = res


def find_face(obj, shape, cfg):
    """La face nommée si elle correspond encore aux indices géométriques, sinon la face qui y correspond."""
    face = None
    if obj.FaceName:
        try:
            face = shape.getElement(obj.FaceName)
        except Exception:
            face = None
    if face is not None and obj.HintRadius > 0:
        if not _matches(face, obj):
            face = None
    if face is None and obj.HintRadius > 0:
        for i, f in enumerate(shape.Faces):
            if _matches(f, obj):
                face, obj.FaceName = f, "Face%d" % (i + 1)
                break
    if face is None and not obj.FaceName and obj.Support:
        pf = point_face(obj, shape)                 # appui ponctuel : face trouvée par l'étude du contact
        if pf:
            obj.FaceName = pf[0]
            face = shape.getElement(pf[0])
    if face is None:
        raise NotThreadable("Face « %s » introuvable : choisis à nouveau la face" % obj.FaceName)
    return face


def point_face(obj, shape):
    """Fileter la face existante depuis un appui ponctuel : (nom de la face, point) d'après l'étude de la face
    de contact. None si l'appui n'est pas un point ; NotThreadable si la topographie n'offre rien à fileter."""
    a = creation.resolve(obj.Support, shape, obj.SupportPoint, obj.HintAxis)
    if a.radius is not None or not obj.Support:
        return None
    ct = a.contact
    if ct is None:
        raise NotThreadable(creation.NO_ARC + " : le point ne touche aucune face de la pièce")
    if not ct.thread_face:
        raise NotThreadable("%s (%s)" % (creation.NO_ARC, ct.face_name))
    return ct.thread_face, a.centers[0]


def end_support(base, info, side):
    """Appui d'un trou / extrusion repris d'une face existante : arête circulaire du bout de départ (ou None)."""
    a = info["axis"]
    for e in info["ends"][side]["edges"]:
        if not creation._is_full_circle(e):
            continue
        k = e.Curve
        for i, g in enumerate(base.Shape.Edges):
            if creation._is_full_circle(g) and abs(g.Curve.Radius - k.Radius) < 1e-6 \
                    and (g.Curve.Center - k.Center).Length < 1e-6 and App.Vector(g.Curve.Axis).cross(a).Length < 1e-6:
                return (base, ["Edge%d" % (i + 1)])
    return None


def _matches(f, obj):
    s = f.Surface
    if not isinstance(s, (Part.Cylinder, Part.Cone)):
        return False
    a = App.Vector(obj.HintAxis)
    if a.Length < 1e-9:
        return True
    a.normalize()
    if a.cross(App.Vector(s.Axis)).Length > 1e-4:
        return False
    if isinstance(s, Part.Cylinder):
        return abs(s.Radius - obj.HintRadius) < 1e-3 and radial(App.Vector(s.Center), obj.HintCenter, a).Length < 1e-3
    return True


def _ref_shape(link):
    if not link:
        return None
    o, subs = link
    if subs and subs[0]:
        return o.Shape.getElement(subs[0])
    return o


def _plane_of(link):
    o, subs = link
    sh = o.Shape.getElement(subs[0]) if subs and subs[0] else Part.getShape(o)
    faces = sh.Faces
    if not faces or not isinstance(faces[0].Surface, Part.Plane):
        raise NotThreadable("La référence de hauteur doit être un plan ou une face plane")
    f = faces[0]
    return App.Vector(f.Surface.Axis), App.Vector(f.CenterOfMass if f.Area < 1e12 else f.Surface.Position)


def spec_of(obj):
    if obj.Standard != "custom":
        try:
            spec = thread_spec.from_entry(thread_data.get(obj.Designation),
                                          getattr(obj, "PitchOverride", 0) and obj.PitchOverride.Value)
        except KeyError:
            raise NotThreadable("Désignation inconnue : %s" % obj.Designation)
        spec.left_hand = obj.LeftHanded
        return spec
    return ThreadSpec(d=obj.CustomDiameter.Value, pitch=obj.CustomPitch.Value, starts=max(1, obj.CustomStarts),
                      left_hand=obj.LeftHanded, flank_a=obj.CustomFlankA.Value, flank_b=obj.CustomFlankB.Value,
                      depth=obj.CustomDepth.Value, crest=obj.CustomCrest.Value, taper=obj.CustomTaper)


def head_of(obj, spec, kind, write=True):
    """(tête demandée ou None, message). Hors norme : pas de tête, avec le message d'activation."""
    asked = (getattr(obj, "HoleHead", heads.NONE) if kind == "trou" else getattr(obj, "ScrewHead", heads.NONE))
    if asked == heads.NONE:
        return None, ""
    if spec.is_custom:
        return None, heads.NEED_STANDARD
    h = heads.params(obj, spec.d, kind, write)
    errs = heads.check(h, spec.d, kind)
    if errs:
        raise NotThreadable("Tête : " + " ; ".join(errs))
    return h, ""


def head_frame(plan, info, h):
    """Centre et direction de la tête d'un filetage existant (d'après le plan du filet)."""
    a, c, u = plan.a, plan.c, plan.u
    if plan.kind == "trou":
        return c + a * plan.t_face, a * u
    if h.get("position") == heads.POSITIONS[1]:                # face de début
        return c + a * plan.t_face, a * -u
    far = "high" if plan.side == "low" else "low"
    t = info["ends"][far]["t"] if "ends" in info else (info["t_max"] if far == "high" else info["t_min"])
    return c + a * t, a * u


SUB_TYPE = "PartDesign::FeatureSubtractivePython"
ADD_TYPE = "PartDesign::FeatureAdditivePython"
WARN_SUB = ("Symétrie / répétition : seule la matière enlevée sera reproduite (cette fonction ajoute aussi "
            "de la matière : rebouchage du trou, ajustement du Ø ou tête de vis)")
WARN_ADD = "Symétrie / répétition : seule la matière ajoutée sera reproduite (cette fonction enlève aussi de la matière)"


def wanted_type(obj):
    """Une extrusion filetée ajoute de la matière ; tout le reste en enlève (comme Poche / Perçage)."""
    return ADD_TYPE if getattr(obj, "Operation", "") == creation.OPERATIONS[2] else SUB_TYPE


def set_addsub(obj, base, res, cuts, adds):
    """Outil de la fonction pour la Symétrie et les Répétitions de PartDesign (AddSubShape).

    Ces outils ne savent qu'ajouter OU enlever : un outil unique est donc fourni, avec un avertissement
    si la fonction fait aussi l'opération inverse. Retourne la liste des avertissements."""
    if "AddSubShape" not in obj.PropertiesList:
        return []
    if obj.TypeId == ADD_TYPE:
        try:
            added = res.cut(base)
        except Exception:
            added = Part.Compound([a for a in adds if a is not None])
        obj.AddSubShape = added
        try:
            lost = base.cut(res).Volume
        except Exception:
            lost = 0.0
        return [WARN_ADD] if lost > 1e-3 else []
    obj.AddSubShape = Part.Compound([c for c in cuts if c is not None])
    added = 0.0
    for a in adds:
        try:
            added += a.common(res).Volume - a.common(base).Volume
        except Exception:
            added += a.Volume
    return [WARN_SUB] if added > 1e-3 else []


# propriétés recopiées quand la fonction change de type (additive <-> soustractive)
def _own_props(obj):
    return [p for p in obj.PropertiesList if obj.getGroupOfProperty(p) in
            ("Filetage", "Personnalisé", "Référence", "Tête", "Résultat")]


def ensure_type(obj):
    """Recrée la fonction avec le bon type si besoin (opération changée, ancien document « FeaturePython »).

    Retourne la fonction à utiliser (la même, ou la nouvelle à sa place dans le corps)."""
    want = wanted_type(obj)
    if obj.TypeId == want:
        return obj
    doc = obj.Document
    body = obj.getParentGeoFeatureGroup()
    new = doc.addObject(want, obj.Name)
    ThreadFeature(new)
    body.insertObject(new, obj, True)
    for p in _own_props(obj):
        if p not in new.PropertiesList:
            continue
        try:
            setattr(new, p, getattr(obj, p))
        except Exception:
            pass
    label = obj.Label
    was_tip = body.Tip == obj
    if App.GuiUp:
        ViewProviderThread(new.ViewObject)
    body.removeObject(obj)
    doc.removeObject(obj.Name)
    if was_tip:
        body.Tip = new
    new.Label = label
    return new


def creating(obj):
    return getattr(obj, "Operation", "Existant") in creation.OPERATIONS[1:]


def creation_context(obj, shape, cfg):
    """Appui, filetage et plan (sens, contrôles « dans le vide ») d'un trou taraudé / extrusion filetée."""
    anchor = creation.resolve(obj.Support, shape, obj.SupportPoint, obj.HintAxis)
    obj.HintAxis = anchor.normal
    spec = spec_of(obj)
    r = spec.d / 2 if spec.d > 0 else (anchor.radius or 0.0)
    if spec.d <= 0:
        spec.d = 2 * r
    if obj.Operation == creation.OPERATIONS[1] and r > 0:
        # perçage directement au Ø d'alésage du taraudage : la fonction ne fait qu'enlever de la matière
        r = thread_spec.groove(spec, "trou", r, obj.Clearance.Value)["r_open"]
    plan = creation.plan(anchor, shape, obj.Operation, r, obj.Depth.Value, obj.Reversed)
    return dict(anchor=anchor, spec=spec, plan=plan)


def context(obj, shape, cfg):
    """Analyse + paramètres du builder à partir des propriétés de la fonction."""
    face = find_face(obj, shape, cfg)
    info = detect.analyse(shape, face, _ref_shape(obj.AxisReference), cfg)
    obj.HintCenter, obj.HintAxis, obj.HintRadius = info["center"], info["axis"], info["R"]
    side = obj.Side if obj.Side in SIDE_ENUM else "high"
    ref_t = None
    if obj.HeightReference:
        n, p0 = _plane_of(obj.HeightReference)
        a, c = info["axis"], info["center"]
        if abs(a.dot(n)) < 1e-6:
            raise NotThreadable("Le plan de référence est parallèle à l'axe")
        ref_t = (p0 - c).dot(n) / a.dot(n)
    kind = {"Taraudage": "trou", "Filetage": "arbre"}.get(obj.Mode)
    src = source_feature(obj, info)
    kw = dict(side=side, ref_t=ref_t, depth=obj.Depth.Value, kind=kind, clearance=obj.Clearance.Value,
              max_length=src["length"] if src else None, start_offset=obj.StartOffset.Value)
    return dict(info=info, spec=spec_of(obj), kw=kw, source=src)


# propriété de longueur de chaque type de fonction (comme le Perçage, qui connaît sa profondeur en interne)
_LENGTH_PROPS = {"PartDesign::Pad": "Length", "PartDesign::Pocket": "Length", "PartDesign::Hole": "Depth",
                 "PartDesign::AdditiveCylinder": "Height", "PartDesign::SubtractiveCylinder": "Height"}
_DIM_TYPES = {"Length", "Dimension", "TwoLengths"}


def source_feature(obj, info):
    """Fonction du corps qui a créé la face (Protrusion, Poche, Perçage, cylindre…) et sa longueur.

    Retourne dict(obj, label, prop, length) ou None. La longueur n'est reprise que si la fonction
    est cotée (type « Dimension ») ; sinon seule la géométrie compte."""
    body = obj.getParentGeoFeatureGroup()
    if body is None or not hasattr(body, "Group"):
        return None
    a, c, R = info["axis"], info["center"], info["R"]
    found = None
    for f in body.Group:
        if f is obj:
            break
        prop = _LENGTH_PROPS.get(f.TypeId)
        sub = getattr(f, "AddSubShape", None)
        if not prop or sub is None or sub.isNull():
            continue
        for face in sub.Faces:
            s = face.Surface
            if isinstance(s, Part.Cylinder) and abs(s.Radius - R) < 1e-3 \
                    and App.Vector(s.Axis).cross(a).Length < 1e-4 and radial(App.Vector(s.Center), c, a).Length < 1e-3:
                found = f
                break
    if found is None:
        return None
    prop = _LENGTH_PROPS[found.TypeId]
    typ = getattr(found, "Type", "Length") if found.TypeId in ("PartDesign::Pad", "PartDesign::Pocket") \
        else getattr(found, "DepthType", "Dimension")
    length = getattr(found, prop).Value if str(typ) in _DIM_TYPES else None
    if found.TypeId in ("PartDesign::Pad", "PartDesign::Pocket") and str(typ) == "TwoLengths":
        length = getattr(found, prop).Value + found.Length2.Value
    return dict(obj=found, label=found.Label, prop=prop, length=length)


class ViewProviderThread:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return ICON

    def claimChildren(self):
        o = getattr(self, "Object", None)
        sup = getattr(o, "Support", None) if o else None
        if sup and sup[0].isDerivedFrom("PartDesign::SubShapeBinder"):
            return [sup[0]]                                   # lien vers un point hors du corps
        if sup and creating(o) and sup[0].isDerivedFrom("Sketcher::SketchObject"):
            return [sup[0]]                                   # l'esquisse sous la fonction, comme une Poche
        return []

    def setEdit(self, vobj, mode=0):
        if mode != 0:
            return None
        import FreeCADGui as Gui
        from .task_panel import ThreadTaskPanel
        from . import commands
        commands.LAST_PANEL = ThreadTaskPanel(vobj.Object, new=False)
        Gui.Control.showDialog(commands.LAST_PANEL)
        return True

    def unsetEdit(self, vobj, mode=0):
        import FreeCADGui as Gui
        Gui.Control.closeDialog()
        return True

    def doubleClicked(self, vobj):
        vobj.Document.setEdit(vobj.Object.Name, 0)
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def create(body, name="Thread", operation=None):
    """Nouvelle fonction : soustractive (taraudage, filetage, trou taraudé) ou additive (extrusion filetée)."""
    typ = ADD_TYPE if operation == creation.OPERATIONS[2] else SUB_TYPE
    obj = body.newObject(typ, name)
    ThreadFeature(obj)
    if operation:
        obj.Operation = operation
    if App.GuiUp:
        ViewProviderThread(obj.ViewObject)
    obj.Label = "Filetage"
    return obj
