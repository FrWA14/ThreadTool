"""Têtes : lamage / fraisage d'un taraudage (comme le Perçage) et tête de vis d'un filetage, avec empreinte.

Les cotes viennent des normes de la vis correspondante, rangées par Ø nominal d (mm). Pour un filetage
d'une autre norme (UNC, BSW, Tr…), les cotes sont prises « en équivalence » : interpolées sur d, ou
proportionnelles à d hors des tables. Un filetage personnalisé (hors norme) n'a pas de tête."""
import math
import FreeCAD as App
import Part

from .i18n import tr, N_, enum_get

V = App.Vector
NONE = N_("Aucune")
NEED_STANDARD = tr("Activez l'option en choisissant une norme de filet")

# ----------------------------------------------------------------------------------- lamages / fraisages
# Données de FreeCAD 1.1.1 (src/Mod/PartDesign/Resources/Hole/*.json), filetages ISO pas gros.
# Lamage : d -> (Ø, profondeur) ; fraisage : d -> Ø (angle donné).
HOLE_CUTS = {
    "ISO 4762": (tr("Lamage — ISO 4762 (CHC)"), "lamage", None, {
        1.6: (3.5, 1.7), 2: (4.3, 2.1), 2.5: (5.0, 3.0), 3: (6.0, 3.4), 3.5: (6.5, 3.9), 4: (8.0, 4.4),
        5: (10.0, 5.4), 6: (11.0, 6.4), 8: (15.0, 8.6), 10: (18.0, 10.6), 12: (20.0, 12.6), 14: (24.0, 14.6),
        16: (26.0, 16.6), 18: (30.0, 18.6), 20: (33.0, 20.6), 22: (36.0, 22.8), 24: (40.0, 24.8), 30: (50.0, 31.0),
        33: (54.0, 34.0), 36: (58.0, 37.0), 42: (69.0, 43.0), 48: (78.0, 49.0), 56: (90.0, 57.0), 64: (103.0, 65.0)}),
    "ISO 4762 + 7089": (tr("Lamage — ISO 4762 + rondelle ISO 7089"), "lamage", None, {
        2: (6.0, 2.4), 2.5: (7.0, 3.5), 3: (9.0, 3.9), 3.5: (9.0, 4.4), 4: (10.0, 5.2), 5: (13.0, 6.4),
        6: (15.0, 8.0), 8: (18.0, 10.2), 10: (24.0, 12.6), 12: (26.0, 15.1), 14: (30.0, 17.1), 16: (33.0, 16.6),
        18: (36.0, 21.6), 20: (40.0, 23.6), 22: (43.0, 25.8), 24: (48.0, 29.8), 27: (54.0, 35.0), 30: (61.0, 38.0),
        33: (63.0, 41.0), 36: (69.0, 42.0)}),
    "DIN 7984": (tr("Lamage — DIN 7984 (CHC tête basse)"), "lamage", None, {
        2: (4.3, 1.6), 2.5: (5.0, 2.0), 3: (6.0, 2.4), 3.5: (6.5, 2.9), 4: (8.0, 3.2), 5: (10.0, 4.0), 6: (11.0, 4.7),
        8: (15.0, 6.0), 10: (18.0, 7.0), 12: (20.0, 8.0), 14: (24.0, 9.0), 16: (26.0, 10.5), 18: (30.0, 11.5),
        20: (33.0, 12.5), 22: (36.0, 13.5), 24: (40.0, 14.5)}),
    "ISO 14583": (tr("Lamage — ISO 14583 (tête cylindrique bombée)"), "lamage", None, {
        2: (4.4, 2.0), 2.5: (5.4, 2.5), 3: (6.0, 2.8), 3.5: (7.6, 3.0), 4: (8.6, 3.5), 5: (10.1, 4.1), 6: (12.6, 5.0),
        8: (16.6, 6.6), 10: (20.8, 8.1)}),
    "ISO 10642": (tr("Fraisage 90° — ISO 10642 (FHC)"), "fraisage", 90.0, {
        2: 4.7, 2.5: 5.9, 3: 6.7, 4: 9.0, 5: 11.2, 6: 13.4, 8: 17.9, 10: 22.4, 12: 26.9, 14: 30.8, 16: 33.6, 20: 40.3}),
    "ISO 2009": (tr("Fraisage 90° — ISO 2009 (fraisée fendue)"), "fraisage", 90.0, {
        2: 4.3, 2.5: 5.3, 3: 6.3, 4: 9.5, 5: 10.5, 6: 12.7, 8: 17.7, 10: 20.2, 12: 24.7}),
    "ISO 7046": (tr("Fraisage 90° — ISO 7046 (fraisée Phillips)"), "fraisage", 90.0, {
        1.6: 3.6, 2: 4.4, 2.5: 5.5, 3: 6.3, 3.5: 8.2, 4: 9.4, 5: 10.4, 6: 12.6, 8: 17.3, 10: 20.0}),
}
HOLE_HEADS = [NONE] + list(HOLE_CUTS)

