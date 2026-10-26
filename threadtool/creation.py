"""Trou taraudé / extrusion filetée à partir d'un appui : esquisse, point, cercle ou face plane (section 13 du cahier).

Toute sélection est ramenée à un « point d'appui » : centres, normale et Ø de départ éventuel.
Le perçage (ou la matière de l'extrusion) et le filet sont faits dans la même fonction."""
import math
import FreeCAD as App
import Part

from .axis import NotThreadable, radial
from . import detect, builder
from .i18n import tr, N_

V = App.Vector
OPERATIONS = [N_("Existant"), N_("Trou taraudé"), N_("Extrusion filetée")]   # valeurs enregistrées (affichées traduites)
VOID_HOLE = tr("Enlèvement de matière dans le vide impossible")
VOID_PAD = tr("Création d'un solide dans le vide impossible")
NO_ARC = tr("La topographie ne présente aucun cercle ou arc pouvant être fileté")


class Anchor:
    """centers : points (repère du corps) ; normal : normale unitaire ; radius : rayon du cercle ou None.

    contact : étude de la face où se trouve un appui ponctuel (Contact), sinon None."""

    def __init__(self, centers, normal, radius=None, desc="", contact=None):
        n = V(normal)
        n.normalize()
        self.centers, self.normal, self.radius, self.desc = [V(c) for c in centers], n, radius, desc
        self.contact = contact


def _is_full_circle(edge):
    c = edge.Curve
    return isinstance(c, Part.Circle) and abs(edge.Length - 2 * math.pi * c.Radius) < 1e-6 * max(1.0, c.Radius)


class Contact:
    """Face de la pièce qui porte un point, et sa topographie.

    face_name, normal (au point) ; thread_face : face cylindrique / conique filetable désignée par la face
    (elle-même, ou celle qui s'appuie sur le cercle / l'arc le plus proche du point), sinon None."""


_SURF = {"Plane": N_("plane"), "Cylinder": N_("cylindrique"), "Cone": N_("conique")}


def _arc_face(base, face, e):
    """Face cylindrique ou conique de base (autre que face) qui s'appuie sur l'arc e, ou None."""
    c = e.Curve
    ax, ctr = V(c.Axis), V(c.Center)
    mid = Part.Vertex(e.valueAt((e.FirstParameter + e.LastParameter) / 2))
    for i, g in enumerate(base.Faces):
        s = g.Surface
        if g.isSame(face) or not isinstance(s, (Part.Cylinder, Part.Cone)) or V(s.Axis).cross(ax).Length > 1e-6:
            continue
        if isinstance(s, Part.Cylinder):
            if abs(s.Radius - c.Radius) > 1e-6 or radial(V(s.Center), ctr, ax).Length > 1e-6:
                continue
        elif radial(V(s.Apex), ctr, ax).Length > 1e-6:
            continue
        if g.distToShape(mid)[0] < 1e-6:
            return "Face%d" % (i + 1)
    return None


def contact(base, p):
    """Étude de la face de base qui porte le point p (une face plane d'abord), ou None hors de la pièce."""
    v = Part.Vertex(p)
    found = [(i, f) for i, f in enumerate(base.Faces) if f.distToShape(v)[0] < 1e-5]
    if not found:
        return None
    found.sort(key=lambda x: not isinstance(x[1].Surface, Part.Plane))
    i, f = found[0]
    ct = Contact()
    ct.face_name, ct.thread_face, ct.arc = "Face%d" % (i + 1), None, None
    ct.normal = f.normalAt(*f.Surface.parameter(p))
    surf = tr(_SURF.get(type(f.Surface).__name__, N_("courbe")))
    if isinstance(f.Surface, (Part.Cylinder, Part.Cone)):
        ct.thread_face = ct.face_name
        ct.desc = tr("sur %s (%s)") % (ct.face_name, surf)
        return ct
    arcs = []
    for e in f.Edges:
        if isinstance(e.Curve, Part.Circle):
            g = _arc_face(base, f, e)
            if g:
                arcs.append(((V(e.Curve.Center) - p).Length, e, g))
    if arcs:                                       # le cercle / l'arc dont le centre est le plus proche du point
        _, ct.arc, ct.thread_face = min(arcs, key=lambda x: x[0])
        ct.desc = tr("sur %s (%s, %s Ø %.3f → %s)") % (ct.face_name, surf, tr("cercle") if _is_full_circle(ct.arc) else tr("arc"),
                                                   2 * ct.arc.Curve.Radius, ct.thread_face)
    else:
        ct.desc = tr("sur %s (%s, aucun cercle ni arc)") % (ct.face_name, surf)
    return ct


