"""ThreadSpec : description commune des filetages normalisés et personnalisés (section 8 du cahier)."""
import json
import math
import dataclasses

from . import thread_data


@dataclasses.dataclass
class ThreadSpec:
    name: str = "Personnalisé"
    standard: str = "custom"        # "ISO" | "UNC" | ... | "Tr" | "custom"
    d: float = 0.0                  # mm, Ø nominal ; 0 = garder le Ø de la face (personnalisé)
    pitch: float = 2.0              # mm entre deux filets voisins
    starts: int = 1                 # nombre de filets ; avance = pitch * starts
    left_hand: bool = False
    flank_a: float = 30.0           # degrés, demi-angle du flanc 1 (par rapport au plan radial)
    flank_b: float = 30.0           # degrés, demi-angle du flanc 2 (différent = dent de scie)
    depth: float = 0.0              # mm ; 0 = automatique
    crest: float = 0.0              # mm, méplat de sommet ; 0 = automatique
    taper: bool = False             # conicité 1:16 sur le diamètre
    pitch_override: float = 0.0     # mm ; >0 : norme choisie mais pas personnalisé (ex. M3 au pas de 0,4)

    @property
    def lead(self):
        return self.pitch * max(1, self.starts)

    @property
    def is_custom(self):
        return self.standard == "custom"

    def entry(self):
        if self.is_custom:
            return None
        e = thread_data.get(self.name)
        if self.pitch_override > 0 and not e.taper:
            e = e._replace(P=self.pitch_override)     # cotes recalculées avec le pas choisi
        return e


def from_entry(e, pitch_override=0.0):
    m = thread_data.dims(e)
    po = pitch_override if pitch_override > 0 and not e.taper else 0.0
    return ThreadSpec(name=e.name, standard=e.standard, d=e.d, pitch=po or e.P, flank_a=m["flank"],
                      flank_b=m["flank"], taper=bool(e.taper), pitch_override=po)


def _auto_custom(spec):
    """Profondeur et méplat automatiques d'un profil personnalisé."""
    P = spec.pitch
    ta, tb = math.tan(math.radians(spec.flank_a)), math.tan(math.radians(spec.flank_b))
    crest = spec.crest or (P / 8 if ta + tb > 1e-6 else P / 2)
    if spec.depth:
        depth = spec.depth
    elif ta + tb > 1e-6:
        depth = min((P - crest - P / 8) / (ta + tb), 0.6 * P)   # fond de largeur ≥ P/8
    else:
        depth = 0.5 * P                                           # profil carré
    return depth, crest


def groove(spec, kind, face_R, clearance):
    """Géométrie du sillon à creuser.

    kind : "arbre" (filetage) ou "trou" (taraudage).
    Retourne dict :
      r_open  : rayon de la surface où le sillon s'ouvre au bout libre (= Ø cible de l'ajustement / 2)
      depth   : profondeur radiale du sillon (vers l'axe pour un arbre, vers l'extérieur pour un trou)
      width   : largeur du sillon à r_open
      flank_a, flank_b : demi-angles (degrés)
      taper   : conicité sur le diamètre (0 ou 1/16)
      resize  : True si le Ø de la face doit être ajusté à 2*r_open
    """
    P = spec.pitch
    ext = kind == "arbre"
    c = clearance / 2.0
    if not spec.is_custom:
        e = spec.entry()
        m = thread_data.dims(e)
        if ext:
            major = m.get("free_major_ext", m["d"])
            r_open = major / 2 - c
            depth = m["h_ext"]
            width = P - m["crest_ext"]
        else:
            minor = m.get("free_minor_int", m["minor_int"])
            r_open = minor / 2 + c
            depth = m["h_int"]
            width = P - m["crest_int"]
        return dict(r_open=r_open, depth=depth, width=width, flank_a=m["flank"], flank_b=m["flank"],
                    taper=thread_data.TAPER_1_16 if e.taper else 0.0, resize=True)
    depth, crest = _auto_custom(spec)
    width = P - crest
    if spec.d <= 0:                    # garder le Ø de la face : le jeu élargit le sillon
        r_open, width, resize = face_R, min(width + clearance, P - 0.05 * P), False
    elif ext:
        r_open, resize = spec.d / 2 - c, True
    else:
        r_open, resize = spec.d / 2 - depth + c, True
    return dict(r_open=r_open, depth=depth, width=width, flank_a=spec.flank_a, flank_b=spec.flank_b,
                taper=thread_data.TAPER_1_16 if spec.taper else 0.0, resize=resize)


def check(spec, g):
    """Contrôles de cohérence ; retourne une liste de messages d'erreur."""
    errs = []
    if spec.pitch <= 0:
        errs.append("Le pas doit être positif")
    bottom = g["width"] - g["depth"] * (math.tan(math.radians(g["flank_a"])) + math.tan(math.radians(g["flank_b"])))
    if bottom < -1e-6:
        errs.append("Profil impossible : pas trop petit pour cette profondeur et ces angles "
                    "(réduire la profondeur ou les angles, ou augmenter le pas)")
    if g["width"] >= spec.pitch:
        errs.append("Le sillon est plus large que le pas")
    if g["depth"] <= 0:
        errs.append("La profondeur doit être positive")
    return errs


def presets_load(cfg):
    try:
        return [ThreadSpec(**p) for p in json.loads(cfg.custom_presets or "[]")]
    except Exception:
        return []


def presets_save(cfg, presets):
    cfg.custom_presets = json.dumps([dataclasses.asdict(p) for p in presets])
    cfg.save()
