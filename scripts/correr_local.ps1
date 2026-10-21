param([switch]$Publicar, [switch]$SoloPreparar, [int]$MaxProductos = 0)
$ErrorActionPreference = 'Stop'
$env:PATH = "$env:ProgramFiles\Git\cmd;$env:ProgramFiles\GitHub CLI;$env:SystemRoot\System32;$env:PATH"
$raiz = Split-Path -Parent $PSScriptRoot
$servicio = Join-Path $raiz 'data\operacion'
$repo = Join-Path $servicio 'repo'
$datos = Join-Path $servicio 'workspace'
$py = Join-Path $raiz '.venv\Scripts\python.exe'
$hoy = Get-Date -Format 'yyyy-MM-dd'
New-Item -ItemType Directory -Force -Path $servicio, $datos, (Join-Path $raiz 'logs') | Out-Null
$log = Join-Path $raiz "logs\servicio_$hoy.log"
Start-Transcript -Path $log -Append | Out-Null
try {
    if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
        & git clone --depth 1 'https://github.com/d1512pb/sconto-reale-o-falso.git' $repo
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear la copia operativa del repositorio.' }
    }
    & git -C $repo config credential.helper '!gh auth git-credential'
    & git -C $repo pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'La copia operativa requiere revisar su sincronizacion.' }
    $corrida = & gh run list --repo d1512pb/sconto-reale-o-falso --workflow recoleccion_diaria.yml --limit 5 --json databaseId,status --jq 'map(select(.status != "completed")) | .[0].databaseId'
    if ($LASTEXITCODE -eq 0 -and "$corrida".Trim() -match '^\d+$') {
        & gh run watch "$corrida" --repo d1512pb/sconto-reale-o-falso --interval 60 --compact --exit-status
        & git -C $repo pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo sincronizar el resultado cloud.' }
    }
    $env:SCONTO_RAIZ = $datos
    $env:SCONTO_ENVFILE = Join-Path $raiz '.env'
    $env:SCONTO_CONTACTO = '+https://github.com/d1512pb/sconto-reale-o-falso'
    $env:PYTHONPATH = Join-Path $repo 'src'
    $env:PYTHONIOENCODING = 'utf-8'
    foreach ($carpeta in @('config', 'reports')) {
        $destino = Join-Path $datos $carpeta
        New-Item -ItemType Directory -Force -Path $destino | Out-Null
        Get-ChildItem -LiteralPath (Join-Path $repo $carpeta) -File | Copy-Item -Destination $destino -Force
    }
    foreach ($carpeta in @('data\bronze', 'data\estado')) {
        $origen = Join-Path $repo $carpeta
        foreach ($archivo in Get-ChildItem -LiteralPath $origen -Recurse -File) {
            $relativa = $archivo.FullName.Substring($repo.Length + 1)
            $destino = Join-Path $datos $relativa
            if (-not (Test-Path -LiteralPath $destino) -or $archivo.Name -eq 'github.csv') {
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destino) | Out-Null
                Copy-Item -LiteralPath $archivo.FullName -Destination $destino -Force
            }
        }
    }
    $carpetaQqp = Join-Path $datos 'data\raw\qqp'
    New-Item -ItemType Directory -Force -Path $carpetaQqp | Out-Null
    foreach ($nombre in @('QQP_2026.rar', 'QQP_2026.rar.manifest.json')) {
        $destino = Join-Path $carpetaQqp $nombre
        $origen = Join-Path $raiz "data\raw\qqp\$nombre"
        if (-not (Test-Path -LiteralPath $destino) -and (Test-Path -LiteralPath $origen)) {
            Copy-Item -LiteralPath $origen -Destination $destino
        }
    }
    $argumentos = @('-m', 'sconto.operacion', '--entorno', 'local')
    if ($SoloPreparar) {
        $argumentos += '--solo-preparar'
    } else {
        $argumentos += '--qqp-semanal'
        $enCurso = & gh run list --repo d1512pb/sconto-reale-o-falso --workflow recoleccion_diaria.yml --status in_progress --json databaseId --jq length
        if ($LASTEXITCODE -eq 0 -and "$enCurso".Trim() -eq '0') { $argumentos += '--respaldo' }
    }
    if ($MaxProductos -gt 0) { $argumentos += @('--max-productos', "$MaxProductos") }
    & $py @argumentos
    if ($LASTEXITCODE -ne 0) { throw 'Fallo del ciclo local; revisar el log antes de publicar.' }
    if ($Publicar) {
        foreach ($fuente in @('tiendas', 'preciometro', 'preciometro_ofertas', 'preciometro_productos')) {
            $origen = Join-Path $datos "data\bronze\$fuente\$hoy.parquet"
            if (Test-Path -LiteralPath $origen) {
                $carpeta = Join-Path $repo "data\bronze\$fuente"
                New-Item -ItemType Directory -Force -Path $carpeta | Out-Null
                Copy-Item -LiteralPath $origen -Destination $carpeta -Force
            }
        }
        foreach ($carpeta in Get-ChildItem -LiteralPath (Join-Path $datos 'data\bronze') -Directory -Filter 'qqp_*') {
            if ($carpeta.Name -like 'qqp_nacional*') { continue }
            foreach ($archivo in Get-ChildItem -LiteralPath $carpeta.FullName -File | Where-Object { $_.BaseName -in @('2026', 'BF2026') }) {
                $destino = Join-Path $repo "data\bronze\$($carpeta.Name)"
                New-Item -ItemType Directory -Force -Path $destino | Out-Null
                Copy-Item -LiteralPath $archivo.FullName -Destination $destino -Force
            }
        }
        foreach ($nombre in @('local.csv', 'ciclo_local.json')) {
            $origen = Join-Path $datos "data\estado\$nombre"
            if (Test-Path -LiteralPath $origen) { Copy-Item -LiteralPath $origen -Destination (Join-Path $repo 'data\estado') -Force }
        }
        $evidencia = Join-Path $datos "data\evidencia\preciometro\$hoy"
        if (Test-Path -LiteralPath $evidencia) {
            $destino = Join-Path $repo "data\evidencia\preciometro\$hoy"
            New-Item -ItemType Directory -Force -Path $destino | Out-Null
            Get-ChildItem -LiteralPath $evidencia -File | Copy-Item -Destination $destino -Force
            & git -C $repo add -- data/evidencia
        }
        & git -C $repo config user.name 'sconto-pc'
        & git -C $repo config user.email '93066782+d1512pb@users.noreply.github.com'
        & git -C $repo add -- data/bronze data/estado/local.csv data/estado/ciclo_local.json
        & git -C $repo diff --cached --quiet
        if ($LASTEXITCODE -ne 0) {
            & git -C $repo commit -m "datos: respaldo local $hoy"
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo guardar el respaldo local.' }
            & git -C $repo pull --rebase
            if ($LASTEXITCODE -ne 0) { throw 'Conflicto de datos: se conserva la copia operativa sin descartar cambios.' }
            & git -C $repo push
            if ($LASTEXITCODE -ne 0) { throw 'El respaldo local queda pendiente de publicar.' }
        }
        $paquete = Join-Path $datos "data\exportaciones\sconto_colab_$hoy.zip"
        $actual = Join-Path $datos 'data\exportaciones\sconto_colab_actual.zip'
        Copy-Item -LiteralPath $paquete -Destination $actual -Force
        & gh release upload datos $paquete $actual --repo d1512pb/sconto-reale-o-falso --clobber
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo publicar el paquete actualizado.' }
    }
    & $py -m sconto.operacion --entorno local --verificar
    $codigo = $LASTEXITCODE
} catch {
    Write-Output $_
    $codigo = 1
} finally {
    Stop-Transcript | Out-Null
}
exit $codigo
