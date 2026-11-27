$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$nombreCampana = 'Sconto v2 Piloto PROFECO Buen Fin 2026'
$nombrePermanente = 'Sconto v2 Vigilancia QQP'
$tarea = Get-ScheduledTask -TaskName $nombreCampana
$original = $tarea.Triggers
if ($original.Count -ne 1 -or $original[0].CimClass.CimClassName -ne 'MSFT_TaskDailyTrigger') {
    throw 'Los disparadores de la campaña cambiaron. Revisa la tarea antes de actualizarla.'
}
$backup = Join-Path $raiz 'data\operacion\v2\profeco_campana\tareas'
New-Item -ItemType Directory -Path $backup -Force | Out-Null
$respaldo = Join-Path $backup ('campana_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff') + 'Z.xml')
Export-ScheduledTask -TaskName $nombreCampana | Out-File -LiteralPath $respaldo -Encoding unicode -NoClobber

$original[0].EndBoundary = '2026-12-01T23:59:59'
Set-ScheduledTask -TaskName $nombreCampana -Trigger $original | Out-Null
if (-not (Get-ScheduledTask -TaskName $nombrePermanente -ErrorAction SilentlyContinue)) {
    $usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'
    $lanzador = Join-Path $raiz 'scripts\ejecutar_tarea_sin_ventana.vbs'
    $argsTarea = '//B //Nologo "' + $lanzador + '" qqp'
    $accion = New-ScheduledTaskAction -Execute $wscript -WorkingDirectory $raiz -Argument $argsTarea
    $ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
    $disparador = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At ([DateTime]::new(2026, 11, 22, 12, 5, 0))
    $principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $nombrePermanente -Action $accion -Trigger $disparador -Settings $ajustes `
        -Principal $principal -Description 'Vigila el catalogo oficial de QQP y aisla archivos candidatos. Registro y avisos locales.' | Out-Null
}
foreach ($nombre in @($nombreCampana, $nombrePermanente)) {
    $tarea = Get-ScheduledTask -TaskName $nombre
    $info = Get-ScheduledTaskInfo -TaskName $nombre
    [pscustomobject]@{ Tarea=$nombre; Estado=$tarea.State; Proxima=$info.NextRunTime;
        Fin=$tarea.Triggers[0].EndBoundary; Recupera=$tarea.Settings.StartWhenAvailable }
}
