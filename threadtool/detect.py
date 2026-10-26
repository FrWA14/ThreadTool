"""Analyse d'une face : axe, Ø, cylindre / cône 1:16, trou / arbre, extrémités libres."""
import math
import FreeCAD as App
import Part

from .axis import NotThreadable, frame, radial, positive, resolve_axis
from .i18n import tr

TAPER_HALF_ANGLE = math.degrees(math.atan(1.0 / 32.0))     # 1,7899° (conicité 1:16)


def face_name(shape, face):
    for i, f in enumerate(shape.Faces):
        if f.isSame(face):
            return "Face%d" % (i + 1)
    raise NotThreadable(tr("Face introuvable dans la forme"))


def _tess_points(face, cfg):
    try:
        pts, _ = face.tessellate(cfg.tessellation_deflection)
    except Exception:
        pts = []
    return pts or [v.Point for v in face.Vertexes]


def wire_points(w, n):
    """Points d'un wire, arête par arête (Wire.discretize plante sur certaines arêtes dégénérées)."""
    pts = []
    edges = [e for e in w.Edges if e.Length > 1e-7]
    total = sum(e.Length for e in edges) or 1.0
    for e in edges:
        try:
            pts += e.discretize(Number=max(2, int(n * e.Length / total) + 1))
        except Exception:
            pts += [v.Point for v in e.Vertexes]
    return pts


def _coaxial(a1, c1, a2, c2, tol):
    if a1.cross(a2).Length > 1e-6:
        return False
    return radial(c2, c1, a1).Length <= tol


def collect_group(shape, face, a, c, R, half_angle, cfg):
    """Faces coaxiales de même rayon (faces scindées, facettes de polygone)."""
    tol = cfg.tol(R)
    group = []
    for f in shape.Faces:
        if f.isSame(face):
            group.append(f)
            continue
        s = f.Surface
        if isinstance(s, Part.Cylinder):
            if half_angle == 0 and abs(s.Radius - R) <= tol and _coaxial(a, c, App.Vector(s.Axis), App.Vector(s.Center), tol):
                group.append(f)
            continue
        if isinstance(s, Part.Cone):
            if half_angle and abs(abs(math.degrees(s.SemiAngle)) - abs(half_angle)) < 1e-3 \
                    and _coaxial(a, c, App.Vector(s.Axis), App.Vector(s.Apex), tol):
                group.append(f)
            continue
        if isinstance(s, Part.Plane):
            if cfg.polygon_sides < 3 or abs(App.Vector(s.Axis).dot(a)) > 1e-3:
                continue                       # facette de polygone uniquement
        elif isinstance(s, (Part.Sphere, Part.Toroid)):
            continue
        if half_angle:
            continue
        pts = _tess_points(f, cfg)
        if pts and all(abs(radial(p, c, a).Length - R) <= tol for p in pts):
            group.append(f)
    return _connected(face, group)


def _connected(face, group):
    """Faces du groupe reliées à la face choisie par des arêtes communes (moitiés d'un cylindre, facettes).

    Deux portées de même Ø séparées par un collet (pièce de révolution) restent deux faces distinctes."""
    keep, todo = [face], [f for f in group if not f.isSame(face)]
    grown = True
    while grown and todo:
        grown = False
        for f in list(todo):
            if any(e.isSame(g) for e in f.Edges for k in keep for g in k.Edges):
                keep.append(f)
                todo.remove(f)
                grown = True
    return keep


