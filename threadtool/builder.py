"""Construction du filet : ajustement du Ø puis sillon hélicoïdal (sections 2.7, 2.10, 2.11 du cahier)."""
import math
import FreeCAD as App
import Part

from .axis import NotThreadable, radial
from . import thread_spec
from .detect import radius_at, _interior_point
from .i18n import tr, N_

ENTRY_MSGS = (N_("Entrée de %.2f mm ramenée au Ø %.3f (pied du filet)"),
              N_("Entrée de %.2f mm alésée au Ø %.3f (pied du taraudage)"))


def is_entry_msg(m):
    """Message « entrée ramenée au Ø de pied » (retiré quand un lamage occupe déjà l'entrée)."""
    return any(m.startswith(tr(t).split("%")[0]) for t in ENTRY_MSGS)

V = App.Vector


class Plan:
    """Tout ce qui est calculé avant les booléens (sert aussi à la prévisualisation)."""
    pass


def make_plan(shape, info, spec, cfg, side="high", ref_t=None, depth=None, kind=None, clearance=None,
              max_length=None, start_offset=0.0):
    p = Plan()
    p.kind = kind or info["kind"]
    p.side = side
    p.a, p.c = info["axis"], info["center"]
    p.u = 1.0 if side == "low" else -1.0                     # sens du bout libre vers la matière
    t_end = info["ends"][side]["t"] if "ends" in info else (info["t_min"] if side == "low" else info["t_max"])
    t_far = info["t_max"] if side == "low" else info["t_min"]
    p.t0 = t_end if ref_t is None else ref_t
    if ref_t is not None and (t_far - p.t0) * p.u <= 1e-6:
        # le plan est au-delà de l'extrémité choisie : on part de l'autre extrémité
        side = "low" if side == "high" else "high"
        p.side, p.u = side, -p.u
        t_end, t_far = t_far, t_end
    # Décalage du début du filet vers l'intérieur de la matière (ex. 2 mm après la face, derrière un chanfrein)
    p.offset = max(0.0, start_offset or 0.0)
    p.t0 += p.offset * p.u
    p.t_face = t_end
    zone = (p.t0 - t_end) * p.u
    p.zone = zone if zone > 1e-6 else 0.0                    # entrée entre la face et le début du filet
    # Fin utilisable : le point du bord opposé le PLUS PROCHE (bord oblique, raccord avec le cône de
    # perçage, épaulement de tête de vis…), moins la marge de fin.
    far_side = "high" if side == "low" else "low"
    far_edges = info.get("ends", {}).get(far_side, {}).get("edges", [])
    t_safe = t_far
    for e in far_edges:
        pts = e.discretize(Number=24) if e.Length > 1e-7 else [v.Point for v in e.Vertexes]
        for q in pts:
            tq = (q - p.c).dot(p.a)
            if (tq - p.t0) * p.u < (t_safe - p.t0) * p.u:
                t_safe = tq
    p.available = (t_safe - p.t0) * p.u
    p.length_source = "géométrie"
    if max_length and max_length > 0 and ref_t is None and max_length - p.zone <= p.available + 1e-6:
        p.available = max_length - p.zone                     # longueur reprise de la fonction d'origine
        p.length_source = "fonction"
    p.available -= cfg.end_margin
    if p.available <= 1e-6:
        raise NotThreadable(tr("Le plan de référence est au-delà de la face : aucune longueur à fileter"))
    p.messages = []
    if depth is None or depth <= 0:
        depth = default_depth(p.available, cfg)
    if depth > p.available + 1e-6:
        p.messages.append(tr("Profondeur ramenée à la longueur disponible (%.2f mm)") % p.available)
        depth = p.available
    p.depth = depth
    p.lead = spec.lead
    # Débord du filet hors de la matière : au bout libre, ou dans la zone d'entrée (ramenée au Ø de pied,
    # le sillon n'y enlève rien) pour que le filet soit complet dès son début.
    p.overflow = spec.lead + 0.5 if ((t_end - p.t0) * p.u >= -1e-6 or p.zone) else 0.0
    # Hélice prolongée d'un tour au-delà du plan d'arrêt : sinon le sillon, qui a une largeur, s'arrête
    # avec l'hélice et laisse un anneau de matière sur le dernier tour (l'écrou bloque). Le volume limite
    # coupe ensuite tout au plan d'arrêt : rien ne dépasse.
    p.tail = spec.lead + 0.5
    p.H = p.depth + p.overflow + p.tail
    p.R = radius_at(info, p.t0)                              # rayon actuel de la face au départ
    clr = cfg.clearance if clearance is None else clearance
    p.g = thread_spec.groove(spec, p.kind, p.R, clr)
    errs = thread_spec.check(spec, p.g)
    if errs:
        raise NotThreadable(" ; ".join(errs))
    face_taper = info.get("slope", 0.0)
    if not p.g["resize"] and face_taper:                      # garder une face conique telle quelle
        p.k = abs(face_taper)
    else:
        p.k = p.g["taper"] / 2.0                             # pente radiale (1/32 pour 1:16)
    ext = p.kind == "arbre"
    # repère local : z le long de l'axe, dans le sens où le rayon croît (coniques)
    if ext:
        p.dir = p.u
        p.origin_t = p.t0 - p.overflow * p.u
        p.z_free = p.overflow
    else:
        p.dir = -p.u
        p.origin_t = p.t0 + (p.depth + p.tail) * p.u
        p.z_free = p.depth + p.tail
    a = p.a * p.dir
    p.placement = App.Placement(p.c + p.a * p.origin_t, App.Rotation(V(0, 0, 1), a))
    p.r_open = p.g["r_open"]
    p.r_at = lambda z: p.r_open + p.k * (z - p.z_free)
    # Volume limite : de l'entrée (prolongée hors matière si on part du bout libre) au plan d'arrêt.
    # Les outils (sillons, alésage) sont plus longs que nécessaire puis coupés par ce volume :
    # le filet atteint toujours la face d'entrée et ne dépasse jamais le plan d'arrêt.
    p.t_stop = p.t0 + p.depth * p.u
    if p.zone:
        p.t_entry = p.t_face                                  # jamais au-delà de la face de début
    else:
        p.t_entry = p.t0 - (p.overflow + p.lead + 1.0) * p.u if p.overflow else p.t0
    p.r_root = p.g["r_open"] - p.g["depth"] if ext else p.g["r_open"] + p.g["depth"]
    if abs(p.R - p.r_open) > cfg.max_resize:
        p.messages.append(tr("Ajustement important du Ø : %+.2f mm") % (2 * (p.r_open - p.R)))
    return p


