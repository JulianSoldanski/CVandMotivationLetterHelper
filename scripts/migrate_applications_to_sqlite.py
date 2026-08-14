"""One-shot: applications.json → SQLite.

Usage: python scripts/migrate_applications_to_sqlite.py

Refuses to run if the DB already has applications.
On success, renames applications.json → applications.json.bak so the JSON
loader can't accidentally clobber the DB on the next request.
"""
import json
import os
import sys

# Allow running as `python scripts/migrate_applications_to_sqlite.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import db  # noqa: E402

JSON_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "applications.json",
)
BAK_FILE = JSON_FILE + ".bak"


def main() -> int:
    db.init_schema()

    with db.get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    if existing:
        print(
            f"Refusing to migrate: applications table already has {existing} row(s).\n"
            f"Inspect with: sqlite3 {db.DB_FILE} 'SELECT id, company FROM applications;'"
        )
        return 1

    if not os.path.exists(JSON_FILE):
        if os.path.exists(BAK_FILE):
            print(f"Nothing to do: {JSON_FILE} is already gone and {BAK_FILE} exists.")
            return 0
        print(f"No source file at {JSON_FILE}. Nothing to migrate.")
        return 0

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Failed to parse {JSON_FILE}: {e}")
            return 1

    if not isinstance(entries, list):
        print(f"Expected a list at root of {JSON_FILE}, got {type(entries).__name__}.")
        return 1

    apps_n, events_n = 0, 0
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("id"):
            print(f"Skipping invalid entry: {entry!r}")
            continue

        db.upsert_application({
            "id":          entry["id"],
            "company":     entry.get("company", ""),
            "position":    entry.get("position", ""),
            "stage":       entry.get("stage", "documents_created"),
            "feedback":    entry.get("feedback", ""),
            "applied_at":  entry.get("applied_at"),
            "job_posting": entry.get("job_posting", ""),
            "created_at":  entry.get("created_at") or entry.get("updated_at") or "",
            "updated_at":  entry.get("updated_at") or entry.get("created_at") or "",
        })
        apps_n += 1

        history = entry.get("stage_history")
        if isinstance(history, list) and history:
            for h in history:
                stage = h.get("stage")
                at    = h.get("at")
                if stage and at:
                    db.append_stage_event(entry["id"], stage, at)
                    events_n += 1
        else:
            # Legacy row: synthesize one event matching today's _ensure_history
            synth_at = entry.get("created_at") or entry.get("updated_at")
            stage    = entry.get("stage", "documents_created")
            if synth_at:
                db.append_stage_event(entry["id"], stage, synth_at)
                events_n += 1

    os.rename(JSON_FILE, BAK_FILE)
    print(f"Migrated {apps_n} application(s) and {events_n} stage event(s).")
    print(f"Source backed up to {BAK_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
