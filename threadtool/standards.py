"""Proposition automatique des filetages normalisés à partir du Ø mesuré (section 2.10 du cahier)."""
from collections import namedtuple

from . import thread_data

Candidate = namedtuple("Candidate", "entry ref_diameter delta score recommended")

_SERIES_PENALTY = {"coarse": 0.0, "fine": 0.05, "extra-fine": 0.1}
_STD_PENALTY = {"BSW": 0.1, "BSF": 0.1, "Tr": 0.1, "G": 0.02}


def reference_diameter(e, kind, cfg):
    m = thread_data.dims(e)
    if kind == "arbre" or cfg.hole_reference == "nominal":
        return m["d"]                     # trou dessiné au Ø nominal : Ø3 → M3
    if e.taper:
        return m["free_minor_int"]
    return m["minor_int"] if cfg.hole_reference == "minor" else m["drill"]


def propose(kind, diameter, cfg, tapered_face=False):
    """Liste complète des filetages autorisés, triée, les meilleurs en tête."""
    enabled = {s.strip() for s in cfg.standards.split(",") if s.strip()}
    out = []
    for e in thread_data.ALL:
        if e.standard not in enabled:
            continue
        if tapered_face and not e.taper:
            continue
        ref = reference_diameter(e, kind, cfg)
        delta = ref - diameter
        pen = _STD_PENALTY.get(e.standard, 0.0)
        if cfg.series_pref == "coarse":
            pen += _SERIES_PENALTY.get(e.series, 0.0)
        elif cfg.series_pref == "fine":
            pen += {"coarse": 0.05, "fine": 0.0, "extra-fine": 0.03}.get(e.series, 0.0)
        imperial = e.standard in thread_data.IMPERIAL
        if cfg.units_pref == "metric" and imperial or cfg.units_pref == "imperial" and not imperial:
            pen += 0.15
        if e.taper and not tapered_face:
            pen += 0.5
        out.append(Candidate(e, ref, delta, abs(delta) + pen, abs(delta) <= cfg.match_tol))
    out.sort(key=lambda c: c.score)
    return out
