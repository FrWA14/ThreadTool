"""Crée ou met à jour un fichier de traduction de ThreadTool.

    python3 translations/update.py ja          -> crée / complète translations/ja.json
    python3 translations/update.py <chemin>/ja.json  -> complète un fichier rangé ailleurs
    python3 translations/update.py --check     -> vérifie tous les fichiers (textes manquants, %s / %d…)

Les textes à traduire sont les textes français passés à tr(…) ou N_(…) dans threadtool/*.py.
Un texte nouveau est ajouté avec une valeur vide (à traduire) ; un texte qui n'existe plus est retiré.
Les traductions déjà faites sont conservées. Python 3 suffit (FreeCAD n'est pas nécessaire)."""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "threadtool")
FORMAT = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[sdfgeEx%]")


def source_texts():
    """{texte français: [fichier:ligne, …]} de tous les appels tr("…") / N_("…")."""
    out = {}
    for name in sorted(os.listdir(SRC)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(SRC, name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("tr", "N_") and n.args \
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out.setdefault(n.args[0].value, []).append("%s:%d" % (name, n.lineno))
    return out


def formats(text):
    return sorted(FORMAT.findall(text))


def update(code):
    path = code if code.endswith(".json") else os.path.join(HERE, code + ".json")
    code = os.path.basename(path)[:-5]
    old = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    texts = source_texts()
    data = {"_language": old.get("_language", code),
            "_note": old.get("_note", "Clé = texte français de ThreadTool ; valeur = traduction (vide = pas encore "
                                      "traduit). Garder les %s, %d, %.2f… dans le même ordre, et les \\n.")}
    missing = 0
    for t in texts:
        data[t] = old.get(t, "")
        missing += not data[t]
    removed = [k for k in old if not k.startswith("_") and k not in texts]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("%s : %d textes, %d à traduire, %d retirés" % (path, len(texts), missing, len(removed)))


def check():
    texts = source_texts()
    bad = 0
    for name in sorted(os.listdir(HERE)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            data = json.load(f)
        keys = {k for k in data if not k.startswith("_")}
        missing = [t for t in texts if not data.get(t)]
        unknown = sorted(keys - set(texts))
        wrong = [k for k in keys & set(texts) if data[k] and formats(k) != formats(data[k])]
        print("%s : %d manquants, %d inconnus, %d avec des %%… différents" % (name, len(missing), len(unknown), len(wrong)))
        for k in wrong:
            print("   %%… différents : %r -> %r" % (k, data[k]))
        bad += len(wrong)
    return bad


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
    elif args[0] == "--check":
        sys.exit(1 if check() else 0)
    else:
        for code in args:
            update(code)
