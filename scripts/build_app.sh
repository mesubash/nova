#!/usr/bin/env bash
# Build dist/NOVA.app from a clean state.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf build dist
pyinstaller --noconfirm --clean packaging/nova.spec
echo "Built: dist/NOVA.app"
