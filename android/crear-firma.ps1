param([string]$SigningDirectory = (Join-Path $PSScriptRoot '../data/operacion/firma-android'))
$ErrorActionPreference = 'Stop'
$keystore = Join-Path $SigningDirectory 'sconto-release.jks'
$passwordFile = Join-Path $SigningDirectory 'clave.xml'
if ((Test-Path -LiteralPath $keystore) -or (Test-Path -LiteralPath $passwordFile)) {
    throw 'Ya hay material de firma. No se reemplazó; conservarlo permite actualizar instalaciones existentes.'
}
New-Item -ItemType Directory -Force -Path $SigningDirectory | Out-Null
# DPAPI cifra la contraseña para el usuario y equipo actuales; nunca se imprime.
$password = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(48))
ConvertTo-SecureString -String $password -AsPlainText -Force | Export-Clixml -LiteralPath $passwordFile
$previousPassword = $env:SCONTO_SIGN_PASSWORD
try {
    $env:SCONTO_SIGN_PASSWORD = $password
    & keytool -genkeypair -keystore $keystore -storetype PKCS12 -alias sconto -keyalg RSA -keysize 3072 `
        -validity 10000 -dname 'CN=Sconto, OU=Proyecto academico, O=Sconto, C=MX' `
        -storepass:env SCONTO_SIGN_PASSWORD -keypass:env SCONTO_SIGN_PASSWORD -noprompt
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la firma.' }
} finally {
    $env:SCONTO_SIGN_PASSWORD = $previousPassword
    $password = $null
}
Write-Output 'Firma local creada en la carpeta privada de operación. No subirla a GitHub ni compartirla con el APK.'
