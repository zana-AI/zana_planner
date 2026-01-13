"""
Version tracking for Xaana AI bot.
Reads version from git, environment variable, or VERSION file.
Formats version as vx.y.z starting from v1.0.0
"""
from __future__ import annotations

import os
import subprocess
import re
import sys
import platform
import json
from pathlib import Path
from datetime import datetime, timezone

# Process start time (module import time) for uptime reporting.
_STARTED_AT_UTC = datetime.now(timezone.utc)


def _find_git_root(start_dir: Path) -> Path | None:
    """Find the nearest parent directory containing a .git folder."""
    try:
        start_dir = start_dir.resolve()
    except Exception:
        pass

    for p in [start_dir, *start_dir.parents]:
        try:
            if (p / ".git").exists():
                return p
        except Exception:
            continue
    return None


def _run_git(args: list[str], cwd: Path, timeout: float = 2.0) -> str | None:
    """Run a git command and return stdout (stripped) or None."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        if result.returncode != 0:
            return None
        out = (result.stdout or "").strip()
        return out or None
    except Exception:
        return None


def _safe_iso_date(date_str: str | None) -> str | None:
    """
    Convert git %ci or other date-like strings to YYYY-MM-DD.
    Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        # git %ci looks like: "2025-12-22 10:11:12 +0000"
        return (date_str.split()[0] or "").strip() or None
    except Exception:
        return None


def _fs_last_modified_date(root: Path, max_files: int = 8000) -> str | None:
    """
    Best-effort 'last update' based on newest mtime under root.
    Bounded to avoid expensive scans.
    """
    ignore_dirs = {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
        ".idea",
        ".vscode",
        ".ruff_cache",
    }
    exts = {
        ".py",
        ".yml",
        ".yaml",
        ".toml",
        ".json",
        ".txt",
        ".md",
        ".ini",
        ".cfg",
        ".sh",
        ".ps1",
        ".bat",
        ".cmd",
    }
    try:
        newest = 0.0
        seen = 0
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories in-place.
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]

            for fn in filenames:
                if seen >= max_files:
                    break
                seen += 1

                # Keep scan focused on "code-like" files.
                if fn == "Dockerfile" or fn.lower().endswith(tuple(exts)):
                    fpath = Path(dirpath) / fn
                    try:
                        mtime = fpath.stat().st_mtime
                        if mtime > newest:
                            newest = mtime
                    except Exception:
                        continue
            if seen >= max_files:
                break

        if newest <= 0:
            return None
        return datetime.fromtimestamp(newest, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None

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
    git_root = _find_git_root(Path(__file__).parent)
    if git_root:
        tag = _run_git(["describe", "--tags", "--abbrev=0"], cwd=git_root)
        if tag:
            try:
                x, y, z = _parse_version_tag(tag)
                return _format_version(x, y, z)
            except Exception:
                pass
    
    # Try to get all tags and find the highest version
    if git_root:
        tags_out = _run_git(["tag", "-l", "v*"], cwd=git_root)
        if tags_out:
            tags = [t.strip() for t in tags_out.splitlines() if t.strip()]
            max_version = (1, 0, 0)
            for tag in tags:
                try:
                    parsed = _parse_version_tag(tag)
                    if parsed > max_version:
                        max_version = parsed
                except Exception:
                    continue
            return _format_version(*max_version)
    
    # Try git commit hash (return v1.0.0 with commit info)
    if git_root:
        commit = _run_git(["rev-parse", "--short", "HEAD"], cwd=git_root)
        if commit:
            return f"v1.0.0+{commit}"
    
    # Fallback to v1.0.0
    return "v1.0.0"

def get_last_update_date() -> str:
    """Get the last update date from git (last commit date or tag date)."""
    repo_path = Path(__file__).parent.parent.parent
    git_root = _find_git_root(repo_path)
    if git_root:
        commit_date = _run_git(["show", "-s", "--format=%ci", "HEAD"], cwd=git_root)
        iso = _safe_iso_date(commit_date)
        if iso:
            return iso

    # Fallback to filesystem newest mtime date
    fs_date = _fs_last_modified_date(repo_path)
    return fs_date or "unknown"


def _load_commit_info() -> dict | None:
    """
    Load commit info from COMMIT_INFO.json file if it exists.
    Returns dict with commit, message, author, date, or None if file doesn't exist.
    """
    commit_info_path = Path("/app/COMMIT_INFO.json")
    if not commit_info_path.exists():
        # Try relative to current file (for local development)
        commit_info_path = Path(__file__).parent.parent.parent / "COMMIT_INFO.json"
        if not commit_info_path.exists():
            return None
    
    try:
        with open(commit_info_path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def _get_git_status_summary(git_root: Path) -> dict:
    """Return a compact git status-like summary."""
    info: dict = {"available": True, "root": str(git_root)}

    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    if branch:
        info["branch"] = branch

    head_full = _run_git(["rev-parse", "HEAD"], cwd=git_root)
    if head_full:
        info["head"] = head_full
        info["head_short"] = head_full[:7]

    commit_date = _run_git(["show", "-s", "--format=%ci", "HEAD"], cwd=git_root)
    if commit_date:
        info["commit_date"] = commit_date
        iso = _safe_iso_date(commit_date)
        if iso:
            info["commit_date_iso"] = iso

    subject = _run_git(["show", "-s", "--format=%s", "HEAD"], cwd=git_root)
    if subject:
        info["subject"] = subject

    # Porcelain status for "dirty" detection.
    porcelain = _run_git(["status", "--porcelain=v1"], cwd=git_root)
    lines = [ln for ln in (porcelain.splitlines() if porcelain else []) if ln.strip()]
    changed = [ln for ln in lines if not ln.startswith("??")]
    untracked = [ln for ln in lines if ln.startswith("??")]
    info["dirty"] = bool(lines)
    info["changed_files"] = len(changed)
    info["untracked_files"] = len(untracked)
    if lines:
        info["status_sample"] = "\n".join(lines[:20])

    # Ahead/behind relative to upstream (best-effort).
    upstream = _run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=git_root)
    if upstream:
        info["upstream"] = upstream
        counts = _run_git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], cwd=git_root)
        if counts and "\t" in counts:
            behind, ahead = counts.split("\t", 1)
            try:
                info["behind"] = int(behind)
                info["ahead"] = int(ahead)
            except Exception:
                pass

    return info

