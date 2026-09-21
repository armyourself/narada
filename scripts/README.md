# scripts/

Cross-platform development and installation scripts.

- `install.ps1` — Windows installer (PowerShell). Sets up the server
  (Python 3.13 + uv) and the desktop client (Bun + Tauri + Rust toolchain).
- `dev.ps1` — convenience launcher: starts the server and the desktop client in
  development mode.

The `install.sh` in the repo root is preserved for Linux/macOS users.
