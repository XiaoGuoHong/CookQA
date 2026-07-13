param(
    [string]$SourceRoot = "Data/source/howtocook"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not $env:NEO4J_PASSWORD) {
    throw "请先在当前终端设置 NEO4J_PASSWORD。"
}

python -m cookqa.cli build-indexes --source-root $SourceRoot
