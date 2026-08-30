# Lattice — dev launcher
# Starts the Lattice node and the desktop client in development mode.
# Two terminal windows are spawned so you can see each process's logs.
#
# Usage (from repo root):
#   pwsh -File scripts/dev.ps1

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")

Write-Host "Starting Lattice node in a new window..."
Start-Process -FilePath "pwsh" -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$root/node`"; uv run python -m src.main"
) -WorkingDirectory $root

Write-Host "Starting Lattice desktop client in a new window..."
Start-Process -FilePath "pwsh" -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$root/client`"; bun run tauri dev"
) -WorkingDirectory $root

Write-Host "Both processes launched. Close their windows to stop."
