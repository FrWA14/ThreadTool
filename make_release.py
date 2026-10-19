"""Fabrique dist/ThreadTool-<version>.zip (Windows, Linux, macOS) : python3 make_release.py

Contenu de l'archive :
  ThreadTool/                    le module (à copier dans le dossier Mod de FreeCAD)
  Installer_ThreadTool.FCMacro   macro qui fait la copie toute seule
  LISEZMOI.txt                   instructions courtes
"""
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {"__pycache__", ".git", "dist"}
EXCLUDE_EXT = {".pyc", ".FCStd1"}

README = """ThreadTool {v} — filetage / taraudage pour FreeCAD Part Design (FreeCAD 1.0 ou plus récent)

INSTALLATION (Windows, Linux, macOS)

Méthode 1 : macro (la plus simple)
  1. Décompresse cette archive n'importe où.
  2. Dans FreeCAD : Fichier > Ouvrir... et choisis Installer_ThreadTool.FCMacro
     (elle s'ouvre dans l'éditeur de macro).
  3. Clique sur « Exécuter la macro » (triangle vert ▶ dans la barre Macro, ou Macro > Exécuter la macro).
  4. Redémarre FreeCAD.

Méthode 2 : copie à la main
  1. Dans FreeCAD, ouvre la console Python (Affichage > Panneaux > Console Python) et tape :
        App.getUserAppDataDir()
     Le dossier affiché contient (ou doit contenir) un sous-dossier « Mod ».
       Windows : C:\\Users\\<nom>\\AppData\\Roaming\\FreeCAD\\v1-1\\Mod
       Linux   : ~/.local/share/FreeCAD/v1-1/Mod
  2. Copie le dossier « ThreadTool » de cette archive dans « Mod » (crée « Mod » s'il n'existe pas).
  3. Redémarre FreeCAD.

UTILISATION
  Atelier Part Design : l'icône « Filetage / taraudage » est juste à côté de « Perçage ».
  Préférences : Édition > Préférences > Part/Part Design > Filetage.
  Détails : ThreadTool/README.md

DÉSINSTALLATION
  Supprime le dossier Mod/ThreadTool, ou utilise le gestionnaire d'extensions s'il a servi à l'installer.
"""


def version():
    with open(os.path.join(HERE, "package.xml"), encoding="utf-8") as f:
        return re.search(r"<version>([^<]+)</version>", f.read()).group(1)


def main():
    v = version()
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "ThreadTool-%s.zip" % v)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(HERE):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
            for f in sorted(files):
                if os.path.splitext(f)[1] in EXCLUDE_EXT:
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, HERE)
                z.write(full, "ThreadTool/" + rel.replace(os.sep, "/"))
        z.write(os.path.join(HERE, "Installer_ThreadTool.FCMacro"), "Installer_ThreadTool.FCMacro")
        z.writestr("LISEZMOI.txt", README.format(v=v).replace("\n", "\r\n"))
    print(out)


if __name__ == "__main__":
    main()
