# Installe ThreadTool dans FreeCAD 1.1 (Windows), équivalent de install.sh.
#   .\install.ps1          -> jonction (les modifications du dossier sont prises en compte directement)
#   .\install.ps1 -Copy    -> copie du dossier
#   .\install.ps1 -Remove  -> désinstallation
# Si PowerShell refuse de lancer le script :
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
param([switch]$Copy, [switch]$Remove)
$ErrorActionPreference = "Stop"

$Src = $PSScriptRoot
$Mod = if ($env:FREECAD_MOD_DIR) { $env:FREECAD_MOD_DIR } else { Join-Path $env:APPDATA "FreeCAD\v1-1\Mod" }
$Dest = Join-Path $Mod "ThreadTool"

function Remove-Dest {
    if (-not (Test-Path -LiteralPath $Dest)) { return }
    $item = Get-Item -LiteralPath $Dest -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        # Jonction : on supprime le lien seulement, jamais le dossier de travail.
        [IO.Directory]::Delete($Dest)
    } else {
        Remove-Item -LiteralPath $Dest -Recurse -Force
    }
}

if ($Remove) {
    Remove-Dest
    Write-Host "ThreadTool désinstallé ($Dest supprimé)."
    exit 0
}

if ((Resolve-Path -LiteralPath $Src).Path -eq $Dest) {
    Write-Host "Ce dossier est déjà le dossier d'installation : $Dest"
    exit 0
}

New-Item -ItemType Directory -Force -Path $Mod | Out-Null
if (Test-Path -LiteralPath $Dest) {
    Write-Host "Une version existe déjà dans $Dest : remplacement."
    Remove-Dest
}
if ($Copy) {
    New-Item -ItemType Directory -Path $Dest | Out-Null
    Get-ChildItem -LiteralPath $Src -Force |
        Where-Object { $_.Name -notin @("dist", ".git", "__pycache__") } |
        Copy-Item -Destination $Dest -Recurse -Force
    Get-ChildItem -LiteralPath $Dest -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Write-Host "ThreadTool copié dans $Dest"
} else {
    New-Item -ItemType Junction -Path $Dest -Target $Src | Out-Null
    Write-Host "Jonction créée : $Dest -> $Src"
}
Write-Host "Redémarre FreeCAD, puis ouvre l'atelier Part Design."
