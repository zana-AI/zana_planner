# Documentation

This folder contains documentation for the Zana AI bot system.

## Structure

- `diagrams/` - PlantUML source files (`.puml`)
- `diagrams/svg/` - Compiled SVG diagrams (generated)
- `chat_flow.md` - Main documentation with embedded SVG references

## Compiling Diagrams

The diagrams are stored as PlantUML (`.puml`) files in the `diagrams/` folder. To generate SVG files:

### Prerequisites

Install PlantUML:
- **macOS**: `brew install plantuml`
- **Ubuntu/Debian**: `sudo apt-get install plantuml`
- **Windows**: `choco install plantuml`
- **Or download JAR**: https://plantuml.com/download

### Compilation

**Linux/macOS:**
```bash
cd docs
./compile_diagrams.sh
```

**Windows (PowerShell):**
```powershell
cd docs
.\compile_diagrams.ps1
```

**Manual:**
```bash
plantuml -tsvg -o diagrams/svg diagrams/*.puml
```

## Adding New Diagrams

1. Create a new `.puml` file in `diagrams/`
2. Run the compilation script
3. Add a reference to the SVG in `chat_flow.md`:
   ```markdown
   ![Diagram Name](diagrams/svg/diagram_name.svg)
   ```

