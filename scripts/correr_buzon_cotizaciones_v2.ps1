$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $raiz 'src'
$env:PYTHONIOENCODING = 'utf-8'
$env:SCONTO_RAIZ = $raiz
$buzon = Join-Path $raiz 'data\operacion\v2\buzon_cotizaciones_privado'
$python = Join-Path $raiz '.venv\Scripts\python.exe'
$logs = Join-Path $raiz 'logs'
New-Item -ItemType Directory -Force -Path $buzon, $logs | Out-Null
$marca = Get-Date -Format 'yyyy-MM-dd'
Start-Transcript -LiteralPath (Join-Path $logs "buzon_cotizaciones_v2_$marca.log") -Append | Out-Null
try {
    & $python -m sconto.alimentar_api_v2 --buzon $buzon
    $codigo = $LASTEXITCODE
    if ($env:SCONTO_SYNC_FLY_APP -and $env:SCONTO_SYNC_FLY_MAQUINA) {
        & $python -m sconto.sincronizar_publico_v2 enviar --app $env:SCONTO_SYNC_FLY_APP --maquina $env:SCONTO_SYNC_FLY_MAQUINA
        if ($LASTEXITCODE -ne 0) { $codigo = $LASTEXITCODE }
    } elseif ($env:SCONTO_SYNC_FLY_APP -or $env:SCONTO_SYNC_FLY_MAQUINA) {
        Write-Error 'Completa la aplicación y la máquina de sincronización Fly.'
    }
} finally {
    Stop-Transcript | Out-Null
}
exit $codigo
