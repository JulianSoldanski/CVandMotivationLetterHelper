"""Load applicant-specific text from config/cv_personal.json (not committed)."""

from __future__ import annotations

import json
import os
from functools import lru_cache

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERSONAL_FILE = os.path.join(_BASE_DIR, "config", "cv_personal.json")
EXAMPLE_FILE = os.path.join(_BASE_DIR, "config", "cv_personal.example.json")


def _personal_missing_message() -> str:
    hint = ""
    if os.path.isfile(EXAMPLE_FILE):
        hint = (
            f' Kopiere "{EXAMPLE_FILE}" nach "{PERSONAL_FILE}" '
            "und trage deine Daten ein."
        )
    return f"Persönliche Konfiguration fehlt: {PERSONAL_FILE}.{hint}"


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    if not os.path.isfile(PERSONAL_FILE):
        raise FileNotFoundError(_personal_missing_message())
    with open(PERSONAL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def reload_personal_config() -> None:
    _load_raw.cache_clear()


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