# ----------------------------------------------------------------------------------- têtes de vis
# d -> cotes. dk : Ø de tête (ou s : sur plats), k : hauteur.
SCREW_HEADS = {
    "ISO 4017": (tr("Hexagonale — ISO 4017"), "hex", NONE, {
        1.6: (3.2, 1.1), 2: (4, 1.4), 2.5: (5, 1.7), 3: (5.5, 2), 4: (7, 2.8), 5: (8, 3.5), 6: (10, 4), 8: (13, 5.3),
        10: (16, 6.4), 12: (18, 7.5), 14: (21, 8.8), 16: (24, 10), 20: (30, 12.5), 24: (36, 15), 30: (46, 18.7),
        36: (55, 22.5)}),
    "ISO 4762": (tr("Cylindrique — ISO 4762 (CHC)"), "cyl", "Six pans creux", {
        1.6: (3.0, 1.6), 2: (3.8, 2), 2.5: (4.5, 2.5), 3: (5.5, 3), 4: (7, 4), 5: (8.5, 5), 6: (10, 6), 8: (13, 8),
        10: (16, 10), 12: (18, 12), 14: (21, 14), 16: (24, 16), 20: (30, 20), 24: (36, 24), 30: (45, 30), 36: (54, 36)}),
    "ISO 1207": (tr("Cylindrique — ISO 1207 (fendue)"), "cyl", "Fente", {
        1.6: (3, 1.1), 2: (3.8, 1.4), 2.5: (4.5, 1.8), 3: (5.5, 2), 4: (7, 2.6), 5: (8.5, 3.3), 6: (10, 3.9),
        8: (13, 5), 10: (16, 6)}),
    "ISO 7380": (tr("Bombée — ISO 7380"), "dome", "Six pans creux", {
        3: (5.7, 1.65), 4: (7.6, 2.2), 5: (9.5, 2.75), 6: (10.5, 3.3), 8: (14, 4.4), 10: (17.5, 5.5), 12: (21, 6.6),
        16: (28, 8.8)}),
    "ISO 7045": (tr("Cylindrique large — ISO 7045 (poêlier)"), "pan", "Phillips", {
        1.6: (3.2, 1.3), 2: (4, 1.6), 2.5: (5, 2.1), 3: (5.6, 2.4), 3.5: (7, 2.6), 4: (8, 3.1), 5: (9.5, 3.7),
        6: (12, 4.6), 8: (16, 6), 10: (20, 7.5)}),
    "ISO 10642": (tr("Fraisée 90° — ISO 10642 (FHC)"), "csk", "Six pans creux", {
        3: (6.72, 1.86), 4: (8.96, 2.48), 5: (11.2, 3.1), 6: (13.44, 3.72), 8: (17.92, 4.96), 10: (22.4, 6.2),
        12: (26.88, 7.44), 16: (33.6, 8.8), 20: (40.32, 10.16)}),
    "DIN 478": (tr("Carrée — DIN 478 (cotes approchées, sans collerette)"), "square", NONE, {
        5: (8, 3.5), 6: (10, 4), 8: (13, 5), 10: (17, 6), 12: (19, 7), 16: (24, 9), 20: (30, 11)}),
}
SCREW_HEAD_NAMES = [NONE] + list(SCREW_HEADS)
POSITIONS = [N_("Face opposée"), N_("Face de début")]

