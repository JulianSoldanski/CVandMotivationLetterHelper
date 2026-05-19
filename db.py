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
                job_url             TEXT NOT NULL DEFAULT '',
                cv_content          TEXT,        -- JSON snapshot of the generated CV (or NULL)
                anschreiben_content TEXT,        -- JSON snapshot of the generated Anschreiben (or NULL)
                company_info        TEXT,        -- JSON: description, industry, employees, founded, hq, sources, …
                fit_score           TEXT,        -- JSON: {score, summary, strengths[], gaps[]}
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

            CREATE TABLE IF NOT EXISTS job_queue (
                id             TEXT PRIMARY KEY,
                url            TEXT NOT NULL,
                title          TEXT NOT NULL DEFAULT '',
                note           TEXT NOT NULL DEFAULT '',
                status         TEXT NOT NULL DEFAULT 'pending',
                added_at       TEXT NOT NULL,
                processed_at   TEXT,
                error          TEXT,
                fit_score      TEXT,            -- JSON: {score, summary, strengths[], gaps[]}
                company_info   TEXT,            -- JSON: description, industry, employees, kununu, …
                enriched_at    TEXT,            -- ISO datetime: when background enrichment finished
                application_id TEXT REFERENCES applications(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_app   ON stage_events(application_id, at);
            CREATE INDEX IF NOT EXISTS idx_events_stage ON stage_events(stage);
            CREATE INDEX IF NOT EXISTS idx_apps_company ON applications(company);
            CREATE INDEX IF NOT EXISTS idx_queue_status ON job_queue(status, added_at);
        """)
        # Lightweight forward-migration for users who already ran an earlier
        # init_schema before the snapshot columns existed.
        existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
        for col, decl in [
            ("cv_content",          "TEXT"),
            ("anschreiben_content", "TEXT"),
            ("layout_used",         "TEXT"),
            ("language",            "TEXT"),
            ("job_url",             "TEXT NOT NULL DEFAULT ''"),
            ("company_info",        "TEXT"),
            ("fit_score",           "TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {col} {decl}")

        existing_queue_cols = {r["name"] for r in conn.execute("PRAGMA table_info(job_queue)")}
        if "fit_score" not in existing_queue_cols:
            conn.execute("ALTER TABLE job_queue ADD COLUMN fit_score TEXT")
        if "company_info" not in existing_queue_cols:
            conn.execute("ALTER TABLE job_queue ADD COLUMN company_info TEXT")
        if "enriched_at" not in existing_queue_cols:
            conn.execute("ALTER TABLE job_queue ADD COLUMN enriched_at TEXT")
            # Backfill: anything created before this column existed is
            # considered enrichment-finished (success or no-op), so the
            # frontend doesn't loop polling on legacy rows.
            conn.execute("UPDATE job_queue SET enriched_at = added_at WHERE enriched_at IS NULL")


def _row_to_dict(row: sqlite3.Row, history: list[dict]) -> dict:
    import json
    def _parse(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except (TypeError, ValueError):
            return None
    keys = set(row.keys())
    return {
        "id":                  row["id"],
        "company":             row["company"],
        "position":            row["position"],
        "stage":               row["current_stage"],
        "stage_history":       history,
        "feedback":            row["feedback"],
        "applied_at":          row["applied_at"],
        "job_posting":         row["job_posting"],
        "job_url":             row["job_url"] if "job_url" in keys else "",
        "cv_content":          _parse(row["cv_content"]),
        "anschreiben_content": _parse(row["anschreiben_content"]),
        "company_info":        _parse(row["company_info"]) if "company_info" in keys else None,
        "fit_score":           _parse(row["fit_score"])    if "fit_score"    in keys else None,
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
                  job_posting, job_url, cv_content, anschreiben_content,
                  company_info, fit_score, layout_used, language,
                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 company             = excluded.company,
                 position            = excluded.position,
                 current_stage       = excluded.current_stage,
                 feedback            = excluded.feedback,
                 applied_at          = excluded.applied_at,
                 job_posting         = excluded.job_posting,
                 job_url             = excluded.job_url,
                 cv_content          = COALESCE(excluded.cv_content,          applications.cv_content),
                 anschreiben_content = COALESCE(excluded.anschreiben_content, applications.anschreiben_content),
                 company_info        = COALESCE(excluded.company_info,        applications.company_info),
                 fit_score           = COALESCE(excluded.fit_score,           applications.fit_score),
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
                entry.get("job_url", ""),
                _serialize(entry.get("cv_content")),
                _serialize(entry.get("anschreiben_content")),
                _serialize(entry.get("company_info")),
                _serialize(entry.get("fit_score")),
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


def update_last_rejected_event_at(app_id: str, at: str) -> int:
    """Set the timestamp of the most recent 'rejected' stage_event for this app.

    Returns the number of rows updated (0 if no rejected event exists).
    """
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE stage_events SET at = ?
               WHERE id = (
                 SELECT id FROM stage_events
                 WHERE application_id = ? AND stage = 'rejected'
                 ORDER BY id DESC LIMIT 1
               )""",
            (at, app_id),
        )
        return cur.rowcount


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


# ─── Queue (job links collected throughout the day) ──────────────────────────

QUEUE_STATUSES = ("pending", "processing", "done", "failed", "skipped")


def _queue_row_to_dict(row: sqlite3.Row) -> dict:
    import json
    def _parse_col(name):
        if name in row.keys() and row[name]:
            try:
                return json.loads(row[name])
            except (TypeError, ValueError):
                return None
        return None
    return {
        "id":             row["id"],
        "url":            row["url"],
        "title":          row["title"],
        "note":           row["note"],
        "status":         row["status"],
        "added_at":       row["added_at"],
        "processed_at":   row["processed_at"],
        "error":          row["error"],
        "application_id": row["application_id"],
        "fit_score":      _parse_col("fit_score"),
        "company_info":   _parse_col("company_info"),
        "enriched_at":    row["enriched_at"] if "enriched_at" in row.keys() else None,
    }


def list_queue(status: str | None = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM job_queue WHERE status = ? ORDER BY added_at DESC",
                (status,),
            ).fetchall()
        else:
            # Pending first (oldest first so you work through them in order),
            # then everything else newest-first.
            rows = conn.execute(
                """SELECT * FROM job_queue
                   ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                            CASE status WHEN 'pending' THEN added_at END ASC,
                            added_at DESC"""
            ).fetchall()
        return [_queue_row_to_dict(r) for r in rows]


def get_queue_item(qid: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM job_queue WHERE id = ?", (qid,)).fetchone()
        return _queue_row_to_dict(row) if row else None


def find_queue_item_by_url(url: str) -> dict | None:
    """Find an existing queue entry with the same URL (any status).

    Used to dedupe when the bookmarklet is clicked twice on the same posting.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM job_queue WHERE url = ? ORDER BY added_at DESC LIMIT 1",
            (url,),
        ).fetchone()
        return _queue_row_to_dict(row) if row else None


def add_queue_item(qid: str, url: str, title: str, note: str, added_at: str) -> dict:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO job_queue (id, url, title, note, status, added_at)
               VALUES (?, ?, ?, ?, 'pending', ?)""",
            (qid, url, title, note, added_at),
        )
    return get_queue_item(qid)  # type: ignore[return-value]


def update_queue_item(
    qid: str,
    *,
    status: str | None = None,
    note: str | None = None,
    error: str | None = None,
    processed_at: str | None = None,
    application_id: str | None = None,
    fit_score: dict | None = None,
    company_info: dict | None = None,
    enriched_at: str | None = None,
) -> dict | None:
    """Partial-update a queue row. Only fields explicitly passed are touched.

    `fit_score=None` / `company_info=None` is the default sentinel for
    "don't touch"; pass an explicit empty dict `{}` to clear, or a
    populated dict to set.
    """
    import json
    sets, vals = [], []
    if status is not None:
        if status not in QUEUE_STATUSES:
            raise ValueError(f"invalid status: {status}")
        sets.append("status = ?"); vals.append(status)
    if note is not None:
        sets.append("note = ?"); vals.append(note)
    if error is not None:
        sets.append("error = ?"); vals.append(error)
    if processed_at is not None:
        sets.append("processed_at = ?"); vals.append(processed_at)
    if application_id is not None:
        sets.append("application_id = ?"); vals.append(application_id)
    if fit_score is not None:
        sets.append("fit_score = ?")
        vals.append(json.dumps(fit_score, ensure_ascii=False) if fit_score else None)
    if company_info is not None:
        sets.append("company_info = ?")
        vals.append(json.dumps(company_info, ensure_ascii=False) if company_info else None)
    if enriched_at is not None:
        sets.append("enriched_at = ?"); vals.append(enriched_at)
    if not sets:
        return get_queue_item(qid)
    vals.append(qid)
    with get_conn() as conn:
        conn.execute(f"UPDATE job_queue SET {', '.join(sets)} WHERE id = ?", vals)
    return get_queue_item(qid)


def delete_queue_item(qid: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM job_queue WHERE id = ?", (qid,))
        return cur.rowcount > 0
