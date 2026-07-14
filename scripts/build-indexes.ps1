param(
    [string]$SourceRoot = "Data/source/howtocook"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $env:NEO4J_PASSWORD) {
    throw "NEO4J_PASSWORD is not set in this PowerShell session."
}

python -m cookqa.cli build-indexes --source-root $SourceRoot
