param([string]$SkillsDir)
$ErrorActionPreference = 'Stop'
if (-not $SkillsDir) {
    $codexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    $SkillsDir = Join-Path $codexRoot 'skills'
}
$source = Join-Path $PSScriptRoot 'skills\ai-meeting'
$target = Join-Path $SkillsDir 'ai-meeting'
$files = @('SKILL.md', 'scripts\meeting.py')
foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $relative) -PathType Leaf)) {
        throw "Missing skill source: $relative"
    }
}
$backup = Join-Path (Split-Path -Parent $SkillsDir) ('skill-backups\ai-meeting\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
foreach ($relative in $files) {
    $from = Join-Path $source $relative
    $to = Join-Path $target $relative
    if (Test-Path -LiteralPath $to -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $from).Hash -eq (Get-FileHash -LiteralPath $to).Hash) { continue }
        $saved = Join-Path $backup $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $saved) -Force | Out-Null
        Copy-Item -LiteralPath $to -Destination $saved
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $to) -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $to -Force
}
Write-Output "Codex meeting skill installed: $target"
Write-Output 'If an existing Codex chat does not discover the skill, open a new chat or reload Codex.'