# ----------------------------------------------------------------------------------- empreintes
DRIVES = [NONE, N_("Six pans creux"), N_("Fente"), N_("Phillips"), N_("Carré"), N_("Torx")]
# six pans creux, d -> (s, profondeur) : ISO 4762, ISO 7380, ISO 10642
_HEX_SOCKET = {
    "ISO 4762": {1.6: (1.5, 0.7), 2: (1.5, 1.0), 2.5: (2, 1.1), 3: (2.5, 1.3), 4: (3, 2), 5: (4, 2.5), 6: (5, 3),
                 8: (6, 4), 10: (8, 5), 12: (10, 6), 14: (12, 7), 16: (14, 8), 20: (17, 10), 24: (19, 12),
                 30: (22, 15.5), 36: (27, 19)},
    "ISO 7380": {3: (2, 1.04), 4: (2.5, 1.3), 5: (3, 1.56), 6: (4, 2.08), 8: (5, 2.6), 10: (6, 3.12), 12: (8, 4.16),
                 16: (10, 5.2)},
    "ISO 10642": {3: (2, 1.1), 4: (2.5, 1.5), 5: (3, 1.9), 6: (4, 2.2), 8: (5, 3.0), 10: (6, 3.6), 12: (8, 4.3),
                  16: (10, 4.8), 20: (12, 5.6)},
}
# fente ISO 1207, d -> (largeur n, profondeur t)
_SLOT = {1.6: (0.4, 0.45), 2: (0.5, 0.6), 2.5: (0.6, 0.7), 3: (0.8, 0.85), 4: (1.2, 1.1), 5: (1.2, 1.3),
         6: (1.6, 1.6), 8: (2, 2), 10: (2.5, 2.4)}
# Phillips : taille -> (Ø de l'empreinte m, largeur d'aile b, profondeur t) ; d -> taille (ISO 7045)
_PH = {0: (2.0, 0.5, 1.0), 1: (3.0, 0.7, 1.4), 2: (4.6, 1.0, 2.2), 3: (6.6, 1.5, 3.0), 4: (8.8, 2.0, 4.0)}
_PH_BY_D = [(2.0, 0), (3.0, 1), (5.0, 2), (6.0, 3), (1e9, 4)]
# carré (Robertson) : n° -> côté ; d -> n°
_SQ = {0: 1.8, 1: 2.1, 2: 2.7, 3: 3.5}
_SQ_BY_D = [(2.5, 0), (3.5, 1), (5.0, 2), (1e9, 3)]
# Torx (ISO 10664) : T -> A (pointe à pointe) ; d -> T (ISO 14579)
_TORX = {6: 1.75, 8: 2.4, 10: 2.8, 15: 3.35, 20: 3.95, 25: 4.5, 27: 5.07, 30: 5.6, 40: 6.75, 45: 7.93, 50: 8.95,
         55: 11.35, 60: 13.45, 70: 15.7, 80: 17.75, 90: 20.2}
_TORX_BY_D = [(2.0, 6), (2.5, 8), (3.0, 10), (3.5, 15), (4.0, 20), (5.0, 25), (6.0, 30), (8.0, 45), (10.0, 50),
              (12.0, 55), (14.0, 60), (16.0, 70), (1e9, 90)]


