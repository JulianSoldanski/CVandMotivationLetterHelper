"""Rebuild ``data/.demo/cvcreater.db`` from ``examples/demo/applications.json``.

Use this when you've expanded the demo applications seed file and want the
live demo workspace to pick up the new entries without nuking the rest of
``data/.demo/`` (your demo profile/projects/settings edits stay intact).

Only touches the demo workspace. Refuses to run when ``DEMO_MODE`` is not
set — there's no demo DB to rebuild if you're on real data, and we don't
want to encourage silently building a demo DB on a non-demo install.

Idempotent: running it twice in a row produces the same DB. The running
Flask app picks up the change on the next request because every
``get_conn()`` opens a fresh sqlite connection against ``db.DB_FILE``.

Usage::

    python3 scripts/reseed_demo_db.py
    python3 scripts/reseed_demo_db.py --force-when-not-demo   # escape hatch
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

import demo_mode  # noqa: E402
import db         # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-when-not-demo", action="store_true",
        help="Build the demo DB even if DEMO_MODE is not currently set. "
             "Useful when you want to pre-seed before flipping the env var.",
    )
    args = parser.parse_args()

    if not demo_mode.is_demo_mode() and not args.force_when_not_demo:
        print("DEMO_MODE is not set — refusing to build a demo DB.")
        print("Set DEMO_MODE=1 (or pass --force-when-not-demo) and retry.")
        return 2

    demo_db = demo_mode.db_path() if demo_mode.is_demo_mode() else os.path.join(
        demo_mode.DEMO_WORK, "cvcreater.db"
    )
    apps_seed = os.path.join(demo_mode.DEMO_SEED, "applications.json")

    if not os.path.exists(apps_seed):
        print(f"ERROR: missing seed file at {apps_seed}")
        return 1

    # Make sure the demo workspace dir exists. If we got here via
    # --force-when-not-demo, the lazy seeder hasn't run yet.
    os.makedirs(os.path.dirname(demo_db), exist_ok=True)

    if os.path.exists(demo_db):
        os.remove(demo_db)
        print(f"  removed {os.path.relpath(demo_db, ROOT)}")

    # Drive db.py at the demo path by temporarily rebinding DB_FILE — the
    # same trick demo_mode._build_demo_db uses during the initial seed.
    saved = db.DB_FILE
    try:
        db.DB_FILE = demo_db
        demo_mode._build_demo_db(demo_db, apps_seed)
    finally:
        db.DB_FILE = saved if not demo_mode.is_demo_mode() else demo_db

    apps = []
    db.DB_FILE = demo_db
    apps = db.list_applications()
    print(f"  built {os.path.relpath(demo_db, ROOT)} with {len(apps)} applications.")
    from collections import Counter
    stages = Counter(a["stage"] for a in apps)
    for s in ("documents_created", "application_sent", "interview_1",
              "interview_2", "interview_3", "rejected"):
        n = stages.get(s, 0)
        if n:
            print(f"    {s:<20} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