def get_version_info() -> dict:
    """Get detailed version information."""
    version = get_version()
    last_update = get_last_update_date()

    repo_path = Path(__file__).parent.parent.parent
    build_date = os.getenv("BUILD_DATE") or os.getenv("SOURCE_DATE_EPOCH")
    if build_date and build_date.isdigit():
        try:
            build_date = datetime.fromtimestamp(int(build_date), tz=timezone.utc).isoformat()
        except Exception:
            pass

    now_utc = datetime.now(timezone.utc)
    uptime_seconds = int((now_utc - _STARTED_AT_UTC).total_seconds())

    info = {
        "version": version,
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "last_update": last_update,
        "repo_path": str(repo_path),
        "started_at_utc": _STARTED_AT_UTC.isoformat(),
        "uptime_seconds": uptime_seconds,
        "host": os.getenv("HOSTNAME") or platform.node() or "unknown",
        "pid": os.getpid(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "build_date": build_date or os.getenv("BUILD_AT") or os.getenv("RELEASE_DATE"),
    }

    # Load commit info from COMMIT_INFO.json (build-time metadata)
    commit_info = _load_commit_info()
    if commit_info:
        info["commit_message"] = commit_info.get("message", "")
        info["commit_author"] = commit_info.get("author", "")
        commit_date_str = commit_info.get("date", "")
        if commit_date_str:
            # Format commit date: "2025-12-31 10:30:00 +0000" -> "2025-12-31 10:30:00 UTC"
            try:
                # Parse git date format: "2025-12-31 10:30:00 +0000"
                parts = commit_date_str.split()
                if len(parts) >= 2:
                    date_part = parts[0]
                    time_part = parts[1]
                    info["commit_date"] = f"{date_part} {time_part} UTC"
                else:
                    info["commit_date"] = commit_date_str
            except Exception:
                info["commit_date"] = commit_date_str
        else:
            info["commit_date"] = None
        # Also set commit hash if available
        if commit_info.get("commit"):
            info["commit"] = commit_info.get("commit")

    # Git status-like metadata (best-effort, for local development).
    git_root = _find_git_root(repo_path)
    if git_root:
        git_info = _get_git_status_summary(git_root)
        info["git"] = git_info
        # Back-compat fields used by older /version formatting.
        # Only set if not already set from COMMIT_INFO.json
        if git_info.get("head_short") and "commit" not in info:
            info["commit"] = git_info["head_short"]
        if git_info.get("subject") and "commit_message" not in info:
            info["commit_message"] = str(git_info["subject"])[:50]
        if (not info.get("last_update") or info["last_update"] == "unknown") and git_info.get("commit_date_iso"):
            info["last_update"] = git_info["commit_date_iso"]
    else:
        info["git"] = {"available": False}

    return info
