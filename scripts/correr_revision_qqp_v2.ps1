$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz '.venv\Scripts\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONPATH = Join-Path $raiz 'src'
$env:SCONTO_RAIZ = $raiz
$env:SCONTO_CONTACTO = '+https://github.com/d1512pb/sconto-reale-o-falso'
$zona = [TimeZoneInfo]::FindSystemTimeZoneById('Central Standard Time (Mexico)')
$dia = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $zona).ToString('yyyy-MM-dd')
$logs = Join-Path $raiz 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$codigo = 1
Start-Transcript -LiteralPath (Join-Path $logs "qqp_v2_$dia.log") -Append | Out-Null
try {
    $ErrorActionPreference = 'Continue'
    & $python -m sconto.fuentes.qqp_vigilar
    $codigo = $LASTEXITCODE
    & $python -m sconto.operacion_profeco_bf_v2 --revisar
    if ($LASTEXITCODE -ne 0 -and $codigo -eq 0) { $codigo = $LASTEXITCODE }
} finally {
    Stop-Transcript | Out-Null
}
exit $codigo
