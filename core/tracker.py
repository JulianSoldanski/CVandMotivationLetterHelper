"""Application tracking: the bridge between a generate event and the DB.
"""
import uuid

from core import config
from core import db
from core.util import _now_iso, _today_iso

def load_applications() -> list:
    return db.list_applications()


def get_application(app_id: str) -> dict | None:
    return db.get_application(app_id)


def apply_stage_transition(entry: dict, new_stage: str):
    """Apply a stage transition to an in-memory entry dict.

    Mutates entry["stage"], entry["stage_history"], and entry["applied_at"].
    Caller is responsible for persisting via db.upsert_application + db.append_stage_event.
    Returns the new event dict if a transition happened, else None.
    """
    history = entry.setdefault("stage_history", [])
    if history and history[-1]["stage"] == new_stage:
        return None
    event = {"stage": new_stage, "at": _now_iso()}
    history.append(event)
    entry["stage"] = new_stage
    if new_stage == "application_sent" and not entry.get("applied_at"):
        entry["applied_at"] = _today_iso()
    return event


def log_application(
    company: str,
    position: str,
    job_posting: str = "",
    job_url: str = "",
    cv_content: dict | None = None,
    anschreiben_content: dict | None = None,
    layout_used: str | None = None,
    language: str | None = None,
    tracked_seconds: int = 0,
) -> dict | None:
    """Create or refresh an application entry from a generate event.

    Dedupes by (company, position) case-insensitively so multiple generate
    clicks for the same opening don't spawn duplicates. Stores the generated
    CV/Anschreiben content snapshot when provided.
    """
    company  = (company or "").strip()
    position = (position or "").strip()
    if not company and not position:
        return None

    # Defensive clamp: 24h cap swallows obviously-bogus values from a stale
    # localStorage timestamp (e.g. user left the tab open for days).
    tracked_seconds = max(0, min(int(tracked_seconds or 0), 86400))

    existing = db.find_application_by_company_position(company, position)
    now = _now_iso()
    if existing:
        existing["updated_at"] = now
        if job_posting:
            existing["job_posting"] = job_posting[:config.JOB_POSTING_MAX]
        if job_url:
            existing["job_url"] = job_url[:config.JOB_URL_MAX]
        if cv_content is not None:
            existing["cv_content"] = cv_content
        if anschreiben_content is not None:
            existing["anschreiben_content"] = anschreiben_content
        if layout_used:
            existing["layout_used"] = layout_used
        if language:
            existing["language"] = language
        existing["research_seconds"] = int(existing.get("research_seconds") or 0) + tracked_seconds
        db.upsert_application(existing)
        return existing

    entry = {
        "id":                  str(uuid.uuid4())[:8],
        "company":             company,
        "position":            position,
        "stage":               "documents_created",
        "stage_history":       [{"stage": "documents_created", "at": now}],
        "applied_at":          None,
        "feedback":            "",
        "job_posting":         job_posting[:config.JOB_POSTING_MAX] if job_posting else "",
        "job_url":             job_url[:config.JOB_URL_MAX] if job_url else "",
        "cv_content":          cv_content,
        "anschreiben_content": anschreiben_content,
        "layout_used":         layout_used,
        "language":            language,
        "created_at":          now,
        "updated_at":          now,
        "research_seconds":    tracked_seconds,
    }
    db.upsert_application(entry)
    db.append_stage_event(entry["id"], "documents_created", now)
    return entry
