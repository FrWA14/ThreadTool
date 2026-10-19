"""Panneau « Tâches » de la fonction Filetage (section 9.5 du cahier)."""
import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtCore, QtGui, QtWidgets

from .axis import NotThreadable, radial
from .config import ThreadConfig
from . import detect, builder, standards, thread_data, thread_spec, feature, creation, heads
from .preview import Preview
from .i18n import tr, enum_get, enum_put

QDBB = QtWidgets.QDialogButtonBox


def _dspin(lo, hi, step, dec=3, suffix=" mm"):
    s = QtWidgets.QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(dec)
    s.setSuffix(suffix)
    s.setKeyboardTracking(False)
    return s


def _field(le, text):
    """Champ du tableau : texte affiché depuis le début, texte complet en info-bulle."""
    le.setText(text)
    le.setCursorPosition(0)
    le.setToolTip(text)


def body_of(obj):
    b = obj.getParentGeoFeatureGroup()
    if b is None or not b.isDerivedFrom("PartDesign::Body"):
        raise NotThreadable(tr("La fonction doit être dans un corps PartDesign"))
    return b


def to_local(shape, body):
    """Forme globale -> repère du corps."""
    s = shape.copy()
    s.transformShape(body.getGlobalPlacement().inverse().toMatrix())
    return s


def match_face(base_shape, face_local):
    """Retrouve dans la forme de base la face géométriquement identique à face_local."""
    best = None
    for i, f in enumerate(base_shape.Faces):
        if type(f.Surface) is not type(face_local.Surface):
            continue
        d = (f.CenterOfMass - face_local.CenterOfMass).Length + abs(f.Area - face_local.Area)
        if best is None or d < best[0]:
            best = (d, i)
    if best is None or best[0] > 1e-2 * max(1.0, face_local.BoundBox.DiagonalLength):
        return None
    return "Face%d" % (best[1] + 1)


