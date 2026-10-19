"""Page Édition → Préférences → Part/Part Design → Filetage."""
import dataclasses
from PySide import QtGui, QtWidgets

from .config import ThreadConfig
from . import thread_data

# champ : (onglet, libellé, min, max, pas, décimales, suffixe)
FIELDS = {
    "default_depth": ("Valeurs par défaut", "Profondeur filetée par défaut", 0.1, 1000, 1, 2, " mm"),
    "short_ratio": ("Valeurs par défaut", "Pièce plus courte : fraction de la longueur", 0.05, 1, 0.05, 2, ""),
    "clearance": ("Valeurs par défaut", "Jeu d'impression (sur le Ø)", 0, 2, 0.05, 3, " mm"),
    "default_left_hand": ("Valeurs par défaut", "Pas à gauche par défaut"),
    "create_diameter": ("Valeurs par défaut", "Ø proposé pour un trou / extrusion sur un point", 0.5, 500, 0.5, 2, " mm"),
    "allow_add_material": ("Valeurs par défaut", "Autoriser l'ajout de matière pour ajuster le Ø"),
    "max_resize": ("Valeurs par défaut", "Avertir si le Ø change de plus de (rayon)", 0, 50, 0.1, 2, " mm"),
    "groove_extension": ("Valeurs par défaut", "Débord du sillon hors matière", 0.05, 5, 0.05, 2, " mm"),
    "end_margin": ("Valeurs par défaut", "Marge avant le fond / l'épaulement", 0, 50, 0.1, 2, " mm"),
    "preview_enabled": ("Prévisualisation", "Prévisualisation activée à l'ouverture"),
    "preview_color_thread": ("Prévisualisation", "Couleur d'un filetage (arbre)"),
    "preview_color_tap": ("Prévisualisation", "Couleur d'un taraudage (trou)"),
    "axis_follow_type": ("Prévisualisation", "Axe de la couleur du type (rouge / vert)"),
    "axis_color": ("Prévisualisation", "Couleur fixe de l'axe"),
    "axis_width": ("Prévisualisation", "Épaisseur de l'axe", 1, 10, 1, 0, " px"),
    "show_start_face": ("Prévisualisation", "Surligner la face de début"),
    "start_face_color": ("Prévisualisation", "Couleur de la face de début"),
    "preview_transparency": ("Prévisualisation", "Transparence", 0, 95, 5, 0, " %"),
    "preview_delay_ms": ("Prévisualisation", "Délai avant recalcul", 0, 5000, 50, 0, " ms"),
    "show_axis": ("Prévisualisation", "Afficher l'axe détecté"),
    "units_pref": ("Normes", "Préférence d'unités", ["metric", "imperial", "both"]),
    "series_pref": ("Normes", "Série préférée", ["coarse", "fine", "any"]),
    "hole_reference": ("Normes", "Ø de référence d'un trou", ["nominal", "drill", "minor"]),
    "match_tol": ("Normes", "Écart max pour une proposition ★", 0, 10, 0.05, 2, " mm"),
    "n_candidates": ("Normes", "Nombre de propositions ★", 1, 50, 1, 0, ""),
    "allow_taper": ("Normes", "Accepter les faces coniques 1:16"),
    "taper_tol_deg": ("Normes", "Tolérance sur l'angle de conicité", 0.01, 2, 0.01, 2, " °"),
    "delta_m": ("Détection", "Écart radial toléré", 0, 1, 0.005, 4, " mm"),
    "delta_rel": ("Détection", "Écart radial relatif toléré", 0, 0.1, 0.001, 4, ""),
    "polygon_sides": ("Détection", "Cercles en polygones (0 = cercle parfait)", 0, 1000, 1, 0, " côtés"),
    "n_slices": ("Détection", "Nombre de coupes", 2, 50, 1, 0, ""),
    "n_samples": ("Détection", "Points par coupe", 8, 1000, 4, 0, ""),
    "slice_margin": ("Détection", "Marge ignorée aux extrémités", 0, 0.45, 0.01, 2, ""),
    "tessellation_deflection": ("Détection", "Finesse du maillage d'analyse", 0.001, 5, 0.01, 3, " mm"),
    "eps_ratio": ("Détection", "Sonde trou / arbre (fraction du rayon)", 1e-6, 0.1, 1e-4, 6, ""),
    "eps_min": ("Détection", "Sonde minimale", 1e-6, 1, 1e-4, 6, " mm"),
    "axis_mode": ("Détection", "Axe", ["auto", "user"]),
    "axis_warn_deg": ("Détection", "Écart d'axe toléré", 0, 90, 0.1, 2, " °"),
    "axis_conflict": ("Détection", "Si l'axe imposé diffère", ["warn", "error"]),
}


