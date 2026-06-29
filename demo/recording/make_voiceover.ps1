<#
.SYNOPSIS
  Generate a text-to-speech WAV voiceover for the 2-minute demo timeline.

.USAGE
  pwsh .\demo\recording\make_voiceover.ps1
  pwsh .\demo\recording\make_voiceover.ps1 -VoiceName "Microsoft Zira Desktop"

.OUTPUT
  demo\recording\voiceover.wav
#>
param(
    [string]$TimelinePath = (Join-Path $PSScriptRoot "timeline.json"),
    [string]$OutPath = (Join-Path $PSScriptRoot "voiceover.wav"),
    [string]$VoiceName = "",
    [int]$Rate = 0,
    [int]$Volume = 100
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech

$timeline = Get-Content $TimelinePath -Raw | ConvertFrom-Json
$text = ($timeline | ForEach-Object { $_.voiceover }) -join "`r`n`r`n"

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($VoiceName) {
    $synth.SelectVoice($VoiceName)
}
$synth.Rate = $Rate
$synth.Volume = $Volume
$synth.SetOutputToWaveFile($OutPath)
$synth.Speak($text)
$synth.SetOutputToDefaultAudioDevice()
$synth.Dispose()

Write-Host "Wrote $OutPath"
Write-Host "Available voices:"
$voices = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices.GetInstalledVoices() | ForEach-Object { "- " + $_.VoiceInfo.Name }
$voices.Dispose()
