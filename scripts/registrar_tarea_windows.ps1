$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
$script = Join-Path $raiz 'scripts\correr_local.ps1'
$usuario = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$accion = New-ScheduledTaskAction -Execute $powershell -WorkingDirectory $raiz `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Publicar"
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
$disparadores = @((New-ScheduledTaskTrigger -Daily -At '12:30'), (New-ScheduledTaskTrigger -AtLogOn -User $usuario))
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Sconto recoleccion diaria' -Action $accion -Trigger $disparadores `
    -Settings $ajustes -Principal $principal -Description 'ESCOM-IPN: precios diarios, respaldo y paquete publico para Colab.' -Force | Out-Null
Get-ScheduledTask -TaskName 'Sconto recoleccion diaria' | Select-Object TaskName, State