def _core(r, H, base=None, axis=None):
    """Cylindre à NE PAS enlever dans un trou : ce qui est à l'intérieur du perçage (plot, broche d'un
    connecteur…) ne fait pas partie du taraudage. r : un peu moins que le rayon actuel du trou."""
    if r <= 1e-3:
        return None
    if base is None:
        return Part.makeCylinder(r, H)
    return Part.makeCylinder(r, H, base, axis)


CORE_GAP = 0.05                  # retrait du noyau protégé sous la paroi du trou (mm)


def entry_solid(info, p, cfg):
    """Zone entre la face de début et le filet : son Ø doit laisser passer la pièce vissée.

    Arbre : rayon <= rayon de pied du filet, sinon on enlève la matière en trop (tournage).
    Trou : rayon >= rayon de pied du taraudage, sinon on alèse. Retourne le solide à enlever ou None."""
    if not p.zone:
        return None
    cur = [radius_at(info, p.t_face + p.u * p.zone * k / 4.0) for k in range(5)]
    tol = max(cfg.tol(p.R), 1e-3)
    base = p.c + p.a * min(p.t_face, p.t0)
    m = 0.02                     # léger retrait : la surface d'entrée ne coïncide jamais avec le fond du sillon
    if p.kind == "arbre":
        target = p.r_root - m
        if max(cur) <= target + 1e-4:
            return None
        sol = Part.makeCylinder(max(cur) + 1.0, p.zone, base, p.a).cut(Part.makeCylinder(target, p.zone, base, p.a))
        if max(cur) > p.r_root + tol:
            p.messages.append(tr(ENTRY_MSGS[0]) % (p.zone, 2 * target))
    else:
        target = p.r_root + m
        if min(cur) >= target - 1e-4:
            return None
        sol = Part.makeCylinder(target, p.zone, base, p.a)
        core = _core(min(cur) - CORE_GAP, p.zone, base, p.a)      # anneau : l'intérieur du trou est conservé
        if core is not None:
            sol = sol.cut(core)
        if min(cur) < p.r_root - tol:
            p.messages.append(tr(ENTRY_MSGS[1]) % (p.zone, 2 * target))
    return sol


