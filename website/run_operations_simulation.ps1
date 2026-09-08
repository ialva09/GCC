[CmdletBinding()]
param(
    [switch]$Keep,
    [switch]$Serve
)

$ErrorActionPreference = "Stop"
$websiteRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$simulationRoot = Join-Path $tempBase ("grand-coast-simulation-" + [Guid]::NewGuid().ToString("N"))
$databasePath = Join-Path $simulationRoot "db.sqlite3"
$mediaRoot = Join-Path $simulationRoot "media"
$reportPath = Join-Path $simulationRoot "simulation-report.json"
$oldEnvironment = @{}
$environmentNames = @(
    "DJANGO_DEBUG",
    "GCC_SIMULATION_MODE",
    "GCC_DATABASE_PATH",
    "GCC_MEDIA_ROOT",
    "GCC_STORAGE_SMOKE_ENABLED",
    "GCC_STORAGE_PREFIX",
    "USE_SUPABASE_STORAGE",
    "USE_SUPABASE_CONTACT_STORAGE",
    "SUPABASE_S3_ENDPOINT",
    "SUPABASE_S3_ACCESS_KEY",
    "SUPABASE_S3_SECRET_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "SUPABASE_S3_REGION",
    "GCC_EXECUTION_LOOP_ENABLED",
    "GCC_EXECUTION_LOOP_PROJECT_IDS",
    "GCC_EXECUTION_LOOP_USER_IDS",
    "GCC_AI_ENABLED",
    "GCC_TURNSTILE_ENABLED",
    "GCC_TURNSTILE_ALLOW_MISSING",
    "GCC_EMAIL_DELIVERY_ENABLED",
    "EMAIL_BACKEND",
    "EXPO_PUSH_ENABLED"
)

foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

New-Item -ItemType Directory -Path $simulationRoot -Force | Out-Null
New-Item -ItemType Directory -Path $mediaRoot -Force | Out-Null

try {
    $env:DJANGO_DEBUG = "true"
    $env:GCC_SIMULATION_MODE = "true"
    $env:GCC_DATABASE_PATH = $databasePath
    $env:GCC_MEDIA_ROOT = $mediaRoot
    $env:GCC_STORAGE_SMOKE_ENABLED = "false"
    $env:GCC_STORAGE_PREFIX = ""
    $env:USE_SUPABASE_STORAGE = "false"
    $env:USE_SUPABASE_CONTACT_STORAGE = "false"
    $env:SUPABASE_S3_ENDPOINT = ""
    $env:SUPABASE_S3_ACCESS_KEY = ""
    $env:SUPABASE_S3_SECRET_KEY = ""
    $env:SUPABASE_STORAGE_BUCKET = ""
    $env:SUPABASE_S3_REGION = ""
    $env:GCC_EXECUTION_LOOP_ENABLED = "true"
    $env:GCC_EXECUTION_LOOP_PROJECT_IDS = ""
    $env:GCC_EXECUTION_LOOP_USER_IDS = ""
    $env:GCC_AI_ENABLED = "false"
    $env:GCC_TURNSTILE_ENABLED = "false"
    $env:GCC_TURNSTILE_ALLOW_MISSING = "true"
    $env:GCC_EMAIL_DELIVERY_ENABLED = "false"
    $env:EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    $env:EXPO_PUSH_ENABLED = "false"

    Push-Location $websiteRoot
    try {
        Write-Host "Creating isolated simulation database: $databasePath"
        python manage.py migrate --noinput
        python manage.py simulate_operations --scenario full-lifecycle --report $reportPath

        $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        $env:GCC_EXECUTION_LOOP_PROJECT_IDS = [string]$report.pilot.project_id
        $env:GCC_EXECUTION_LOOP_USER_IDS = (($report.pilot.user_ids.psobject.Properties | ForEach-Object { $_.Value }) -join ",")

        Write-Host ""
        Write-Host "Isolated report: $reportPath"
        Write-Host "Generated pilot environment:"
        Write-Host "  GCC_EXECUTION_LOOP_ENABLED=true"
        Write-Host "  GCC_EXECUTION_LOOP_PROJECT_IDS=$env:GCC_EXECUTION_LOOP_PROJECT_IDS"
        Write-Host "  GCC_EXECUTION_LOOP_USER_IDS=$env:GCC_EXECUTION_LOOP_USER_IDS"
        Write-Host "  GCC_AI_ENABLED=false"
        Write-Host ""

        if ($Serve) {
            Write-Host "Starting isolated server. Press Ctrl+C to stop it."
            python manage.py runserver 127.0.0.1:8001
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
    }
    $resolvedTempBase = [IO.Path]::GetFullPath($tempBase).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $resolvedSimulationRoot = [IO.Path]::GetFullPath($simulationRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    if (-not $Keep -and $resolvedSimulationRoot.StartsWith($resolvedTempBase + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $resolvedSimulationRoot) {
            Remove-Item -LiteralPath $resolvedSimulationRoot -Recurse -Force
        }
    }
    elseif ($Keep) {
        Write-Host "Retained isolated simulation root: $resolvedSimulationRoot"
    }
}
