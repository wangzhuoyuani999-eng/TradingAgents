# Restart the DeepSeek Harness desktop app so the edited trading-desk plugin reloads.
# Runs detached from the app itself: wait, stop, relaunch, log the outcome.
$ErrorActionPreference = 'Stop'
$exe = 'D:\workspace\app\dsh\DeepSeek Harness.exe'
$log = 'D:\workspace\trading\TradingAgents\logs_ashare\restart.log'

function Write-Log([string]$message) {
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message" | Out-File -FilePath $log -Append -Encoding UTF8
}

Write-Log 'restart scheduled, waiting 25s'
Start-Sleep -Seconds 25

try {
  $apps = Get-Process | Where-Object { $_.Path -eq $exe }
  Write-Log ("stopping " + ($apps.Id -join ','))
  $apps | Stop-Process -Force
} catch {
  Write-Log "stop failed: $($_.Exception.Message)"
}

Start-Sleep -Seconds 4
try {
  Start-Process -FilePath $exe
  Write-Log 'relaunched'
} catch {
  Write-Log "relaunch failed: $($_.Exception.Message)"
}