def bore_solid(info):
    """Le perçage existant lui-même (face filetée, d'un bout à l'autre), pour la Symétrie / les Répétitions :
    une copie du taraudage emporte son trou, même si seule la fonction Filetage est répétée.
    Sans effet à l'emplacement d'origine (FreeCAD n'y applique pas l'outil, et c'est déjà du vide)."""
    a, c = info["axis"], info["center"]
    t1, t2 = info["t_min"], info["t_max"]
    if t2 - t1 <= 1e-6:
        return None
    r1, r2 = radius_at(info, t1), radius_at(info, t2)
    base = c + a * t1
    if abs(r1 - r2) < 1e-6:
        return Part.makeCylinder(r1, t2 - t1, base, a)
    return Part.makeCone(r1, r2, t2 - t1, base, a)


def limit_solid(shape, p):
    """Cylindre (très large) entre le plan d'entrée et le plan d'arrêt, perpendiculaires à l'axe."""
    t1, t2 = sorted((p.t_entry, p.t_stop))
    big = shape.BoundBox.DiagonalLength * 2 + p.r_open + 10
    return Part.makeCylinder(big, t2 - t1, p.c + p.a * t1, p.a)


def default_depth(available, cfg):
    if available >= cfg.default_depth:
        return cfg.default_depth
    return cfg.short_ratio * available


def _cone(r0, r1, H):
    if abs(r1 - r0) < 1e-9:
        return Part.makeCylinder(r0, H)
    return Part.makeCone(r0, r1, H)


def _ring_range(p):
    """Intervalle z (repère local) du filet dans la matière, sans débord."""
    if p.kind == "arbre":
        return p.z_free, p.z_free + p.depth
    return p.tail, p.tail + p.depth


def resize_solids(shape, info, p, cfg):
    """Retourne (à_enlever, à_ajouter) dans le repère de la pièce, ou None."""
    if not p.g["resize"]:
        return None, None
    tol = max(cfg.tol(p.R), 1e-3)
    H = p.H
    r0, rH = p.r_at(0.0), p.r_at(H)
    rmin, rmax = min(r0, rH), max(r0, rH)
    # rayon actuel de la face le long de la zone (face cylindrique ou conique)
    za, zb = _ring_range(p)
    cur = [radius_at(info, p.origin_t + p.dir * z) for z in (za, zb)]
    cmin, cmax = min(cur), max(cur)
    cut = add = None
    big = max(cmax, rmax) + p.g["depth"] + cfg.groove_extension + 1.0
    if p.kind == "arbre":
        if rmin < cmax - tol:                               # trop gros : on enlève
            cut = Part.makeCylinder(big, H).cut(_cone(r0, rH, H))
        if rmax > cmin + tol:                               # trop petit : on ajoute
            if not cfg.allow_add_material:
                raise NotThreadable(tr("Le Ø de la face (%.2f) est plus petit que le Ø requis (%.2f) et l'ajout "
                                    "de matière est désactivé (Préférences)") % (2 * cmin, 2 * rmax))
            ri = max(cmin - min(0.3, 0.5 * cmin), 0.01)
            ring = _cone(p.r_at(za), p.r_at(zb), zb - za)
            ring.translate(V(0, 0, za))
            add = ring.cut(Part.makeCylinder(ri, zb - za, V(0, 0, za)))
    else:
        if rmax > cmin + tol:                               # trou trop petit : on alèse (anneau)
            cut = _cone(r0, rH, H)
            core = _core(cmin - CORE_GAP, H)
            if core is not None:
                cut = cut.cut(core)
        if rmin < cmax - tol:                               # trou trop grand : on rebouche
            if not cfg.allow_add_material:
                raise NotThreadable(tr("Le Ø du trou (%.2f) est plus grand que le Ø requis (%.2f) et l'ajout "
                                    "de matière est désactivé (Préférences)") % (2 * cmax, 2 * rmin))
            ro = cmax + 0.3
            sleeve = Part.makeCylinder(ro, zb - za, V(0, 0, za))
            inner = _cone(p.r_at(za), p.r_at(zb), zb - za)
            inner.translate(V(0, 0, za))
            add = sleeve.cut(inner)
    if cut:
        cut.Placement = p.placement.multiply(cut.Placement)
    if add:
        add.Placement = p.placement.multiply(add.Placement)
        add = clip_to_envelope(add, shape, info, p, cfg)
    return cut, add


