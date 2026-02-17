#!/bin/bash
# One-time setup: create a Python venv on the VM for running migrations and other scripts
# (e.g. when Docker/python aren't available on the host.)
# Run from project root: bash scripts/setup_venv_on_vm.sh

set -e
cd "$(dirname "$0")/.."
PROJECT_ROOT="$PWD"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/venv}"

if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "Error: requirements.txt not found in $PROJECT_ROOT"
    exit 1
fi

echo "Using Python: $(python3 --version 2>/dev/null || echo 'python3 not found')"
if ! command -v python3 &>/dev/null; then
    echo "Install Python 3 first, e.g.: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

echo "Creating venv at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"
# Upgrade pip so install is smooth
"$VENV_DIR/bin/pip" install --upgrade pip
echo "Installing dependencies from requirements.txt ..."
"$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"

echo ""
echo "Done. To use the venv:"
echo "  source $VENV_DIR/bin/activate"
echo "  # Then run migrations (set ENVIRONMENT and DATABASE_URL_STAGING or DATABASE_URL_PROD first):"
echo "  python scripts/run_migrations.py"
echo ""
echo "Or run without activating: $VENV_DIR/bin/python scripts/run_migrations.py"