def _point_anchor(points, base, normal, desc):
    """Appui ponctuel : étude de la face de contact du premier point ; axe = normal, sinon normale de la face."""
    ct = contact(base, points[0]) if base is not None else None
    where = ct.desc if ct else tr("hors de la pièce")
    if normal is None:
        normal = ct.normal if ct else V(0, 0, 1)
        where += "" if ct else tr(", axe Z")
    return Anchor(points, normal, None, "%s — %s" % (desc, where), contact=ct)


def _sketch(sk, sub, desc, base=None):
    pl = sk.Placement
    n = pl.Rotation.multVec(V(0, 0, 1))
    if sub.startswith("Edge"):
        e = sk.Shape.getElement(sub)
        if not _is_full_circle(e):
            raise NotThreadable(tr("L'arête choisie de l'esquisse n'est pas un cercle"))
        return Anchor([e.Curve.Center], n, e.Curve.Radius, tr("cercle Ø %.3f (%s)") % (2 * e.Curve.Radius, desc))
    if sub.startswith("Vertex"):
        return _point_anchor([sk.Shape.getElement(sub).Point], base, n, tr("point (%s)") % desc)
    circles, points, cpoints = [], [], []
    for i, g in enumerate(sk.Geometry):
        if isinstance(g, Part.Point):
            (cpoints if sk.getConstruction(i) else points).append(pl.multVec(V(g.X, g.Y, g.Z)))
        elif isinstance(g, Part.Circle) and not sk.getConstruction(i):
            circles.append((pl.multVec(g.Center), g.Radius))
    if circles:
        radii = sorted({round(r, 6) for _, r in circles})
        if len(radii) > 1:
            raise NotThreadable(tr("Cercles de Ø différents dans l'esquisse (%s) : un seul Ø par fonction") %
                                ", ".join("%.3f" % (2 * r) for r in radii))
        k = len(circles)
        return Anchor([c for c, _ in circles], n, circles[0][1],
                      (tr("%d cercles Ø %.3f (%s)") if k > 1 else tr("%d cercle Ø %.3f (%s)")) % (k, 2 * circles[0][1], desc))
    if points or cpoints:                          # points de construction : seulement s'il n'y a rien d'autre
        pts = points or cpoints
        k = len(pts)
        if points:
            what = tr("%d points (%s)") if k > 1 else tr("%d point (%s)")
        else:
            what = tr("%d points de construction (%s)") if k > 1 else tr("%d point de construction (%s)")
        return _point_anchor(pts, base, n, what % (k, desc))
    raise NotThreadable(tr("L'esquisse ne contient ni cercle ni point"))


