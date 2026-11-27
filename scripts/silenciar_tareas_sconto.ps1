$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$lanzador = Join-Path $PSScriptRoot 'ejecutar_tarea_sin_ventana.vbs'
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'
if (-not (Test-Path -LiteralPath $lanzador) -or -not (Test-Path -LiteralPath $wscript)) {
    throw 'Falta el lanzador silencioso o Windows Script Host.'
}

$objetivos = @(
    @{ Nombre = 'Sconto recoleccion diaria'; Modo = 'diario'; Script = 'correr_local.ps1' },
    @{ Nombre = 'Sconto v2 Piloto PROFECO Buen Fin 2026'; Modo = 'profeco'; Script = 'correr_piloto_buen_fin_v2.ps1' },
    @{ Nombre = 'Sconto v2 Vigilancia QQP'; Modo = 'qqp'; Script = 'correr_revision_qqp_v2.ps1' },
    @{ Nombre = 'Sconto v2 Buzon de cotizaciones autorizadas'; Modo = 'buzon'; Script = 'correr_buzon_cotizaciones_v2.ps1' }
)
$tareas = @{}
foreach ($objetivo in $objetivos) {
    $tarea = Get-ScheduledTask -TaskName $objetivo.Nombre -TaskPath '\'
    if ($tarea.Actions.Count -ne 1) { throw ('Acciones inesperadas: ' + $objetivo.Nombre) }
    $accion = $tarea.Actions[0]
    $scriptEsperado = Join-Path $PSScriptRoot $objetivo.Script
    $esOriginal = $accion.Execute -match '\\powershell\.exe$' -and $accion.Arguments.Contains($scriptEsperado)
    $esSilenciosa = $accion.Execute -ieq $wscript -and $accion.Arguments.Contains($lanzador)
    if (-not ($esOriginal -or $esSilenciosa)) { throw ('Revisar accion antes de cambiarla: ' + $objetivo.Nombre) }
    $tareas[$objetivo.Nombre] = $tarea
}
$reactivadores = @(Get-ScheduledTask -TaskName 'Sconto v2 Reactivar buzon*' -ErrorAction SilentlyContinue)
$buzon = Join-Path $raiz 'data\operacion\v2\buzon_cotizaciones_privado'
if (Test-Path -LiteralPath $buzon) {
    $pendientes = @(Get-ChildItem -LiteralPath $buzon -File | Where-Object { $_.Extension -in @('.json', '.pdf', '.png', '.jpg', '.jpeg', '.txt') })
    if ($pendientes.Count -gt 0) { throw 'El buzon contiene entregas. Revisa su necesidad antes de desactivarlo.' }
}
$backup = Join-Path $raiz ('data\operacion\v2\tareas_silenciosas\' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + 'Z')
New-Item -ItemType Directory -Path $backup | Out-Null
foreach ($tarea in @($tareas.Values) + $reactivadores) {
    Export-ScheduledTask -TaskName $tarea.TaskName -TaskPath $tarea.TaskPath |
        Out-File -LiteralPath (Join-Path $backup ($tarea.TaskName + '.xml')) -Encoding unicode -NoClobber
}

Disable-ScheduledTask -TaskName 'Sconto v2 Buzon de cotizaciones autorizadas' -TaskPath '\' | Out-Null
foreach ($tarea in $reactivadores) {
    Disable-ScheduledTask -TaskName $tarea.TaskName -TaskPath $tarea.TaskPath | Out-Null
}
foreach ($objetivo in $objetivos) {
    $argumentos = '//B //Nologo "' + $lanzador + '" ' + $objetivo.Modo
    $accion = New-ScheduledTaskAction -Execute $wscript -Argument $argumentos -WorkingDirectory $raiz
    Set-ScheduledTask -TaskName $objetivo.Nombre -TaskPath '\' -Action $accion | Out-Null
}

$estado = foreach ($objetivo in $objetivos) {
    $tarea = Get-ScheduledTask -TaskName $objetivo.Nombre -TaskPath '\'
    if ($tarea.Actions[0].Execute -ine $wscript) { throw ('No quedo silenciosa: ' + $objetivo.Nombre) }
    if ($objetivo.Modo -eq 'buzon' -and $tarea.State -ne 'Disabled') { throw 'El buzon no quedo desactivado.' }
    [pscustomobject]@{ Nombre = $tarea.TaskName; Estado = [string]$tarea.State; Modo = $objetivo.Modo;
        Ejecutable = $tarea.Actions[0].Execute; Argumentos = $tarea.Actions[0].Arguments }
}
$estado | ConvertTo-Json -Depth 3 | Out-File -LiteralPath (Join-Path $backup 'estado_despues.json') -Encoding utf8
[pscustomobject]@{ Respaldo = $backup; Tareas = @($estado); ReactivadoresDesactivados = $reactivadores.Count } |
    ConvertTo-Json -Depth 4
