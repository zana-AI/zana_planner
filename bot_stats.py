#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List

def is_user_dir(name: str) -> bool:
    return name.isdigit()

def file_info(path: str) -> Dict:
    try:
        st = os.stat(path)
        return {"exists": True, "bytes": st.st_size, "mtime": datetime.fromtimestamp(st.st_mtime)}
    except FileNotFoundError:
        return {"exists": False, "bytes": 0, "mtime": None}

def count_users(data_dir: str) -> List[str]:
    try:
        return sorted([d for d in os.listdir(data_dir) if is_user_dir(d) and os.path.isdir(os.path.join(data_dir, d))])
    except FileNotFoundError:
        return []

def active_within(mtime: datetime, window_days: int, now: datetime) -> bool:
    if not mtime:
        return False
    return (now - mtime) <= timedelta(days=window_days)

def main():
    parser = argparse.ArgumentParser(description="Privacy-friendly usage stats for Zana Planner bot.")
    parser.add_argument("data_dir", help="Path to USERS_DATA_DIR")
    parser.add_argument("--threshold-bytes", type=int, default=12,
                        help="Minimum bytes to consider a CSV as non-empty (default: 12)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args()

    users = count_users(args.data_dir)
    now = datetime.now()

    total_users = len(users)
    users_with_promises = 0
    users_with_actions = 0

    # activity windows (based on actions.csv mtime)
    windows = [7, 30, 90, 365]
    active_counts = {f"{d}d": 0 for d in windows}

    # optional extra: brand-new users (based on folder mtime)
    new_counts = {f"{d}d": 0 for d in [7, 30]}

    for uid in users:
        udir = os.path.join(args.data_dir, uid)

        # promises.csv presence & size
        promises_path = os.path.join(udir, "promises.csv")
        pinfo = file_info(promises_path)
        if pinfo["exists"] and pinfo["bytes"] > args.threshold_bytes:
            users_with_promises += 1

        # actions.csv presence, size, and mtime
        actions_path = os.path.join(udir, "actions.csv")
        ainfo = file_info(actions_path)
        if ainfo["exists"] and ainfo["bytes"] > args.threshold_bytes:
            users_with_actions += 1
            for d in windows:
                if active_within(ainfo["mtime"], d, now):
                    active_counts[f"{d}d"] += 1

        # rough “new users” using directory mtime (best-effort)
        try:
            dst = os.stat(udir)
            dir_mtime = datetime.fromtimestamp(dst.st_mtime)
            for d in [7, 30]:
                if active_within(dir_mtime, d, now):
                    new_counts[f"{d}d"] += 1
        except FileNotFoundError:
            pass

    report = {
        "total_users": total_users,
        "users_with_promises": users_with_promises,
        "users_with_actions": users_with_actions,
        "active_users_by_actions_mtime": active_counts,
        "new_users_by_dir_mtime": new_counts,
        "threshold_bytes": args.threshold_bytes,
        "data_dir": os.path.abspath(args.data_dir),
        "generated_at": now.isoformat(timespec="seconds"),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # pretty print
    print(f"== Zana Planner usage stats ==")
    print(f"Data dir:    ***{report['data_dir'][-19:]}")
    print(f"Generated:   {report['generated_at']}")
    print()
    print(f"Total users: {report['total_users']}")
    print(f"With promises: {report['users_with_promises']}")
    print(f"With actions:  {report['users_with_actions']}")
    print()
    print("Active users (by actions.csv mtime):")
    for k in ["7d", "30d", "90d", "365d"]:
        print(f"  last {k:>4}: {report['active_users_by_actions_mtime'][k]}")
    print()
    print("New users (by folder mtime):")
    for k in ["7d", "30d"]:
        print(f"  last {k:>4}: {report['new_users_by_dir_mtime'][k]}")
    print()
    print(f"(A file counts only if its size > {args.threshold_bytes} bytes.)")

if __name__ == "__main__":
    main()
