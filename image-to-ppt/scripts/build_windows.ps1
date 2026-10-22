# 建置 Windows ZIP：解壓後直接執行 ImageToPPT.exe
# 用法： powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

uv sync --group dev
uv run pyinstaller --noconfirm --clean ImageToPPT.spec

$dist = Join-Path $root "dist\ImageToPPT"
$zip = Join-Path $root "dist\ImageToPPT-Windows.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path $dist -DestinationPath $zip

Write-Host "完成：$zip"
