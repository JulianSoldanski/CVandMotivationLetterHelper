"""SQLite data-access layer for applications + stage_events.

Keeps the same dict shape the routes and frontend already expect, so the
HTTP boundary stays untouched.
"""
import os
import sqlite3
from contextlib import contextmanager

DB_FILE = os.path.join(os.path.dirname(__file__), "data", "cvcreater.db")


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS applications (
                id                  TEXT PRIMARY KEY,
                company             TEXT NOT NULL,
                position            TEXT NOT NULL DEFAULT '',
                current_stage       TEXT NOT NULL,
                feedback            TEXT NOT NULL DEFAULT '',
                applied_at          TEXT,
                job_posting         TEXT NOT NULL DEFAULT '',
                cv_content          TEXT,        -- JSON snapshot of the generated CV (or NULL)
                anschreiben_content TEXT,        -- JSON snapshot of the generated Anschreiben (or NULL)
                layout_used         TEXT,
                language            TEXT,
                created_at          TEXT NOT NULL,
                updated_at          TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stage_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
                stage          TEXT NOT NULL,
                at             TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_app   ON stage_events(application_id, at);
            CREATE INDEX IF NOT EXISTS idx_events_stage ON stage_events(stage);
            CREATE INDEX IF NOT EXISTS idx_apps_company ON applications(company);
        """)
        # Lightweight forward-migration for users who already ran an earlier
        # init_schema before the snapshot columns existed.
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
        for col, decl in [
            ("cv_content",          "TEXT"),
            ("anschreiben_content", "TEXT"),
            ("layout_used",         "TEXT"),
            ("language",            "TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {decl}")


def _row_to_dict(row: sqlite3.Row, history: list[dict]) -> dict:
    import json
    def _parse(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except (TypeError, ValueError):
            return None
    return {
        "id":                  row["id"],
        "company":             row["company"],
        "position":            row["position"],
        "stage":               row["current_stage"],
        "stage_history":       history,
        "feedback":            row["feedback"],
        "applied_at":          row["applied_at"],
        "job_posting":         row["job_posting"],
        "cv_content":          _parse(row["cv_content"]),
        "anschreiben_content": _parse(row["anschreiben_content"]),
        "layout_used":         row["layout_used"],
        "language":            row["language"],
        "created_at":          row["created_at"],
        "updated_at":          row["updated_at"],
    }


def _history_for(conn, app_id: str) -> list[dict]:
    return [
        {"stage": r["stage"], "at": r["at"]}
        for r in conn.execute(
            "SELECT stage, at FROM stage_events WHERE application_id = ? ORDER BY at, id",
            (app_id,),
        )
    ]


def list_applications() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY updated_at DESC").fetchall()
        # One query per row would be N+1; for the volumes we expect this is fine
        # and avoids the awkward Python-side group-by for a JOIN.
        return [_row_to_dict(r, _history_for(conn, r["id"])) for r in rows]


def get_application(app_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        if not row:
            return None
        return _row_to_dict(row, _history_for(conn, app_id))


def find_application_by_company_position(company: str, position: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM applications
               WHERE LOWER(company) = LOWER(?) AND LOWER(position) = LOWER(?)
               LIMIT 1""",
            (company, position),
        ).fetchone()
        if not row:
            return None
        return _row_to_dict(row, _history_for(conn, row["id"]))


def upsert_application(entry: dict):
    """INSERT or UPDATE the applications row. Does NOT touch stage_events."""
    import json
    def _serialize(val):
        if val is None:
            return None
        return json.dumps(val, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO applications
                 (id, company, position, current_stage, feedback, applied_at,
                  job_posting, cv_content, anschreiben_content, layout_used, language,
                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 company             = excluded.company,
                 position            = excluded.position,
                 current_stage       = excluded.current_stage,
                 feedback            = excluded.feedback,
                 applied_at          = excluded.applied_at,
                 job_posting         = excluded.job_posting,
                 cv_content          = COALESCE(excluded.cv_content,          applications.cv_content),
                 anschreiben_content = COALESCE(excluded.anschreiben_content, applications.anschreiben_content),
                 layout_used         = COALESCE(excluded.layout_used,         applications.layout_used),
                 language            = COALESCE(excluded.language,            applications.language),
                 updated_at          = excluded.updated_at""",
            (
                entry["id"],
                entry.get("company", ""),
                entry.get("position", ""),
                entry.get("stage", "documents_created"),
                entry.get("feedback", ""),
                entry.get("applied_at"),
                entry.get("job_posting", ""),
                _serialize(entry.get("cv_content")),
                _serialize(entry.get("anschreiben_content")),
                entry.get("layout_used"),
                entry.get("language"),
                entry["created_at"],
                entry["updated_at"],
            ),
        )


def append_stage_event(app_id: str, stage: str, at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO stage_events (application_id, stage, at) VALUES (?, ?, ?)",
            (app_id, stage, at),
        )


def last_stage_event(app_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT stage, at FROM stage_events WHERE application_id = ? ORDER BY at DESC, id DESC LIMIT 1",
            (app_id,),
        ).fetchone()
        return {"stage": row["stage"], "at": row["at"]} if row else None


def delete_application(app_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        return cur.rowcount > 0
