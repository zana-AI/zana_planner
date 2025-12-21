"""
Version tracking for Zana AI bot.
Reads version from git, environment variable, or VERSION file.
"""
import os
import subprocess
from pathlib import Path

def get_version() -> str:
    """
    Get the current version of the bot.
    Priority:
    1. VERSION environment variable
    2. Git tag (latest)
    3. Git commit hash (short)
    4. VERSION file in project root
    5. Default fallback
    """
    # Try environment variable first
    version = os.getenv("BOT_VERSION")
    if version:
        return version
    
    # Try to read from VERSION file
    version_file = Path("/app/VERSION")
    if not version_file.exists():
        # Try relative to current file
        version_file = Path(__file__).parent.parent.parent / "VERSION"
    
    if version_file.exists():
        try:
            with open(version_file, 'r') as f:
                version = f.read().strip()
            if version:
                return version
        except Exception:
            pass
    
    # Try git tag (latest)
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    
    # Try git commit hash
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"dev-{result.stdout.strip()}"
    except Exception:
        pass
    
    # Fallback
    return "unknown"

def get_version_info() -> dict:
    """Get detailed version information."""
    version = get_version()
    
    info = {
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "unknown"),
    }
    
    # Try to get git commit info
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H|%ci|%s"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|")
            if len(parts) >= 3:
                info["commit"] = parts[0][:7]
                info["date"] = parts[1]
                info["message"] = parts[2][:50]
    except Exception:
        pass
    
    return info
