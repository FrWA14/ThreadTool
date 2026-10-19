# ThreadTool : filetage / taraudage automatique pour PartDesign.
# Ajoute la commande « Filetage / taraudage » à côté de « Perçage » dans PartDesign,
# et une page « Filetage » dans Édition → Préférences → Part/Part Design.
# (FreeCAD exécute ce fichier de façon particulière : tout est fait dans le module threadtool.)

try:
    import threadtool.commands
    threadtool.commands.setup_gui()
except Exception as e:
    import FreeCAD
    FreeCAD.Console.PrintError("ThreadTool : échec du chargement / loading failed : %s\n" % e)
