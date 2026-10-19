"""Tables normalisées. On ne stocke que d et P ; toutes les cotes sont calculées (section 7 du cahier)."""
import math
from collections import namedtuple

from .i18n import tr

IN = 25.4
TAPER_1_16 = 1.0 / 16.0            # conicité sur le diamètre

Entry = namedtuple("Entry", "standard name d P series profile taper extra")
# standard : "ISO", "UNC", "UNF", "UNEF", "G", "BSW", "BSF", "NPT", "BSPT", "Tr"
# series   : "coarse" | "fine" | "extra-fine"
# profile  : "ISO" | "UN" | "W55" | "NPT" | "TR"

STANDARDS = ["ISO", "UNC", "UNF", "UNEF", "G", "BSW", "BSF", "NPT", "BSPT", "Tr"]
STANDARD_LABELS = {
    "ISO": tr("ISO métrique (M)"),
    "UNC": tr("UNC – unifié gros (impérial)"),
    "UNF": tr("UNF – unifié fin (impérial)"),
    "UNEF": tr("UNEF – unifié extra-fin (impérial)"),
    "G": tr("BSP G – gaz cylindrique (55°)"),
    "BSW": tr("BSW – Whitworth gros (55°)"),
    "BSF": tr("BSF – Whitworth fin (55°)"),
    "NPT": tr("NPT – conique américain 1:16"),
    "BSPT": tr("BSPT R/Rc – conique 1:16 (55°)"),
    "Tr": tr("Tr – trapézoïdal 30°"),
}
# choix proposés dans « Norme / format » : (clé, libellé, norme, série ou None)
CHOICES = [
    ("ISO|coarse", tr("ISO métrique – pas gros (normal)"), "ISO", "coarse"),
    ("ISO|fine", tr("ISO métrique – pas fin"), "ISO", "fine"),
    ("ISO|extra-fine", tr("ISO métrique – pas extra-fin"), "ISO", "extra-fine"),
    ("UNC", tr("UNC – unifié gros (impérial)"), "UNC", None),
    ("UNF", tr("UNF – unifié fin (impérial)"), "UNF", None),
    ("UNEF", tr("UNEF – unifié extra-fin (impérial)"), "UNEF", None),
    ("G", tr("BSP G – gaz cylindrique (55°)"), "G", None),
    ("BSW", tr("BSW – Whitworth gros (55°)"), "BSW", None),
    ("BSF", tr("BSF – Whitworth fin (55°)"), "BSF", None),
    ("NPT", tr("NPT – conique américain 1:16"), "NPT", None),
    ("BSPT", tr("BSPT R/Rc – conique 1:16 (55°)"), "BSPT", None),
    ("Tr", tr("Tr – trapézoïdal 30°"), "Tr", None),
]


def choice_key(e):
    return "ISO|" + e.series if e.standard == "ISO" else e.standard


IMPERIAL = {"UNC", "UNF", "UNEF", "G", "BSW", "BSF", "NPT", "BSPT"}


def _g(x):
    return ("%.3f" % x).rstrip("0").rstrip(".")


def _frac(s):
    """'1-1/4' -> 1.25 ; '3/8' -> 0.375 ; '2' -> 2.0"""
    whole, frac = 0.0, s
    if "-" in s:
        w, frac = s.split("-")
        whole = float(w)
    if "/" in frac:
        a, b = frac.split("/")
        return whole + float(a) / float(b)
    return whole + float(frac)


