<#
  SAM9X75-RDK PC Console — dev server launcher.

  Serves public\ with PHP's built-in web server. The live MJPEG is fetched by the
  browser DIRECTLY from the PIC64 (.38), so the single-threaded built-in server
  only ever handles short JSON/snapshot requests — fine for a home console.

  Usage:
    .\run.ps1                 # http://localhost:8080  (also reachable on the LAN)
    .\run.ps1 -Port 9000
    .\run.ps1 -Bind 127.0.0.1 # localhost only (default binds 0.0.0.0 so the board can reach the API)
#>
param(
  [int]$Port = 8080,
  [string]$Bind = "0.0.0.0"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- locate php.exe: local portable copy first (offline-first, R7), then PATH/common installs
$candidates = @(
  (Join-Path $root "php\php.exe"),
  "php",
  "C:\php\php.exe",
  "C:\xampp\php\php.exe",
  "C:\tools\php\php.exe"
)
$php = $null
foreach ($c in $candidates) {
  try {
    if ($c -eq "php") { if (Get-Command php -ErrorAction SilentlyContinue) { $php = "php"; break } }
    elseif (Test-Path $c) { $php = $c; break }
  } catch {}
}

if (-not $php) {
  Write-Host "PHP not found." -ForegroundColor Red
  Write-Host "Install once (internet needed only for this step):" -ForegroundColor Yellow
  Write-Host "  1. Download the Windows PHP zip (VS16/17 x64, Thread Safe) from https://windows.php.net/download/"
  Write-Host "  2. Extract into:  $root\php\   (so this file exists: $root\php\php.exe)"
  Write-Host "  3. In that php folder copy php.ini-development to php.ini and enable: extension=curl, extension=gd"
  Write-Host "  4. Re-run .\run.ps1"
  exit 1
}

# --- ensure the state file exists & is writable
$state = Join-Path $root "data\state.json"
if (-not (Test-Path $state)) {
  '{ "armed": false, "armed_at": 0, "motion_last": 0, "updated": 0, "events": [] }' |
    Out-File -Encoding utf8 $state
}

$docroot = Join-Path $root "public"
Write-Host "PHP:      $php" -ForegroundColor Green
& $php -v | Select-Object -First 1
Write-Host "Docroot:  $docroot"
Write-Host "Serving:  http://$Bind`:$Port   (login: see src\config.php)" -ForegroundColor Cyan
Write-Host "Camera:   MJPEG comes direct from the PIC64 at 192.168.0.38"
Write-Host "Stop:     Ctrl-C`n"

& $php -S "$Bind`:$Port" -t $docroot
