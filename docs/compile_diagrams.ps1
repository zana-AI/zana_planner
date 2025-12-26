# PowerShell script to compile PlantUML diagrams to SVG
# Requires: plantuml (install via: choco install plantuml, or download jar)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DiagramsDir = Join-Path $ScriptDir "diagrams"
$OutputDir = Join-Path $ScriptDir "diagrams\svg"

# Create output directory if it doesn't exist
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

# Check if plantuml is available
$plantumlCmd = Get-Command plantuml -ErrorAction SilentlyContinue
if (-not $plantumlCmd) {
    Write-Host "Error: plantuml command not found." -ForegroundColor Red
    Write-Host "Install PlantUML:"
    Write-Host "  - Chocolatey: choco install plantuml"
    Write-Host "  - Or download jar from https://plantuml.com/download"
    exit 1
}

Write-Host "Compiling PlantUML diagrams to SVG..."
Write-Host "Source: $DiagramsDir"
Write-Host "Output: $OutputDir"
Write-Host ""

# Check if plantuml.jar exists, use it if plantuml command is not available
$plantumlJar = Join-Path $ScriptDir "plantuml.jar"
$useJar = $false

if (-not $plantumlCmd -and (Test-Path $plantumlJar)) {
    $javaCmd = Get-Command java -ErrorAction SilentlyContinue
    if ($javaCmd) {
        $useJar = $true
        Write-Host "Using plantuml.jar with Java" -ForegroundColor Yellow
    }
}

# Compile all .puml files to SVG
Push-Location $DiagramsDir
try {
    Get-ChildItem -Filter "*.puml" | ForEach-Object {
        $filename = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
        Write-Host "Compiling: $($_.Name) -> ${filename}.svg"
        
        if ($useJar) {
            java -jar (Join-Path $ScriptDir "plantuml.jar") -tsvg -o svg $_.Name
            # Rename output file to match source filename (PlantUML uses @startuml title)
            $titleBasedName = $_.BaseName -replace '[^a-zA-Z0-9_-]', '_'
            $svgFromTitle = Get-ChildItem -Path svg -Filter "*${titleBasedName}*.svg" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($svgFromTitle) {
                $targetPath = Join-Path svg "${filename}.svg"
                if ($svgFromTitle.FullName -ne $targetPath) {
                    Move-Item -Path $svgFromTitle.FullName -Destination $targetPath -Force
                }
            }
        } else {
            plantuml -tsvg -o svg $_.Name
        }
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done! SVG files are in $OutputDir" -ForegroundColor Green

