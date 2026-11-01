param([switch]$Publicar, [switch]$SoloPreparar, [int]$MaxProductos = 0)
$ErrorActionPreference = 'Stop'
$env:PATH = "$env:ProgramFiles\Git\cmd;$env:ProgramFiles\GitHub CLI;$env:SystemRoot\System32;$env:PATH"
$raiz = Split-Path -Parent $PSScriptRoot
$datos = Join-Path $raiz 'data\operacion\workspace'
$env:SCONTO_RAIZ = $datos
$env:SCONTO_ENVFILE = Join-Path $raiz '.env'
$env:SCONTO_CONTACTO = '+https://github.com/d1512pb/sconto-reale-o-falso'
$env:SCONTO_PARTICION = 'local'
$env:PYTHONPATH = Join-Path $raiz 'src'
$env:PYTHONIOENCODING = 'utf-8'
$py = Join-Path $raiz '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path (Join-Path $raiz 'logs'), $datos | Out-Null
$log = Join-Path $raiz ("logs\servicio_" + (Get-Date -Format 'yyyy-MM-dd') + '.log')
Start-Transcript -Path $log -Append | Out-Null
try {
    $argumentos = @('-m', 'sconto.servicio', '--raiz', $raiz)
    if ($Publicar) { $argumentos += '--publicar' }
    if ($SoloPreparar) { $argumentos += '--solo-preparar' }
    if ($MaxProductos -gt 0) { $argumentos += @('--max-productos', "$MaxProductos") }
    & $py @argumentos
    $codigo = $LASTEXITCODE
} catch {
    Write-Output $_
    $codigo = 1
} finally {
    Stop-Transcript | Out-Null
}
exit $codigo
