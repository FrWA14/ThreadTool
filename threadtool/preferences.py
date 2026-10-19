"""Page Édition → Préférences → Part/Part Design → Filetage."""
import dataclasses
import FreeCAD as App
from PySide import QtGui, QtWidgets

from .config import ThreadConfig
from . import thread_data, i18n
from .i18n import tr, N_

# champ : (onglet, libellé, min, max, pas, décimales, suffixe) ; liste : (onglet, libellé, [(valeur, libellé)])
D, P, N, A = N_("Valeurs par défaut"), N_("Prévisualisation"), N_("Normes"), N_("Détection")
FIELDS = {
    "default_depth": (D, N_("Profondeur filetée par défaut"), 0.1, 1000, 1, 2, " mm"),
    "short_ratio": (D, N_("Pièce plus courte : fraction de la longueur"), 0.05, 1, 0.05, 2, ""),
    "clearance": (D, N_("Jeu d'impression (sur le Ø)"), 0, 2, 0.05, 3, " mm"),
    "default_left_hand": (D, N_("Pas à gauche par défaut")),
    "create_diameter": (D, N_("Ø proposé pour un trou / extrusion sur un point"), 0.5, 500, 0.5, 2, " mm"),
    "allow_add_material": (D, N_("Autoriser l'ajout de matière pour ajuster le Ø")),
    "max_resize": (D, N_("Avertir si le Ø change de plus de (rayon)"), 0, 50, 0.1, 2, " mm"),
    "groove_extension": (D, N_("Débord du sillon hors matière"), 0.05, 5, 0.05, 2, " mm"),
    "end_margin": (D, N_("Marge avant le fond / l'épaulement"), 0, 50, 0.1, 2, " mm"),
    "preview_enabled": (P, N_("Prévisualisation activée à l'ouverture")),
    "preview_color_thread": (P, N_("Couleur d'un filetage (arbre)")),
    "preview_color_tap": (P, N_("Couleur d'un taraudage (trou)")),
    "axis_follow_type": (P, N_("Axe de la couleur du type (rouge / vert)")),
    "axis_color": (P, N_("Couleur fixe de l'axe")),
    "axis_width": (P, N_("Épaisseur de l'axe"), 1, 10, 1, 0, " px"),
    "show_start_face": (P, N_("Surligner la face de début")),
    "start_face_color": (P, N_("Couleur de la face de début")),
    "preview_transparency": (P, N_("Transparence"), 0, 95, 5, 0, " %"),
    "preview_delay_ms": (P, N_("Délai avant recalcul"), 0, 5000, 50, 0, " ms"),
    "show_axis": (P, N_("Afficher l'axe détecté")),
    "units_pref": (N, N_("Préférence d'unités"), [("metric", N_("métrique")), ("imperial", N_("impérial")), ("both", N_("les deux"))]),
    "series_pref": (N, N_("Série préférée"), [("coarse", N_("pas gros")), ("fine", N_("pas fin")), ("any", N_("indifférent"))]),
    "hole_reference": (N, N_("Ø de référence d'un trou"), [("nominal", N_("nominal")), ("drill", N_("perçage")), ("minor", N_("noyau"))]),
    "match_tol": (N, N_("Écart max pour une proposition ★"), 0, 10, 0.05, 2, " mm"),
    "n_candidates": (N, N_("Nombre de propositions ★"), 1, 50, 1, 0, ""),
    "allow_taper": (N, N_("Accepter les faces coniques 1:16")),
    "taper_tol_deg": (N, N_("Tolérance sur l'angle de conicité"), 0.01, 2, 0.01, 2, " °"),
    "delta_m": (A, N_("Écart radial toléré"), 0, 1, 0.005, 4, " mm"),
    "delta_rel": (A, N_("Écart radial relatif toléré"), 0, 0.1, 0.001, 4, ""),
    "polygon_sides": (A, N_("Cercles en polygones (0 = cercle parfait)"), 0, 1000, 1, 0, N_(" côtés")),
    "n_slices": (A, N_("Nombre de coupes"), 2, 50, 1, 0, ""),
    "n_samples": (A, N_("Points par coupe"), 8, 1000, 4, 0, ""),
    "slice_margin": (A, N_("Marge ignorée aux extrémités"), 0, 0.45, 0.01, 2, ""),
    "tessellation_deflection": (A, N_("Finesse du maillage d'analyse"), 0.001, 5, 0.01, 3, " mm"),
    "eps_ratio": (A, N_("Sonde trou / arbre (fraction du rayon)"), 1e-6, 0.1, 1e-4, 6, ""),
    "eps_min": (A, N_("Sonde minimale"), 1e-6, 1, 1e-4, 6, " mm"),
    "axis_mode": (A, N_("Axe"), [("auto", N_("automatique")), ("user", N_("axe de référence imposé"))]),
    "axis_warn_deg": (A, N_("Écart d'axe toléré"), 0, 90, 0.1, 2, " °"),
    "axis_conflict": (A, N_("Si l'axe imposé diffère"), [("warn", N_("avertir")), ("error", N_("erreur"))]),
}


