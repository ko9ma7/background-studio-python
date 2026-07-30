$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$releaseRoot = Join-Path $projectRoot "release"
$packageName = "BackgroundStudio-Python-v1.4.0-win-x64"
$packageFolder = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"
$buildRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "BackgroundStudio-Python-" + [Guid]::NewGuid().ToString("N")
)
$buildDist = Join-Path $buildRoot "dist"
$resolvedReleaseRoot = [IO.Path]::GetFullPath($releaseRoot) + [IO.Path]::DirectorySeparatorChar
$resolvedPackageFolder = [IO.Path]::GetFullPath($packageFolder)

if (-not $resolvedPackageFolder.StartsWith($resolvedReleaseRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to build outside the project release directory."
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Run 'uv sync --extra dev' before building the Windows package."
}

New-Item -ItemType Directory -Path $buildRoot | Out-Null
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name "BackgroundStudio-Python" `
    --distpath $buildDist `
    --workpath (Join-Path $buildRoot "work") `
    --specpath $buildRoot `
    --paths (Join-Path $projectRoot "src") `
    --collect-all rembg `
    --collect-all onnxruntime `
    --collect-all pymatting `
    --collect-all uvicorn `
    --hidden-import background_studio.api `
    --hidden-import multipart `
    (Join-Path $projectRoot "src\background_studio\windows_launcher.py")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$builtFolder = Join-Path $buildDist "BackgroundStudio-Python"
if (Test-Path -LiteralPath $packageFolder) {
    Remove-Item -LiteralPath $packageFolder -Recurse -Force
}
Move-Item -LiteralPath $builtFolder -Destination $packageFolder
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $packageFolder
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packageFolder

if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $packageFolder -DestinationPath $zipPath -CompressionLevel Optimal
$hash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
"$($hash.Hash.ToLowerInvariant())  $packageName.zip" |
    Set-Content -LiteralPath "$zipPath.sha256" -Encoding ascii
Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Created $zipPath"
Write-Host "SHA256 $($hash.Hash)"
