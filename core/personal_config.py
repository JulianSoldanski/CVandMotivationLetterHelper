"""Load applicant-specific text from config/cv_personal.json (not committed)."""

from __future__ import annotations

import json
import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_FILE = os.path.join(_BASE_DIR, "config", "cv_personal.example.json")


def _personal_file_path() -> str:
    """Resolve the active cv_personal.json path on every call.

    Resolution is deferred (rather than captured at import time) so that
    ``demo_mode.bootstrap()`` — which runs after ``load_dotenv()`` — can flip
    the path without us needing a re-import dance.
    """
    try:
        from core import demo_mode  # noqa: WPS433 — lazy avoids an import cycle
        return demo_mode.cv_personal_path()
    except ImportError:
        return os.path.join(_BASE_DIR, "config", "cv_personal.json")


_raw_cache: dict | None = None
_raw_mtime: float | None = None
_raw_path:  str | None = None


def _personal_missing_message() -> str:
    path = _personal_file_path()
    hint = ""
    if os.path.isfile(EXAMPLE_FILE):
        hint = (
            f' Kopiere "{EXAMPLE_FILE}" nach "{path}" '
            "und trage deine Daten ein."
        )
    return f"Persönliche Konfiguration fehlt: {path}.{hint}"


def _load_raw() -> dict:
    """Reload from disk when cv_personal.json changes (mtime or path), so
    edits apply without a server restart and DEMO_MODE toggles take effect."""
    global _raw_cache, _raw_mtime, _raw_path
    path = _personal_file_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(_personal_missing_message())
    mtime = os.path.getmtime(path)
    if _raw_cache is not None and _raw_mtime == mtime and _raw_path == path:
        return _raw_cache
    with open(path, "r", encoding="utf-8") as f:
        _raw_cache = json.load(f)
    _raw_mtime = mtime
    _raw_path  = path
    return _raw_cache


def reload_personal_config() -> None:
    global _raw_cache, _raw_mtime, _raw_path
    _raw_cache = None
    _raw_mtime = None
    _raw_path  = None


def get_candidate_base() -> str:
    data = _load_raw()
    base = (data.get("candidate_base") or "").strip()
    if not base:
        raise ValueError('config/cv_personal.json: Feld "candidate_base" darf nicht leer sein.')
    return base


def get_contact() -> dict[str, str]:
    data = _load_raw()
    c = data.get("contact") or {}
    required = ("full_name", "address_dot", "address_sidebar_html", "phone", "email")
    out: dict[str, str] = {}
    missing: list[str] = []
    for key in required:
        val = (c.get(key) or "").strip()
        if not val:
            missing.append(key)
        else:
            out[key] = val
    if missing:
        raise ValueError(
            f'config/cv_personal.json → "contact": fehlen oder leer: {", ".join(missing)}'
        )
    return out


def get_letter_address_lines() -> list[str]:
    data = _load_raw()
    lines = data.get("letter_address_lines")
    if isinstance(lines, list):
        parsed = [str(x).strip() for x in lines if str(x).strip()]
        if parsed:
            return parsed
    ad = get_contact()["address_dot"]
    return [p.strip() for p in ad.replace("·", ",").split(",") if p.strip()]


def sender_address_html() -> str:
    c = get_contact()
    parts = [c["full_name"], *get_letter_address_lines()]
    return "<br/>".join(parts)