def clip_to_envelope(solid, shape, info, p, cfg):
    """Découpe la matière ajoutée par les plans des faces d'extrémité côté libre (plan oblique…)."""
    big = shape.BoundBox.DiagonalLength * 4 + 10
    for g in info["ends"][p.side]["neighbors"]:
        if not isinstance(g.Surface, Part.Plane):
            continue
        n = App.Vector(g.Surface.Axis)
        if abs(n.dot(p.a)) < 1e-3:
            continue                                          # plan parallèle à l'axe
        try:
            q = _interior_point(g)
        except NotThreadable:
            continue
        eps = 1e-3
        side = 1.0 if shape.isInside(q + n * eps, cfg.inside_tol, False) else -1.0
        u = n.cross(V(1, 0, 0)) if abs(n.x) < 0.9 else n.cross(V(0, 1, 0))
        u.normalize()
        w = n.cross(u)
        corners = [q + u * big + w * big, q - u * big + w * big, q - u * big - w * big, q + u * big - w * big]
        half = Part.Face(Part.makePolygon(corners + [corners[0]])).extrude(n * (side * big))
        solid = solid.common(half)
    return solid


def groove_cutters(p, cfg):
    """Sillons hélicoïdaux (un par filet) dans le repère de la pièce."""
    g = p.g
    h, w = g["depth"], g["width"]
    ta, tb = math.tan(math.radians(g["flank_a"])), math.tan(math.radians(g["flank_b"]))
    bottom_a = -w / 2 + h * ta
    bottom_b = w / 2 - h * tb
    if bottom_b - bottom_a < 1e-3:                            # fond en pointe : petit méplat
        mid = (bottom_a + bottom_b) / 2
        bottom_a, bottom_b = mid - 5e-4, mid + 5e-4
    ext = cfg.groove_extension
    r = p.r_at(0.0)
    s = -1.0 if p.kind == "arbre" else 1.0                    # sens de creusement (vers l'axe pour un arbre)
    # Aucun sommet exactement sur la surface (r) : les flancs sont prolongés de e1 hors de la matière,
    # sinon des arêtes hélicoïdales coïncident avec le cylindre et le booléen échoue.
    pitch = p.lead / max(1, p.starts)
    if ta + tb > 1e-6:
        e1 = max(min(0.3 * h, (0.97 * pitch - w) / (ta + tb), ext), 1e-3)
    else:
        e1 = min(0.3 * h, ext)
    we = w + e1 * (ta + tb)
    prof = [(r - s * ext, -we / 2), (r - s * e1, -we / 2), (r + s * h, bottom_a),
            (r + s * h, bottom_b), (r - s * e1, we / 2), (r - s * ext, we / 2)]
    if ext <= e1 + 1e-6:
        prof = prof[1:5]
    wire = Part.makePolygon([V(x, 0, z) for x, z in prof] + [V(prof[0][0], 0, prof[0][1])])
    angle = math.degrees(math.atan(p.k)) if p.k else 0.0
    helix = Part.makeLongHelix(p.lead, p.H, r, angle, bool(p.spec_left))
    ps = Part.BRepOffsetAPI.MakePipeShell(Part.Wire(helix))
    ps.setBiNormalMode(V(0, 0, 1))
    ps.add(wire, False, False)
    ps.build()
    ps.makeSolid()
    one = ps.shape()
    if one.Volume < 0:
        one.reverse()
    out = []
    n = max(1, p.starts)
    for i in range(n):
        c = one.copy()
        if i:
            c.rotate(V(0, 0, 0), V(0, 0, 1), 360.0 * i / n)
        c.Placement = p.placement.multiply(c.Placement)
        out.append(c)
    return out


