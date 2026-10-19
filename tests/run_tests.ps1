# Lance les tests de ThreadTool sous Windows.
#   .\run_tests.ps1               -> tous les tests sans interface (freecadcmd)
#   .\run_tests.ps1 -Gui          -> aussi les tests d'interface (ouvrent FreeCAD, captures dans %TEMP%)
#   .\run_tests.ps1 test_heads    -> seulement les fichiers nommés
# Autre installation de FreeCAD : variable FREECAD_BIN (dossier contenant freecad.exe).
# Si PowerShell refuse de lancer le script :
#   powershell -ExecutionPolicy Bypass -File .\run_tests.ps1
param([switch]$Gui, [Parameter(ValueFromRemainingArguments)][string[]]$Only)

$Bin = if ($env:FREECAD_BIN) { $env:FREECAD_BIN } else { "C:\Program Files\FreeCAD 1.1\bin" }
$Cmd = Join-Path $Bin "freecadcmd.exe"
$Fc = Join-Path $Bin "freecad.exe"
# freecadcmd écrit en cp1252 sous Windows : on le lit dans ce codage pour garder les accents.
[Console]::OutputEncoding = [Text.Encoding]::GetEncoding(1252)
Set-Location $PSScriptRoot
# Les tests vérifient les messages en français, quelle que soit la langue de FreeCAD.
if (-not $env:THREADTOOL_LANG) { $env:THREADTOOL_LANG = "fr" }

$headlessTests = "run_tests", "test_feature", "test_exercise", "test_creation", "test_offset", "test_heads", "test_transform"
$guiTests = "gui_test", "gui_exercise", "gui_creation", "gui_offset", "gui_heads", "gui_support"
$todo = if ($Only) { $Only } elseif ($Gui) { $headlessTests + $guiTests } else { $headlessTests }

$failed = @()
foreach ($t in $todo) {
    Write-Host "=== $t" -ForegroundColor Cyan
    $start = Get-Date
    if ($t -like "gui_*") {
        # Les tests d'interface écrivent leur journal et leurs captures dans THREADTOOL_GUI_OUT (%TEMP% par défaut).
        $p = Start-Process -FilePath $Fc -ArgumentList "$t.py" -Wait -PassThru
        $dir = if ($env:THREADTOOL_GUI_OUT) { $env:THREADTOOL_GUI_OUT } else { $env:TEMP }
        $log = Join-Path $dir "$t.log"
        $bad = -not (Test-Path $log) -or (Select-String -Path $log -Encoding UTF8 -Pattern "ÉCHEC|EXCEPTION" -Quiet) -or
               -not (Select-String -Path $log -Encoding UTF8 -Pattern "^FIN" -Quiet)
        if ($bad) {
            Select-String -Path $log -Encoding UTF8 -Pattern "ÉCHEC|EXCEPTION" -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_.Line }
            $p = @{ ExitCode = 1 }
        }
    } else {
        # freecadcmd renvoie 0 même si le script échoue : on lit aussi sa sortie
        # (« ÉCHEC », « n échec(s) », exception non rattrapée ; pas « Traceback » : FreeCAD en écrit pour
        # chaque recalcul refusé, même attendu ; motifs sans accent, la console n'est pas en UTF-8).
        $out = & $Cmd "$t.py" 2>&1 | Where-Object { $_ -notmatch "^\s*(\(\d+ %\)\s*)*$|^Recompute" } | Tee-Object -Variable lines
        $out | Write-Host
        $bad = ($lines -match "CHEC |chec\(s\)|Exception while processing").Count -gt 0
        $p = @{ ExitCode = $(if ($bad) { 1 } else { $LASTEXITCODE }) }
    }
    $s = [int]((Get-Date) - $start).TotalSeconds
    if ($p.ExitCode -ne 0) { $failed += $t; Write-Host "ÉCHEC $t (code $($p.ExitCode), $s s)" -ForegroundColor Red }
    else { Write-Host "ok $t ($s s)" -ForegroundColor Green }
}
if ($failed) { Write-Host "Échecs : $($failed -join ', ')" -ForegroundColor Red; exit 1 }
Write-Host "Tous les tests sont réussis." -ForegroundColor Green
