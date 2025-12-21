"""
Version tracking for Zana AI bot.
Reads version from git, environment variable, or VERSION file.
Formats version as vx.y.z starting from v1.0.0
"""
import os
import subprocess
import re
from pathlib import Path
from datetime import datetime

def _parse_version_tag(tag: str) -> tuple:
    """
    Parse version tag and return (x, y, z) tuple.
    Handles formats like: v1.0.0, 1.0.0, v1.0.1, etc.
    """
    # Remove 'v' prefix if present
    tag = tag.lstrip('v')
    
    # Extract version numbers
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', tag)
    if match:
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    
    # If no match, try to extract any numbers
    numbers = re.findall(r'\d+', tag)
    if len(numbers) >= 3:
        return (int(numbers[0]), int(numbers[1]), int(numbers[2]))
    elif len(numbers) == 2:
        return (int(numbers[0]), int(numbers[1]), 0)
    elif len(numbers) == 1:
        return (int(numbers[0]), 0, 0)
    
    # Default to 1.0.0
    return (1, 0, 0)

def _format_version(x: int, y: int, z: int) -> str:
    """Format version as vx.y.z"""
    return f"v{x}.{y}.{z}"

def get_version() -> str:
    """
    Get the current version of the bot in vx.y.z format.
    Priority:
    1. VERSION environment variable
    2. Git tag (latest, formatted as vx.y.z)
    3. Git commit hash (short) - returns v1.0.0+commit
    4. VERSION file in project root
    5. Default: v1.0.0
    """
    # Try environment variable first
    version = os.getenv("BOT_VERSION")
    if version:
        # Try to parse and format it
        try:
            x, y, z = _parse_version_tag(version)
            return _format_version(x, y, z)
        except Exception:
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
                try:
                    x, y, z = _parse_version_tag(version)
                    return _format_version(x, y, z)
                except Exception:
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
            tag = result.stdout.strip()
            x, y, z = _parse_version_tag(tag)
            return _format_version(x, y, z)
    except Exception:
        pass
    
    # Try to get all tags and find the highest version
    try:
        result = subprocess.run(
            ["git", "tag", "-l", "v*"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            tags = result.stdout.strip().split('\n')
            # Parse all tags and find the highest version
            max_version = (1, 0, 0)
            for tag in tags:
                try:
                    parsed = _parse_version_tag(tag)
                    # Compare: (x, y, z) tuple comparison works correctly
                    if parsed > max_version:
                        max_version = parsed
                except Exception:
                    continue
            
            return _format_version(*max_version)
    except Exception:
        pass
    
    # Try git commit hash (return v1.0.0 with commit info)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).parent.parent.parent
        )
        if result.returncode == 0 and result.stdout.strip():
            commit = result.stdout.strip()
            return f"v1.0.0+{commit}"
    except Exception:
        pass
    
    # Fallback to v1.0.0
    return "v1.0.0"

def get_last_update_date() -> str:
    """Get the last update date from git (last commit date or tag date)."""
    repo_path = Path(__file__).parent.parent.parent
    
    # Try to get date from latest tag
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "--tags", "--"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repo_path
        )
        if result.returncode == 0 and result.stdout.strip():
            date_str = result.stdout.strip()
            # Parse and format date
            try:
                dt = datetime.fromisoformat(date_str.replace(' ', 'T', 1).split()[0])
                return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
    except Exception:
        pass
    
    # Fallback to last commit date
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=repo_path
        )
        if result.returncode == 0 and result.stdout.strip():
            date_str = result.stdout.strip()
            try:
                # Parse ISO format date
                dt = datetime.fromisoformat(date_str.replace(' ', 'T', 1).split()[0])
                return dt.strftime("%Y-%m-%d")
            except Exception:
                # Try alternative parsing
                try:
                    dt = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
                    return dt.strftime("%Y-%m-%d")
                except Exception:
                    return date_str.split()[0] if date_str else "unknown"
    except Exception:
        pass
    
    return "unknown"

def get_version_info() -> dict:
    """Get detailed version information."""
    version = get_version()
    last_update = get_last_update_date()
    
    info = {
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "last_update": last_update,
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
                if not info.get("last_update") or info["last_update"] == "unknown":
                    # Use commit date if tag date not available
                    try:
                        date_str = parts[1]
                        dt = datetime.fromisoformat(date_str.replace(' ', 'T', 1).split()[0])
                        info["last_update"] = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass
                info["message"] = parts[2][:50]
    except Exception:
        pass
    
    return info