_ISO = [  # d, pas gros, pas fins (du plus gros au plus fin)
    (1, 0.25, [0.2]), (1.2, 0.25, [0.2]), (1.4, 0.3, [0.2]), (1.6, 0.35, [0.2]), (1.8, 0.35, [0.2]),
    (2, 0.4, [0.25]), (2.2, 0.45, [0.25]), (2.5, 0.45, [0.35]), (3, 0.5, [0.35]), (3.5, 0.6, [0.35]),
    (4, 0.7, [0.5]), (4.5, 0.75, [0.5]), (5, 0.8, [0.5]), (6, 1, [0.75]), (7, 1, [0.75]),
    (8, 1.25, [1, 0.75]), (10, 1.5, [1.25, 1, 0.75]), (12, 1.75, [1.5, 1.25, 1]), (14, 2, [1.5, 1.25, 1]),
    (16, 2, [1.5, 1]), (18, 2.5, [2, 1.5, 1]), (20, 2.5, [2, 1.5, 1]), (22, 2.5, [2, 1.5, 1]),
    (24, 3, [2, 1.5, 1]), (27, 3, [2, 1.5, 1]), (30, 3.5, [3, 2, 1.5, 1]), (33, 3.5, [3, 2, 1.5]),
    (36, 4, [3, 2, 1.5]), (39, 4, [3, 2, 1.5]), (42, 4.5, [4, 3, 2, 1.5]), (45, 4.5, [4, 3, 2, 1.5]),
    (48, 5, [4, 3, 2, 1.5]), (52, 5, [4, 3, 2, 1.5]), (56, 5.5, [4, 3, 2, 1.5]), (60, 5.5, [4, 3, 2, 1.5]),
    (64, 6, [4, 3, 2, 1.5]),
]

_UN = [  # nom, d (pouces), UNC, UNF, UNEF (TPI)
    ("#0", 0.060, None, 80, None), ("#1", 0.073, 64, 72, None), ("#2", 0.086, 56, 64, None),
    ("#3", 0.099, 48, 56, None), ("#4", 0.112, 40, 48, None), ("#5", 0.125, 40, 44, None),
    ("#6", 0.138, 32, 40, None), ("#8", 0.164, 32, 36, None), ("#10", 0.190, 24, 32, None),
    ("#12", 0.216, 24, 28, 32), ("1/4", 0.25, 20, 28, 32), ("5/16", 0.3125, 18, 24, 32),
    ("3/8", 0.375, 16, 24, 32), ("7/16", 0.4375, 14, 20, 28), ("1/2", 0.5, 13, 20, 28),
    ("9/16", 0.5625, 12, 18, 24), ("5/8", 0.625, 11, 18, 24), ("11/16", 0.6875, None, None, 24),
    ("3/4", 0.75, 10, 16, 20), ("13/16", 0.8125, None, None, 20), ("7/8", 0.875, 9, 14, 20),
    ("15/16", 0.9375, None, None, 20), ("1", 1.0, 8, 12, 20), ("1-1/8", 1.125, 7, 12, 18),
    ("1-1/4", 1.25, 7, 12, 18), ("1-3/8", 1.375, 6, 12, 18), ("1-1/2", 1.5, 6, 12, 18),
    ("1-3/4", 1.75, 5, None, None), ("2", 2.0, 4.5, None, None),
]

_G = [  # nom, d (mm), TPI, longueur de jauge ISO 7-1 (mm, pour BSPT)
    ("1/16", 7.723, 28, 4.0), ("1/8", 9.728, 28, 4.0), ("1/4", 13.157, 19, 6.0), ("3/8", 16.662, 19, 6.4),
    ("1/2", 20.955, 14, 8.2), ("5/8", 22.911, 14, None), ("3/4", 26.441, 14, 9.5), ("7/8", 30.201, 14, None),
    ("1", 33.249, 11, 10.4), ("1-1/8", 37.897, 11, None), ("1-1/4", 41.910, 11, 12.7),
    ("1-1/2", 47.803, 11, 12.7), ("1-3/4", 53.746, 11, None), ("2", 59.614, 11, 15.9),
    ("2-1/2", 75.184, 11, 17.5), ("3", 87.884, 11, 20.6), ("4", 113.030, 11, 25.4),
]