def resolve(link, base, picked=None, hint_axis=None):
    """Appui de la fonction. link = (objet, [sous-élément]) ; base = forme de la fonction précédente."""
    if not link:
        raise NotThreadable(tr("Choisis un appui : esquisse, point, cercle ou face plane"))
    ob, subs = link
    sub = subs[0] if subs else ""
    desc = "%s:%s" % (ob.Label, sub) if sub else ob.Label
    if ob.isDerivedFrom("Sketcher::SketchObject"):
        return _sketch(ob, sub, desc, base)
    try:
        sh = ob.Shape.getElement(sub) if sub else ob.Shape
    except Exception:
        sh = None
    if sh is None or sh.isNull():
        if picked is not None and hint_axis is not None and V(hint_axis).Length > 1e-9:
            return Anchor([picked], hint_axis, None, tr("%s (position mémorisée)") % desc)
        raise NotThreadable(tr("Appui « %s » introuvable : choisis-le à nouveau") % desc)
    if sub.startswith("Face"):
        f = sh.Faces[0]
        if not isinstance(f.Surface, Part.Plane):
            raise NotThreadable(tr("Face non plane : choisis une face plane ou une face cylindrique (filetage existant)"))
        ow = f.OuterWire
        if len(ow.Edges) == 1 and _is_full_circle(ow.Edges[0]):
            c = ow.Edges[0].Curve
            return Anchor([c.Center], f.normalAt(*f.Surface.parameter(c.Center)), c.Radius,
                          tr("centre du cercle Ø %.3f (%s)") % (2 * c.Radius, desc))
        p = f.CenterOfMass
        if picked is not None and f.distToShape(Part.Vertex(picked))[0] < 1e-3:
            p = V(picked)
        return Anchor([p], f.normalAt(*f.Surface.parameter(p)), None, tr("point de la face (%s)") % desc)
    if sub.startswith("Edge"):
        e = sh.Edges[0]
        if not _is_full_circle(e):
            raise NotThreadable(tr("L'arête choisie n'est pas un cercle complet"))
        c = e.Curve
        return Anchor([c.Center], V(c.Axis), c.Radius, tr("cercle Ø %.3f (%s)") % (2 * c.Radius, desc))
    if sh.Vertexes:                                           # sommet, point de référence : face de contact étudiée
        return _point_anchor([sh.Vertexes[0].Point], base, None, tr("point (%s)") % desc)
    raise NotThreadable(tr("Appui non utilisable : %s") % desc)


class CPlan:
    pass


def _cyl(r, L, c, d):
    return Part.makeCylinder(r, L, c, d)


def _run(base, c, d, big):
    """Longueur de matière d'un seul tenant depuis c dans la direction d (0 si c est dans le vide)."""
    seg = Part.LineSegment(c, c + d * big).toShape()
    try:
        com = seg.common(base)
    except Exception:
        return 0.0
    for e in com.Edges:
        if min((v.Point - c).Length for v in e.Vertexes) < 1e-6:
            return e.Length
    return 0.0


def thickness(base, c, d, r=0.0):
    """Épaisseur de matière depuis c dans la direction d.

    Mesurée sur l'axe ; si l'axe est dans le vide (fente, rainure qui traverse l'entrée du trou), sur des
    lignes parallèles réparties sur le Ø r : la plus longue compte."""
    big = base.BoundBox.DiagonalLength * 2 + 10
    t = _run(base, c, d, big)
    if t > 0 or r <= 0:
        return t
    u = d.cross(V(1, 0, 0)) if abs(d.x) < 0.9 else d.cross(V(0, 1, 0))
    u.normalize()
    w = d.cross(u)
    for k in range(12):
        ang = 2 * math.pi * k / 12
        t = max(t, _run(base, c + (u * math.cos(ang) + w * math.sin(ang)) * (0.8 * r), d, big))
    return t


