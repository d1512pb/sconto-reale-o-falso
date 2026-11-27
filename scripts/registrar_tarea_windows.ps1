$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$lanzador = Join-Path $raiz 'scripts\ejecutar_tarea_sin_ventana.vbs'
$usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'
$accion = New-ScheduledTaskAction -Execute $wscript -WorkingDirectory $raiz `
    -Argument ('//B //Nologo "' + $lanzador + '" diario')
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
$disparadores = @((New-ScheduledTaskTrigger -Daily -At '12:30'), (New-ScheduledTaskTrigger -Daily -At '20:30'), (New-ScheduledTaskTrigger -AtLogOn -User $usuario))
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Sconto recoleccion diaria' -Action $accion -Trigger $disparadores `
    -Settings $ajustes -Principal $principal -Description 'ESCOM-IPN: precios diarios, respaldo y paquete publico para Colab.' -Force | Out-Null
Get-ScheduledTask -TaskName 'Sconto recoleccion diaria' | Select-Object TaskName, State
