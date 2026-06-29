<#
.SYNOPSIS
  Timed director for a 2-minute dow chatbot demo screen recording.

.DESCRIPTION
  Opens a clean throwaway recording workspace, demonstrates `dow init`, copies in
  the chatbot demo, progressively types the runbook commands, starts the dashboard,
  runs the Playwright dashboard tour, then returns to CLI analysis commands.

  Start your screen recorder first, then run this script from the repository root:

    pwsh .\demo\recording\record_demo.ps1

  Optional:
    -KeepWorkspace leaves the temp workspace behind for debugging.
    -SkipDashboardTour skips Playwright browser automation.
        -TypingDelayMs controls per-character command typing speed.
        -CommandPauseScale stretches pauses after each command.
        -ShowDashboardServerWindow allows the background dashboard server window to show.

    Slower CLI example:
        pwsh .\demo\recording\record_demo.ps1 -TypingDelayMs 55 -CommandPauseScale 2.3
#>
param(
    [switch]$KeepWorkspace,
    [switch]$SkipDashboardTour,
    [int]$DashboardPort = 8131,
        [double]$TimeScale = 1.0,
        [int]$TypingDelayMs = 38,
        [double]$CommandPauseScale = 1.8,
        [switch]$ShowDashboardServerWindow
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$DemoRoot = Join-Path $RepoRoot "demo"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Timeline = Join-Path $PSScriptRoot "timeline.json"
$TourScript = Join-Path $PSScriptRoot "tour_dashboard.mjs"
$WorkRoot = Join-Path $env:TEMP ("dow_recording_" + (Get-Random))
$InitRoot = Join-Path $WorkRoot "init-demo"
$ChatbotRoot = Join-Path $WorkRoot "chatbot"

function Say-Step([string]$Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Wait-Demo([double]$Seconds) {
    if ($Seconds -le 0) { return }
    $milliseconds = [Math]::Max(1, [int]($Seconds * 1000 * $TimeScale))
    Start-Sleep -Milliseconds $milliseconds
}

function Invoke-TypedCommand([string]$Command, [double]$DelaySeconds = 1.4) {
    foreach ($ch in $Command.ToCharArray()) {
        Write-Host -NoNewline $ch
        Start-Sleep -Milliseconds ([Math]::Max(1, [int]($TypingDelayMs * $TimeScale)))
    }
    Write-Host ""
    Invoke-Expression $Command
    Wait-Demo ($DelaySeconds * $CommandPauseScale)
}

function Show-CleanHistory([string]$ExportPath = ".\recording-data.json") {
    Invoke-TypedCommand "dow dashboard --export $ExportPath" 0.4
    $data = Get-Content $ExportPath -Raw | ConvertFrom-Json
    Write-Host ""
    Write-Host "chatbot: behavior history" -ForegroundColor Cyan
    Write-Host "version  stability  tags          summary"
    Write-Host "-------  ---------  ------------  ------------------------------"
    foreach ($version in $data.versions) {
        $tags = if ($version.tags -and $version.tags.Count -gt 0) { $version.tags -join ", " } else { "-" }
        $summary = if ($version.summary) { $version.summary } else { "-" }
        $stability = if ($null -ne $version.metrics.stability) { [double]$version.metrics.stability } else { 0.0 }
        Write-Host ("{0,-7}  {1,-9}  {2,-12}  {3}" -f $version.id, ("{0:N3}" -f $stability), $tags, $summary)
    }
    Wait-Demo (0.9 * $CommandPauseScale)
}

function Set-SystemPrompt([string]$Prompt) {
    (Get-Content .\specs\chatbot.yaml) -replace '^\s*system:.*', "  system: $Prompt" |
        Set-Content .\specs\chatbot.yaml -Encoding utf8
}

function Set-Temperature([string]$Temperature) {
    (Get-Content .\specs\chatbot.yaml) -replace 'temperature: [0-9.]+', "temperature: $Temperature" |
        Set-Content .\specs\chatbot.yaml -Encoding utf8
}

try {
    if (!(Test-Path $Python)) {
        throw "Expected Python virtualenv at $Python. Run the install block from demo/RUNBOOK.md first."
    }

    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PATH = (Split-Path $Python) + [IO.Path]::PathSeparator + $env:PATH

    if (-not $SkipDashboardTour) {
        Push-Location $PSScriptRoot
        try {
            $playwrightCheck = node -e "import('playwright').then(()=>process.exit(0)).catch(()=>process.exit(1))"
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Playwright is not installed. Run: pwsh .\demo\recording\prepare_recording.ps1"
                Write-Warning "Continuing without automated dashboard navigation."
                $SkipDashboardTour = $true
            }
        }
        finally {
            Pop-Location
        }
    }

    New-Item $InitRoot -ItemType Directory -Force | Out-Null
    New-Item $ChatbotRoot -ItemType Directory -Force | Out-Null

    Clear-Host
    Write-Host "dow - 2 minute chatbot behavior demo" -ForegroundColor Green
    Write-Host "Timeline: $Timeline"
    Write-Host "Workspace: $WorkRoot"
    Wait-Demo 2

    Say-Step "dow init"
    Push-Location $InitRoot
    Invoke-TypedCommand "dow init chatbot" 1.0
    Pop-Location

    Say-Step "prepare chatbot project"
    Copy-Item (Join-Path $DemoRoot "chatbot.py") $ChatbotRoot
    Copy-Item (Join-Path $DemoRoot "evals.py") $ChatbotRoot
    New-Item (Join-Path $ChatbotRoot "specs") -ItemType Directory -Force | Out-Null
    Copy-Item (Join-Path $DemoRoot "specs\chatbot.yaml") (Join-Path $ChatbotRoot "specs\chatbot.yaml")
    Push-Location $ChatbotRoot
    Invoke-TypedCommand "Get-ChildItem -Name" 0.7

    Say-Step "commit versions"
    Invoke-TypedCommand "dow commit -m 'baseline ordering assistant'" 0.6
    Invoke-TypedCommand "dow tag baseline v1" 0.4

    Set-SystemPrompt "You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention."
    Invoke-TypedCommand "dow commit -m 'warm welcome and quote prices'" 0.4

    Set-SystemPrompt "You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order."
    Invoke-TypedCommand "dow commit -m 'confirm spice level'" 0.4

    Set-SystemPrompt "You are the ordering chatbot for Spice Route Biryani. Greet every customer warmly and always state the price of each dish you mention. Confirm the customer's spice level (mild, medium, or spicy) before taking the order. Recommend the chef's signature biryani and suggest a drink or dessert to pair."
    Invoke-TypedCommand "dow commit -m 'recommend special and suggest a pairing'" 0.4
    Invoke-TypedCommand "dow tag good v4" 0.25
    Invoke-TypedCommand "dow tag golden v4" 0.25

    Set-Temperature "0.9"
    Invoke-TypedCommand "dow commit -m 'stress-test high temperature'" 0.4
    Invoke-TypedCommand "dow tag bad v5" 0.25

    Set-Temperature "0.0"
    Invoke-TypedCommand "dow commit --from v4 -m 'deterministic release'" 0.4
    Invoke-TypedCommand "dow tag release v6" 0.5

    Say-Step "start dashboard and navigate"
    $dashOut = Join-Path $WorkRoot "dashboard.out.txt"
    $dashErr = Join-Path $WorkRoot "dashboard.err.txt"
    $dashArgs = @("-m", "dow", "dashboard", "--port", "$DashboardPort", "--no-open")
    $startInfo = @{
        FilePath = $Python
        ArgumentList = $dashArgs
        WorkingDirectory = $ChatbotRoot
        PassThru = $true
        RedirectStandardOutput = $dashOut
        RedirectStandardError = $dashErr
    }
    if (-not $ShowDashboardServerWindow) {
        $startInfo.WindowStyle = "Hidden"
    }
    $dash = Start-Process @startInfo
    Wait-Demo 2

    if (-not $SkipDashboardTour) {
        if (Test-Path $TourScript) {
            try {
                node $TourScript "http://127.0.0.1:$DashboardPort/"
            } catch {
                Write-Warning "Dashboard tour failed; continue manually for this segment. $_"
                Wait-Demo 36
            }
        } else {
            Write-Warning "Dashboard tour script not found: $TourScript"
            Wait-Demo 36
        }
    } else {
        Wait-Demo 36
    }

    Say-Step "CLI analysis"
    Set-Temperature "0.5"
    Invoke-TypedCommand "dow eval --draft" 1.0
    Set-Temperature "0.0"
    Invoke-TypedCommand "dow eval" 0.8
    Show-CleanHistory
    Invoke-TypedCommand "dow inspect golden" 0.8
    Invoke-TypedCommand "dow compare baseline golden" 0.8
    Invoke-TypedCommand "dow explain v3 v4" 0.8
    Invoke-TypedCommand "dow explain v4 v5" 0.8
    Invoke-TypedCommand "dow tree" 0.8
    Invoke-TypedCommand "dow tree -o evolution.md" 0.8

    Say-Step "end card"
    Write-Host "dow" -ForegroundColor Green
    Write-Host "Version control for AI behavior"
    Write-Host "Dashboard + CLI for prompts, settings, outputs, metrics, drift, and lineage."
    Wait-Demo 6
}
finally {
    if ($dash -and -not $dash.HasExited) {
        Stop-Process -Id $dash.Id -Force -ErrorAction SilentlyContinue
    }
    Pop-Location -ErrorAction SilentlyContinue
    if (-not $KeepWorkspace -and (Test-Path $WorkRoot)) {
        Remove-Item $WorkRoot -Recurse -Force -ErrorAction SilentlyContinue
    } elseif (Test-Path $WorkRoot) {
        Write-Host "Kept recording workspace: $WorkRoot" -ForegroundColor Yellow
    }
}
