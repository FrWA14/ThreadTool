"""Langues de l'interface (freecadcmd tests/test_i18n.py) : choix du fichier, anglais, listes des propriétés.

1. choix de la langue : fr, fr-CA -> textes du code ; en, es-AR (pas de fichier) -> anglais ;
   nouveau fichier zz.json découvert automatiquement, zz-YY -> zz ;
2. fichiers de traduction complets, avec les mêmes %s / %d que le français ;
3. en anglais : messages, listes des propriétés traduites, valeurs françaises pour le code, calcul valide ;
4. document enregistré en anglais, rouvert en français : listes converties, choix conservés."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.dirname(HERE))
os.environ["THREADTOOL_LANG"] = "en"

import FreeCAD as App
import Part
from threadtool import i18n

FAILS = []
V = App.Vector


def log(*a):
    print(*a)
    sys.stdout.flush()


def check(cond, msg):
    log(("  ok   " if cond else "  ÉCHEC ") + msg)
    if not cond:
        FAILS.append(msg)


# ------------------------------------------------------------ 1. choix de la langue
check(i18n.LANG == "en", "THREADTOOL_LANG=en -> anglais (%s)" % i18n.LANG)
check(i18n.resolve("fr") == "fr" and i18n.resolve("fr-CA") == "fr", "fr, fr-CA -> textes du code")
check(i18n.resolve("es-AR") == "en", "es-AR sans fichier -> anglais")
check(i18n.resolve("en-GB") == "en", "en-GB -> en")
zz = os.path.join(i18n.HERE, "translations", "zz.json")
try:
    with open(zz, "w", encoding="utf-8") as f:
        json.dump({"_language": "Test", "Filetage": "ZZ-Thread"}, f)
    check("zz" in i18n.available(), "nouveau fichier zz.json découvert")
    check(i18n.resolve("zz-YY") == "zz", "zz-YY -> zz.json")
    i18n.load("zz")
    check(i18n.tr("Filetage") == "ZZ-Thread", "texte traduit par zz.json")
    check(i18n.tr("Pas") == "Pitch", "texte absent de zz.json -> anglais")
    check(i18n.language_name("zz") == "Test", "nom de la langue lu dans le fichier")
finally:
    os.remove(zz)
i18n.load("fr")
check(i18n.tr("Pas") == "Pas", "français : texte du code")
i18n.load("en")

# ------------------------------------------------------------ 2. fichiers complets
sys.path.insert(0, os.path.join(i18n.HERE, "translations"))
import update                                                    # translations/update.py
texts = update.source_texts()
for name in sorted(os.listdir(os.path.join(i18n.HERE, "translations"))):
    if name.endswith(".json"):
        with open(os.path.join(i18n.HERE, "translations", name), encoding="utf-8") as f:
            data = json.load(f)
        missing = [t for t in texts if not data.get(t)]
        wrong = [t for t in texts if data.get(t) and update.formats(t) != update.formats(data[t])]
        check(not missing and not wrong, "%s : %d manquants, %d %%… différents %s" % (name, len(missing), len(wrong),
                                                                                      (missing + wrong)[:3]))

# ------------------------------------------------------------ 3. en anglais
from threadtool import feature, creation, heads

check(creation.VOID_HOLE == "Cannot remove material from empty space", "message traduit : %s" % creation.VOID_HOLE)
doc = App.newDocument("I18N")
body = doc.addObject("PartDesign::Body", "Body")
box = body.newObject("PartDesign::AdditiveBox", "Bloc")
box.Length, box.Width, box.Height = 30, 30, 20
sk = body.newObject("Sketcher::SketchObject", "Sk")
sk.AttachmentSupport = [([o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
sk.MapMode = "FlatFace"
sk.AttachmentOffset = App.Placement(V(0, 0, 20), App.Rotation())
sk.addGeometry(Part.Circle(V(10, 10, 0), V(0, 0, 1), 2.5))
doc.recompute()
t = feature.create(body, "T", creation.OPERATIONS[1])
t.Support = (sk, [])
t.Standard, t.Designation, t.Depth = "ISO", "M5", 10
i18n.enum_put(t, "HoleHead", heads.HOLE_HEADS, "ISO 4762")
doc.recompute()
check(t.Label == "Thread", "nom de la fonction : %s" % t.Label)
check(t.getEnumerationsOfProperty("Operation") == ["Existing", "Tapped hole", "Threaded pad"],
      "liste Operation : %s" % t.getEnumerationsOfProperty("Operation"))
check(t.Operation == "Tapped hole" and feature.op(t) == creation.OPERATIONS[1], "valeur affichée / valeur du code")
check(t.getEnumerationsOfProperty("HoleHead")[0] == "None", "Aucune -> None")
check(t.getGroupOfProperty("Depth") == "Thread" and t.getGroupOfProperty("HoleHead") == "Head",
      "groupes : %s, %s" % (t.getGroupOfProperty("Depth"), t.getGroupOfProperty("HoleHead")))
check(t.getDocumentationOfProperty("Depth") == "Threaded length", "bulle d'aide : %s" % t.getDocumentationOfProperty("Depth"))
check(t.isValid() and len(t.Shape.Solids) == 1, "trou taraudé M5 + lamage en anglais : valide (%s)" % t.getStatusString())
check(t.DetectedKind == "hole", "type détecté : %s" % t.DetectedKind)
bad = feature.create(body, "Bad", creation.OPERATIONS[1])
bad.Support = (sk, [])
bad.Standard, bad.Designation = "ISO", "M99"
try:
    feature.spec_of(bad)
    got = ""
except Exception as e:
    got = str(e)
check(got == "Unknown designation: M99", "erreur en anglais : « %s »" % got)
doc.removeObject(bad.Name)
doc.recompute()

# ------------------------------------------------------------ 4. rouvert en français
path = os.path.join(tempfile.gettempdir(), "threadtool_i18n.FCStd")
doc.saveAs(path)
App.closeDocument(doc.Name)
i18n.load("fr")
doc = App.openDocument(path)
t = doc.getObject("T")
check(t.getEnumerationsOfProperty("Operation") == creation.OPERATIONS, "liste Operation en français : %s"
      % t.getEnumerationsOfProperty("Operation"))
check(t.Operation == "Trou taraudé" and t.HoleHead == "ISO 4762", "choix conservés : %s, %s" % (t.Operation, t.HoleHead))
check(t.getGroupOfProperty("Depth") == "Filetage", "groupe en français : %s" % t.getGroupOfProperty("Depth"))
t.touch()
doc.recompute()
check(t.isValid(), "recalcul après changement de langue : valide (%s)" % t.getStatusString())
App.closeDocument(doc.Name)
os.remove(path)

log("\nLANGUES : %s" % ("RÉUSSI" if not FAILS else "%d échec(s)" % len(FAILS)))