def axial_range(faces, a, c, cfg):
    ts = []
    for f in faces:
        for e in f.Edges:
            if e.Length > 1e-7:
                ts += [(q - c).dot(a) for q in e.discretize(Number=max(8, cfg.n_samples // 4))]
    if not ts:
        raise NotThreadable(tr("Aucune arête de bord exploitable"))
    return min(ts), max(ts)


def measure(group, a, c, cfg):
    """Coupes perpendiculaires : rayon (ou loi r(t) pour un cône). Retourne (r0, pente dr/dt, tmin, tmax)."""
    tmin, tmax = axial_range(group, a, c, cfg)
    span, m = tmax - tmin, cfg.slice_margin
    if span <= 1e-6:
        raise NotThreadable(tr("Face de longueur nulle"))
    samples = []
    for i in range(cfg.n_slices):
        t = tmin + span * (m + (1 - 2 * m) * (i + 0.5) / cfg.n_slices)
        d = []
        for f in group:
            try:
                wires = f.slice(a, a.dot(c) + t)
            except Exception:
                wires = []
            for w in wires:
                d += [radial(q, c, a).Length for q in wire_points(w, cfg.n_samples)]
        if not d:
            continue
        r = max(d) if cfg.polygon_sides >= 3 else sum(d) / len(d)
        if max(abs(x - r) for x in d) > cfg.tol(r):
            raise NotThreadable(tr("Section non circulaire (axe incorrect ? choisis un axe de référence)"))
        samples.append((t, r))
    if len(samples) < 2:
        raise NotThreadable(tr("Pas assez de coupes valides"))
    n = len(samples)
    mt = sum(t for t, _ in samples) / n
    mr = sum(r for _, r in samples) / n
    den = sum((t - mt) ** 2 for t, _ in samples)
    slope = sum((t - mt) * (r - mr) for t, r in samples) / den if den > 0 else 0.0
    r0 = mr - slope * mt
    if max(abs(r0 + slope * t - r) for t, r in samples) > cfg.tol(mr):
        raise NotThreadable(tr("Surface ni cylindrique ni conique"))
    if abs(slope * span) <= cfg.tol(mr):
        slope = 0.0
        r0 = mr
    return r0, slope, tmin, tmax


def _interior_point(face):
    u0, u1, v0, v1 = face.ParameterRange
    best = None
    for fu in (0.5, 0.37, 0.63, 0.25, 0.75):
        for fv in (0.5, 0.37, 0.63, 0.25, 0.75):
            u, v = u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv
            if face.isPartOfDomain(u, v):
                p = face.valueAt(u, v)
                dist = Part.Vertex(p).distToShape(Part.Compound(face.Edges))[0]
                if best is None or dist > best[0]:
                    best = (dist, p)
        if best and best[0] > 0:
            break
    if best is None:
        raise NotThreadable(tr("Impossible de trouver un point sur la face"))
    return best[1]


def classify(shape, p, a, c, R, cfg):
    rad = radial(p, c, a)
    rad.normalize()
    eps = max(R * cfg.eps_ratio, cfg.eps_min)
    in_axis = shape.isInside(p - rad * eps, cfg.inside_tol, True)
    in_out = shape.isInside(p + rad * eps, cfg.inside_tol, True)
    if in_out and not in_axis:
        return "trou"
    if in_axis and not in_out:
        return "arbre"
    raise NotThreadable(tr("Trou ou arbre indéterminé (paroi plus fine que ε ?)"))


def analyse(shape, face, ref=None, cfg=None):
    """face : objet Part.Face de shape, ou nom 'FaceN'."""
    from .config import ThreadConfig
    cfg = cfg or ThreadConfig.load()
    if not shape.Solids:
        raise NotThreadable(tr("La pièce n'est pas un solide"))
    if isinstance(face, str):
        face = shape.getElement(face)
    a, c, half, warn = resolve_axis(face, ref, cfg)
    a = positive(App.Vector(a))
    a.normalize()
    if half and not cfg.allow_taper:
        raise NotThreadable(tr("Surface conique (demi-angle %.2f°)") % half)
    pts = _tess_points(face, cfg)
    R0 = sum(radial(p, c, a).Length for p in pts) / len(pts)
    if half:
        group = collect_group(shape, face, a, c, R0, half, cfg)
    else:
        group = collect_group(shape, face, a, c, max(radial(p, c, a).Length for p in pts), 0, cfg)
    r0, slope, tmin, tmax = measure(group, a, c, cfg)
    half_angle = math.degrees(math.atan(slope)) if slope else 0.0
    if half_angle:
        if abs(abs(half_angle) - TAPER_HALF_ANGLE) > cfg.taper_tol_deg or not cfg.allow_taper:
            raise NotThreadable(tr("Cône détecté (demi-angle ≈ %.2f°) : seule la conicité 1:16 (%.2f°) "
                                "des filetages NPT / BSPT est acceptée") % (abs(half_angle), TAPER_HALF_ANGLE))
    tmid = (tmin + tmax) / 2
    R = r0 + slope * tmid
    p = _interior_point(face)
    Rp = r0 + slope * (p - c).dot(a)
    kind = classify(shape, p, a, c, Rp, cfg)
    info = dict(kind=kind, R=R, diameter=2 * R, r0=r0, slope=slope, half_angle=half_angle,
                axis=a, center=c, group=group, t_min=tmin, t_max=tmax, warning=warn,
                face=face, face_name=face_name(shape, face))
    info["ends"] = ends(shape, info, cfg)
    return info


def radius_at(info, t):
    return info["r0"] + info["slope"] * t


def end_edges(shape, info, cfg):
    """Bords d'extrémité du groupe : [(arête, faces voisines hors groupe, t moyen)].

    Une fente, un méplat ou un perçage transversal découpent aussi la face, mais ne la terminent pas : le
    filet continue de part et d'autre. Sont donc écartés les bords droits parallèles à l'axe (flancs d'une
    fente) et les chaînes de bords qui ne touchent ni t_min ni t_max (fond d'une fente, perçage transversal)."""
    a, c, group = info["axis"], info["center"], info["group"]
    tol = max(cfg.tol(info["R"]), 1e-4)
    cand = []
    for f in group:
        for e in f.Edges:
            nb = [g for g in shape.ancestorsOfType(e, Part.Face)
                  if not any(g.isSame(h) for h in group)]
            if not nb:
                continue                                   # couture ou arête interne au groupe
            if isinstance(e.Curve, Part.Line) and App.Vector(e.Curve.Direction).cross(a).Length < 1e-6:
                continue                                   # flanc d'une fente / d'un méplat
            pts = e.discretize(Number=16) if e.Length > 1e-7 else [v.Point for v in e.Vertexes]
            ts = [(q - c).dot(a) for q in pts]
            cand.append([e, nb, sum(ts) / len(ts), min(ts), max(ts), None])
    # chaînes de bords reliés par leurs sommets
    for i, x in enumerate(cand):
        if x[5] is None:
            x[5], todo = i, [x]
            while todo:
                y = todo.pop()
                for z in cand:
                    if z[5] is None and any((v.Point - w.Point).Length < 1e-6
                                            for v in y[0].Vertexes for w in z[0].Vertexes):
                        z[5] = i
                        todo.append(z)
    out = []
    for i in {x[5] for x in cand}:
        chain = [x for x in cand if x[5] == i]
        if min(x[3] for x in chain) <= info["t_min"] + tol or max(x[4] for x in chain) >= info["t_max"] - tol:
            out += [(x[0], x[1], x[2]) for x in chain]
    return out


def ends(shape, info, cfg, others=()):
    """Pour chaque extrémité ('low' = t_min, 'high' = t_max) : libre ou non.

    Libre = les faces voisines du bord sont côté vide (bout d'arbre / entrée de trou)
    et le bord ne touche aucun autre corps (others : formes dans le même repère)."""
    a, c, kind = info["axis"], info["center"], info["kind"]
    tmid = (info["t_min"] + info["t_max"]) / 2
    res = {"low": dict(t=info["t_min"], free=True, edges=[], neighbors=[]),
           "high": dict(t=info["t_max"], free=True, edges=[], neighbors=[])}
    for e, nb, tm in end_edges(shape, info, cfg):
        side = res["high" if tm > tmid else "low"]
        side["edges"].append(e)
        for g in nb:
            side["neighbors"].append(g)
            Rg = radius_at(info, tm)
            try:
                q = _interior_point(g)            # point bien à l'intérieur de la face voisine
            except NotThreadable:
                continue
            rq = radial(q, c, a).Length
            void_side = rq < Rg - 1e-6 if kind == "arbre" else rq > Rg + 1e-6
            if not void_side:
                side["free"] = False
    for side in res.values():
        if not side["edges"]:
            side["free"] = False
        elif side["free"] and others:
            comp = Part.Compound(side["edges"])
            tol = max(cfg.tol(info["R"]), 1e-3)
            for o in others:
                try:
                    if comp.distToShape(o)[0] <= tol:
                        side["free"] = False
                        break
                except Exception:
                    pass
    return res


def find_default(shape, cfg, others=(), max_groups=40):
    """Face et extrémité par défaut (section 9.4).

    Retourne (info, end) avec end = 'low' ou 'high', ou (None, None) si aucune face filetable."""
    seen = []
    options = []
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, (Part.Cylinder, Part.Cone)):
            continue
        if any(f.isSame(g) for g in seen):
            continue
        if len(options) >= max_groups:
            break
        try:
            info = analyse(shape, f, None, cfg)
        except NotThreadable:
            seen.append(f)
            continue
        except Exception:
            seen.append(f)
            continue
        seen += info["group"]
        if others:
            info["ends"] = ends(shape, info, cfg, others)
        options.append(info)
    if not options:
        return None, None
    free = [(info, side) for info in options for side in ("low", "high") if info["ends"][side]["free"]]

    def score(item):
        info, side = item
        a, c = info["axis"], info["center"]
        p = c + a * info["ends"][side]["t"]
        return (p.dot(positive(a)), info["R"])

    if len(free) == 1:
        return free[0]
    if free:
        return max(free, key=score)
    info = max(options, key=lambda i: i["R"])
    return info, "high"
