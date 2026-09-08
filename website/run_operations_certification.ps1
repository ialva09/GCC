[CmdletBinding()]
param(
    [ValidateSet("Emulator", "Provider", "Both")]
    [string]$StorageMode = "Emulator",
    [switch]$Browser,
    [switch]$Keep,
    [switch]$Serve
)

$ErrorActionPreference = "Stop"
$websiteRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$runId = [Guid]::NewGuid().ToString("N")
$certificationRoot = Join-Path $tempBase "grand-coast-certification-$runId"
$pythonPath = Join-Path $websiteRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
}

if ($Serve -and ($Browser -or $StorageMode -eq "Both")) {
    throw "-Serve can only be used for one storage mode without browser automation."
}

$environmentNames = @(
    "DJANGO_DEBUG",
    "GCC_SIMULATION_MODE",
    "GCC_DATABASE_PATH",
    "GCC_MEDIA_ROOT",
    "GCC_EXECUTION_LOOP_ENABLED",
    "GCC_EXECUTION_LOOP_PROJECT_IDS",
    "GCC_EXECUTION_LOOP_USER_IDS",
    "GCC_AI_ENABLED",
    "GCC_TURNSTILE_ENABLED",
    "GCC_TURNSTILE_ALLOW_MISSING",
    "GCC_NATIVE_MEDIA_ENABLED",
    "GCC_EMAIL_DELIVERY_ENABLED",
    "EMAIL_BACKEND",
    "EXPO_PUSH_ENABLED",
    "GCC_STORAGE_SMOKE_ENABLED",
    "GCC_STORAGE_PREFIX",
    "USE_SUPABASE_STORAGE",
    "SUPABASE_S3_ENDPOINT",
    "SUPABASE_S3_ACCESS_KEY",
    "SUPABASE_S3_SECRET_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "SUPABASE_S3_REGION"
)
$oldEnvironment = @{}
foreach ($name in $environmentNames) {
    $oldEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

New-Item -ItemType Directory -Path $certificationRoot -Force | Out-Null
$runResults = [System.Collections.Generic.List[object]]::new()

function Invoke-Python {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $pythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

function Require-ProviderStorage {
    foreach ($name in @("SUPABASE_S3_ENDPOINT", "SUPABASE_S3_ACCESS_KEY", "SUPABASE_S3_SECRET_KEY", "SUPABASE_STORAGE_BUCKET", "SUPABASE_S3_REGION")) {
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            throw "Provider mode requires the development-only $name environment variable."
        }
    }
}

function Get-StorageConfiguration {
    param([ValidateSet("Emulator", "Provider")][string]$Mode)
    if ($Mode -eq "Provider") {
        Require-ProviderStorage
        return [ordered]@{
            endpoint = $env:SUPABASE_S3_ENDPOINT
            access_key = $env:SUPABASE_S3_ACCESS_KEY
            secret_key = $env:SUPABASE_S3_SECRET_KEY
            bucket = $env:SUPABASE_STORAGE_BUCKET
            region = $env:SUPABASE_S3_REGION
        }
    }
    return [ordered]@{
        endpoint = if ($env:GCC_CERTIFICATION_EMULATOR_ENDPOINT) { $env:GCC_CERTIFICATION_EMULATOR_ENDPOINT } else { "http://127.0.0.1:9000" }
        access_key = if ($env:GCC_CERTIFICATION_EMULATOR_ACCESS_KEY) { $env:GCC_CERTIFICATION_EMULATOR_ACCESS_KEY } else { "minioadmin" }
        secret_key = if ($env:GCC_CERTIFICATION_EMULATOR_SECRET_KEY) { $env:GCC_CERTIFICATION_EMULATOR_SECRET_KEY } else { "minioadmin" }
        bucket = if ($env:GCC_CERTIFICATION_EMULATOR_BUCKET) { $env:GCC_CERTIFICATION_EMULATOR_BUCKET } else { "gcc-certification" }
        region = if ($env:GCC_CERTIFICATION_EMULATOR_REGION) { $env:GCC_CERTIFICATION_EMULATOR_REGION } else { "us-east-1" }
    }
}

function Invoke-CertificationRun {
    param(
        [ValidateSet("Emulator", "Provider")][string]$Mode,
        [bool]$RunBrowser
    )

    $config = Get-StorageConfiguration $Mode
    $modeId = $Mode.ToLowerInvariant()
    $modeRoot = Join-Path $certificationRoot $modeId
    $databasePath = Join-Path $modeRoot "db.sqlite3"
    $mediaRoot = Join-Path $modeRoot "media"
    $reportPath = Join-Path $modeRoot "certification-report.json"
    $browserReportPath = Join-Path $modeRoot "browser-report.json"
    $artifactRoot = Join-Path $modeRoot "browser-artifacts"
    $prefix = "certification/$runId/$modeId"
    New-Item -ItemType Directory -Path $mediaRoot -Force | Out-Null

    $env:DJANGO_DEBUG = "true"
    $env:GCC_SIMULATION_MODE = "true"
    $env:GCC_DATABASE_PATH = $databasePath
    $env:GCC_MEDIA_ROOT = $mediaRoot
    $env:GCC_EXECUTION_LOOP_ENABLED = "true"
    $env:GCC_EXECUTION_LOOP_PROJECT_IDS = ""
    $env:GCC_EXECUTION_LOOP_USER_IDS = ""
    $env:GCC_AI_ENABLED = "false"
    $env:GCC_TURNSTILE_ENABLED = "false"
    $env:GCC_TURNSTILE_ALLOW_MISSING = "true"
    $env:GCC_NATIVE_MEDIA_ENABLED = "true"
    $env:GCC_EMAIL_DELIVERY_ENABLED = "false"
    $env:EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    $env:EXPO_PUSH_ENABLED = "false"
    $env:GCC_STORAGE_SMOKE_ENABLED = "true"
    $env:GCC_STORAGE_PREFIX = $prefix
    $env:USE_SUPABASE_STORAGE = "true"
    $env:SUPABASE_S3_ENDPOINT = $config.endpoint
    $env:SUPABASE_S3_ACCESS_KEY = $config.access_key
    $env:SUPABASE_S3_SECRET_KEY = $config.secret_key
    $env:SUPABASE_STORAGE_BUCKET = $config.bucket
    $env:SUPABASE_S3_REGION = $config.region

    try {
        Push-Location $websiteRoot
        try {
            Write-Host "[$Mode] Migrating isolated certification database: $databasePath"
            if ($Mode -eq "Emulator") {
                Invoke-Python manage.py prepare_certification_storage --create-if-missing
            }
            else {
                Invoke-Python manage.py prepare_certification_storage
            }
            Invoke-Python manage.py migrate --noinput
            Invoke-Python manage.py certify_operations --storage-mode $modeId --report $reportPath
        }
        finally {
            Pop-Location
        }

        $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
        $env:GCC_EXECUTION_LOOP_PROJECT_IDS = [string]$report.lifecycle.pilot.project_id
        $env:GCC_EXECUTION_LOOP_USER_IDS = (($report.lifecycle.pilot.user_ids.psobject.Properties | ForEach-Object { $_.Value }) -join ",")
        $serverProcess = $null
        try {
            if ($RunBrowser) {
                $serverLog = Join-Path $modeRoot "server.log"
                $serverErrorLog = Join-Path $modeRoot "server-error.log"
                $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @("manage.py", "runserver", "127.0.0.1:8001", "--noreload") -WorkingDirectory $websiteRoot -RedirectStandardOutput $serverLog -RedirectStandardError $serverErrorLog -WindowStyle Hidden -PassThru
                $ready = $false
                for ($attempt = 0; $attempt -lt 20; $attempt++) {
                    Start-Sleep -Milliseconds 500
                    try {
                        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/accounts/login/" -UseBasicParsing -TimeoutSec 2
                        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                            $ready = $true
                            break
                        }
                    }
                    catch {}
                }
                if (-not $ready) {
                    throw "Isolated certification server did not become ready. See $serverLog."
                }
                Push-Location $websiteRoot
                try {
                    & (Join-Path $websiteRoot "run_browser_smoke.ps1") -BaseUrl "http://127.0.0.1:8001" -ProjectId $report.lifecycle.pilot.project_id -ReportPath $browserReportPath -ArtifactDirectory $artifactRoot
                    if ($LASTEXITCODE -ne 0) {
                        throw "Browser smoke runner failed with exit code $LASTEXITCODE."
                    }
                }
                finally {
                    Pop-Location
                }
            }
            elseif ($Serve) {
                Push-Location $websiteRoot
                try {
                    Invoke-Python manage.py runserver 127.0.0.1:8001
                }
                finally {
                    Pop-Location
                }
            }
        }
        finally {
            if ($serverProcess -and -not $serverProcess.HasExited) {
                Stop-Process -Id $serverProcess.Id -Force
            }
        }

        $runResults.Add([ordered]@{
            mode = $Mode
            passed = $true
            report = $reportPath
            browser_report = if (Test-Path -LiteralPath $browserReportPath) { $browserReportPath } else { $null }
            project_id = [string]$report.lifecycle.pilot.project_id
            storage_prefix = $prefix
        })
    }
    finally {
        if (-not $Keep) {
            Push-Location $websiteRoot
            try {
                try {
                    Invoke-Python manage.py cleanup_certification_storage
                }
                catch {
                    Write-Warning "Certification storage cleanup failed for $prefix. Review the provider prefix before rerunning."
                }
            }
            finally {
                Pop-Location
            }
        }
    }
}