def plan_shapes(shape, info, spec, cfg, **kw):
    """Plan + solides intermédiaires (utilisé par la prévisualisation)."""
    p = make_plan(shape, info, spec, cfg, **kw)
    p.spec_left = spec.left_hand
    p.starts = spec.starts
    cut, add = resize_solids(shape, info, p, cfg)
    lim = limit_solid(shape, p)
    if cut is not None:
        cut = cut.common(lim)
    p.entry = entry_solid(info, p, cfg)
    out = []
    for c in groove_cutters(p, cfg):
        cc = c.common(lim)
        if not cc.Solids or cc.Volume < 1e-9:
            raise NotThreadable(tr("Échec de la découpe du filet au plan d'arrêt (booléen)"))
        out.append(cc)
    return p, cut, add, out


def build(shape, info, spec, cfg, **kw):
    """Retourne (forme filetée, plan).

    Recette du Perçage de FreeCAD : l'outil (ajustement du Ø + sillons) est construit et limité
    à part, puis la pièce n'est coupée qu'UNE fois. L'éventuel ajout de matière est fusionné avant."""
    p, cut, add, cutters = plan_shapes(shape, info, spec, cfg, **kw)
    res = shape
    if add is not None:
        # pas de removeSplitter : il corrompt les solides qui contiennent déjà un filet hélicoïdal
        res = res.fuse(add)
    tools = ([cut] if cut is not None else []) + ([p.entry] if p.entry is not None else []) + cutters
    p.cut_tools, p.add_tool = tools, add                      # outils (Symétrie / Répétition de FreeCAD)
    before = res.Volume
    out = res.cut(tools)                                      # une seule opération, plusieurs outils
    if not out.Solids or before - out.Volume < 1e-6:
        out = res.cut(tools, 1e-5)                            # booléen flou en secours
    res = out
    if not res.Solids:
        raise NotThreadable(tr("Échec du calcul booléen du filet"))
    if len(res.Solids) > 1:
        raise NotThreadable(tr("Le filet coupe la pièce en %d morceaux (paroi trop fine ?)") % len(res.Solids))
    if before - res.Volume < 1e-6:
        raise NotThreadable(tr("Le sillon n'a rien enlevé (échec du booléen ?)"))
    _wall_warning(shape, info, p, cfg)
    return res.Solids[0], p


def _wall_warning(shape, info, p, cfg):
    za, zb = _ring_range(p)
    z = (za + zb) / 2
    t = p.origin_t + p.dir * z
    rr = p.r_at(z) + (-1 if p.kind == "arbre" else 1) * (p.g["depth"] + 0.05)
    if rr <= 0:
        return
    u = radial(info["face"].Vertexes[0].Point if info["face"].Vertexes else p.c + V(1, 0, 0), p.c, p.a)
    if u.Length < 1e-9:
        return
    u.normalize()
    q = p.c + p.a * t + u * rr
    if not shape.isInside(q, cfg.inside_tol, True):
        p.messages.append(tr("Attention : paroi peut-être trop fine derrière le filet"))
