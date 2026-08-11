<#
PowerShell helper to bootstrap Antigravity plugin resources.
This script will clone the GSD repository (if git is available) and print manual steps
for Ralph Loop and CodeRabbit which require in-app or web-based installation.
#>

Param()

function Write-Notice($s){ Write-Host "[INFO] $s" -ForegroundColor Cyan }

Write-Notice "Creating directory: tools/plugins"
New-Item -ItemType Directory -Path .\tools\plugins -Force | Out-Null

$gsdDir = '.\tools\plugins\get-shit-done-for-antigravity'
if (-not (Test-Path $gsdDir)) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Notice "Cloning GSD repository into $gsdDir"
        git clone https://github.com/toonight/get-shit-done-for-antigravity.git $gsdDir
    } else {
        Write-Notice "Git not found. Please clone https://github.com/toonight/get-shit-done-for-antigravity.git into $gsdDir"
    }
} else {
    Write-Notice "GSD repo already present at $gsdDir"
}

Write-Host "`nManual steps for Ralph Loop and CodeRabbit:`n" -ForegroundColor Green
Write-Host "Ralph Loop: Open Antigravity -> Extensions -> Search 'Ralph Loop' -> Install and enable." -ForegroundColor Yellow
Write-Host "CodeRabbit: Visit https://www.coderabbit.ai/, connect your repository, and enable real-time code reviews." -ForegroundColor Yellow

Write-Notice "Docs added: docs/ANTIGRAVITY_PLUGINS.md"
Write-Notice "When ready, register GSD inside Antigravity per the plugin README." 