def plan(anchor, base, op, r, L, reverse=False):
    """Sens, contrôles « dans le vide » et outils, sans aucun booléen sur la pièce."""
    if r <= 0:
        raise NotThreadable(tr("Ø nominal nul : choisis une taille"))
    if L <= 0:
        raise NotThreadable(tr("Profondeur nulle"))
    n, c0 = anchor.normal, anchor.centers[0]
    hole = op == OPERATIONS[1]
    vp = base.common(_cyl(r, L, c0, n)).Volume
    vm = base.common(_cyl(r, L, c0, n * -1)).Volume
    if hole:
        s = -1.0 if vm >= vp - 1e-9 else 1.0                  # vers la matière (comme la Poche)
    else:
        s = 1.0 if vp <= vm + 1e-9 else -1.0                  # à l'opposé de la matière (comme la Protrusion)
    if reverse:
        s = -s
    d = n * s
    p = CPlan()
    p.op, p.hole, p.kind = op, hole, "trou" if hole else "arbre"
    p.r, p.L, p.dir, p.centers, p.normal = r, L, d, anchor.centers, n
    p.tools = [_cyl(r, L, c, d) for c in anchor.centers]
    p.messages = []
    many = len(anchor.centers) > 1
    for i, (c, t) in enumerate(zip(p.centers, p.tools)):
        where = " (n° %d)" % (i + 1) if many else ""
        if hole:
            if base.common(t).Volume < 1e-6:
                raise NotThreadable(VOID_HOLE + where)
        else:
            disc = Part.Face(Part.Wire(Part.makeCircle(r, c, d)))
            if base.distToShape(disc)[0] > 1e-6:
                raise NotThreadable(VOID_PAD + where)
    if hole:
        p.thickness = min(thickness(base, c, d, r) for c in p.centers)
        if p.thickness < L - 1e-6:
            p.messages.append(tr("Trou débouchant : %.2f mm de matière pour %.2f mm demandés") % (p.thickness, L))
    else:
        p.thickness = None
    return p


def _bore_face(shape, c, d, r):
    for i, f in enumerate(shape.Faces):
        s = f.Surface
        if isinstance(s, Part.Cylinder) and abs(s.Radius - r) < 1e-6 and V(s.Axis).cross(d).Length < 1e-6 \
                and radial(V(s.Center), c, d).Length < 1e-6:
            return "Face%d" % (i + 1)
    raise NotThreadable(tr("Face du perçage introuvable après l'enlèvement de matière"))


def build(base, p, spec, cfg, clearance, start_offset=0.0, head=None):
    """Perce (ou ajoute l'extrusion) puis filette chaque appui.

    Retourne (forme, messages, outils enlevés, outils ajoutés)."""
    res = base.cut(p.tools) if p.hole else base.fuse(p.tools)
    cuts, adds = (list(p.tools), []) if p.hole else ([], list(p.tools))
    if not res.Solids:
        raise NotThreadable(tr("Échec du calcul booléen du perçage") if p.hole else tr("Échec du calcul booléen de l'extrusion"))
    if len(res.Solids) > 1:
        raise NotThreadable(VOID_PAD if not p.hole else tr("Le perçage coupe la pièce en %d morceaux") % len(res.Solids))
    res = res.Solids[0]
    msgs = list(p.messages)
    for c in p.centers:
        info = detect.analyse(res, _bore_face(res, c, p.dir, p.r), None, cfg)
        entry = c if p.hole else c + p.dir * p.L             # entrée du trou / bout libre de l'extrusion
        t = (entry - info["center"]).dot(info["axis"])
        side = "low" if abs(t - info["t_min"]) < abs(t - info["t_max"]) else "high"
        if start_offset >= p.L - 1e-6:
            raise NotThreadable(tr("Le décalage du début (%.2f mm) dépasse la profondeur (%.2f mm)") % (start_offset, p.L))
        res, bp = builder.build(res, info, spec, cfg, side=side, depth=p.L - start_offset, kind=p.kind,
                                clearance=clearance, max_length=p.L, start_offset=start_offset)
        msgs += [m for m in bp.messages if m not in msgs]
        cuts += bp.cut_tools
        adds += [bp.add_tool] if bp.add_tool is not None else []
        if head:
            from . import heads
            hb, hd = head_frame(p, c, head)
            res, m, tool = heads.apply(res, head, spec.d or 2 * p.r, p.kind, hb, hd)
            (cuts if p.hole else adds).append(tool)
            if m and m not in msgs:
                msgs.append(m)
    return res, msgs, cuts, adds


def head_frame(p, c, head):
    """Centre et direction de la tête d'un trou / extrusion créé sur le centre c."""
    from . import heads
    if p.hole:
        return c, p.dir                                       # lamage / fraisage à l'entrée
    if head.get("position") == heads.POSITIONS[1]:
        return c + p.dir * p.L, p.dir                         # face de début = bout libre de l'extrusion
    return c, p.dir * -1
