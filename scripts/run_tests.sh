#!/bin/bash
# Run pytest for zana_planner. Clears PYTHONPATH so system packages (e.g. ROS)
# do not inject plugins that break the run. Use from project root:
#   bash scripts/run_tests.sh
#   bash scripts/run_tests.sh tests/learning_pipeline -v

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT"
# Avoid loading pytest plugins from ROS or other system Python (e.g. launch_testing)
export PYTHONPATH=""
exec python -m pytest "$@"
