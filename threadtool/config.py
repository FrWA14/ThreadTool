"""Paramètres de ThreadTool, persistés dans les préférences FreeCAD."""
import math
import dataclasses
import FreeCAD as App

PARAM_PATH = "User parameter:BaseApp/Preferences/Mod/ThreadTool"


@dataclasses.dataclass
class ThreadConfig:
    # --- Tolérances de rondeur ---
    delta_m: float = 0.01          # mm, écart radial toléré (valeur absolue)
    delta_rel: float = 0.0         # fraction du rayon (0.002 = 0,2 %), on prend le max des deux
    polygon_sides: int = 0         # 0 = cercle parfait ; N>=3 = cercle approximé par N facettes
    # --- Échantillonnage ---
    n_slices: int = 5              # coupes perpendiculaires à l'axe
    n_samples: int = 60            # points par coupe
    slice_margin: float = 0.05     # fraction de longueur ignorée à chaque bout
    tessellation_deflection: float = 0.1
    # --- Sonde trou/arbre ---
    eps_ratio: float = 1e-3        # sonde = rayon * eps_ratio
    eps_min: float = 1e-3          # mm
    inside_tol: float = 1e-6
    # --- Axe ---
    axis_mode: str = "auto"        # "auto" | "user" (axe de référence obligatoire)
    axis_warn_deg: float = 0.5     # écart angulaire entre axe de la face et axe utilisateur
    axis_conflict: str = "warn"    # "warn" | "error"
    # --- Balayage de la matière ---
    scan_step: float = 0.0         # mm, 0 = pas/2
    scan_angles: int = 12          # points testés par station
    scan_refine: int = 6           # itérations de dichotomie pour trouver la fin exacte
    wall_check: bool = True        # vérifier qu'il y a de la matière derrière la face
    wall_depth_ratio: float = 0.65 # profondeur testée = ratio * pas
    # --- Filet ---
    clearance: float = 0.2         # mm (sur le diamètre), jeu pour impression 3D
    groove_extension: float = 0.5  # mm, débord du sillon hors matière (évite les faces confondues)
    end_margin: float = 0.0        # mm laissés avant le fond (perçage borgne) ou l'épaulement (tête de vis)
    # --- Normes et proposition automatique ---
    units_pref: str = "metric"     # "metric" | "imperial" | "both"
    standards: str = "ISO,UNC,UNF,UNEF,G,BSW,BSF,NPT,BSPT,Tr"  # normes proposées
    series_pref: str = "coarse"    # "coarse" | "fine" | "any"
    hole_reference: str = "nominal"  # "nominal" (trou Ø3 = M3) | "drill" (D-P) | "minor" (D1)
    match_tol: float = 0.3         # mm, écart max pour une proposition « recommandée »
    n_candidates: int = 5          # nombre de propositions mises en tête
    # --- Ajustement du diamètre ---
    allow_add_material: bool = True  # autoriser l'ajout de matière (découpé par l'enveloppe)
    max_resize: float = 1.0        # mm sur le rayon, au-delà : avertissement
    # --- Coniques ---
    allow_taper: bool = True       # accepter une face conique de conicité normalisée 1:16
    taper_tol_deg: float = 0.15    # écart toléré autour de 1,79°
    # --- Personnalisé ---
    custom_presets: str = "[]"     # JSON : liste de ThreadSpec nommées
    # --- Panneau Tâches / valeurs par défaut ---
    default_depth: float = 10.0    # mm, longueur filetée proposée
    short_ratio: float = 0.5       # si longueur utile < default_depth : profondeur = ratio * longueur
    default_standard: str = "ISO"  # norme sélectionnée à l'ouverture (si aucune proposition)
    default_left_hand: bool = False
    create_diameter: float = 6.0   # mm, Ø proposé pour un trou / extrusion créé sur un point ou une face sans cercle
    preview_enabled: bool = True   # case « Prévisualisation » cochée par défaut
    preview_color_thread: int = 0x33CC33  # RGB, aperçu d'un filetage (arbre)
    preview_color_tap: int = 0xE03030     # RGB, aperçu d'un taraudage (trou)
    axis_follow_type: bool = True  # l'axe prend la couleur du type (rouge / vert)
    axis_color: int = 0xFF8000     # RGB, couleur fixe de l'axe si axis_follow_type est faux
    axis_width: int = 2            # px
    show_start_face: bool = True   # surligner la face de début du filet
    start_face_color: int = 0x9933CC  # RGB (violet)
    preview_transparency: int = 60 # %
    preview_delay_ms: int = 400    # attente après la dernière modification avant recalcul
    show_axis: bool = True         # afficher l'axe détecté pendant l'édition

    def tol(self, R):
        t = max(self.delta_m, self.delta_rel * R)
        if self.polygon_sides >= 3:                      # flèche d'un polygone inscrit
            t += R * (1 - math.cos(math.pi / self.polygon_sides))
        return t

    @classmethod
    def load(cls):
        p, cfg = App.ParamGet(PARAM_PATH), cls()
        for f in dataclasses.fields(cls):
            d = getattr(cfg, f.name)
            if isinstance(d, bool):
                v = p.GetBool(f.name, d)
            elif isinstance(d, int):
                v = p.GetInt(f.name, d)
            elif isinstance(d, float):
                v = float(p.GetFloat(f.name, d))
            else:
                v = p.GetString(f.name, d)
            setattr(cfg, f.name, v)
        return cfg

    def save(self):
        p = App.ParamGet(PARAM_PATH)
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool):
                p.SetBool(f.name, v)
            elif isinstance(v, int):
                p.SetInt(f.name, v)
            elif isinstance(v, float):
                p.SetFloat(f.name, v)
            else:
                p.SetString(f.name, v)

    @classmethod
    def reset(cls):
        p = App.ParamGet(PARAM_PATH)
        for f in dataclasses.fields(cls):
            for rm in (p.RemBool, p.RemInt, p.RemFloat, p.RemString):
                rm(f.name)
        return cls()
