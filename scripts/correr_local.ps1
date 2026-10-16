# Corrida local diaria (PC de Daniel). La lanza el Programador de tareas de Windows.
#   -Pasada 1: diaria. -Pasada 2: sólo tiene efecto del 10 al 20 de noviembre.
# 1) trae lo que subió GitHub Actions, 2) corre las fuentes del entorno local (Amazon) y reintenta las que
# GitHub no logró hoy, 3) sube los datos nuevos. Idempotente: correrla dos veces el mismo día no duplica.
param([int]$Pasada = 1)
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $raiz
$py = Join-Path $raiz '.venv\Scripts\python.exe'
$hoy = Get-Date -Format 'yyyy-MM-dd'
$log = Join-Path $raiz "logs\correr_local_$hoy.log"
"=== $(Get-Date -Format o) pasada $Pasada ===" | Out-File -Append -Encoding utf8 $log

git pull --rebase --autostash 2>&1 | Out-File -Append -Encoding utf8 $log
& $py -m sconto.run_diario --entorno local --pasada $Pasada 2>&1 | Out-File -Append -Encoding utf8 $log
& $py -m sconto.run_diario --entorno local --pasada $Pasada --solo-si-falta --fuentes preciometro mercadolibre 2>&1 |
    Out-File -Append -Encoding utf8 $log

git add -A data reports 2>&1 | Out-File -Append -Encoding utf8 $log
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "datos: recolección $hoy (PC local, pasada $Pasada)" 2>&1 | Out-File -Append -Encoding utf8 $log
    foreach ($i in 1..3) {
        git pull --rebase --strategy-option=theirs 2>&1 | Out-File -Append -Encoding utf8 $log
        git push 2>&1 | Out-File -Append -Encoding utf8 $log
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds (20 * $i)
    }
}
"=== fin $(Get-Date -Format o) ===" | Out-File -Append -Encoding utf8 $log
