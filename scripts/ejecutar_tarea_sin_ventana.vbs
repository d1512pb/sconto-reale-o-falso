Option Explicit

Dim shell, files, root, powershell, script, command, mode, extra, result
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
If WScript.Arguments.Count <> 1 Then WScript.Quit 64

root = files.GetParentFolderName(files.GetParentFolderName(WScript.ScriptFullName))
powershell = shell.ExpandEnvironmentStrings("%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe")
mode = LCase(WScript.Arguments(0))
extra = ""
Select Case mode
    Case "diario"
        script = "correr_local.ps1"
        extra = " -Publicar"
    Case "profeco"
        script = "correr_piloto_buen_fin_v2.ps1"
    Case "qqp"
        script = "correr_revision_qqp_v2.ps1"
    Case "buzon"
        script = "correr_buzon_cotizaciones_v2.ps1"
    Case "comprobar"
        script = ""
    Case Else
        WScript.Quit 64
End Select

shell.CurrentDirectory = root
command = Quote(powershell) & " -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden"
If mode = "comprobar" Then
    command = command & " -Command " & Quote("exit 0")
Else
    script = files.BuildPath(files.BuildPath(root, "scripts"), script)
    If Not files.FileExists(script) Then WScript.Quit 66
    command = command & " -File " & Quote(script) & extra
End If

' wscript no crea consola; el hijo nace oculto y conserva su codigo de salida.
result = shell.Run(command, 0, True)
WScript.Quit result

Function Quote(value)
    If InStr(value, Chr(34)) > 0 Then WScript.Quit 64
    Quote = Chr(34) & value & Chr(34)
End Function