try {
    $modes = if ($StorageMode -eq "Both") { @("Emulator", "Provider") } else { @($StorageMode) }
    $browserPending = $Browser
    foreach ($mode in $modes) {
        Invoke-CertificationRun -Mode $mode -RunBrowser $browserPending
        $browserPending = $false
    }

    $overallReportPath = Join-Path $certificationRoot "certification-report.json"
    [ordered]@{
        scenario = "development-certification"
        passed = $true
        storage_mode = $StorageMode
        ai_enabled = $false
        runs = @($runResults)
        retained = [bool]$Keep
    } | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $overallReportPath -Encoding UTF8

    Write-Host ""
    Write-Host "Grand Coast development certification passed."
    Write-Host "Storage mode: $StorageMode"
    Write-Host "Overall report: $overallReportPath"
    foreach ($run in $runResults) {
        Write-Host "  $($run.mode): project $($run.project_id)"
    }
}
finally {
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $oldEnvironment[$name], "Process")
    }
    $resolvedRoot = [IO.Path]::GetFullPath($certificationRoot).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    if (-not $Keep -and $resolvedRoot.StartsWith($tempBase + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $resolvedRoot) {
            Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
        }
    }
    elseif ($Keep) {
        Write-Host "Retained certification root: $resolvedRoot"
    }
}