_BSW = [("1/16", 60), ("3/32", 48), ("1/8", 40), ("5/32", 32), ("3/16", 24), ("7/32", 24), ("1/4", 20),
        ("5/16", 18), ("3/8", 16), ("7/16", 14), ("1/2", 12), ("9/16", 12), ("5/8", 11), ("11/16", 11),
        ("3/4", 10), ("7/8", 9), ("1", 8), ("1-1/8", 7), ("1-1/4", 7), ("1-1/2", 6), ("1-3/4", 5), ("2", 4.5)]
_BSF = [("3/16", 32), ("7/32", 28), ("1/4", 26), ("9/32", 26), ("5/16", 22), ("3/8", 20), ("7/16", 18),
        ("1/2", 16), ("9/16", 16), ("5/8", 14), ("11/16", 14), ("3/4", 12), ("7/8", 11), ("1", 10),
        ("1-1/8", 9), ("1-1/4", 9), ("1-1/2", 8), ("1-3/4", 7), ("2", 7)]

_NPT = [("1/16", 0.3125, 27), ("1/8", 0.405, 27), ("1/4", 0.540, 18), ("3/8", 0.675, 18), ("1/2", 0.840, 14),
        ("3/4", 1.050, 14), ("1", 1.315, 11.5), ("1-1/4", 1.660, 11.5), ("1-1/2", 1.900, 11.5),
        ("2", 2.375, 11.5), ("2-1/2", 2.875, 8), ("3", 3.500, 8), ("4", 4.500, 8)]

_TR = [(8, 1.5), (10, 2), (12, 3), (14, 3), (16, 4), (18, 4), (20, 4), (22, 5), (24, 5), (26, 5), (28, 5),
       (30, 6), (32, 6), (36, 6), (40, 7), (44, 7), (48, 8), (50, 8), (52, 8), (60, 9), (70, 10), (80, 10),
       (90, 12), (100, 12)]


def tr_ac(P):
    """Jeu au sommet du trapézoïdal ISO 2904."""
    return 0.15 if P <= 1.5 else 0.25 if P <= 5 else 0.5 if P <= 12 else 1.0


def _build():
    out = []
    for d, pc, fins in _ISO:
        out.append(Entry("ISO", "M%s" % _g(d), d, pc, "coarse", "ISO", 0.0, {}))
        for i, p in enumerate(fins):
            out.append(Entry("ISO", "M%s×%s" % (_g(d), _g(p)), d, p, "fine" if i == 0 else "extra-fine",
                             "ISO", 0.0, {}))
    for n, din, c, f, ef in _UN:
        for tpi, std, ser in ((c, "UNC", "coarse"), (f, "UNF", "fine"), (ef, "UNEF", "extra-fine")):
            if tpi:
                out.append(Entry(std, '%s"-%s %s' % (n, _g(tpi), std) if not n.startswith("#")
                                 else "%s-%s %s" % (n, _g(tpi), std),
                                 din * IN, IN / tpi, ser, "UN", 0.0, {"tpi": tpi}))
    for n, d, tpi, _lj in _G:
        out.append(Entry("G", "G %s" % n, d, IN / tpi, "coarse", "W55", 0.0, {"tpi": tpi}))
    for rows, std, ser in ((_BSW, "BSW", "coarse"), (_BSF, "BSF", "fine")):
        for n, tpi in rows:
            out.append(Entry(std, '%s" %s' % (n, std), _frac(n) * IN, IN / tpi, ser, "W55", 0.0, {"tpi": tpi}))
    for n, D, tpi in _NPT:
        p = 1.0 / tpi
        E0 = D - (0.05 * D + 1.1) * p           # pouces
        L2 = (0.8 * D + 6.8) * p
        out.append(Entry("NPT", '%s" NPT' % n, D * IN, IN / tpi, "coarse", "NPT", TAPER_1_16,
                         {"tpi": tpi, "E0": E0 * IN, "L2": L2 * IN}))
    for n, d, tpi, lj in _G:
        if lj:
            out.append(Entry("BSPT", "R %s / Rc %s" % (n, n), d, IN / tpi, "coarse", "W55", TAPER_1_16,
                             {"tpi": tpi, "gauge_length": lj}))
    for d, p in _TR:
        out.append(Entry("Tr", "Tr%s×%s" % (_g(d), _g(p)), d, p, "coarse", "TR", 0.0, {}))
    return out


