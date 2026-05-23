import re
from pathlib import Path

root = Path(r"c:/workspace/Zana/zana_planner/webapp_frontend/src")
for path in root.rglob("*.tsx"):
    text = path.read_text(encoding="utf-8")
    fixed = re.sub(r"</motion-safe-[a-zA-Z-]+>", "</div>", text)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8")
        print(f"fixed {path}")