def lookup(table, d):
    """Valeur(s) de la table pour le Ø d : exacte, interpolée entre deux Ø, ou proportionnelle hors table."""
    keys = sorted(table)
    vals = lambda k: table[k] if isinstance(table[k], tuple) else (table[k],)
    out = None
    for k in keys:
        if abs(k - d) < 1e-6:
            out = vals(k)
    if out is None:
        if d < keys[0] or d > keys[-1]:
            k = keys[0] if d < keys[0] else keys[-1]
            out = tuple(v * d / k for v in vals(k))
        else:
            lo = max(k for k in keys if k < d)
            hi = min(k for k in keys if k > d)
            f = (d - lo) / (hi - lo)
            out = tuple(a + (b - a) * f for a, b in zip(vals(lo), vals(hi)))
    return out if isinstance(table[keys[0]], tuple) else out[0]


def _by_d(pairs, d):
    for lim, v in pairs:
        if d <= lim + 1e-6:
            return v
    return pairs[-1][1]


def hole_cut(name, d):
    """dict(type, diameter, depth, angle) d'un lamage / fraisage normalisé pour une vis de Ø d."""
    label, typ, angle, table = HOLE_CUTS[name]
    if typ == "lamage":
        D, depth = lookup(table, d)
        return dict(type=typ, diameter=D, depth=depth, angle=90.0)
    return dict(type=typ, diameter=lookup(table, d), depth=0.0, angle=angle)


def drive_default(drive, head, d, size, height):
    """dict(size, depth, label) d'une empreinte pour une tête (size = Ø ou sur plats de la tête)."""
    if drive == "Six pans creux":
        s, t = lookup(_HEX_SOCKET.get(head, _HEX_SOCKET["ISO 4762"]), d)
        s = min(s, 0.6 * size)
        return dict(size=s, depth=min(t, 0.75 * height), label=tr("six pans %.3g mm") % s)
    if drive == "Fente":
        n, t = lookup(_SLOT, d)
        return dict(size=n, depth=min(t, 0.6 * height), label=tr("fente %.3g mm") % n)
    if drive == "Phillips":
        ph = _by_d(_PH_BY_D, d)
        m, b, t = _PH[ph]
        return dict(size=min(m, 0.8 * size), depth=min(t, 0.8 * height), label="PH%d" % ph)
    if drive == "Carré":
        n = _by_d(_SQ_BY_D, d)
        a = min(_SQ[n], 0.5 * size)
        return dict(size=a, depth=min(1.2 * a, 0.75 * height), label=tr("carré n° %d") % n)
    if drive == "Torx":
        T = _by_d(_TORX_BY_D, d)
        A = min(_TORX[T], 0.6 * size)
        t = lookup(_HEX_SOCKET["ISO 4762"], d)[1]
        return dict(size=A, depth=min(t, 0.75 * height), label="T%d" % T)
    return None


def screw_head(name, d, drive=None):
    """dict(shape, size, height, drive, drive_size, drive_depth, drive_label) d'une tête de vis de Ø d."""
    label, shape, default_drive, table = SCREW_HEADS[name]
    size, height = lookup(table, d)
    drive = default_drive if drive is None else drive
    dd = drive_default(drive, name, d, size, height) if drive != NONE else None
    return dict(shape=shape, size=size, height=height, drive=drive,
                drive_size=dd["size"] if dd else 0.0, drive_depth=dd["depth"] if dd else 0.0,
                drive_label=dd["label"] if dd else "")


def ph_wing(size):
    """Largeur d'aile Phillips pour un Ø d'empreinte."""
    best = min(_PH.values(), key=lambda v: abs(v[0] - size))
    return best[1] * size / best[0]


# ----------------------------------------------------------------------------------- solides
def _local(shape, base, direction):
    """Repère local (z = direction, origine = base) -> repère de la pièce."""
    s = shape.copy()
    s.Placement = App.Placement(V(base), App.Rotation(V(0, 0, 1), V(direction))).multiply(s.Placement)
    return s


CORE_RATIO = 0.6                 # noyau conservé : 0,6 × rayon nominal, toujours sous le Ø de perçage


