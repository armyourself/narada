# Lattice — Windows installer
# Sets up the Lattice node (Python 3.13 + uv) and the desktop client
# (Bun + Tauri + Rust toolchain). Intended to be run from a developer shell.
#
# Usage (from repo root):
#   pwsh -File scripts/install.ps1

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Error "Missing required tool: $Name. $InstallHint"
    }
}

Write-Host "Checking prerequisites..."

Require-Command -Name "uv"     -InstallHint "Install from https://github.com/astral-sh/uv"
Require-Command -Name "bun"    -InstallHint "Install from https://bun.sh"
Require-Command -Name "rustup" -InstallHint "Install from https://tauri.app/start/prerequisites/"

Write-Host "Installing Lattice node..."
Push-Location node
try {
    uv sync
} finally {
    Pop-Location
}
Write-Host "  -> node ready."

Write-Host "Installing Lattice desktop client..."
Push-Location client
try {
    bun install
} finally {
    Pop-Location
}
Write-Host "  -> client ready."

Write-Host ""
Write-Host "Installation complete."
Write-Host "To run the node:  cd node;    uv run python -m src.main"
Write-Host "To run the client: cd client; bun run tauri dev"
