"""Runtime switch for "demo mode" — toggled via the ``DEMO_MODE`` env var.

When enabled, the app reads from a writable workspace at ``data/.demo/`` that
is seeded once from ``examples/demo/`` on first run. Real user data under
``data/`` and ``config/cv_personal.json`` is never touched, so the toggle is
reversible just by flipping the env var and restarting.

Why a workspace copy instead of pointing directly at ``examples/demo/``?
The user can edit projects, settings or applications inside the demo (handy
for live screencasts), and we don't want those edits to dirty the committed
seed files. The workspace is per-install, gitignored via the existing
``data/`` ignore rule.

Single source of truth — every module that needs a path or wants to know
whether demo mode is on imports from here. Resolution happens at module load
time, so flipping ``DEMO_MODE`` requires an app restart (Flask debug reloader
counts).
"""
from __future__ import annotations

import json
import os
import shutil

from core.paths import ROOT as _ROOT

DATA_DIR    = os.path.join(_ROOT, "data")
CONFIG_DIR  = os.path.join(_ROOT, "config")
DEMO_SEED   = os.path.join(_ROOT, "examples", "demo")
DEMO_WORK   = os.path.join(DATA_DIR, ".demo")
SEED_MARKER = os.path.join(DEMO_WORK, ".seeded")


def is_demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")


def _seed_demo_workdir() -> None:
    """Copy seed files into ``data/.demo/`` and build a fresh demo DB.

    Idempotent on the file-copy side (re-copy is harmless), but the DB is only
    built when it doesn't already exist so demo edits in the tracker survive
    restarts.
    """
    os.makedirs(DEMO_WORK, exist_ok=True)

    for name in ("profile.json", "projects.json", "settings.json", "cv_personal.json"):
        src = os.path.join(DEMO_SEED, name)
        dst = os.path.join(DEMO_WORK, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)

    db_path = os.path.join(DEMO_WORK, "cvcreater.db")
    apps_seed = os.path.join(DEMO_SEED, "applications.json")
    if not os.path.exists(db_path) and os.path.exists(apps_seed):
        _build_demo_db(db_path, apps_seed)

    if not os.path.exists(SEED_MARKER):
        with open(SEED_MARKER, "w", encoding="utf-8") as f:
            f.write("seeded\n")


def _build_demo_db(db_path: str, apps_seed: str) -> None:
    """Build the demo SQLite DB by importing applications from JSON.

    Imports ``db`` lazily so this module stays import-cheap and avoids a
    circular dependency with the very thing it configures.
    """
    # Temporarily override DB_FILE so db.init_schema() targets the demo path
    # without us having to expose a public setter just for this seed step.
    from core import db as _db  # noqa: WPS433 — local import is intentional
    original = _db.DB_FILE
    try:
        _db.DB_FILE = db_path
        _db.init_schema()
        with open(apps_seed, "r", encoding="utf-8") as f:
            entries = json.load(f)
        for entry in entries:
            _db.upsert_application({
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
                _db.append_stage_event(entry["id"], h["stage"], h["at"])
    finally:
        _db.DB_FILE = original


def _resolve(name: str, real_dir: str) -> str:
    """Return ``data/.demo/<name>`` when demo mode is on, else ``<real_dir>/<name>``.

    Triggers seeding lazily — the first resolution after toggling DEMO_MODE on
    will populate ``data/.demo/`` so callers don't need to know about seeding.
    """
    if is_demo_mode():
        if not os.path.exists(SEED_MARKER):
            _seed_demo_workdir()
        return os.path.join(DEMO_WORK, name)
    return os.path.join(real_dir, name)


# Path resolvers — call these from app.py / personal_config.py.
def profile_path()     -> str: return _resolve("profile.json",     DATA_DIR)
def projects_path()    -> str: return _resolve("projects.json",    DATA_DIR)
def settings_path()    -> str: return _resolve("settings.json",    DATA_DIR)
def db_path()          -> str: return _resolve("cvcreater.db",     DATA_DIR)
def cv_personal_path() -> str: return _resolve("cv_personal.json", CONFIG_DIR)


def bootstrap() -> bool:
    """Wire up demo mode if ``DEMO_MODE`` is enabled.

    Idempotent. Returns True iff demo mode is active so the caller can show
    a banner / log it. Called once from ``app.py`` right after ``load_dotenv``
    and before any DB work happens.
    """
    if not is_demo_mode():
        return False
    _seed_demo_workdir()
    # Rebind db.DB_FILE so every subsequent get_conn() targets the demo DB.
    # Done here (rather than at import time) to avoid a circular import.
    from core import db  # noqa: WPS433
    db.DB_FILE = db_path()
    return True