ALL = _build()
_BY_NAME = {e.name: e for e in ALL}


def get(name):
    return _BY_NAME[name]


def by_standard(std):
    return [e for e in ALL if e.standard == std]


def dims(e):
    """Cotes de base (mm) : d, P, d2, minor_ext, minor_int (D1), drill, + géométrie du sillon.

    Pour les coniques, les diamètres sont ceux du bout libre :
      mâle  : Ø de sommet au petit bout ; femelle : Ø intérieur à l'entrée (grand bout).
    """
    d, P = e.d, e.P
    r = dict(d=d, P=P)
    if e.profile in ("ISO", "UN"):
        r.update(d2=d - 0.649519 * P,
                 minor_ext=d - (1.226869 if e.profile == "ISO" else 1.190784) * P,
                 minor_int=d - 1.082532 * P, drill=d - P,
                 flank=30.0, crest_ext=P / 8, crest_int=P / 4,
                 h_ext=(0.613343 if e.profile == "ISO" else 0.595392) * P, h_int=0.541266 * P)
    elif e.profile == "W55":
        r.update(d2=d - 0.640327 * P, minor_ext=d - 1.280654 * P, minor_int=d - 1.280654 * P,
                 drill=d - P, flank=27.5, crest_ext=0.1667 * P, crest_int=0.1667 * P,
                 h_ext=0.640327 * P, h_int=0.640327 * P)
    elif e.profile == "NPT":
        r.update(d2=e.extra["E0"], minor_ext=e.extra["E0"] - 0.8 * P, minor_int=e.extra["E0"] - 0.8 * P,
                 drill=e.extra["E0"] + e.extra["L2"] / 16 - 0.8 * P, flank=30.0,
                 crest_ext=0.038 * P, crest_int=0.038 * P, h_ext=0.8 * P, h_int=0.8 * P)
    elif e.profile == "TR":
        ac = tr_ac(P)
        r.update(d2=d - 0.5 * P, minor_ext=d - 2 * (0.5 * P + ac), minor_int=d - P, drill=d - P,
                 major_int=d + 2 * ac, flank=15.0, crest_ext=0.366 * P, crest_int=0.366 * P, ac=ac,
                 h_ext=0.5 * P + ac, h_int=0.5 * P + ac)
    r.setdefault("major_int", d)
    # coniques : diamètres au bout libre
    if e.standard == "NPT":
        r["free_major_ext"] = e.extra["E0"] + 0.8 * P                    # petit bout du mâle
        r["free_minor_int"] = e.extra["E0"] + e.extra["L2"] / 16 - 0.8 * P  # entrée du femelle
    elif e.standard == "BSPT":
        lj = e.extra["gauge_length"]
        r["free_major_ext"] = d - lj / 16                                # petit bout du mâle R
        r["free_minor_int"] = d - 1.280654 * P                           # entrée du Rc = plan de jauge
        r["drill"] = r["free_minor_int"]
    return r


def describe(e):
    m = dims(e)
    s = "Ø %s × P %s" % (_g(m["d"]), _g(m["P"]))
    if "tpi" in e.extra:
        s += " (%s TPI)" % _g(e.extra["tpi"])
    s += tr(" — d2 %s, noyau vis %s, D1 écrou %s, perçage %s") % (
        _g(m["d2"]), _g(m["minor_ext"]), _g(m["minor_int"]), _g(m["drill"]))
    if e.taper:
        s += tr(" — conique 1:16")
    return s
