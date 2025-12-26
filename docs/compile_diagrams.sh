#!/bin/bash
# Script to compile PlantUML diagrams to SVG
# Requires: plantuml (install via: brew install plantuml, apt-get install plantuml, or download jar)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIAGRAMS_DIR="${SCRIPT_DIR}/diagrams"
OUTPUT_DIR="${SCRIPT_DIR}/diagrams/svg"

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

# Check if plantuml is available
if ! command -v plantuml &> /dev/null; then
    echo "Error: plantuml command not found."
    echo "Install PlantUML:"
    echo "  - macOS: brew install plantuml"
    echo "  - Ubuntu/Debian: sudo apt-get install plantuml"
    echo "  - Or download jar from https://plantuml.com/download"
    exit 1
fi

echo "Compiling PlantUML diagrams to SVG..."
echo "Source: ${DIAGRAMS_DIR}"
echo "Output: ${OUTPUT_DIR}"
echo ""

# Compile all .puml files to SVG
for puml_file in "${DIAGRAMS_DIR}"/*.puml; do
    if [ -f "$puml_file" ]; then
        filename=$(basename "$puml_file" .puml)
        echo "Compiling: ${filename}.puml -> ${filename}.svg"
        plantuml -tsvg -o "${OUTPUT_DIR}" "$puml_file"
    fi
done

echo ""
echo "Done! SVG files are in ${OUTPUT_DIR}"

