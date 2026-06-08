<#
.SYNOPSIS
    Pull the bot's run data (trades/positions/pnl CSVs + state.json + bot.log) from
    a VPS down to a local folder, then print a quick P&L summary.

.DESCRIPTION
    Run from your LOCAL PowerShell (not inside an SSH session). You'll be prompted
    for the server password. Lands everything in .\vps_data by default, separate
    from your local .\data so nothing is overwritten.

.EXAMPLE
    .\scripts\pull_vps_data.ps1
    .\scripts\pull_vps_data.ps1 -Server root@1.2.3.4 -RemotePath /home/claude/lol -Dest .\vps_data
#>
param(
    [string]$Server     = "root@72.60.98.54",
    [string]$RemotePath = "/home/claude/lol",
    [string]$Dest       = ".\vps_data"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "scp not found. Install the OpenSSH client (Windows: Settings > Apps > Optional Features > OpenSSH Client) or use WinSCP."
}

if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }

Write-Host "Pulling $Server`:$RemotePath  ->  $Dest" -ForegroundColor Cyan

# data/ contents (trades.csv, positions.csv, pnl.csv, state.json, sim/, ...)
scp -r "${Server}:${RemotePath}/data/*" "$Dest"
# full log (ignore failure if it doesn't exist)
try { scp "${Server}:${RemotePath}/logs/bot.log" "$Dest" } catch { Write-Host "(no bot.log)" -ForegroundColor DarkGray }

Write-Host "`nPulled files:" -ForegroundColor Green
Get-ChildItem -Recurse $Dest | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize

# Quick P&L summary from pnl.csv
$pnl = Join-Path $Dest "pnl.csv"
if (Test-Path $pnl) {
    $rows = @(Import-Csv $pnl)
    if ($rows.Count -gt 0) {
        $total = ($rows | ForEach-Object { [double]$_.realized_pnl } | Measure-Object -Sum).Sum
        $wins  = @($rows | Where-Object { [double]$_.realized_pnl -gt 0 }).Count
        $loss  = @($rows | Where-Object { [double]$_.realized_pnl -lt 0 }).Count
        Write-Host ("`nMarkets resolved: {0}   Wins: {1}   Losses: {2}   Total realized P&L: {3:+0.00;-0.00;0.00}" `
            -f $rows.Count, $wins, $loss, $total) -ForegroundColor Yellow
    } else {
        Write-Host "`npnl.csv has no resolved markets yet." -ForegroundColor DarkGray
    }
}
