# Registra (o actualiza) las tareas del Programador de tareas para la corrida local.
# Ejecutar UNA vez, en PowerShell normal (no requiere administrador):
#   powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1
# Para quitarlas: Unregister-ScheduledTask -TaskName 'Sconto*' -Confirm:$false
$raiz = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz 'scripts\correr_local.ps1'
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew

foreach ($t in @(
    @{Nombre = 'Sconto recoleccion diaria'; Pasada = 1; Hora = '09:30'},
    @{Nombre = 'Sconto recoleccion 2a pasada (10-20 nov)'; Pasada = 2; Hora = '20:30'}
)) {
    $accion = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Pasada $($t.Pasada)" `
        -WorkingDirectory $raiz
    # Diario a la hora indicada y, si la PC estaba apagada, al iniciar sesión (StartWhenAvailable + AtLogOn).
    $disparadores = @((New-ScheduledTaskTrigger -Daily -At $t.Hora), (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME))
    Register-ScheduledTask -TaskName $t.Nombre -Action $accion -Trigger $disparadores -Settings $ajustes `
        -Description 'Sconto reale o falso: colector diario de precios (ESCOM-IPN). Ver README.' -Force | Out-Null
    Write-Host "Registrada: $($t.Nombre) ($($t.Hora))"
}
Get-ScheduledTask -TaskName 'Sconto*' | Select-Object TaskName, State
