#!/bin/bash
# Install Miniconda in WSL and create a conda env for zana_planner.
# Run from WSL: bash scripts/install_conda_wsl.sh
# Then: conda activate zana_planner

set -e

MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
INSTALL_DIR="${HOME}/miniconda3"
ENV_NAME="zana_planner"
PYTHON_VERSION="3.11"

# Resolve project root: prefer directory containing this script, else cwd (e.g. when run from /tmp)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../requirements.txt" ]; then
    PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    PROJECT_ROOT="$(pwd)"
fi
REQUIREMENTS="${PROJECT_ROOT}/requirements.txt"
if [ ! -f "${REQUIREMENTS}" ]; then
    echo "ERROR: requirements.txt not found at ${REQUIREMENTS}. Run from zana_planner or use: cd /mnt/c/workspace/zana/zana_planner && bash scripts/install_conda_wsl.sh"
    exit 1
fi

echo "[conda] Installing Miniconda to ${INSTALL_DIR}..."
if [ -f "${INSTALL_DIR}/bin/conda" ]; then
    echo "[conda] Miniconda already present at ${INSTALL_DIR}, skipping download."
else
    wget -q "${MINICONDA_URL}" -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p "${INSTALL_DIR}"
    rm -f /tmp/miniconda.sh
fi

# Initialize conda for bash (append to .bashrc if not already there)
CONDA_INIT=". \"${INSTALL_DIR}/etc/profile.d/conda.sh\""
if ! grep -q "miniconda3/etc/profile.d/conda.sh" "${HOME}/.bashrc" 2>/dev/null; then
    echo "" >> "${HOME}/.bashrc"
    echo "# Miniconda (zana_planner)" >> "${HOME}/.bashrc"
    echo "${CONDA_INIT}" >> "${HOME}/.bashrc"
    echo "conda activate ${ENV_NAME}  # optional: auto-activate zana env" >> "${HOME}/.bashrc"
    echo "[conda] Added conda init to ~/.bashrc"
fi

# Source conda in this script
# shellcheck source=/dev/null
. "${INSTALL_DIR}/etc/profile.d/conda.sh"

echo "[conda] Creating env '${ENV_NAME}' with Python ${PYTHON_VERSION} (if missing)..."
conda create -n "${ENV_NAME}" "python=${PYTHON_VERSION}" -y 2>/dev/null || true

echo "[conda] Activating and installing from requirements.txt..."
conda activate "${ENV_NAME}"
pip install --upgrade pip
pip install -r "${REQUIREMENTS}"

echo ""
echo "Done. To use the env in a new shell:"
echo "  source ~/miniconda3/etc/profile.d/conda.sh"
echo "  conda activate ${ENV_NAME}"
echo ""
echo "Run tests: bash scripts/run_tests.sh   (or: PYTHONPATH= python -m pytest tests/ -v)"
echo "Run bot:   python -m tm_bot.run_bot    (set env/DATABASE_URL etc.)"
