param([switch]$Restart)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$port = if ($env:MEETING_PORT) { $env:MEETING_PORT } else { "7720" }
$url = "http://127.0.0.1:$port/"
$running = $false
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "${url}api/rooms" | Out-Null; $running = $true } catch {}
if ($running -and -not $Restart) { Write-Output "already running: $url"; exit 0 }
if ($running) {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Method Post -ContentType "application/json" -Body "{}" "${url}api/shutdown" | Out-Null } catch {}
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 "${url}api/rooms" | Out-Null } catch { break }
    }
}

$py = $null
$store = $null
$cands = @($env:MEETING_PYTHON, "$env:LOCALAPPDATA\Python\bin\python.exe") + @("python3", "python", "py" | ForEach-Object { (Get-Command $_ -ErrorAction SilentlyContinue).Source })
foreach ($c in $cands) {
    if (-not $c -or -not (Test-Path $c)) { continue }
    $exe = & $c -c "import sys; print(sys.executable if sys.version_info >= (3, 9) else '')" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $exe) { continue }
    if ("$exe" -match "WindowsApps") { if (-not $store) { $store = $c }; continue }
    $py = $exe; break
}
if (-not $py) { $py = $store }
if (-not $py) { Write-Error "Python 3.9+ not found"; exit 1 }

$home_ = if ($env:MEETING_HOME) { $env:MEETING_HOME } else { Join-Path $env:LOCALAPPDATA "ai-meeting-room" }
New-Item -ItemType Directory -Force $home_ | Out-Null
Start-Process -FilePath $py -ArgumentList "-u", "`"$(Join-Path $PSScriptRoot 'hub.py')`"" -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $home_ "hub.log") -RedirectStandardError (Join-Path $home_ "hub.err.log")
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "${url}api/rooms" | Out-Null; Write-Output "started: $url"; exit 0 } catch {}
}
Write-Error "did not start in time; see $home_\hub.err.log"
exit 1