def hole_solid(h, base, inward, r_hole=0.0):
    """Lamage / fraisage à enlever : base = centre de la face d'entrée, inward = vers la matière.

    C'est un anneau : ce qui se trouve au cœur du trou (plot, broche d'un connecteur) est conservé."""
    if h["type"] == "lamage":
        sol = Part.makeCylinder(h["diameter"] / 2, h["depth"], V(base), V(inward))
        length = h["depth"]
    else:
        R = h["diameter"] / 2
        H = R / math.tan(math.radians(h["angle"]) / 2)
        # le cône s'arrête au rayon du trou (au-delà il est dans le vide du perçage)
        r_end = min(max(r_hole, 0.0), 0.95 * R)
        length = H * (R - r_end) / R
        sol = Part.makeCone(R, r_end, length, V(base), V(inward))
    r_core = CORE_RATIO * r_hole
    if r_core > 1e-3 and length > 1e-6:
        d = V(inward)
        d.normalize()
        sol = sol.cut(Part.makeCylinder(r_core, length + 2.0, V(base) - d * 1.0, d))
    return sol


def _hex_prism(s, h, z0=0.0):
    r = s / math.sqrt(3)
    pts = [V(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i)), z0) for i in range(6)]
    return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, h))


def _top_chamfer(solid, across, k):
    """Chanfrein 30° du sommet d'une tête à pans (hexagonale, carrée)."""
    r_top = across / 2 * 0.95
    r_bot = r_top + k / math.tan(math.radians(30))
    return solid.common(Part.makeCone(r_bot, r_top, k))


def _drive(h, z_top):
    """Empreinte à enlever, centrée sur l'axe, depuis le sommet z_top vers le bas."""
    kind, a, t = h["drive"], h["drive_size"], h["drive_depth"]
    if kind == NONE or a <= 0 or t <= 0:
        return None
    up = 1.0                                                     # dépasse au-dessus de la tête
    z0 = z_top - t
    if kind == "Six pans creux":
        return _hex_prism(a, t + up, z0)
    if kind == "Fente":
        L = 4 * max(h["size"], a)
        return Part.makeBox(L, a, t + up, V(-L / 2, -a / 2, z0))
    if kind == "Carré":
        return Part.makeBox(a, a, t + up, V(-a / 2, -a / 2, z0))
    if kind == "Phillips":
        b = ph_wing(a)
        cross = Part.makeBox(a, b, t + up, V(-a / 2, -b / 2, z0)).fuse(Part.makeBox(b, a, t + up, V(-b / 2, -a / 2, z0)))
        cone = Part.makeCone(0.12 * a, a / 2 + up * a / (2 * t), t + up, V(0, 0, z0))   # ailes en pointe
        return cross.common(cone)
    if kind == "Torx":
        A, B = a, 0.715 * a
        rm, ra = (A + B) / 4, (A - B) / 4
        pts = [V((rm + ra * math.cos(6 * th)) * math.cos(th), (rm + ra * math.cos(6 * th)) * math.sin(th), z0)
               for th in (2 * math.pi * i / 144 for i in range(144))]
        return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, 0, t + up))
    return None


def screw_solid(h, d, base, outward):
    """Tête de vis à ajouter : base = centre de la face d'extrémité de la tige, outward = hors de la tige."""
    shape, a, k = h["shape"], h["size"], h["height"]
    if shape == "hex":
        head = _top_chamfer(_hex_prism(a, k), a, k)
    elif shape == "square":
        head = _top_chamfer(Part.makeBox(a, a, k, V(-a / 2, -a / 2, 0)), a, k)
    elif shape == "dome":
        R = ((a / 2) ** 2 + k ** 2) / (2 * k)
        head = Part.makeSphere(R, V(0, 0, k - R)).common(Part.makeCylinder(a / 2, k))
    elif shape == "pan":
        head = Part.makeCylinder(a / 2, k)
        top = [e for e in head.Edges if isinstance(e.Curve, Part.Circle) and e.Curve.Center.z > k / 2]
        try:
            head = head.makeFillet(min(0.8 * k, 0.2 * a), top)
        except Exception:
            pass
    elif shape == "csk":
        head = Part.makeCone(min(d / 2, a / 2 * 0.9), a / 2, k)
    else:
        head = Part.makeCylinder(a / 2, k)
    dr = _drive(h, k)
    if dr is not None:
        head = head.cut(dr)
    return _local(head, base, outward)


