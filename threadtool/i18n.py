"""Traduction de l'interface selon la langue de FreeCAD.

Les textes du code sont écrits en français : ils servent de clés. Une traduction est un fichier JSON
« <code>.json » (code de langue de FreeCAD : en, de, es-ES, ja, zh-CN…) qui associe chaque texte français
à sa traduction. Les fichiers sont cherchés au démarrage dans :
  - <dossier de données de FreeCAD>/ThreadTool/translations  (traductions personnelles, gardées lors des mises à jour)
  - ThreadTool/translations                                   (traductions fournies avec le module)

Choix de la langue : variable d'environnement THREADTOOL_LANG, sinon préférence « Langue » de ThreadTool,
sinon langue de FreeCAD. Français -> textes du code ; autre langue -> son fichier s'il existe
(es-AR, puis es), sinon anglais. Un texte absent du fichier choisi est pris en anglais, puis en français."""
import json
import os

import FreeCAD as App

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARAM = "User parameter:BaseApp/Preferences/Mod/ThreadTool"
SOURCE = "fr"
FALLBACK = "en"

# Noms de langue de FreeCAD (préférence Général > Langue) -> code, quand FreeCADGui n'est pas disponible.
_NAMES = {
    "English": "en", "Afrikaans": "af", "Arabic": "ar", "Basque": "eu", "Belarusian": "be", "Bulgarian": "bg",
    "Catalan": "ca", "Chinese (Simplified)": "zh-CN", "Chinese (Traditional)": "zh-TW", "Croatian": "hr",
    "Czech": "cs", "Danish": "da", "Dutch": "nl", "Filipino": "fil", "Finnish": "fi", "French": "fr",
    "Galician": "gl", "Georgian": "ka", "German": "de", "Greek": "el", "Hungarian": "hu", "Indonesian": "id",
    "Italian": "it", "Japanese": "ja", "Kabyle": "kab", "Korean": "ko", "Lithuanian": "lt", "Malay": "ms",
    "Norwegian": "no", "Polish": "pl", "Portuguese": "pt-PT", "Portuguese (Brazilian)": "pt-BR",
    "Romanian": "ro", "Russian": "ru", "Serbian": "sr", "Serbian (Latin)": "sr-CS", "Slovak": "sk",
    "Slovenian": "sl", "Spanish": "es-ES", "Spanish (Argentina)": "es-AR", "Swedish": "sv-SE", "Turkish": "tr",
    "Ukrainian": "uk", "Valencian": "val-ES", "Vietnamese": "vi"}


def folders():
    """Dossiers de traductions, du plus prioritaire au moins prioritaire."""
    out = []
    try:
        out.append(os.path.join(App.getUserAppDataDir(), "ThreadTool", "translations"))
    except Exception:
        pass
    out.append(os.path.join(HERE, "translations"))
    return out


def available():
    """{code: fichier} de toutes les traductions trouvées (la plus prioritaire pour un même code)."""
    found = {}
    for d in reversed(folders()):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.endswith(".json"):
                found[n[:-5]] = os.path.join(d, n)
    return found


def language_name(code):
    """Nom de la langue d'un fichier (champ « _language »), sinon son code."""
    path = available().get(code)
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f).get("_language", code)
        except Exception:
            pass
    return {"fr": "Français", "en": "English"}.get(code, code)


def freecad_language():
    """Code de la langue de l'interface de FreeCAD (en, fr, es-ES, zh-CN…)."""
    name = ""
    try:
        import FreeCADGui
        name = FreeCADGui.getLocale()
        code = FreeCADGui.supportedLocales().get(name)
        if code:
            return code
    except Exception:
        pass
    if not name:
        name = App.ParamGet("User parameter:BaseApp/Preferences/General").GetString("Language")
    if name in _NAMES:
        return _NAMES[name]
    try:                                       # langue « du système » : celle de Qt, sinon celle de Python
        from PySide import QtCore
        sys_name = QtCore.QLocale().name()
    except Exception:
        import locale
        sys_name = locale.getlocale()[0] or ""
    return sys_name.replace("_", "-") or FALLBACK


def wanted():
    """Code de langue demandé : THREADTOOL_LANG, préférence de ThreadTool, sinon langue de FreeCAD."""
    env = os.environ.get("THREADTOOL_LANG", "").strip()
    if env:
        return env
    pref = App.ParamGet(PARAM).GetString("Language", "auto").strip()
    if pref and pref.lower() != "auto":
        return pref
    return freecad_language()


def _candidates(code):
    code = code.replace("_", "-")
    out = [code]
    if "-" in code:
        out.append(code.split("-")[0])
    return out


def resolve(code):
    """Code effectivement utilisé : « fr » (textes du code) ou le code d'un fichier trouvé ; sinon « en »."""
    files = available()
    for c in _candidates(code):
        if c.lower() == SOURCE:
            return SOURCE
        for k in files:
            if k.lower() == c.lower():
                return k
    return FALLBACK


def _load(code):
    path = available().get(code)
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        App.Console.PrintWarning("ThreadTool : traduction %s illisible (%s)\n" % (path, e))
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str) and v}


LANG = SOURCE
_TABLE = {}


def load(code=None):
    """Charge la langue (au démarrage du module ; à nouveau si la préférence change)."""
    global LANG, _TABLE
    LANG = resolve(code or wanted())
    _TABLE = {}
    if LANG != SOURCE:
        if LANG != FALLBACK:
            _TABLE.update(_load(FALLBACK))
        _TABLE.update(_load(LANG))
    return LANG


def tr(text):
    """Texte dans la langue choisie (le texte français tel quel s'il n'a pas de traduction)."""
    return _TABLE.get(text, text) if _TABLE else text


def N_(text):
    """Marque un texte à traduire plus tard (avec tr) : le texte lui-même."""
    return text


def untr(text):
    """Texte français d'un texte traduit (pour les valeurs de listes), ou le texte lui-même."""
    if not _TABLE:
        return text
    for k, v in _TABLE.items():
        if v == text:
            return k
    return text


# ----------------------------------------------------------------------- listes des propriétés
# Les propriétés « Enumeration » affichent la liste dans la langue de l'utilisateur ; le code travaille
# toujours avec les valeurs françaises (canon), retrouvées par leur position dans la liste.

def enum_set_list(obj, name, canon):
    """Met la liste traduite de la propriété en gardant la position choisie (document d'une autre langue)."""
    shown = [tr(v) for v in canon]
    cur = obj.getEnumerationsOfProperty(name) or []
    if cur == shown:
        return
    val = getattr(obj, name) if cur else None
    idx = cur.index(val) if val in cur else 0
    if val is not None and val not in shown:
        c = untr(val)
        idx = canon.index(c) if c in canon else (idx if idx < len(canon) else 0)
    setattr(obj, name, shown)
    setattr(obj, name, shown[idx])


def enum_get(obj, name, canon):
    """Valeur française (canon) de la propriété."""
    val = getattr(obj, name)
    if val in canon:
        return val
    cur = obj.getEnumerationsOfProperty(name) or []
    if val in cur and cur.index(val) < len(canon) and len(cur) == len(canon):
        return canon[cur.index(val)]
    c = untr(val)
    return c if c in canon else canon[0]


def enum_put(obj, name, canon, value):
    """Choisit la valeur française value (ou déjà traduite) dans la propriété."""
    shown = obj.getEnumerationsOfProperty(name) or []
    if value in canon and len(shown) == len(canon):
        setattr(obj, name, shown[canon.index(value)])
    else:
        setattr(obj, name, value)


load()
