# scripts/

Cross-platform development and installation scripts for Narada.

- `install.ps1` — Windows installer (PowerShell). Sets up the Narada node
  (Python 3.13 + uv) and the desktop client (Bun + Tauri + Rust toolchain).
- `dev.ps1` — convenience launcher: starts the node and the desktop client in
  development mode.

The legacy `install.sh` in the repo root is preserved for Linux/macOS users
and will eventually be moved here as `install.sh` once the restructure
stabilises.
