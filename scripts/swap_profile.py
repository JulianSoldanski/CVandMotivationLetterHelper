"""Swap between the live profile and the bundled Max-Mustermann demo profile.

Use this when you want to record a screencast, share screenshots, or hand the
app to someone else without exposing your real applications, contact info, and
writing style.

What gets swapped
-----------------
* ``data/profile.json``         ↔ ``examples/demo/profile.json``
* ``data/projects.json``        ↔ ``examples/demo/projects.json``
* ``data/settings.json``        ↔ ``examples/demo/settings.json``
* ``config/cv_personal.json``   ↔ ``examples/demo/cv_personal.json``
* ``data/cvcreater.db``         — rebuilt from ``examples/demo/applications.json``

When you switch to demo, your real files are moved to ``data/.mine_backup/``.
When you switch back, the script restores them from there. The demo DB is
always rebuilt fresh from the JSON — edits you make in the UI while in demo
mode are discarded on the next swap. This is intentional so the demo always
starts in a known state.

A tiny state file ``data/.profile_owner`` tracks whether ``mine`` or ``demo``
is currently active so that repeated runs are no-ops instead of clobbering
the backup.

Usage
-----
::

    python scripts/swap_profile.py status     # show current owner
    python scripts/swap_profile.py demo       # switch to Max Mustermann demo
    python scripts/swap_profile.py mine       # switch back to your real data
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import db  # noqa: E402

DATA_DIR    = os.path.join(ROOT, "data")
CONFIG_DIR  = os.path.join(ROOT, "config")
DEMO_DIR    = os.path.join(ROOT, "examples", "demo")
BACKUP_DIR  = os.path.join(DATA_DIR, ".mine_backup")
STATE_FILE  = os.path.join(DATA_DIR, ".profile_owner")
DEMO_DB     = os.path.join(DATA_DIR, "cvcreater.db")

# (live_path, demo_path) — for plain file swaps
SWAP_PAIRS = [
    (os.path.join(DATA_DIR,   "profile.json"),     os.path.join(DEMO_DIR, "profile.json")),
    (os.path.join(DATA_DIR,   "projects.json"),    os.path.join(DEMO_DIR, "projects.json")),
    (os.path.join(DATA_DIR,   "settings.json"),    os.path.join(DEMO_DIR, "settings.json")),
    (os.path.join(CONFIG_DIR, "cv_personal.json"), os.path.join(DEMO_DIR, "cv_personal.json")),
]
DEMO_APPLICATIONS_JSON = os.path.join(DEMO_DIR, "applications.json")


# ─── state helpers ───────────────────────────────────────────────────────────

def read_owner() -> str:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
            return v if v in ("mine", "demo") else "mine"
    except FileNotFoundError:
        return "mine"


def write_owner(owner: str) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(owner + "\n")


# ─── DB seeding ──────────────────────────────────────────────────────────────

def rebuild_demo_db() -> int:
    """Wipe data/cvcreater.db and repopulate from examples/demo/applications.json."""
    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)
    db.init_schema()

    with open(DEMO_APPLICATIONS_JSON, "r", encoding="utf-8") as f:
        entries = json.load(f)

    n = 0
    for entry in entries:
        db.upsert_application({
            "id":          entry["id"],
            "company":     entry.get("company", ""),
            "position":    entry.get("position", ""),
            "stage":       entry.get("stage", "documents_created"),
            "feedback":    entry.get("feedback", ""),
            "applied_at":  entry.get("applied_at"),
            "job_posting": entry.get("job_posting", ""),
            "job_url":     entry.get("job_url", ""),
            "created_at":  entry["created_at"],
            "updated_at":  entry["updated_at"],
        })
        for h in entry.get("stage_history", []):
            db.append_stage_event(entry["id"], h["stage"], h["at"])
        n += 1
    return n


# ─── swap operations ─────────────────────────────────────────────────────────

def to_demo(force: bool = False) -> int:
    owner = read_owner()
    if owner == "demo" and not force:
        print("Already on demo profile. Nothing to do (use --force to re-seed demo DB).")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)

    moved = []
    # Only back up live files the FIRST time we switch to demo. If we're
    # re-running with --force while already on demo, the live files ARE the
    # demo files — backing them up would overwrite the real user data.
    do_backup = owner != "demo"

    for live, demo_src in SWAP_PAIRS:
        if not os.path.exists(demo_src):
            print(f"  ! missing demo source, skipping: {os.path.relpath(demo_src, ROOT)}")
            continue
        if do_backup and os.path.exists(live):
            backup_target = os.path.join(BACKUP_DIR, os.path.basename(live))
            shutil.move(live, backup_target)
            moved.append(os.path.relpath(live, ROOT))
        elif os.path.exists(live):
            os.remove(live)
        shutil.copy2(demo_src, live)
        print(f"  → {os.path.relpath(live, ROOT)}  (from demo)")

    if do_backup and os.path.exists(DEMO_DB):
        shutil.move(DEMO_DB, os.path.join(BACKUP_DIR, "cvcreater.db"))
        moved.append("data/cvcreater.db")

    seeded = rebuild_demo_db()
    print(f"  → data/cvcreater.db  ({seeded} demo applications)")

    if moved:
        print(f"\nBacked up your real files to {os.path.relpath(BACKUP_DIR, ROOT)}/")

    write_owner("demo")
    print("\nSwitched to demo. Run `python scripts/swap_profile.py mine` to restore.")
    return 0


def to_mine() -> int:
    owner = read_owner()
    if owner == "mine":
        print("Already on your real profile. Nothing to do.")
        return 0

    if not os.path.isdir(BACKUP_DIR):
        print(f"ERROR: no backup directory at {os.path.relpath(BACKUP_DIR, ROOT)}.")
        print("Cannot restore your real profile — was the backup deleted?")
        return 1

    restored = []
    for live, _ in SWAP_PAIRS:
        backup = os.path.join(BACKUP_DIR, os.path.basename(live))
        if not os.path.exists(backup):
            print(f"  ! no backup for {os.path.relpath(live, ROOT)}, leaving demo file in place")
            continue
        if os.path.exists(live):
            os.remove(live)
        shutil.move(backup, live)
        restored.append(os.path.relpath(live, ROOT))
        print(f"  → {os.path.relpath(live, ROOT)}  (restored)")

    backup_db = os.path.join(BACKUP_DIR, "cvcreater.db")
    if os.path.exists(backup_db):
        if os.path.exists(DEMO_DB):
            os.remove(DEMO_DB)
        shutil.move(backup_db, DEMO_DB)
        restored.append("data/cvcreater.db")
        print(f"  → data/cvcreater.db  (restored)")
    else:
        # No real DB existed before the swap — leave the demo DB in place
        # rather than silently dropping the user's tracker entries.
        print("  ! no DB backup found — your tracker keeps whatever is currently in data/cvcreater.db")

    # Clean up the backup dir if it's now empty so future swaps start fresh.
    try:
        if not os.listdir(BACKUP_DIR):
            os.rmdir(BACKUP_DIR)
    except OSError:
        pass

    write_owner("mine")
    print(f"\nRestored {len(restored)} file(s). Welcome back.")
    return 0


def status() -> int:
    owner = read_owner()
    print(f"Current profile owner: {owner}")
    if owner == "demo":
        if os.path.isdir(BACKUP_DIR):
            files = sorted(os.listdir(BACKUP_DIR))
            print(f"Backup dir: {os.path.relpath(BACKUP_DIR, ROOT)}/ ({len(files)} file(s))")
        else:
            print("Backup dir: MISSING — `swap_profile.py mine` will fail until you restore it.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("status", "demo", "mine"),
                   help="status: show current owner; demo: switch to Max-Mustermann demo; mine: restore your real data.")
    p.add_argument("--force", action="store_true",
                   help="When switching to demo while already on demo, re-seed the demo DB from JSON.")
    args = p.parse_args()

    # When DEMO_MODE=1 is set, the app reads from data/.demo/, NOT from
    # data/. Swapping files in data/ at that moment is almost always a
    # mistake (the user thinks they're affecting the running demo when
    # they're actually about to nuke their real profile under a misleading
    # name). Force them to unset DEMO_MODE first.
    try:
        from core import demo_mode  # noqa: WPS433
        if demo_mode.is_demo_mode() and args.command in ("demo", "mine"):
            print("ERROR: DEMO_MODE=1 is currently set in your environment.")
            print("This script operates on your REAL data files in data/ and config/.")
            print("Unset DEMO_MODE (or comment it out in .env) before swapping.")
            return 2
    except ImportError:
        pass

    if args.command == "status":
        return status()
    if args.command == "demo":
        return to_demo(force=args.force)
    if args.command == "mine":
        return to_mine()
    return 1


if __name__ == "__main__":
    sys.exit(main())