# ----------------------------------------------------------------------------------- propriétés
def params(obj, d, kind, write=True):
    """Tête demandée par la fonction, ou None. Les cotes normalisées sont recopiées dans les propriétés
    (si write) ; avec HeadCustom, les propriétés sont utilisées telles quelles."""
    if kind == "trou":
        name = enum_get(obj, "HoleHead", HOLE_HEADS) if hasattr(obj, "HoleHead") else NONE
        if name not in HOLE_CUTS:
            return None
        h = hole_cut(name, d)
        if obj.HeadCustom:
            h.update(diameter=obj.HeadDiameter.Value, depth=obj.HeadHeight.Value, angle=obj.HeadAngle.Value)
        elif write:
            obj.HeadDiameter, obj.HeadHeight, obj.HeadAngle = h["diameter"], h["depth"], h["angle"]
        h["name"] = name
        return h
    name = enum_get(obj, "ScrewHead", SCREW_HEAD_NAMES) if hasattr(obj, "ScrewHead") else NONE
    if name not in SCREW_HEADS:
        return None
    h = screw_head(name, d, enum_get(obj, "Drive", DRIVES))
    if obj.HeadCustom:
        h.update(size=obj.HeadDiameter.Value, height=obj.HeadHeight.Value,
                 drive_size=obj.DriveSize.Value, drive_depth=obj.DriveDepth.Value)
    elif write:
        obj.HeadDiameter, obj.HeadHeight = h["size"], h["height"]
        obj.DriveSize, obj.DriveDepth = h["drive_size"], h["drive_depth"]
    h["name"] = name
    h["position"] = enum_get(obj, "HeadPosition", POSITIONS) if hasattr(obj, "HeadPosition") else POSITIONS[0]
    return h


def check(h, d, kind):
    """Erreurs de cohérence des cotes (personnalisées)."""
    if h is None:
        return []
    errs = []
    if kind == "trou":
        if h["diameter"] <= d:
            errs.append((tr("Ø du lamage (%.2f) ≤ Ø du taraudage (%.2f)") if h["type"] == "lamage" else
                         tr("Ø du fraisage (%.2f) ≤ Ø du taraudage (%.2f)")) % (h["diameter"], d))
        if h["type"] == "lamage" and h["depth"] <= 0:
            errs.append(tr("Profondeur du lamage nulle"))
        if h["type"] == "fraisage" and not 30 <= h["angle"] <= 150:
            errs.append(tr("Angle de fraisage hors de 30°–150°"))
    else:
        if h["size"] <= d * 0.5 or h["height"] <= 0:
            errs.append(tr("Cotes de tête impossibles"))
        if h["drive"] != NONE and (h["drive_depth"] >= h["height"] or h["drive_size"] >= h["size"]):
            errs.append(tr("L'empreinte est plus grande que la tête"))
    return errs


def solid(h, d, kind, base, direction):
    """Solide de la tête : à enlever (trou, direction = vers la matière) ou à ajouter (arbre, direction = hors de la tige)."""
    if kind == "trou":
        return hole_solid(h, base, direction, d / 2)
    return screw_solid(h, d, base, direction)


def apply(res, h, d, kind, base, direction):
    """Applique la tête à la pièce filetée. Retourne (forme, message éventuel, outil)."""
    tool = solid(h, d, kind, base, direction)
    msg = ""
    if kind == "trou":
        out = res.cut(tool)
    else:
        if res.common(tool).Volume > 1e-3:
            msg = tr("La tête recouvre de la matière existante (extrémité non libre)")
        out = res.fuse(tool)
    if not out.Solids:
        raise ValueError(tr("Échec du calcul de la tête"))
    if len(out.Solids) > 1:
        raise ValueError(tr("La tête sépare la pièce en %d morceaux") % len(out.Solids))
    return out.Solids[0], msg, tool
