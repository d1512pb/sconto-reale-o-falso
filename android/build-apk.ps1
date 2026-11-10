param(
    [string]$SdkPath = (Join-Path $env:LOCALAPPDATA 'Android/Sdk'),
    [ValidateSet('release', 'debug')][string]$Variant = 'release',
    [string]$SigningDirectory = (Join-Path $PSScriptRoot '../data/operacion/firma-android')
)
$ErrorActionPreference = 'Stop'
$androidRoot = $PSScriptRoot
$projectRoot = Split-Path $androidRoot -Parent
if (-not (Test-Path -LiteralPath $SdkPath)) { throw 'No se encontró el SDK de Android.' }
if ($Variant -eq 'release' -and -not (Test-Path -LiteralPath (Join-Path $SigningDirectory 'sconto-release.jks'))) {
    throw 'Falta la firma local. Ejecuta android/crear-firma.ps1 una sola vez; no reemplaces una firma existente.'
}
$sdkValue = (Resolve-Path -LiteralPath $SdkPath).Path.Replace('\', '/').Replace(':', '\:')
Set-Content -LiteralPath (Join-Path $androidRoot 'local.properties') -Value "sdk.dir=$sdkValue" -Encoding ascii
$taskVariant = if ($Variant -eq 'release') { 'Release' } else { 'Debug' }
& (Join-Path $androidRoot 'gradlew.bat') -p $androidRoot ":app:assemble$taskVariant" ":app:testDebugUnitTest" ":app:lint$taskVariant" --console=plain --max-workers=2
if ($LASTEXITCODE -ne 0) { throw 'La compilación o sus verificaciones fallaron. No se exportó el APK.' }

$outputDir = Join-Path $projectRoot 'data/exportaciones/apk'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$metadata = Get-Content -LiteralPath (Join-Path $androidRoot "app/build/outputs/apk/$Variant/output-metadata.json") -Raw | ConvertFrom-Json
$version = $metadata.elements[0].versionName
$suffix = if ($Variant -eq 'debug') { '-pruebas' } else { '' }
$apk = Join-Path $outputDir "Sconto-$version$suffix.apk"
$sourceApk = Join-Path $androidRoot "app/build/outputs/apk/$Variant/$($metadata.elements[0].outputFile)"
$buildTools = Join-Path $SdkPath 'build-tools/36.0.0'
$signer = Join-Path $buildTools 'apksigner.bat'
if ($Variant -eq 'release') {
    $secret = Import-Clixml -LiteralPath (Join-Path $SigningDirectory 'clave.xml')
    $previousPassword = $env:SCONTO_SIGN_PASSWORD
    try {
        $env:SCONTO_SIGN_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
        & $signer sign --ks (Join-Path $SigningDirectory 'sconto-release.jks') --ks-key-alias sconto --ks-pass env:SCONTO_SIGN_PASSWORD --key-pass env:SCONTO_SIGN_PASSWORD --out $apk $sourceApk
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo firmar el APK.' }
    } finally { $env:SCONTO_SIGN_PASSWORD = $previousPassword }
} else { Copy-Item -LiteralPath $sourceApk -Destination $apk }

$verification = & $signer verify --verbose --print-certs $apk
if ($LASTEXITCODE -ne 0) { throw 'Firma de APK inválida.' }
$badging = & (Join-Path $buildTools 'aapt.exe') dump badging $apk
if ($LASTEXITCODE -ne 0) { throw 'No se pudo leer el APK.' }
if ($Variant -eq 'release' -and ($badging -match 'application-debuggable')) { throw 'El APK release no debe permitir depuración.' }
$permissions = @($badging | Where-Object { $_ -match '^uses-permission:' })
if ($permissions.Count -ne 1 -or $permissions[0] -notmatch "name='android.permission.INTERNET'") { throw 'Permisos inesperados.' }
$certificateLine = $verification | Where-Object { $_ -match '^Signer #1 certificate SHA-256 digest:' }
$hash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
$sourceHashes = [ordered]@{}
Get-ChildItem -LiteralPath (Join-Path $androidRoot 'app/src') -Recurse -File | Sort-Object FullName | ForEach-Object {
    $relative = [System.IO.Path]::GetRelativePath($projectRoot, $_.FullName).Replace('\', '/')
    $sourceHashes[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$sourceHashes['android/app/build.gradle'] = (Get-FileHash -LiteralPath (Join-Path $androidRoot 'app/build.gradle') -Algorithm SHA256).Hash.ToLowerInvariant()
[ordered]@{
    archivo = (Split-Path $apk -Leaf)
    sha256 = $hash
    bytes = (Get-Item -LiteralPath $apk).Length
    tipo = $Variant
    app_id = 'mx.sconto.app'
    version = $version
    version_code = $metadata.elements[0].versionCode
    android_minimo = '8.0 (API 26)'
    permiso = 'android.permission.INTERNET'
    certificado_sha256 = ($certificateLine -replace '^.*digest:\s*', '')
    fuentes_android_sha256 = $sourceHashes
    construido_utc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputDir 'manifest.json') -Encoding utf8
Set-Content -LiteralPath (Join-Path $outputDir 'SHA256SUMS.txt') -Value "$hash  $(Split-Path $apk -Leaf)" -Encoding ascii
Write-Output "APK verificado: $apk"
Write-Output "SHA-256: $hash"
