<#
  deploy.ps1 - push the console to the RDK board and (re)start it.

    .\deploy.ps1                  # sync files only
    .\deploy.ps1 -Run             # sync, then run in the foreground (Ctrl-C to stop)
    .\deploy.ps1 -Restart         # sync, then restart the background service
    .\deploy.ps1 -Install         # sync + install the boot init script
    .\deploy.ps1 -Board 192.168.0.99

  S40rdk-net gives the board a static address (192.168.0.39), so it behaves
  the same on the LAN and over a direct cable to the PIC64.  Pass -Board if
  you change it; the serial fallback is Workshop\rdk-serial.ps1.
#>
[CmdletBinding()]
param(
  [string]$Board = "192.168.0.39",
  [string]$Dest = "/opt/rdk-console",
  [switch]$Run,
  [switch]$Restart,
  [switch]$Install,
  [switch]$SyncTime
)

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "board"
$sshArgs = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")

function Board-Exec([string]$cmd) {
  & ssh @sshArgs "root@$Board" $cmd
  if ($LASTEXITCODE -ne 0) { throw "remote command failed ($LASTEXITCODE): $cmd" }
}

Write-Host "==> syncing $src -> ${Board}:$Dest"
Board-Exec "mkdir -p $Dest"
& scp @sshArgs (Join-Path $src "*.py") "root@${Board}:$Dest/"
if ($LASTEXITCODE -ne 0) { throw "scp failed" }

if ($SyncTime) {
  # The board has no RTC and no NTP client, so the status-line clock is wrong
  # until something sets it.  Push the PC's time (UTC, as the board runs UTC).
  $now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss")
  Write-Host "==> setting board clock to $now UTC"
  Board-Exec "date -u -s '$now'"
}

if ($Install) {
  # S40 brings up the network (static IP + sshd), S99 starts the console.
  Write-Host "==> installing boot init scripts"
  foreach ($s in @("S40rdk-net", "S99rdk-console")) {
    & scp @sshArgs (Join-Path $PSScriptRoot $s) "root@${Board}:/etc/init.d/$s"
    if ($LASTEXITCODE -ne 0) { throw "scp of $s failed" }
    Board-Exec "chmod +x /etc/init.d/$s"
    Write-Host "    $s"
  }
  Write-Host "    installed - active on next boot (or use -Restart now)"
}

if ($Restart) {
  # This busybox has no pkill/pgrep - the init script tracks the pidfile.
  Write-Host "==> restarting console"
  Board-Exec "/etc/init.d/S99rdk-console restart"
  Start-Sleep -Seconds 3
  Board-Exec "/etc/init.d/S99rdk-console status || tail -20 /tmp/rdk-console.log"
}

if ($Run) {
  Write-Host "==> running in foreground (Ctrl-C to stop)"
  Board-Exec "/etc/init.d/S99rdk-console stop 2>/dev/null; fuser -k /dev/dri/card1 2>/dev/null; sleep 1; cd $Dest && python3 console.py"
}

if (-not ($Run -or $Restart -or $Install)) {
  Write-Host "==> synced. Start it with:  .\deploy.ps1 -Restart   (or -Run)"
}