class ThreadTaskPanel:
    def __init__(self, obj, new=False, restore=None):
        self.obj = obj
        self.restore = restore or []                # sélection d'origine, remise si on annule
        self.anchor = None
        self.cplan = None
        self.new = new
        self.doc = obj.Document
        self.body = body_of(obj)
        self.base = obj.BaseFeature
        self.cfg = ThreadConfig.load()
        self.info = None
        self.err = None
        self.sel_mode = None
        self._busy = False
        if not new:
            self.doc.openTransaction(tr("Modifier le filetage"))
        self.form = self._build_ui()
        self.preview = Preview(self.body.getGlobalPlacement())
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.update_preview)
        if obj.ViewObject:
            obj.ViewObject.hide()
        if self.base and self.base.ViewObject:
            self.base.ViewObject.show()
        Gui.Selection.addObserver(self)
        self.reanalyse()
        self.load_from_obj()
        self.schedule()

    # ------------------------------------------------------------------ interface
    def _build_ui(self):
        w = QtWidgets.QWidget()
        w.setWindowTitle(tr("Filetage / taraudage"))
        lay = QtWidgets.QVBoxLayout(w)

        g = QtWidgets.QGroupBox(tr("Opération"))
        ho = QtWidgets.QHBoxLayout(g)
        self.cb_op = QtWidgets.QComboBox()
        for op, label in zip(creation.OPERATIONS, (tr("Fileter / tarauder la face existante"),
                                                   tr("Trou taraudé (percer + tarauder)"),
                                                   tr("Extrusion filetée (ajouter + fileter)"))):
            self.cb_op.addItem(label, op)
        self.cb_op.setToolTip(tr("Trou / extrusion : créés sur l'appui (esquisse, point, cercle ou face plane),\n"
                              "au Ø nominal du filetage choisi, puis filetés dans la même fonction"))
        ho.addWidget(self.cb_op, 1)
        lay.addWidget(g)

        # Références, comme les champs « Face » de Protrusion / Poche : bouton de sélection à gauche,
        # champ texte « Libellé:FaceN » à droite (modifiable ; vide = automatique).
        g = QtWidgets.QGroupBox(tr("Références"))
        f = QtWidgets.QGridLayout(g)
        f.setColumnStretch(1, 1)

        def row(r, title, tip):
            btn = QtWidgets.QToolButton()
            btn.setText(title)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
            le = QtWidgets.QLineEdit()
            le.setClearButtonEnabled(True)
            le.setToolTip(tip + tr("\nTape « Libellé:FaceN » ou efface le texte pour revenir à l'automatique."))
            f.addWidget(btn, r, 0)
            f.addWidget(le, r, 1)
            return btn, le

        self.btn_sup, self.lbl_sup = row(0, tr("Appui"), tr("Esquisse (tous ses cercles ou points), point, sommet, "
                                                     "cercle ou face plane où créer le trou / extrusion"))
        self.btn_flip_sup = QtWidgets.QToolButton()
        self.btn_flip_sup.setText("⇅")
        self.btn_flip_sup.setToolTip(tr("Inverser le sens du trou / extrusion"))
        f.addWidget(self.btn_flip_sup, 0, 2)
        self.btn_face, self.lbl_face = row(1, tr("Face"), tr("Face cylindrique à fileter / tarauder"))
        self.btn_axis, self.lbl_axis = row(2, tr("Axe"), tr("Axe imposé (facultatif) : arête droite, cercle, face plane ou axe de l'Origin"))
        self.btn_ref, self.lbl_ref = row(3, tr("Début"), tr("Face ou plan de début du filet (surligné en violet)"))
        self.btn_flip = QtWidgets.QToolButton()
        self.btn_flip.setText("⇅")
        self.btn_flip.setToolTip(tr("Inverser : partir de l'autre extrémité de la face"))
        f.addWidget(self.btn_flip, 3, 2)
        lbl = QtWidgets.QLabel(tr("Longueur"))
        lbl.setToolTip(tr("Longueur totale utilisable : reprise de la fonction qui a créé la face "
                       "(Protrusion, Poche, Perçage…), sinon mesurée sur la géométrie"))
        self.lbl_len = QtWidgets.QLineEdit()
        self.lbl_len.setReadOnly(True)
        f.addWidget(lbl, 4, 0)
        f.addWidget(self.lbl_len, 4, 1)
        self.lbl_faceinfo = QtWidgets.QLabel("")
        self.lbl_faceinfo.setWordWrap(True)
        f.addWidget(self.lbl_faceinfo, 5, 0, 1, 3)
        self.existing_widgets = [self.btn_face, self.lbl_face, self.btn_axis, self.lbl_axis, self.btn_ref,
                                 self.lbl_ref, self.btn_flip]
        self.creation_widgets = [self.btn_sup, self.lbl_sup, self.btn_flip_sup]
        for btn in (self.btn_sup, self.btn_face, self.btn_axis, self.btn_ref):
            btn.setMinimumWidth(70)
        lay.addWidget(g)

        g = QtWidgets.QGroupBox(tr("Filetage"))
        f = QtWidgets.QFormLayout(g)
        self.cb_std = QtWidgets.QComboBox()
        self.cb_std.addItem(tr("★ Proposition automatique"), "auto")
        for key, label, _std, _ser in thread_data.CHOICES:
            self.cb_std.addItem(label, key)
        self.cb_std.addItem(tr("Personnalisé (hors norme)"), "custom")
        self.cb_des = QtWidgets.QComboBox()
        for cb in (self.cb_std, self.cb_des):
            cb.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(12)
        self.lbl_info = QtWidgets.QLabel("")
        self.lbl_info.setWordWrap(True)
        self.ck_pitch = QtWidgets.QCheckBox(tr("personnalisé"))
        self.ck_pitch.setToolTip(tr("Garder la norme et le Ø choisis, avec un autre pas (ex. M3 au pas de 0,4)"))
        self.sp_pitch = _dspin(0.05, 50, 0.05)
        hpp = QtWidgets.QHBoxLayout()
        hpp.addWidget(self.sp_pitch, 1)
        hpp.addWidget(self.ck_pitch)
        f.addRow(tr("Norme / format"), self.cb_std)
        f.addRow(tr("Désignation"), self.cb_des)
        f.addRow(tr("Pas"), hpp)
        f.addRow(self.lbl_info)
        lay.addWidget(g)

        self.grp_custom = QtWidgets.QGroupBox(tr("Dimensions personnalisées"))
        f = QtWidgets.QFormLayout(self.grp_custom)
        self.cb_preset = QtWidgets.QComboBox()
        self.btn_preset_save = QtWidgets.QPushButton(tr("Enregistrer…"))
        self.btn_preset_del = QtWidgets.QPushButton(tr("Supprimer"))
        hp = QtWidgets.QHBoxLayout()
        hp.addWidget(self.cb_preset, 1)
        hp.addWidget(self.btn_preset_save)
        hp.addWidget(self.btn_preset_del)
        self.sp_cd = _dspin(0, 1000, 0.1)
        self.sp_cd.setSpecialValueText(tr("garder le Ø de la face"))
        self.sp_cp = _dspin(0.05, 50, 0.1)
        self.sp_cs = QtWidgets.QSpinBox()
        self.sp_cs.setRange(1, 12)
        self.sp_ca = _dspin(0, 60, 1, 1, " °")
        self.sp_cb = _dspin(0, 60, 1, 1, " °")
        self.sp_ch = _dspin(0, 20, 0.05)
        self.sp_ch.setSpecialValueText(tr("auto"))
        self.sp_cc = _dspin(0, 20, 0.05)
        self.sp_cc.setSpecialValueText(tr("auto"))
        self.ck_ct = QtWidgets.QCheckBox(tr("Conique 1:16"))
        f.addRow(tr("Préréglage"), hp)
        f.addRow(tr("Ø nominal"), self.sp_cd)
        f.addRow(tr("Pas"), self.sp_cp)
        f.addRow(tr("Nombre de filets"), self.sp_cs)
        f.addRow(tr("Demi-angle flanc 1"), self.sp_ca)
        f.addRow(tr("Demi-angle flanc 2"), self.sp_cb)
        f.addRow(tr("Profondeur du filet"), self.sp_ch)
        f.addRow(tr("Méplat de sommet"), self.sp_cc)
        f.addRow(self.ck_ct)
        lay.addWidget(self.grp_custom)

        g = QtWidgets.QGroupBox(tr("Options"))
        f = QtWidgets.QFormLayout(g)
        self.sp_depth = _dspin(0.01, 10000, 1, 2)
        self.btn_full = QtWidgets.QPushButton(tr("Jusqu'au bout"))
        hd = QtWidgets.QHBoxLayout()
        hd.addWidget(self.sp_depth, 1)
        hd.addWidget(self.btn_full)
        self.lbl_turns = QtWidgets.QLabel("")
        self.lbl_turns.setToolTip(tr("Longueur filetée exprimée en nombre de filets (profondeur / pas)"))
        self.sp_offset = _dspin(0, 1000, 0.5, 2)
        self.sp_offset.setToolTip(tr("Le filet commence à cette distance de la face (ou du plan) de début.\n"
                                  "Entre les deux, le Ø est ramené au Ø de pied du filet si besoin\n"
                                  "(matière retirée, visible dans l'aperçu)."))
        self.sp_clr = _dspin(0, 2, 0.05)
        self.ck_preview = QtWidgets.QCheckBox(tr("Prévisualisation"))
        self.rb_right = QtWidgets.QRadioButton(tr("À droite"))
        self.rb_left = QtWidgets.QRadioButton(tr("À gauche"))
        hs = QtWidgets.QHBoxLayout()
        hs.addWidget(self.rb_right)
        hs.addWidget(self.rb_left)
        self.bg_hand = QtWidgets.QButtonGroup(w)
        self.bg_hand.addButton(self.rb_right)
        self.bg_hand.addButton(self.rb_left)
        f.addRow(tr("Décalage du début"), self.sp_offset)
        f.addRow(tr("Profondeur"), hd)
        f.addRow("", self.lbl_turns)
        f.addRow(tr("Jeu (sur le Ø)"), self.sp_clr)
        f.addRow(self.ck_preview)
        f.addRow(tr("Sens du pas"), hs)
        lay.addWidget(g)

        g = self.grp_head = QtWidgets.QGroupBox(tr("Tête"))
        f = QtWidgets.QFormLayout(g)
        self.cb_head = QtWidgets.QComboBox()
        self.cb_head.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.cb_head.setMinimumContentsLength(12)
        self.cb_hpos = QtWidgets.QComboBox()
        for pos in heads.POSITIONS:
            self.cb_hpos.addItem(tr(pos), pos)
        self.cb_hpos.setToolTip(tr("Face opposée : à l'autre bout de la tige (vis classique)\n"
                                "Face de début : sur la face d'où part le filet"))
        self.cb_drive = QtWidgets.QComboBox()
        for dr in heads.DRIVES:
            self.cb_drive.addItem(tr(dr), dr)
        self.ck_hcustom = QtWidgets.QCheckBox(tr("Dimensions personnalisées"))
        self.ck_hcustom.setToolTip(tr("Partir des cotes de la norme et les modifier"))
        self.sp_hd = _dspin(0, 1000, 0.1)
        self.sp_hh = _dspin(0, 1000, 0.1)
        self.sp_ha = _dspin(30, 150, 1, 1, " °")
        self.sp_ds = _dspin(0, 100, 0.1)
        self.sp_dd = _dspin(0, 100, 0.1)
        self.lbl_head = QtWidgets.QLabel("")
        self.lbl_head.setWordWrap(True)
        f.addRow(tr("Forme"), self.cb_head)
        f.addRow(tr("Position"), self.cb_hpos)
        f.addRow(tr("Empreinte"), self.cb_drive)
        f.addRow(self.ck_hcustom)
        self.lbl_hd, self.lbl_hh = QtWidgets.QLabel("Ø"), QtWidgets.QLabel(tr("Hauteur"))
        self.lbl_ha, self.lbl_ds, self.lbl_dd = (QtWidgets.QLabel(tr("Angle")), QtWidgets.QLabel(tr("Taille empreinte")),
                                                 QtWidgets.QLabel(tr("Prof. empreinte")))
        f.addRow(self.lbl_hd, self.sp_hd)
        f.addRow(self.lbl_hh, self.sp_hh)
        f.addRow(self.lbl_ha, self.sp_ha)
        f.addRow(self.lbl_ds, self.sp_ds)
        f.addRow(self.lbl_dd, self.sp_dd)
        f.addRow(self.lbl_head)
        self._head_kind = None
        lay.addWidget(g)

        g = self.grp_kind = QtWidgets.QGroupBox(tr("Type"))
        hk = QtWidgets.QHBoxLayout(g)
        self.rb_tap = QtWidgets.QRadioButton(tr("Taraudage (trou)"))
        self.rb_thr = QtWidgets.QRadioButton(tr("Filetage (arbre)"))
        self.bg_kind = QtWidgets.QButtonGroup(w)
        self.bg_kind.addButton(self.rb_tap)
        self.bg_kind.addButton(self.rb_thr)
        hk.addWidget(self.rb_tap)
        hk.addWidget(self.rb_thr)
        lay.addWidget(g)

        self.lbl_msg = QtWidgets.QLabel("")
        self.lbl_msg.setWordWrap(True)
        lay.addWidget(self.lbl_msg)
        lay.addStretch(1)

        self.cb_op.currentIndexChanged.connect(self.on_op)
        self.cb_head.currentIndexChanged.connect(self.on_head)
        self.cb_hpos.currentIndexChanged.connect(self.on_head_value)
        self.cb_drive.currentIndexChanged.connect(self.on_drive)
        self.ck_hcustom.toggled.connect(self.on_head_value)
        for sp in (self.sp_hd, self.sp_hh, self.sp_ha, self.sp_ds, self.sp_dd):
            sp.valueChanged.connect(self.on_head_value)
        self.btn_sup.toggled.connect(lambda on: self.set_sel_mode("support" if on else None))
        self.lbl_sup.editingFinished.connect(lambda: self.on_ref_text("support"))
        self.btn_flip_sup.clicked.connect(self.flip_support)
        self.btn_face.toggled.connect(lambda on: self.set_sel_mode("face" if on else None))
        self.btn_axis.toggled.connect(lambda on: self.set_sel_mode("axis" if on else None))
        self.btn_ref.toggled.connect(lambda on: self.set_sel_mode("ref" if on else None))
        self.lbl_face.editingFinished.connect(lambda: self.on_ref_text("face"))
        self.lbl_axis.editingFinished.connect(lambda: self.on_ref_text("axis"))
        self.lbl_ref.editingFinished.connect(lambda: self.on_ref_text("ref"))
        self.ck_pitch.toggled.connect(self.on_pitch)
        self.sp_pitch.valueChanged.connect(self.on_pitch)
        self.btn_flip.clicked.connect(self.flip_side)
        self.cb_std.currentIndexChanged.connect(self.on_std)
        self.cb_des.currentIndexChanged.connect(self.on_des)
        for sp in (self.sp_cd, self.sp_cp, self.sp_ca, self.sp_cb, self.sp_ch, self.sp_cc, self.sp_depth, self.sp_clr,
                   self.sp_offset):
            sp.valueChanged.connect(self.on_value)
        self.sp_cs.valueChanged.connect(self.on_value)
        self.ck_ct.toggled.connect(self.on_value)
        self.ck_preview.toggled.connect(self.on_preview_toggle)
        self.rb_left.toggled.connect(self.on_value)
        self.rb_tap.toggled.connect(self.on_kind)
        self.btn_full.clicked.connect(self.on_full)
        self.cb_preset.activated.connect(self.on_preset)
        self.btn_preset_save.clicked.connect(self.save_preset)
        self.btn_preset_del.clicked.connect(self.delete_preset)
        return w

    def getStandardButtons(self):
        return QDBB.Ok | QDBB.Cancel

    # ------------------------------------------------------------------ données
    def creating(self):
        return feature.creating(self.obj)

    def reanalyse(self):
        """Analyse de la face courante (ou choix par défaut), ou de l'appui d'un trou / extrusion."""
        self.info, self.err = None, None
        self.anchor, self.cplan = None, None
        if self.base is None:
            self.err = tr("Aucune fonction précédente dans le corps")
            return
        shape = self.base.Shape
        if self.creating():
            try:
                self.anchor = creation.resolve(self.obj.Support, shape, self.obj.SupportPoint, self.obj.HintAxis)
                self.obj.HintAxis = self.anchor.normal
            except NotThreadable as e:
                self.err = str(e)
            except Exception as e:
                self.err = tr("Erreur : %s") % e
            return
        try:
            face = feature.find_face(self.obj, shape, self.cfg)
            self.info = detect.analyse(shape, face, feature._ref_shape(self.obj.AxisReference), self.cfg)
            self.obj.HintCenter, self.obj.HintAxis = self.info["center"], self.info["axis"]
            self.obj.HintRadius = self.info["R"]
        except NotThreadable as e:
            self.err = str(e)
        except Exception as e:
            self.err = tr("Erreur : %s") % e

    def kind(self):
        if self.creating():
            return "trou" if feature.op(self.obj) == creation.OPERATIONS[1] else "arbre"
        forced = {"Taraudage": "trou", "Filetage": "arbre"}.get(feature.mode(self.obj))
        return forced or (self.info["kind"] if self.info else "arbre")

    def available(self):
        if self.creating():
            try:
                cc = feature.creation_context(self.obj, self.base.Shape, self.cfg)
                return cc["plan"].thickness or 0.0
            except Exception:
                return 0.0
        if not self.info:
            return 0.0
        try:
            ctx = feature.context(self.obj, self.base.Shape, self.cfg)
            p = builder.make_plan(self.base.Shape, ctx["info"], ctx["spec"], self.cfg,
                                  **dict(ctx["kw"], depth=0.001))
            return p.available
        except Exception:
            return self.info["t_max"] - self.info["t_min"]

    def load_from_obj(self):
        self._busy = True
        o = self.obj
        self.cb_op.setCurrentIndex(max(0, self.cb_op.findData(feature.op(o))))
        self.update_mode_ui()
        self.refresh_ref_fields()
        if o.Standard == "custom":
            key = "custom"
        elif self.new:
            key = "auto"
        else:
            try:
                key = thread_data.choice_key(thread_data.get(o.Designation))
            except KeyError:
                key = "auto"
        self.cb_std.setCurrentIndex(max(0, self.cb_std.findData(key)))
        self.ck_pitch.setChecked(o.PitchOverride.Value > 0)
        self.sp_cd.setValue(o.CustomDiameter.Value)
        self.sp_cp.setValue(o.CustomPitch.Value)
        self.sp_cs.setValue(o.CustomStarts)
        self.sp_ca.setValue(o.CustomFlankA.Value)
        self.sp_cb.setValue(o.CustomFlankB.Value)
        self.sp_ch.setValue(o.CustomDepth.Value)
        self.sp_cc.setValue(o.CustomCrest.Value)
        self.ck_ct.setChecked(o.CustomTaper)
        self.sp_depth.setValue(o.Depth.Value)
        self.sp_offset.setValue(o.StartOffset.Value)
        self.sp_clr.setValue(o.Clearance.Value)
        self.ck_preview.setChecked(self.cfg.preview_enabled)
        (self.rb_left if o.LeftHanded else self.rb_right).setChecked(True)
        (self.rb_tap if self.kind() == "trou" else self.rb_thr).setChecked(True)
        self.fill_presets()
        self._busy = False
        self.fill_designations()
        self.update_visibility()

    def update_mode_ui(self):
        c = self.creating()
        for wdg in self.existing_widgets:
            wdg.setVisible(not c)
        for wdg in self.creation_widgets:
            wdg.setVisible(c)
        self.grp_kind.setVisible(not c)
        self.btn_full.setVisible(not c or feature.op(self.obj) == creation.OPERATIONS[1])

    def start_faces(self):
        """Faces (ou disque du plan) où commence le filet : surlignées en violet."""
        o = self.obj
        if self.creating():
            if not self.anchor or not self.anchor.centers:
                return []
            r = (self.cplan.r if self.cplan else (self.anchor.radius or 1.0)) * 1.3
            return [Part.Face(Part.Wire(Part.makeCircle(r, c, self.anchor.normal))) for c in self.anchor.centers]
        if not self.info:
            return []
        if o.HeightReference:
            ob, subs = o.HeightReference
            try:
                if subs and subs[0]:
                    return [ob.Shape.getElement(subs[0])]
                n, p0 = feature._plane_of(o.HeightReference)        # plan infini : disque autour de l'axe
                a, c = self.info["axis"], self.info["center"]
                t = (p0 - c).dot(n) / a.dot(n)
                disc = Part.Face(Part.Wire(Part.makeCircle(self.info["R"] * 1.6, c + a * t, n)))
                return [disc]
            except Exception:
                return []
        return list(self.info["ends"][o.Side if o.Side in ("low", "high") else "high"]["neighbors"])

    @staticmethod
    def _link_text(link):
        """Texte FreeCAD d'une référence : « Libellé:FaceN », ou « Libellé » pour un plan / axe."""
        if not link:
            return ""
        ob, subs = link
        return "%s:%s" % (ob.Label, subs[0]) if subs and subs[0] else ob.Label

    def _side_text(self):
        return tr("côté +axe") if self.obj.Side == "high" else tr("côté −axe")

    def _ref_text(self):
        """Texte gris du champ « Début » quand il est automatique."""
        if not self.info and not self.creating():
            return tr("Auto : bout libre de la face")
        names = []
        if self.info and self.base is not None:
            for g in self.start_faces():
                try:
                    names.append(detect.face_name(self.base.Shape, g))
                except Exception:
                    pass
        return tr("Auto : %s:%s (bout libre, %s)") % (self.base.Label if self.base else "?",
                                                   ", ".join(dict.fromkeys(names)) or "?", self._side_text())

    def refresh_ref_fields(self):
        o = self.obj
        for le in (self.lbl_face, self.lbl_axis, self.lbl_ref, self.lbl_sup):
            le.blockSignals(True)
        _field(self.lbl_sup, self._link_text(o.Support))
        self.lbl_sup.setPlaceholderText(tr("Aucun appui sélectionné"))
        if self.creating():
            _field(self.lbl_face, "")
            self.lbl_faceinfo.setText((tr("Appui : %s") % self.anchor.desc) if self.anchor else (self.err or ""))
        elif self.info:
            _field(self.lbl_face, "%s:%s" % (self.base.Label, o.FaceName))
            src = feature.source_feature(o, self.info)
            self.lbl_faceinfo.setText("%s Ø %.3f%s%s" % (
                tr("Trou") if self.info["kind"] == "trou" else tr("Arbre"), self.info["diameter"],
                tr(" (conique 1:16)") if self.info["half_angle"] else "",
                tr(" — face créée par %s") % src["label"] if src else ""))
        else:
            _field(self.lbl_face, "")
            self.lbl_faceinfo.setText(self.err or "")
        self.lbl_face.setPlaceholderText(tr("Aucune face sélectionnée"))
        _field(self.lbl_axis, self._link_text(o.AxisReference))
        self.lbl_axis.setPlaceholderText(tr("Auto : axe de la face"))
        _field(self.lbl_ref, self._link_text(o.HeightReference))
        self.lbl_ref.setPlaceholderText(self._ref_text())
        if o.HeightReference:
            self.lbl_ref.setToolTip("%s (%s)" % (self._link_text(o.HeightReference), self._side_text()))
        for le in (self.lbl_face, self.lbl_axis, self.lbl_ref, self.lbl_sup):
            le.blockSignals(False)
        for rb in (self.rb_tap, self.rb_thr):                  # type affiché = type de la face courante
            rb.blockSignals(True)
        (self.rb_tap if self.kind() == "trou" else self.rb_thr).setChecked(True)
        for rb in (self.rb_tap, self.rb_thr):
            rb.blockSignals(False)
        self._last_text = {m: le.text() for m, le in (("face", self.lbl_face), ("axis", self.lbl_axis),
                                                      ("ref", self.lbl_ref), ("support", self.lbl_sup))}

    def _object_by_label(self, label):
        objs = self.doc.getObjectsByLabel(label)
        if not objs:
            o = self.doc.getObject(label)
            objs = [o] if o else []
        if not objs:
            raise NotThreadable(tr("Aucun objet nommé « %s »") % label)
        return objs[0]

    def on_ref_text(self, mode):
        """Texte tapé ou effacé dans un champ de référence (comme dans Protrusion / Poche)."""
        le = {"face": self.lbl_face, "axis": self.lbl_axis, "ref": self.lbl_ref, "support": self.lbl_sup}[mode]
        text = le.text().strip()
        if text == getattr(self, "_last_text", {}).get(mode):
            return
        try:
            if mode == "support":
                if text:
                    label, _, sub = text.partition(":")
                    self.apply_support(self._object_by_label(label.strip()), sub.strip(), None)
                else:
                    self.obj.Support = None
                    self.reanalyse()
            elif not text:                                     # effacé : retour à l'automatique
                if mode == "face":
                    self.auto_face()
                elif mode == "axis":
                    self.obj.AxisReference = None
                    self.reanalyse()
                else:
                    self.obj.HeightReference = None
                    self.set_default_depth()
            else:
                label, _, sub = text.partition(":")
                ob = self._object_by_label(label.strip())
                sub = sub.strip()
                if mode == "face":
                    if not sub.startswith("Face"):
                        raise NotThreadable(tr("Format attendu : Libellé:FaceN"))
                    self.apply_face(Part.getShape(ob, sub, needSubElement=True))
                else:
                    self.apply_link(mode, ob, sub)
            self.show_msg("", "info")
        except NotThreadable as e:
            self.show_msg(str(e), "error")
        except Exception as e:
            self.show_msg(tr("Référence non utilisable : %s") % e, "error")
        self.refresh_ref_fields()
        self.fill_designations()
        self.schedule()

    def auto_face(self):
        """Face et côté automatiques (section 9.4 du cahier)."""
        from .commands import _other_bodies
        info, side = detect.find_default(self.base.Shape, self.cfg, _other_bodies(self.doc, self.body))
        if info is None:
            raise NotThreadable(tr("Aucune face cylindrique filetable trouvée"))
        self.obj.FaceName = info["face_name"]
        self.obj.HintRadius = 0.0
        self.obj.Side = side
        self.reanalyse()
        self.set_default_depth()

    def apply_face(self, face_local):
        """Face choisie (dans le repère du corps) : retrouvée dans la fonction précédente."""
        name = match_face(self.base.Shape, face_local)
        if name is None:
            raise NotThreadable(tr("Cette face n'appartient pas à la fonction précédente du corps"))
        self.obj.FaceName = name
        self.obj.HintRadius = 0.0
        self.reanalyse()
        if self.info:
            side, _ = self._default_side()
            self.obj.Side = side
        self.set_default_depth()

    def apply_support(self, ob, sub, picked):
        """Nouvel appui d'un trou / extrusion (picked : point cliqué, repère du corps)."""
        link = (ob, [sub] if sub else [])
        creation.resolve(link, self.base.Shape, picked)           # vérifie avant d'enregistrer
        self.obj.Support = link
        if picked is not None:
            self.obj.SupportPoint = picked
        self.reanalyse()
        self.set_default_depth()

    def apply_link(self, mode, ob, sub):
        link = (ob, [sub] if sub else [])
        if mode == "axis":
            self.obj.AxisReference = link
            self.reanalyse()
            return
        self.obj.HeightReference = link
        n, p0 = feature._plane_of(self.obj.HeightReference)          # vérifie que c'est un plan
        if self.info:                                                # partir du bout le plus proche du plan
            a, c = self.info["axis"], self.info["center"]
            if abs(a.dot(n)) > 1e-6:
                t = (p0 - c).dot(n) / a.dot(n)
                near_low = abs(t - self.info["t_min"]) < abs(t - self.info["t_max"])
                self.obj.Side = "low" if near_low else "high"
        self.set_default_depth()

    def fill_designations(self):
        self._busy = True
        self.cb_des.clear()
        key = self.cb_std.currentData()
        basis = self.basis()
        if key == "custom" or not basis:
            self._busy = False
            self.update_info()
            return
        kind, diam, tapered = basis
        cands = standards.propose(kind, diam, self.cfg, tapered_face=tapered)
        if self.creating():
            cands = [c for c in cands if not c.entry.taper]  # perçage / extrusion cylindriques
        top = {c.entry.name for c in cands[:self.cfg.n_candidates] if c.recommended}   # ★ = meilleures propositions
        if key == "auto":
            cands = cands[:max(15, self.cfg.n_candidates)]
        else:                                                 # une norme / série : ordre croissant
            cands = sorted([c for c in cands if thread_data.choice_key(c.entry) == key],
                           key=lambda c: (c.entry.d, -c.entry.P))
        current = -1
        for i, c in enumerate(cands):
            star = "★ " if c.entry.name in top else ""
            self.cb_des.addItem("%s%s  (%+.2f)" % (star, c.entry.name, c.delta), c.entry.name)
            self.cb_des.setItemData(i, tr("Ø de référence %.3f mm, écart %+.3f mm") % (c.ref_diameter, c.delta),
                                    QtCore.Qt.ToolTipRole)
            if c.entry.name == self.obj.Designation and current < 0:
                current = i
        if self.new and key == "auto":
            current = 0
        self.cb_des.setCurrentIndex(max(0, current))
        self._busy = False
        self.on_des()

    def basis(self):
        """(type, Ø de référence, conique) pour les propositions, ou None."""
        if self.creating():
            if not self.anchor:
                return None
            return self.kind(), 2 * self.anchor.radius if self.anchor.radius else self.cfg.create_diameter, False
        if not self.info:
            return None
        return self.kind(), self.info["diameter"], bool(self.info["half_angle"])

    def update_visibility(self):
        self.grp_custom.setVisible(self.cb_std.currentData() == "custom")
        self.cb_des.setEnabled(self.cb_std.currentData() != "custom")

    # ------------------------------------------------------------------ tête
    def refresh_head(self):
        """Liste des têtes selon le type (lamage / fraisage pour un trou, tête de vis pour un arbre) et cotes."""
        o = self.obj
        kind = self.kind()
        widgets = (self.cb_head, self.cb_hpos, self.cb_drive, self.ck_hcustom,
                   self.sp_hd, self.sp_hh, self.sp_ha, self.sp_ds, self.sp_dd)
        for wdg in widgets:
            wdg.blockSignals(True)
        try:
            if kind != self._head_kind:
                self._head_kind = kind
                self.cb_head.clear()
                if kind == "trou":
                    self.cb_head.addItem(tr(heads.NONE), heads.NONE)
                    for key, (label, _t, _a, _tb) in heads.HOLE_CUTS.items():
                        self.cb_head.addItem(label, key)
                else:
                    self.cb_head.addItem(tr(heads.NONE), heads.NONE)
                    for key, (label, _s, _d, _tb) in heads.SCREW_HEADS.items():
                        self.cb_head.addItem(label, key)
            cur = (enum_get(o, "HoleHead", heads.HOLE_HEADS) if kind == "trou"
                   else enum_get(o, "ScrewHead", heads.SCREW_HEAD_NAMES))
            drive = enum_get(o, "Drive", heads.DRIVES)
            self.cb_head.setCurrentIndex(max(0, self.cb_head.findData(cur)))
            self.cb_hpos.setCurrentIndex(max(0, self.cb_hpos.findData(enum_get(o, "HeadPosition", heads.POSITIONS))))
            self.cb_drive.setCurrentIndex(max(0, self.cb_drive.findData(drive)))
            self.ck_hcustom.setChecked(o.HeadCustom)
            custom_std = o.Standard == "custom"
            active = cur != heads.NONE and not custom_std
            screw = kind != "trou"
            self.cb_head.setEnabled(not custom_std)
            for wdg in (self.cb_hpos, self.cb_drive):
                wdg.setVisible(screw)
                self.grp_head.layout().labelForField(wdg).setVisible(screw)
                wdg.setEnabled(active)
            info, h = "", None
            if custom_std:
                info = heads.NEED_STANDARD
            elif active:
                try:
                    spec = feature.spec_of(o)
                    h = heads.params(o, spec.d, kind, write=True)
                except Exception as e:
                    info = str(e)
            cut_type = h.get("type") if h and kind == "trou" else None
            self.lbl_hd.setText("Ø" if kind == "trou" else (tr("Sur plats") if h and h["shape"] in ("hex", "square") else tr("Ø de tête")))
            self.lbl_hh.setText(tr("Profondeur") if kind == "trou" else tr("Hauteur"))
            show = {self.sp_hd: active, self.sp_hh: active and cut_type != "fraisage",
                    self.sp_ha: active and cut_type == "fraisage",
                    self.sp_ds: active and screw and drive != heads.NONE,
                    self.sp_dd: active and screw and drive != heads.NONE}
            for sp, lbl in ((self.sp_hd, self.lbl_hd), (self.sp_hh, self.lbl_hh), (self.sp_ha, self.lbl_ha),
                            (self.sp_ds, self.lbl_ds), (self.sp_dd, self.lbl_dd)):
                sp.setVisible(show[sp])
                lbl.setVisible(show[sp])
                sp.setEnabled(o.HeadCustom)
            self.ck_hcustom.setVisible(active)
            self.sp_hd.setValue(o.HeadDiameter.Value)
            self.sp_hh.setValue(o.HeadHeight.Value)
            self.sp_ha.setValue(o.HeadAngle.Value)
            self.sp_ds.setValue(o.DriveSize.Value)
            self.sp_dd.setValue(o.DriveDepth.Value)
            if h and not info:
                if kind == "trou":
                    info = (tr("Lamage Ø %.2f × %.2f mm") % (h["diameter"], h["depth"]) if h["type"] == "lamage"
                            else tr("Fraisage Ø %.2f à %.0f°") % (h["diameter"], h["angle"]))
                    if h["type"] == "lamage":
                        info += tr(" — le filet commence sous le lamage")
                else:
                    info = tr("Tête %.2f × %.2f mm") % (h["size"], h["height"])
                    if h["drive_label"]:
                        info += tr(" — empreinte %s") % h["drive_label"]
                if not o.HeadCustom:
                    info += (tr(" (norme %s)") if o.Standard == "ISO" else tr(" (norme %s, en équivalence)")) % h["name"]
            self.lbl_head.setText(info)
            self.lbl_head.setStyleSheet("color:#b06000" if custom_std and cur != heads.NONE else "")
            if custom_std and cur == heads.NONE:
                self.lbl_head.setText(heads.NEED_STANDARD)
        finally:
            for wdg in widgets:
                wdg.blockSignals(False)

    def on_head(self, *_):
        if self._busy:
            return
        key = self.cb_head.currentData() or heads.NONE
        if self.kind() == "trou":
            enum_put(self.obj, "HoleHead", heads.HOLE_HEADS, key)
        else:
            enum_put(self.obj, "ScrewHead", heads.SCREW_HEAD_NAMES, key)
            if key in heads.SCREW_HEADS:                      # empreinte habituelle de cette tête
                enum_put(self.obj, "Drive", heads.DRIVES, heads.SCREW_HEADS[key][2])
        self.obj.HeadCustom = False
        self.refresh_head()
        self.schedule()

    def on_drive(self, *_):
        if self._busy:
            return
        drive = self.cb_drive.currentData()
        enum_put(self.obj, "Drive", heads.DRIVES, drive)
        screw = enum_get(self.obj, "ScrewHead", heads.SCREW_HEAD_NAMES)
        if self.obj.HeadCustom and screw in heads.SCREW_HEADS:   # cotes d'empreinte de la norme
            dd = heads.drive_default(drive, screw, feature.spec_of(self.obj).d,
                                     self.obj.HeadDiameter.Value, self.obj.HeadHeight.Value) if drive != heads.NONE else None
            self.obj.DriveSize, self.obj.DriveDepth = (dd["size"], dd["depth"]) if dd else (0.0, 0.0)
        self.refresh_head()
        self.schedule()

    def on_head_value(self, *_):
        if self._busy:
            return
        o = self.obj
        enum_put(o, "HeadPosition", heads.POSITIONS, self.cb_hpos.currentData())
        o.HeadCustom = self.ck_hcustom.isChecked()
        if o.HeadCustom:
            o.HeadDiameter, o.HeadHeight, o.HeadAngle = self.sp_hd.value(), self.sp_hh.value(), self.sp_ha.value()
            o.DriveSize, o.DriveDepth = self.sp_ds.value(), self.sp_dd.value()
        self.refresh_head()
        self.schedule()

    def head_shapes(self, p, info):
        """Tête de la fonction existante pour l'aperçu (lamage / fraisage ou tête de vis)."""
        spec = feature.spec_of(self.obj)
        h, msg = feature.head_of(self.obj, spec, p.kind, write=False)
        if not h:
            return [], msg
        base, direction = feature.head_frame(p, info, h)
        return [heads.solid(h, spec.d or 2 * p.R, p.kind, base, direction)], ""

    def update_info(self):
        o = self.obj
        self.update_turns()
        self.refresh_head()
        custom = o.Standard == "custom"
        self.ck_pitch.setEnabled(not custom)
        if custom:
            self.lbl_info.setText(tr("Filetage personnalisé"))
            self.sp_pitch.setEnabled(False)
            return
        try:
            spec = feature.spec_of(o)
            e = spec.entry()
            base_e = thread_data.get(o.Designation)
            self.ck_pitch.setEnabled(not base_e.taper)
            self.sp_pitch.setEnabled(self.ck_pitch.isChecked() and not base_e.taper)
            self.sp_pitch.blockSignals(True)
            self.sp_pitch.setValue(e.P)
            self.sp_pitch.blockSignals(False)
            txt = thread_data.describe(e)
            if spec.pitch_override:
                txt = tr("Pas personnalisé — ") + txt
            self.lbl_info.setText(txt)
        except (KeyError, NotThreadable):
            self.lbl_info.setText("")

    def update_turns(self):
        try:
            P = feature.spec_of(self.obj).lead
            n = self.obj.Depth.Value / P if P > 0 else 0
            self.lbl_turns.setText((tr("= %.2f filets (pas %.3g mm)") if n >= 2 else tr("= %.2f filet (pas %.3g mm)")) % (n, P))
        except Exception:
            self.lbl_turns.setText("")

    def on_pitch(self, *_):
        if self._busy:
            return
        try:
            base_p = thread_data.get(self.obj.Designation).P
        except KeyError:
            return
        self.obj.PitchOverride = self.sp_pitch.value() if self.ck_pitch.isChecked() else 0.0
        if not self.ck_pitch.isChecked():
            self.sp_pitch.blockSignals(True)
            self.sp_pitch.setValue(base_p)
            self.sp_pitch.blockSignals(False)
        self.update_info()
        self.schedule()

    # ------------------------------------------------------------------ événements
    def on_std(self, *_):
        if self._busy:
            return
        key = self.cb_std.currentData()
        if key == "custom":
            self.obj.Standard = "custom"
        self.update_visibility()
        self.fill_designations()
        self.schedule()

    def on_des(self, *_):
        if self._busy:
            return
        name = self.cb_des.currentData()
        if name and self.cb_std.currentData() != "custom":
            e = thread_data.get(name)
            if name != self.obj.Designation:
                self.obj.PitchOverride = 0.0                  # nouvelle taille : pas normalisé par défaut
                self.ck_pitch.blockSignals(True)
                self.ck_pitch.setChecked(False)
                self.ck_pitch.blockSignals(False)
            self.obj.Standard = e.standard
            self.obj.Designation = name
        self.update_info()
        self.schedule()

    def on_value(self, *_):
        if self._busy:
            return
        o = self.obj
        o.CustomDiameter = self.sp_cd.value()
        o.CustomPitch = self.sp_cp.value()
        o.CustomStarts = self.sp_cs.value()
        o.CustomFlankA = self.sp_ca.value()
        o.CustomFlankB = self.sp_cb.value()
        o.CustomDepth = self.sp_ch.value()
        o.CustomCrest = self.sp_cc.value()
        o.CustomTaper = self.ck_ct.isChecked()
        o.Depth = self.sp_depth.value()
        o.StartOffset = self.sp_offset.value()
        o.Clearance = self.sp_clr.value()
        o.LeftHanded = self.rb_left.isChecked()
        self.update_turns()
        self.schedule()

    def on_kind(self, *_):
        if self._busy or not self.info:
            return
        want = "trou" if self.rb_tap.isChecked() else "arbre"
        enum_put(self.obj, "Mode", feature.MODE_ENUM,
                 "Auto" if want == self.info["kind"] else ("Taraudage" if want == "trou" else "Filetage"))
        self.fill_designations()
        self.schedule()

    def on_op(self, *_):
        if self._busy:
            return
        was_creating = self.creating()
        enum_put(self.obj, "Operation", creation.OPERATIONS, self.cb_op.currentData())
        if self.creating() and not was_creating and not self.obj.Support and self.info:
            # face choisie (ou couture) sans appui : le trou / l'extrusion part du cercle du bout de départ
            link = feature.end_support(self.base, self.info, self.obj.Side)
            if link:
                self.obj.Support = link
        point_err = None
        if not self.creating() and was_creating and self.obj.Support:
            # appui ponctuel : la face à fileter vient de l'étude de la face de contact du point
            try:
                pf = feature.point_face(self.obj, self.base.Shape)
                if pf:
                    self.obj.FaceName, self.obj.HintRadius = pf[0], 0.0
                    self.reanalyse()
                    if self.info:
                        t = (pf[1] - self.info["center"]).dot(self.info["axis"])
                        near_low = abs(t - self.info["t_min"]) < abs(t - self.info["t_max"])
                        self.obj.Side = "low" if near_low else "high"
            except NotThreadable as e:
                point_err = str(e)
                self.obj.FaceName = ""                    # rien à fileter : pas de face prise ailleurs
                self.obj.HintRadius = 0.0
        if not self.creating() and not self.obj.FaceName and not point_err:
            try:
                self.auto_face()
            except NotThreadable as e:
                self.show_msg(str(e), "error")
        self.reanalyse()
        self.update_mode_ui()
        self.refresh_ref_fields()
        self.set_default_depth()
        self.fill_designations()
        self.schedule()

    def flip_support(self):
        self.obj.Reversed = not self.obj.Reversed
        self.set_default_depth()
        self.schedule()

    def on_full(self):
        av = self.available()
        if av > 0:
            self.sp_depth.setValue(av)

    def on_preview_toggle(self, on):
        if on:
            self.schedule()
        else:
            self.preview.clear_shapes()

    def flip_side(self):
        self.obj.Side = "low" if self.obj.Side == "high" else "high"
        self.refresh_ref_fields()
        self.set_default_depth()
        self.schedule()

    def clear_axis(self):
        self.obj.AxisReference = None
        self.reanalyse()
        self.load_from_obj()
        self.schedule()

    def clear_ref(self):
        self.obj.HeightReference = None
        self.refresh_ref_fields()
        self.set_default_depth()
        self.schedule()

    def set_default_depth(self):
        if self.creating() and feature.op(self.obj) != creation.OPERATIONS[1]:
            return                                             # extrusion : la longueur est libre
        av = self.available()
        if av > 0:
            self.sp_depth.setValue(builder.default_depth(av, self.cfg))

    # ------------------------------------------------------------------ préréglages
    def fill_presets(self):
        self.cb_preset.clear()
        self.cb_preset.addItem("—", None)
        for i, p in enumerate(thread_spec.presets_load(self.cfg)):
            self.cb_preset.addItem(p.name, i)

    def on_preset(self, idx):
        i = self.cb_preset.itemData(idx)
        if i is None:
            return
        p = thread_spec.presets_load(self.cfg)[i]
        self._busy = True
        self.sp_cd.setValue(p.d)
        self.sp_cp.setValue(p.pitch)
        self.sp_cs.setValue(p.starts)
        self.sp_ca.setValue(p.flank_a)
        self.sp_cb.setValue(p.flank_b)
        self.sp_ch.setValue(p.depth)
        self.sp_cc.setValue(p.crest)
        self.ck_ct.setChecked(p.taper)
        (self.rb_left if p.left_hand else self.rb_right).setChecked(True)
        self._busy = False
        self.on_value()

    def save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self.form, tr("Préréglage"), tr("Nom du préréglage :"))
        if not ok or not name.strip():
            return
        presets = [p for p in thread_spec.presets_load(self.cfg) if p.name != name.strip()]
        spec = feature.spec_of(self.obj) if self.obj.Standard == "custom" else None
        if spec is None:
            return
        spec.name = name.strip()
        presets.append(spec)
        thread_spec.presets_save(self.cfg, presets)
        self.fill_presets()

    def delete_preset(self):
        i = self.cb_preset.currentData()
        if i is None:
            return
        presets = thread_spec.presets_load(self.cfg)
        del presets[i]
        thread_spec.presets_save(self.cfg, presets)
        self.fill_presets()

    # ------------------------------------------------------------------ sélection 3D
    def set_sel_mode(self, mode):
        for b, m in ((self.btn_face, "face"), (self.btn_axis, "axis"), (self.btn_ref, "ref"),
                     (self.btn_sup, "support")):
            if m != mode and b.isChecked():
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
        self.sel_mode = mode
        Gui.Selection.clearSelection()
        if mode is None:                                       # sélection annulée : on remet les textes
            self.refresh_ref_fields()
            return
        for m, le, idle in (("support", self.lbl_sup, tr("Aucun appui sélectionné")),
                            ("face", self.lbl_face, tr("Aucune face sélectionnée")),
                            ("axis", self.lbl_axis, tr("Auto : axe de la face")),
                            ("ref", self.lbl_ref, self._ref_text() if self.info else "")):
            le.setPlaceholderText({"support": tr("Cliquez sur une esquisse, un point, un cercle ou une face plane"),
                                   "face": tr("Cliquez sur une face du modèle"),
                                   "axis": tr("Cliquez sur une arête, un cercle ou un axe"),
                                   "ref": tr("Cliquez sur une face plane ou un plan")}[m] if m == mode else idle)
            if m == mode:
                le.blockSignals(True)
                le.clear()
                le.blockSignals(False)
        if mode:
            self.show_msg({"support": tr("Clique une esquisse, un point, un cercle ou une face plane"),
                           "face": tr("Clique la face cylindrique à fileter"),
                           "axis": tr("Clique une arête droite, un cercle, une face plane ou un axe"),
                           "ref": tr("Clique un plan ou une face plane")}[mode], "info")

    def addSelection(self, doc, obj_name, sub, pnt):
        if not self.sel_mode or doc != self.doc.Name:
            return
        mode = self.sel_mode
        try:
            top = self.doc.getObject(obj_name)
            leaf_sub = sub.split(".")[-1] if sub else ""
            path = sub[:len(sub) - len(leaf_sub)]
            leaf = top.getSubObject(path, retType=1) if path else top
            if isinstance(leaf, tuple):
                leaf = leaf[0]
            if mode == "support":
                from .commands import external_point, point_binder
                if external_point(top, sub, self.body) is not None:     # point hors du corps : lien de forme
                    self.apply_support(point_binder(self.body, top, sub)[0], "", None)
                else:
                    if leaf.getParentGeoFeatureGroup() is not self.body:
                        raise NotThreadable(tr("L'appui doit être dans le corps actif (ou un point)"))
                    picked = to_local(Part.Vertex(App.Vector(*pnt)), self.body).Point if pnt else None
                    self.apply_support(leaf, leaf_sub, picked)
            elif mode == "face":
                if not leaf_sub.startswith("Face"):
                    raise NotThreadable(tr("Sélectionne une face"))
                self.apply_face(to_local(Part.getShape(top, sub, needSubElement=True), self.body))
            else:
                self.apply_link(mode, leaf, leaf_sub)
            self.refresh_ref_fields()
            self.fill_designations()
            self.show_msg("", "info")
        except NotThreadable as e:
            self.show_msg(str(e), "error")
        except Exception as e:
            self.show_msg(tr("Sélection non utilisable : %s") % e, "error")
        finally:
            self.sel_mode = None
            for b in (self.btn_face, self.btn_axis, self.btn_ref, self.btn_sup):
                b.blockSignals(True)
                b.setChecked(False)
                b.blockSignals(False)
            self.refresh_ref_fields()
            QtCore.QTimer.singleShot(0, Gui.Selection.clearSelection)
            self.schedule()

    def _default_side(self):
        e = self.info["ends"]
        if e["high"]["free"] or not e["low"]["free"]:
            return "high", e["high"]
        return "low", e["low"]

    # ------------------------------------------------------------------ aperçu
    def schedule(self):
        self.timer.start(max(50, self.cfg.preview_delay_ms))

    def show_msg(self, text, level="info"):
        color = {"error": "#c00000", "warn": "#b06000", "info": "#404040"}[level]
        self.lbl_msg.setText('<span style="color:%s">%s</span>' % (color, text) if text else "")

    def update_preview(self):
        if self.creating():
            return self.update_creation_preview()
        color = self.cfg.preview_color_tap if self.kind() == "trou" else self.cfg.preview_color_thread
        if self.info and self.cfg.show_axis:
            a, c = self.info["axis"], self.info["center"]
            ext = max(2.0, 0.2 * (self.info["t_max"] - self.info["t_min"]))
            self.preview.set_axis(c + a * (self.info["t_min"] - ext), c + a * (self.info["t_max"] + ext),
                                  color if self.cfg.axis_follow_type else self.cfg.axis_color, self.cfg.axis_width)
        else:
            self.preview.set_axis(None, None)
        if not self.info:
            self.preview.clear_shapes()
            self.preview.set_highlight([], 0)
            _field(self.lbl_len, "")
            self.show_msg(self.err or "", "error")
            self.set_ok_enabled(False)
            return
        self.set_ok_enabled(True)
        try:
            ctx = feature.context(self.obj, self.base.Shape, self.cfg)
            p, cut, add, cutters = builder.plan_shapes(self.base.Shape, ctx["info"], ctx["spec"], self.cfg,
                                                       **ctx["kw"])
            src = ctx.get("source")
            if p.length_source == "fonction" and src:
                _field(self.lbl_len, "%.2f mm  (%s.%s)" % (p.available, src["label"], src["prop"]))
            else:
                _field(self.lbl_len, tr("%.2f mm  (géométrie%s)") % (
                    p.available, tr(", %s.%s non coté") % (src["label"], src["prop"]) if src and src["length"] is None else ""))
            if self.cfg.show_start_face:
                self.preview.set_highlight(self.start_faces(), self.cfg.start_face_color)
            else:
                self.preview.set_highlight([], 0)
            msgs = list(p.messages)
            if ctx["info"].get("warning"):
                msgs.append(ctx["info"]["warning"])
            self.show_msg(" ; ".join(msgs), "warn")
            if self.ck_preview.isChecked():
                shape = self.base.Shape
                removed = []
                for x in (cut, p.entry):                  # matière réellement retirée (ajustement, entrée)
                    if x is not None:
                        try:
                            r = x.common(shape)
                            if r.Volume > 1e-6:
                                removed.append(r)
                        except Exception:
                            pass
                hs, _ = self.head_shapes(p, ctx["info"])
                self.preview.set_shapes([s for s in [add] + removed + cutters + hs if s is not None],
                                        color, self.cfg.preview_transparency)
            else:
                self.preview.clear_shapes()
        except NotThreadable as e:
            self.preview.clear_shapes()
            self.preview.set_highlight([], 0)
            self.show_msg(str(e), "error")
        except Exception as e:
            self.preview.clear_shapes()
            self.preview.set_highlight([], 0)
            self.show_msg(tr("Erreur : %s") % e, "error")

    def update_creation_preview(self):
        """Trou / extrusion : cylindres au Ø nominal (rouge / vert), axe et disques de départ (violet).

        Aucun booléen sur la pièce ici : seuls les contrôles « dans le vide » sont faits."""
        color = self.cfg.preview_color_tap if self.kind() == "trou" else self.cfg.preview_color_thread
        self.cplan = None
        try:
            if not self.anchor:
                raise NotThreadable(self.err or tr("Choisis un appui"))
            cc = feature.creation_context(self.obj, self.base.Shape, self.cfg)
            p = self.cplan = cc["plan"]
            if self.cfg.show_axis:
                c = p.centers[0]
                ext = max(2.0, 0.2 * p.L)
                self.preview.set_axis(c - p.dir * ext, c + p.dir * (p.L + ext),
                                      color if self.cfg.axis_follow_type else self.cfg.axis_color, self.cfg.axis_width)
            if p.hole:
                _field(self.lbl_len, tr("%.2f mm  (épaisseur de matière)") % p.thickness)
            else:
                _field(self.lbl_len, tr("%.2f mm  (longueur de l'extrusion)") % p.L)
            self.preview.set_highlight(self.start_faces() if self.cfg.show_start_face else [],
                                       self.cfg.start_face_color)
            if self.ck_preview.isChecked():
                hs = []
                h, _ = feature.head_of(self.obj, cc["spec"], p.kind, write=False)
                if h:
                    for c in p.centers:
                        base, direction = creation.head_frame(p, c, h)
                        hs.append(heads.solid(h, cc["spec"].d or 2 * p.r, p.kind, base, direction))
                self.preview.set_shapes(p.tools + hs, color, self.cfg.preview_transparency)
            else:
                self.preview.clear_shapes()
            self.show_msg(" ; ".join(p.messages), "warn")
            self.set_ok_enabled(True)
        except Exception as e:
            self.preview.set_axis(None, None)
            self.preview.clear_shapes()
            self.preview.set_highlight([], 0)
            _field(self.lbl_len, "")
            self.show_msg(str(e) if isinstance(e, NotThreadable) else tr("Erreur : %s") % e, "error")
            self.set_ok_enabled(False)

    def set_ok_enabled(self, on):
        """Bouton OK du dialogue Tâches (désactivé tant que l'appui est dans le vide)."""
        try:
            box = self.form.parent()
            while box is not None and not box.findChild(QDBB):
                box = box.parent()
            bb = box.findChild(QDBB) if box is not None else None
            if bb is not None and bb.button(QDBB.Ok):
                bb.button(QDBB.Ok).setEnabled(on)
        except Exception:
            pass

    # ------------------------------------------------------------------ fin
    def _cleanup(self):
        self.timer.stop()
        try:
            Gui.Selection.removeObserver(self)
        except Exception:
            pass
        self.preview.remove()

    def accept(self):
        self.on_value()
        if self.creating():
            try:
                feature.creation_context(self.obj, self.base.Shape, self.cfg)   # contrôle « dans le vide »
            except Exception as e:
                self.show_msg(str(e), "error")
                return False
        elif not self.info:
            self.show_msg(self.err or tr("Aucune face valide"), "error")
            return False
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self.obj.touch()
            self.doc.recompute()
            # bon type pour la Symétrie / les Répétitions (additive ou soustractive), d'après la matière
            # réellement ajoutée / enlevée par ce calcul : la fonction est recréée à sa place si besoin
            new = feature.ensure_type(self.obj)
            if new is not self.obj:
                self.obj = new
                self.obj.touch()
                self.doc.recompute()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if not self.obj.isValid():
            self.show_msg(tr("Le calcul a échoué : %s") % self.obj.getStatusString(), "error")
            return False
        self._cleanup()
        self.doc.commitTransaction()
        if self.obj.ViewObject:
            self.obj.ViewObject.show()
        if self.base and self.base.ViewObject:
            self.base.ViewObject.hide()
        sup = self.obj.Support
        if self.creating() and sup and sup[0].isDerivedFrom("Sketcher::SketchObject") and sup[0].ViewObject:
            sup[0].ViewObject.hide()                         # comme une Poche : l'esquisse est consommée
        if not self.new:
            Gui.ActiveDocument.resetEdit()
        return True

    def restore_selection(self):
        """Annuler ne perd pas la sélection de départ : on peut relancer l'outil aussitôt."""
        for doc, name, sub in self.restore:
            try:
                Gui.Selection.addSelection(doc, name, sub)
            except Exception:
                pass

    def reject(self):
        self._cleanup()
        self.doc.abortTransaction()
        if not self.new:
            Gui.ActiveDocument.resetEdit()
        try:
            if self.obj.ViewObject:
                self.obj.ViewObject.show()
            if self.base and self.base.ViewObject:
                self.base.ViewObject.hide()
        except Exception:
            # la fonction a été supprimée par l'annulation : on réaffiche la précédente
            if self.base and self.base.ViewObject:
                self.base.ViewObject.show()
        self.doc.recompute()
        QtCore.QTimer.singleShot(0, self.restore_selection)
        return True
