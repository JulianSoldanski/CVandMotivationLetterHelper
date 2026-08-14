"""JSON-file persistence for profile, projects and settings,
plus the text serializers that feed the generation prompts.
"""

from core.personal_config import get_candidate_base

import json
import os

from core import config


def load_projects() -> list:
    try:
        with open(config.PROJECTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_projects(projects: list):
    with open(config.PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


# Fields of the long-form project entry ("Projektliste"). Client, period and
# technologies are language-neutral and stored once; everything a reader
# actually reads as prose is kept per language, because the same project gets
# handed to German and English recruiters alike.
#
# The project's own `title`/`description` are the author's source text in
# whichever language they happened to write it — `detail[<lang>]` holds the
# printable version for that language. Renderers must read the localized block,
# never the source fields, or a German entry ends up in an English document.
PROJECT_DETAIL_LANGS  = ("de", "en")
PROJECT_DETAIL_SHARED = ("client", "period", "team_size")
# Prose fields inside a localized block; `contributions` is a list, the rest strings.
PROJECT_LOCALIZED_TEXT = ("title", "summary", "role", "situation", "result", "team_size")
PROJECT_LOCALIZED_LIST = ("contributions",)


def normalize_project_detail(raw: dict | None) -> dict:
    """Coerce arbitrary input into the project-detail shape (never raises).

    Missing pieces come back as empty strings / lists rather than None so the
    renderer and the editor can treat "not filled in yet" uniformly.
    """
    raw = raw if isinstance(raw, dict) else {}

    def _s(value) -> str:
        return value.strip() if isinstance(value, str) else ""

    def _list(value) -> list:
        if isinstance(value, str):
            value = value.splitlines()
        if not isinstance(value, list):
            return []
        return [_s(v) for v in value if _s(v)]

    detail = {key: _s(raw.get(key)) for key in PROJECT_DETAIL_SHARED}
    detail["technologies"] = _list(raw.get("technologies"))
    detail["in_list"]      = bool(raw.get("in_list", True))
    for lang in PROJECT_DETAIL_LANGS:
        block = raw.get(lang) if isinstance(raw.get(lang), dict) else {}
        loc = {field: _s(block.get(field)) for field in PROJECT_LOCALIZED_TEXT}
        loc.update({field: _list(block.get(field)) for field in PROJECT_LOCALIZED_LIST})
        detail[lang] = loc
    return detail


def project_detail_filled(detail: dict) -> bool:
    """True if the entry carries any long-form content worth printing."""
    if any(detail.get(key) for key in PROJECT_DETAIL_SHARED) or detail.get("technologies"):
        return True
    return any(
        detail.get(lang, {}).get(field)
        for lang in PROJECT_DETAIL_LANGS
        for field in ("role", "situation", "contributions", "result")
    )


def project_locale(project: dict, language: str) -> dict:
    """The localized block a renderer should print for `language`.

    Always returns a fully-shaped block, so callers can read any field without
    null-checks. An unknown language falls back to German.
    """
    detail = normalize_project_detail(project.get("detail"))
    return detail.get(language) or detail["de"]


def load_settings() -> dict:
    """Settings hold a single, language-agnostic writing style.

    The style example may be in any language; the distilled analysis is an
    English style guide applied to both German and English generation.
    Legacy files used per-language dicts ({"de": ..., "en": ...}); those are
    migrated on read by collapsing to whichever language had content.
    """
    defaults = {"style_example": "", "style_analysis": ""}
    try:
        with open(config.SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults

    def _flatten(value) -> str:
        if isinstance(value, dict):  # legacy {"de": ..., "en": ...}
            return (value.get("de") or value.get("en") or "").strip()
        return value.strip() if isinstance(value, str) else ""

    return {
        "style_example":  _flatten(data.get("style_example", data.get("style_examples", ""))),
        "style_analysis": _flatten(data.get("style_analysis", "")),
    }


def save_settings(settings: dict):
    os.makedirs(os.path.dirname(config.SETTINGS_FILE), exist_ok=True)
    with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_profile() -> dict:
    defaults = {
        "experience": [],
        "education": [],
        "hard_skills": [],
        "soft_skills": [],
        "languages": [],
    }
    try:
        with open(config.PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key, default_val in defaults.items():
                if key not in data or not isinstance(data[key], list):
                    data[key] = default_val.copy()
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def save_profile(profile: dict):
    with open(config.PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)


def _sort_key(entry: dict) -> str:
    """Sort descending: current first, then by end date, then by start date."""
    if entry.get("current"):
        return "9999-99"
    return entry.get("end") or entry.get("start") or "0000-00"


def fmt_date(ym: str | None, current: bool = False, language: str = "de") -> str:
    if current:
        return "present" if language == "en" else "heute"
    if not ym:
        return ""
    months_de = ["", "Jan", "Feb", "Mrz", "Apr", "Mai", "Jun",
                 "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    months_en = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    months = months_en if language == "en" else months_de
    try:
        y, m = ym.split("-")
        return f"{months[int(m)]} {y}"
    except Exception:
        return ym


def profile_to_text(profile: dict) -> str:
    lines = [get_candidate_base()]

    # Experience — sorted chronologically descending
    exp = [e for e in profile.get("experience", []) if e.get("visible", True)]
    exp.sort(key=_sort_key, reverse=True)
    if exp:
        lines.append("--- WORK EXPERIENCE ---\n")
        for e in exp:
            loc    = f", {e['location']}" if e.get("location") else ""
            start  = fmt_date(e.get("start"))
            end    = fmt_date(e.get("end"), e.get("current", False))
            period = f"{start} – {end}" if start else ""
            lines.append(f"{e['title']}")
            lines.append(f"{e['company']}{loc} · {period}")
            for b in e.get("bullets", []):
                lines.append(f"- {b}")
            lines.append("")

    # Education — sorted descending
    edu = [e for e in profile.get("education", []) if e.get("visible", True)]
    edu.sort(key=_sort_key, reverse=True)
    if edu:
        lines.append("--- EDUCATION ---\n")
        for e in edu:
            loc    = f", {e['location']}" if e.get("location") else ""
            start  = fmt_date(e.get("start"))
            end    = fmt_date(e.get("end"), e.get("current", False))
            period = f"{start} – {end}" if start else ""
            lines.append(f"{e['degree']}")
            lines.append(f"{e['institution']}{loc} · {period}")
            for d in e.get("details", []):
                lines.append(f"- {d}")
            lines.append("")

    hard = [s.get("name", "").strip() for s in profile.get("hard_skills", []) if s.get("name")]
    soft = [s.get("name", "").strip() for s in profile.get("soft_skills", []) if s.get("name")]
    langs = []
    for l in profile.get("languages", []):
        name = (l.get("name") or "").strip()
        level = (l.get("level") or "").strip()
        if name:
            langs.append(f"{name} ({level})" if level else name)

    if hard or soft or langs:
        lines.append("--- SKILLS ---\n")
        if hard:
            lines.append(f"Hard Skills: {', '.join(hard)}")
        if soft:
            lines.append(f"Soft Skills: {', '.join(soft)}")
        if langs:
            lines.append(f"Languages: {', '.join(langs)}")
        lines.append("")

    return "\n".join(lines)


def projects_to_text(projects: list, language: str = "de") -> str:
    """Project block for the generation prompts, already in the output language.

    Feeding the model pre-translated text keeps it from having to translate and
    tailor in one step — which is where German titles used to survive into an
    English CV.
    """
    visible = [p for p in projects if p.get("visible", True)]
    if not visible:
        return "(keine Projekte vorhanden)"
    lines = []
    for p in visible:
        loc       = project_locale(p, language)
        title     = loc["title"] or p["title"]
        desc      = loc["summary"] or p["description"]
        grade_str = f" (Note: {p['grade']})" if p.get("grade") else ""
        tags_str  = f" [Tags: {', '.join(p['tags'])}]" if p.get("tags") else ""
        lines.append(f"- {title}{grade_str}{tags_str}:\n  {desc}")
    return "\n".join(lines)
