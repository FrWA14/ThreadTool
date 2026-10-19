"""Axe d'une face de révolution : automatique ou imposé par une référence."""
import math
import FreeCAD as App
import Part


class NotThreadable(Exception):
    pass


def frame(a):
    """Deux vecteurs unitaires perpendiculaires à a (et entre eux)."""
    ref = App.Vector(1, 0, 0) if abs(a.x) < 0.9 else App.Vector(0, 1, 0)
    u = a.cross(ref); u.normalize()
    v = a.cross(u); v.normalize()
    return u, v


def radial(p, c, a):
    d = p - c
    return d - a * d.dot(a)


def positive(a):
    """Oriente l'axe pour que sa plus grande composante soit positive."""
    m = max((abs(a.x), a.x), (abs(a.y), a.y), (abs(a.z), a.z))
    return a if m[1] >= 0 else a * -1


def axis_from_face(face):
    """Retourne (axe, point sur l'axe, demi-angle en degrés ; 0 pour un cylindre)."""
    s = face.Surface
    if isinstance(s, Part.Cylinder):
        return App.Vector(s.Axis), App.Vector(s.Center), 0.0
    if isinstance(s, Part.Cone):
        return App.Vector(s.Axis), App.Vector(s.Apex), math.degrees(s.SemiAngle)
    if isinstance(s, Part.SurfaceOfRevolution):
        return App.Vector(s.Direction), App.Vector(s.Location), None
    if isinstance(s, Part.SurfaceOfExtrusion) and isinstance(s.BasisCurve, Part.Circle):
        return App.Vector(s.Direction), App.Vector(s.BasisCurve.Center), 0.0
    raise NotThreadable("Face non cylindrique (%s)" % type(s).__name__)


def axis_from_reference(sh):
    """Arête droite, arête circulaire, face plane, ou objet axe (App::Line, PartDesign::Line)."""
    if not isinstance(sh, Part.Shape):                     # objet du document (axe d'Origin, datum…)
        sh = Part.getShape(sh)
        if sh.ShapeType == "Compound" and len(sh.Edges) == 1 and not sh.Faces:
            sh = sh.Edges[0]
        elif sh.ShapeType == "Compound" and len(sh.Faces) == 1:
            sh = sh.Faces[0]
    if isinstance(sh, Part.Edge):
        k = sh.Curve
        if isinstance(k, (Part.Line, Part.LineSegment)):
            p0, p1 = sh.valueAt(sh.FirstParameter), sh.valueAt(sh.LastParameter)
            a = p1 - p0; a.normalize()
            return a, App.Vector(p0)
        if isinstance(k, Part.Circle):
            return App.Vector(k.Axis), App.Vector(k.Center)
    if isinstance(sh, Part.Face) and isinstance(sh.Surface, Part.Plane):
        return App.Vector(sh.Surface.Axis), App.Vector(sh.CenterOfMass)
    raise NotThreadable("Référence d'axe non reconnue (arête droite, cercle, face plane ou axe)")


def resolve_axis(face, ref, cfg):
    """Retourne (axe, centre, demi-angle, avertissement|None)."""
    auto = None
    try:
        auto = axis_from_face(face)
    except NotThreadable:
        if ref is None:
            raise
    if ref is None:
        if cfg.axis_mode == "user":
            raise NotThreadable("Mode axe utilisateur : sélectionne un axe de référence")
        return auto[0], auto[1], auto[2], None
    a, c = axis_from_reference(ref)
    warn = None
    if auto is not None:
        ang = math.degrees(a.getAngle(auto[0])); ang = min(ang, 180 - ang)
        if ang > cfg.axis_warn_deg:
            warn = "L'axe fourni diffère de l'axe de la face de %.2f°" % ang
            if cfg.axis_conflict == "error":
                raise NotThreadable(warn)
    return a, c, (auto[2] if auto else None), warn