COLOR_FIELDS = {"preview_color_thread", "preview_color_tap", "axis_color", "start_face_color"}


class ThreadPreferencePage:
    def __init__(self, parent=None):
        self.form = QtWidgets.QWidget(parent)
        self.form.setWindowTitle("Filetage")
        lay = QtWidgets.QVBoxLayout(self.form)
        tabs = QtWidgets.QTabWidget()
        lay.addWidget(tabs)
        self.widgets = {}
        pages = {}
        for name, spec in FIELDS.items():
            tab = spec[0]
            if tab not in pages:
                w = QtWidgets.QWidget()
                pages[tab] = QtWidgets.QFormLayout(w)
                tabs.addTab(w, tab)
            fl = pages[tab]
            default = getattr(ThreadConfig(), name)
            if name in COLOR_FIELDS:
                wd = QtWidgets.QPushButton()
                wd.clicked.connect(lambda _=False, b=wd: self._pick_color(b))
            elif len(spec) == 3:
                wd = QtWidgets.QComboBox()
                wd.addItems(spec[2])
            elif isinstance(default, bool):
                wd = QtWidgets.QCheckBox()
            elif isinstance(default, int):
                wd = QtWidgets.QSpinBox()
                wd.setRange(int(spec[2]), int(spec[3]))
                wd.setSingleStep(int(spec[4]))
                wd.setSuffix(spec[6])
            else:
                wd = QtWidgets.QDoubleSpinBox()
                wd.setRange(spec[2], spec[3])
                wd.setSingleStep(spec[4])
                wd.setDecimals(spec[5])
                wd.setSuffix(spec[6])
            self.widgets[name] = wd
            fl.addRow(spec[1], wd)
        # normes proposées
        w = QtWidgets.QWidget()
        vl = QtWidgets.QVBoxLayout(w)
        self.std_boxes = {}
        for s in thread_data.STANDARDS:
            cb = QtWidgets.QCheckBox(thread_data.STANDARD_LABELS[s])
            self.std_boxes[s] = cb
            vl.addWidget(cb)
        vl.addStretch(1)
        tabs.addTab(w, "Normes proposées")
        reset = QtWidgets.QPushButton("Valeurs d'usine")
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)

    @staticmethod
    def _set_color_button(b, color):
        b.setProperty("rgb", int(color))
        b.setStyleSheet("background-color: #%06x; min-height: 20px;" % color)
        b.setText("#%06X" % color)

    def _pick_color(self, b):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor("#%06x" % int(b.property("rgb") or 0)), self.form,
                                            "Couleur")
        if c.isValid():
            self._set_color_button(b, (c.red() << 16) | (c.green() << 8) | c.blue())

    def _show(self, cfg):
        for name, wd in self.widgets.items():
            v = getattr(cfg, name)
            if name in COLOR_FIELDS:
                self._set_color_button(wd, v)
            elif isinstance(wd, QtWidgets.QComboBox):
                wd.setCurrentIndex(max(0, wd.findText(v)))
            elif isinstance(wd, QtWidgets.QCheckBox):
                wd.setChecked(v)
            else:
                wd.setValue(v)
        enabled = {s.strip() for s in cfg.standards.split(",")}
        for s, cb in self.std_boxes.items():
            cb.setChecked(s in enabled)

    def loadSettings(self):
        self._show(ThreadConfig.load())

    def saveSettings(self):
        cfg = ThreadConfig.load()
        for name, wd in self.widgets.items():
            if name in COLOR_FIELDS:
                v = int(wd.property("rgb"))
            elif isinstance(wd, QtWidgets.QComboBox):
                v = wd.currentText()
            elif isinstance(wd, QtWidgets.QCheckBox):
                v = wd.isChecked()
            else:
                v = type(getattr(cfg, name))(wd.value())
            setattr(cfg, name, v)
        cfg.standards = ",".join(s for s, cb in self.std_boxes.items() if cb.isChecked())
        cfg.save()

    def _reset(self):
        self._show(ThreadConfig())
