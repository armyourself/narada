.PHONY: help install install-win run-node run-client test-node

help:
	@echo "narada — available targets:"
	@echo "  make install      Install node + client (Linux/macOS, via install.sh)"
	@echo "  make install-win  Install node + client on Windows (scripts/install.ps1)"
	@echo "  make run-node     Run the narada node (Python)"
	@echo "  make run-client   Run the narada desktop client (Bun + Tauri)"
	@echo "  make test-node    Run the narada node test suite (pytest)"

install:
	./install.sh

install-win:
	pwsh -File scripts/install.ps1

run-node:
	cd node && uv run -m src.main

run-client:
	cd client && bun run tauri dev

test-node:
	cd node && uv run pytest
