"""Affichage temporaire (Coin3D) : axe détecté et aperçu vert transparent. Rien n'est ajouté au document."""
import FreeCAD as App
import FreeCADGui as Gui
from pivy import coin


def _rgb(color):
    return ((color >> 16) & 255) / 255.0, ((color >> 8) & 255) / 255.0, (color & 255) / 255.0


class Preview:
    def __init__(self, placement=None):
        self.view = Gui.ActiveDocument.ActiveView if Gui.ActiveDocument else None
        self.root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style = coin.SoPickStyle.UNPICKABLE                 # ne gêne pas la sélection
        self.root.addChild(pick)
        self.xf = coin.SoTransform()
        self.root.addChild(self.xf)
        self.axis_sep = coin.SoSeparator()
        self.shape_sep = coin.SoSeparator()
        self.hl_sep = coin.SoSeparator()
        self.root.addChild(self.axis_sep)
        self.root.addChild(self.shape_sep)
        self.root.addChild(self.hl_sep)
        self.set_placement(placement or App.Placement())
        self.sg = None
        if self.view is not None:
            try:
                self.sg = self.view.getSceneGraph()
                self.sg.addChild(self.root)
            except Exception:
                self.sg = None

    def set_placement(self, pl):
        """Placement global du corps (les formes sont exprimées dans son repère)."""
        self.xf.translation.setValue(pl.Base.x, pl.Base.y, pl.Base.z)
        q = pl.Rotation.Q
        self.xf.rotation.setValue(q[0], q[1], q[2], q[3])

    def set_axis(self, p1, p2, color=0xFF8000, width=2):
        """Axe en trait mixte (ligne de construction), couleur indépendante des réglages de FreeCAD."""
        self.axis_sep.removeAllChildren()
        if p1 is None:
            return
        ds = coin.SoDrawStyle()
        ds.lineWidth = width
        ds.linePattern = 0xFF18                               # trait long – point (axe)
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR            # pas d'ombrage : couleur exacte
        col = coin.SoBaseColor()
        col.rgb = _rgb(color)
        self.axis_sep.addChild(light)
        try:                                                  # visible à travers la pièce
            db = coin.SoDepthBuffer()
            db.test = False
            db.write = False                                  # ne masque pas la face de début
            self.axis_sep.addChild(db)
        except AttributeError:
            pass
        co = coin.SoCoordinate3()
        co.point.setValues(0, 2, [[p1.x, p1.y, p1.z], [p2.x, p2.y, p2.z]])
        ls = coin.SoLineSet()
        ls.numVertices.setValue(2)
        for n in (ds, col, co, ls):
            self.axis_sep.addChild(n)

    def set_shapes(self, shapes, color=0x33CC33, transparency=60, deflection=0.05):
        self.shape_sep.removeAllChildren()
        if not shapes:
            return
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        hints.shapeType = coin.SoShapeHints.UNKNOWN_SHAPE_TYPE
        mat = coin.SoMaterial()
        mat.diffuseColor = _rgb(color)
        mat.emissiveColor = tuple(0.3 * x for x in _rgb(color))
        mat.transparency = max(0, min(95, transparency)) / 100.0
        self.shape_sep.addChild(hints)
        self.shape_sep.addChild(mat)
        try:                                                  # visible à travers la pièce (taraudage)
            db = coin.SoDepthBuffer()
            db.test = False
            db.write = False                                  # ne masque pas la face de début
            self.shape_sep.addChild(db)
        except AttributeError:
            pass
        for sh in shapes:
            if sh is None or sh.isNull():
                continue
            try:
                pts, tris = sh.tessellate(deflection)
            except Exception:
                continue
            if not tris:
                continue
            co = coin.SoCoordinate3()
            co.point.setValues(0, len(pts), [[p.x, p.y, p.z] for p in pts])
            idx = []
            for t in tris:
                idx += [t[0], t[1], t[2], -1]
            fs = coin.SoIndexedFaceSet()
            fs.coordIndex.setValues(0, len(idx), idx)
            sep = coin.SoSeparator()
            sep.addChild(co)
            sep.addChild(fs)
            self.shape_sep.addChild(sep)

    def set_highlight(self, faces, color=0x9933CC, deflection=0.05):
        """Surligne les faces de début du filet (légèrement en avant des faces de la pièce)."""
        self.hl_sep.removeAllChildren()
        if not faces:
            return
        light = coin.SoLightModel()
        light.model = coin.SoLightModel.BASE_COLOR
        col = coin.SoMaterial()
        col.diffuseColor = _rgb(color)
        col.transparency = 0.05        # passe « transparente » de Coin : dessiné après l'aperçu vert / rouge
        hints = coin.SoShapeHints()
        hints.vertexOrdering = coin.SoShapeHints.UNKNOWN_ORDERING
        off = coin.SoPolygonOffset()                          # devant la face de la pièce (pas de scintillement)
        off.factor = -2.0
        off.units = -2.0
        for n in (light, col, hints, off):
            self.hl_sep.addChild(n)
        for f in faces:
            try:
                pts, tris = f.tessellate(deflection)
            except Exception:
                continue
            if not tris:
                continue
            co = coin.SoCoordinate3()
            co.point.setValues(0, len(pts), [[q.x, q.y, q.z] for q in pts])
            idx = []
            for t in tris:
                idx += [t[0], t[1], t[2], -1]
            fs = coin.SoIndexedFaceSet()
            fs.coordIndex.setValues(0, len(idx), idx)
            sep = coin.SoSeparator()
            sep.addChild(co)
            sep.addChild(fs)
            self.hl_sep.addChild(sep)

    def clear_shapes(self):
        self.shape_sep.removeAllChildren()

    def remove(self):
        if self.sg is not None:
            try:
                self.sg.removeChild(self.root)
            except Exception:
                pass
        self.sg = None