COLOR_FIELDS = {"preview_color_thread", "preview_color_tap", "axis_color", "start_face_color"}


class ThreadPreferencePage:
    def __init__(self, parent=None):
        self.form = QtWidgets.QWidget(parent)
        self.form.setWindowTitle(tr("Filetage"))
        lay = QtWidgets.QVBoxLayout(self.form)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel(tr("Langue de ThreadTool")))
        self.cb_lang = QtWidgets.QComboBox()
        self.cb_lang.addItem(tr("Auto (langue de FreeCAD)"), "auto")
        for code in sorted({"fr", "en"} | set(i18n.available())):
            self.cb_lang.addItem("%s (%s)" % (i18n.language_name(code), code), code)
        self.cb_lang.setToolTip(tr("Pris en compte au prochain démarrage de FreeCAD"))
        row.addWidget(self.cb_lang, 1)
        lay.addLayout(row)
        tabs = QtWidgets.QTabWidget()
        lay.addWidget(tabs)
        self.widgets = {}
        pages = {}
        for name, spec in FIELDS.items():
            tab = spec[0]
            if tab not in pages:
                w = QtWidgets.QWidget()
                pages[tab] = QtWidgets.QFormLayout(w)
                tabs.addTab(w, tr(tab))
            fl = pages[tab]
            default = getattr(ThreadConfig(), name)
            if name in COLOR_FIELDS:
                wd = QtWidgets.QPushButton()
                wd.clicked.connect(lambda _=False, b=wd: self._pick_color(b))
            elif len(spec) == 3:
                wd = QtWidgets.QComboBox()
                for value, label in spec[2]:
                    wd.addItem(tr(label), value)
            elif isinstance(default, bool):
                wd = QtWidgets.QCheckBox()
            elif isinstance(default, int):
                wd = QtWidgets.QSpinBox()
                wd.setRange(int(spec[2]), int(spec[3]))
                wd.setSingleStep(int(spec[4]))
                wd.setSuffix(tr(spec[6]))
            else:
                wd = QtWidgets.QDoubleSpinBox()
                wd.setRange(spec[2], spec[3])
                wd.setSingleStep(spec[4])
                wd.setDecimals(spec[5])
                wd.setSuffix(tr(spec[6]))
            self.widgets[name] = wd
            fl.addRow(tr(spec[1]), wd)
        # normes proposées
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        self.std_boxes = {}
        for s in thread_data.STANDARDS:
            cb = QtWidgets.QCheckBox(thread_data.STANDARD_LABELS[s])        # déjà traduit
            self.std_boxes[s] = cb
            vl.addWidget(cb)
        vl.addStretch(1)
        tabs.addTab(w, tr("Normes proposées"))
        reset = QtWidgets.QPushButton(tr("Valeurs d'usine"))
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)

    @staticmethod
    def _set_color_button(b, color):
        b.setProperty("rgb", int(color))
        b.setStyleSheet("background-color: #%06x; min-height: 20px;" % color)
        b.setText("#%06X" % color)

    def _pick_color(self, b):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor("#%06x" % int(b.property("rgb") or 0)), self.form,
                                            tr("Couleur"))
        if c.isValid():
            self._set_color_button(b, (c.red() << 16) | (c.green() << 8) | c.blue())

    def _show(self, cfg):
        for name, wd in self.widgets.items():
            v = getattr(cfg, name)
            if name in COLOR_FIELDS:
                self._set_color_button(wd, v)
            elif isinstance(wd, QtWidgets.QComboBox):
                wd.setCurrentIndex(max(0, wd.findData(v)))
            elif isinstance(wd, QtWidgets.QCheckBox):
                wd.setChecked(v)
            else:
                wd.setValue(v)
        enabled = {s.strip() for s in cfg.standards.split(",")}
        for s, cb in self.std_boxes.items():
            cb.setChecked(s in enabled)

    def loadSettings(self):
        self._show(ThreadConfig.load())
        lang = App.ParamGet(i18n.PARAM).GetString("Language", "auto") or "auto"
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(lang)))

    def saveSettings(self):
        cfg = ThreadConfig.load()
        for name, wd in self.widgets.items():
            if name in COLOR_FIELDS:
                v = int(wd.property("rgb"))
            elif isinstance(wd, QtWidgets.QComboBox):
                v = wd.currentData()
            elif isinstance(wd, QtWidgets.QCheckBox):
                v = wd.isChecked()
            else:
                v = type(getattr(cfg, name))(wd.value())
            setattr(cfg, name, v)
        cfg.standards = ",".join(s for s, cb in self.std_boxes.items() if cb.isChecked())
        cfg.save()
        App.ParamGet(i18n.PARAM).SetString("Language", self.cb_lang.currentData() or "auto")

    def _reset(self):
        self._show(ThreadConfig())
