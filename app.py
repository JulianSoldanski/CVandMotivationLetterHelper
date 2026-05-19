import os
import json
import uuid
import re
import requests as http_requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import date, datetime

from cv_layouts import ANSCHREIBEN_HTML_STYLE, LAYOUTS
from personal_config import get_candidate_base, get_contact, sender_address_html
import db

load_dotenv()

app = Flask(__name__)

GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PROJECTS_FILE     = os.path.join(os.path.dirname(__file__), "data", "projects.json")
PROFILE_FILE      = os.path.join(os.path.dirname(__file__), "data", "profile.json")
APPLICATIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "applications.json")
SETTINGS_FILE     = os.path.join(os.path.dirname(__file__), "data", "settings.json")

db.init_schema()
JOB_POSTING_MAX = 50_000
JOB_URL_MAX = 500
APPLICATION_STAGES = [
    "documents_created",
    "application_sent",
    "interview_1",
    "interview_2",
    "interview_3",
    "rejected",
]
CV_DIR            = os.path.join(os.path.dirname(__file__), "cvs")
ANSCHREIBEN_DIR   = os.path.join(os.path.dirname(__file__), "anschreiben")
os.makedirs(CV_DIR, exist_ok=True)
os.makedirs(ANSCHREIBEN_DIR, exist_ok=True)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_projects() -> list:
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_projects(projects: list):
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)


def load_settings() -> dict:
    defaults = {
        "style_examples": {"de": "", "en": ""},
        "style_analysis": {"de": "", "en": ""},
    }
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults
    for field in ("style_examples", "style_analysis"):
        if not isinstance(data.get(field), dict):
            data[field] = {"de": "", "en": ""}
        for k in ("de", "en"):
            if not isinstance(data[field].get(k), str):
                data[field][k] = ""
    return data


def save_settings(settings: dict):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today_iso() -> str:
    return date.today().isoformat()


def _normalize_calendar_date(value: str) -> str | None:
    """Accept YYYY-MM-DD (from <input type=\"date\">) or leading YYYY-MM-DD of an ISO string."""
    value = (value or "").strip()
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        try:
            date.fromisoformat(value[:10])
            return value[:10]
        except ValueError:
            return None
    return None


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

    existing = db.find_application_by_company_position(company, position)
    now = _now_iso()
    if existing:
        existing["updated_at"] = now
        if job_posting:
            existing["job_posting"] = job_posting[:JOB_POSTING_MAX]
        if job_url:
            existing["job_url"] = job_url[:JOB_URL_MAX]
        if cv_content is not None:
            existing["cv_content"] = cv_content
        if anschreiben_content is not None:
            existing["anschreiben_content"] = anschreiben_content
        if layout_used:
            existing["layout_used"] = layout_used
        if language:
            existing["language"] = language
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
        "job_posting":         job_posting[:JOB_POSTING_MAX] if job_posting else "",
        "job_url":             job_url[:JOB_URL_MAX] if job_url else "",
        "cv_content":          cv_content,
        "anschreiben_content": anschreiben_content,
        "layout_used":         layout_used,
        "language":            language,
        "created_at":          now,
        "updated_at":          now,
    }
    db.upsert_application(entry)
    db.append_stage_event(entry["id"], "documents_created", now)
    return entry


def load_profile() -> dict:
    defaults = {
        "experience": [],
        "education": [],
        "hard_skills": [],
        "soft_skills": [],
        "languages": [],
    }
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key, default_val in defaults.items():
                if key not in data or not isinstance(data[key], list):
                    data[key] = default_val.copy()
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults


def save_profile(profile: dict):
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
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


def projects_to_text(projects: list) -> str:
    visible = [p for p in projects if p.get("visible", True)]
    if not visible:
        return "(keine Projekte vorhanden)"
    lines = []
    for p in visible:
        grade_str = f" (Note: {p['grade']})" if p.get("grade") else ""
        tags_str  = f" [Tags: {', '.join(p['tags'])}]" if p.get("tags") else ""
        lines.append(f"- {p['title']}{grade_str}{tags_str}:\n  {p['description']}")
    return "\n".join(lines)


def strip_code_fence(text: str) -> str:
    import re
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("html"):
            text = text[4:]
        text = text.rsplit("```", 1)[0]
    # Convert leftover markdown bold/italic to HTML tags
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text.strip()


def call_gemini(prompt: str, max_tokens: int = 8192) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return strip_code_fence(response.text)


# ─── Generation ──────────────────────────────────────────────────────────────

def pick_layout(job_posting: str, company: str, position: str, requested_layout: str) -> str:
    if requested_layout in LAYOUTS:
        return requested_layout
    if requested_layout != "auto":
        return "modern"
    text = f"{job_posting} {company} {position}".lower()
    classic_kw = ["consult","berater","finance","bank","audit","legal","jur","public sector","behörde","verwaltung","compliance","risk","steuer","versicherung"]
    sidebar_kw = ["design","ux","ui","creative","marketing","brand","content","product manager","produktmanager","startup","innovation","growth"]
    if any(k in text for k in classic_kw):
        return "classic"
    if any(k in text for k in sidebar_kw):
        return "sidebar"
    return "modern"


def _call_gemini_json(prompt: str, max_tokens: int = 4096) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return json.loads(response.text)


def generate_cv_content(
    job_posting: str, company: str, position: str,
    language: str, custom_notes: str, projects: list
) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    projects_text = projects_to_text(projects)
    notes_block = f"\nEIGENE HINWEISE (unbedingt berücksichtigen):\n{custom_notes}\n" if custom_notes.strip() else ""
    profile_text = profile_to_text(load_profile())
    profile = load_profile()

    exp = [e for e in profile.get("experience", []) if e.get("visible", True)]
    exp.sort(key=_sort_key, reverse=True)
    edu = [e for e in profile.get("education", []) if e.get("visible", True)]
    edu.sort(key=_sort_key, reverse=True)
    visible_projects = [p for p in projects if p.get("visible", True)]

    exp_ids  = [e["id"] for e in exp if e.get("id")]
    edu_ids  = [e["id"] for e in edu if e.get("id")]
    proj_ids = [p["id"] for p in visible_projects if p.get("id")]

    applicant = get_contact()["full_name"]
    prompt = f"""Du bist ein professioneller CV-Verfasser. Erstelle strukturierten Inhalt {lang} für den Lebenslauf von {applicant}.

PROFIL DES BEWERBERS:
{profile_text}

PROJEKTE & ERFOLGE:
{projects_text}
{notes_block}
STELLENAUSSCHREIBUNG:
{job_posting}

UNTERNEHMEN: {company or "aus Stellenausschreibung entnehmen"}
POSITION: {position or "aus Stellenausschreibung entnehmen"}

Gib ein JSON-Objekt zurück mit exakt dieser Struktur:
{{
  "profile": "2-3 sentence profile statement tailored to this position",
  "experience": [
    {{
      "id": "original ID from profile",
      "title": "job title{' translated to English' if language == 'en' else ' auf Deutsch'}",
      "bullets": ["bullet 1 tailored to position", "bullet 2"]
    }}
  ],
  "education": [
    {{
      "id": "original ID from profile",
      "degree": "degree name{' translated to English' if language == 'en' else ' auf Deutsch'}"
    }}
  ],
  "projects": [
    {{
      "id": "project id",
      "title": "project title{' translated to English' if language == 'en' else ' auf Deutsch'}",
      "description": "project description{' translated to English' if language == 'en' else ' auf Deutsch'}"
    }}
  ],
  "skills": {{
    "{'Technical' if language == 'en' else 'Technisch'}": "React, TypeScript, Python, ...",
    "{'Methods' if language == 'en' else 'Methoden'}": "...",
    "{'Languages' if language == 'en' else 'Sprachen'}": "{'German (Native), English (C1)' if language == 'en' else 'Deutsch (Muttersprache), Englisch (C1)'}"
  }}
}}

Regeln:
- Verwende NUR diese Experience-IDs: {exp_ids}
- Verwende NUR diese Education-IDs: {edu_ids}
- Verwende NUR diese Project-IDs: {proj_ids}
- Wähle die 3-4 relevantesten Projekte
- {"Übersetze alle Titel, Abschlüsse, Skill-Kategorien und Projektbeschreibungen ins Englische" if language == 'en' else "Alles auf Deutsch"}
- Bullet Points: NUR konkrete Tätigkeiten und Ergebnisse, KEIN "– was meine XY-Skills beweist/zeigt/unterstreicht"
- Keine Wiederholungen von Informationen die bereits anderswo stehen
- Erfinde keine Fakten
"""
    return _call_gemini_json(prompt, 4096)


def generate_job_summary(job_posting: str, language: str) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    prompt = f"""Analysiere die folgende Stellenausschreibung und gib eine kompakte Zusammenfassung {lang} zurück.

STELLENAUSSCHREIBUNG:
{job_posting[:8000]}

Gib ein JSON-Objekt zurück mit exakt dieser Struktur:
{{
  "company_does": "2-3 Sätze: Was macht das Unternehmen? Branche, Produkt, Mission.",
  "searching_for": [
    "Stichpunkt 1: konkrete Anforderung an den Bewerber",
    "Stichpunkt 2: ...",
    "Stichpunkt 3: ..."
  ],
  "technologies": [
    "Technologie/Tool 1",
    "Technologie/Tool 2"
  ]
}}

Regeln:
- 4-7 Stichpunkte für "searching_for" (Verantwortlichkeiten, Skills, Erfahrung, Soft Skills)
- "technologies": NUR konkrete Technologien, Frameworks, Sprachen, Tools — keine Soft Skills. Leere Liste falls keine genannt.
- Wenn das Unternehmen nicht beschrieben ist: best-guess auf Basis von Position/Branche, sonst "Nicht in der Ausschreibung beschrieben."
- Keine Floskeln, keine Wiederholungen
"""
    return _call_gemini_json(prompt, 1024)


def generate_anschreiben_content(
    job_posting: str, company: str, position: str,
    contact: str, city: str, language: str,
    custom_notes: str, projects: list,
    company_address: str = ""
) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    today = date.today().strftime("%d. %B %Y") if language == "de" else date.today().strftime("%B %d, %Y")
    projects_text = projects_to_text(projects)
    notes_block = f"\nEIGENE HINWEISE (unbedingt einarbeiten):\n{custom_notes}\n" if custom_notes.strip() else ""
    profile_text = profile_to_text(load_profile())

    settings_data  = load_settings()
    style_analysis = (settings_data.get("style_analysis", {}).get(language) or "").strip()
    style_example  = (settings_data.get("style_examples", {}).get(language) or "").strip()
    style_block = ""
    if style_analysis:
        style_block = (
            "\nSTIL-VORGABE DES BEWERBERS (befolge diese Stilrichtlinien strikt — sie destillieren, "
            "wie der Bewerber selbst schreibt):\n"
            f"{style_analysis[:4000]}\n"
        )
    elif style_example:
        style_block = (
            "\nSTIL-BEISPIEL DES BEWERBERS (orientiere dich an Tonfall, Satzlänge, "
            "Wortwahl und Rhythmus — übernimm aber KEINE Inhalte oder konkreten Formulierungen "
            "wörtlich, da es sich um ein anderes Anschreiben handelt):\n"
            f"\"\"\"\n{style_example[:6000]}\n\"\"\"\n"
        )

    applicant = get_contact()["full_name"]
    prompt = f"""Du bist ein professioneller Bewerbungsschreiber. Erstelle strukturierten Inhalt {lang} für das Anschreiben von {applicant}.
{style_block}
PROFIL DES BEWERBERS:
{profile_text}

PROJEKTE & ERFOLGE:
{projects_text}
{notes_block}
STELLENAUSSCHREIBUNG:
{job_posting}

UNTERNEHMEN: {company or "aus Stellenausschreibung entnehmen"}
POSITION: {position or "aus Stellenausschreibung entnehmen"}
ANREDE: {contact}
ORT: {city or "Berlin"}
DATUM: {today}

STIL: Direkt einsteigen, kein "hiermit bewerbe ich mich". Konkrete Beispiele, keine Floskeln. 4-6 kompakte Absätze.

Gib ein JSON-Objekt zurück mit exakt dieser Struktur:
{{
  "company_name": "Firmenname",
  "company_address": "{company_address if company_address else 'Adresse falls bekannt, sonst leer'}",
  "city_date": "{city or 'Berlin'}, {today}",
  "subject": "Bewerbung um die Stelle als [POSITION]",
  "greeting": "{contact},",
  "paragraphs": [
    "Absatz 1 Text...",
    "Absatz 2 Text...",
    "Absatz 3 Text...",
    "Abschluss-Absatz..."
  ]
}}
"""
    return _call_gemini_json(prompt, 3072)


# ─── Rendering ───────────────────────────────────────────────────────────────

def _render_jobs(jobs_content: list, profile: dict, layout: str, language: str = "de") -> str:
    exp_map = {e["id"]: e for e in profile.get("experience", []) if e.get("id")}
    parts = []
    for item in jobs_content:
        entry = exp_map.get(item.get("id"), {})
        if not entry:
            continue
        title    = item.get("title") or entry.get("title", "")
        company  = entry.get("company", "")
        location = entry.get("location", "")
        start    = fmt_date(entry.get("start"), language=language)
        end      = fmt_date(entry.get("end"), entry.get("current", False), language=language)
        bullets  = item.get("bullets", entry.get("bullets", []))
        bl_html  = "".join(f"<li>{b}</li>" for b in bullets)

        if layout == "classic":
            parts.append(
                f'<div class="job">'
                f'<div class="job-date">{start}<br>– {end}</div>'
                f'<div class="job-content">'
                f'<div class="job-title">{title}</div>'
                f'<div class="job-company">{company}{(", " + location) if location else ""}</div>'
                f'{"<ul>" + bl_html + "</ul>" if bl_html else ""}'
                f'</div></div>'
            )
        else:
            meta = f"{company}{(', ' + location) if location else ''} · {start} – {end}"
            parts.append(
                f'<div class="job">'
                f'<div class="job-title">{title}</div>'
                f'<div class="job-meta">{meta}</div>'
                f'{"<ul>" + bl_html + "</ul>" if bl_html else ""}'
                f'</div>'
            )
    return "\n".join(parts)


def _render_education(edu_content: list, profile: dict, layout: str, language: str = "de") -> str:
    edu_map = {e["id"]: e for e in profile.get("education", []) if e.get("id")}
    parts = []
    for item in edu_content:
        entry = edu_map.get(item.get("id"), {})
        if not entry:
            continue
        degree      = item.get("degree") or entry.get("degree", "")
        institution = entry.get("institution", "")
        location    = entry.get("location", "")
        start       = fmt_date(entry.get("start"), language=language)
        end         = fmt_date(entry.get("end"), entry.get("current", False), language=language)
        details     = list(entry.get("details", []))
        det_html = "".join(f"<li>{d}</li>" for d in details)

        if layout == "sidebar":
            parts.append(
                f'<div class="edu-item">'
                f'<div class="edu-title">{degree}</div>'
                f'<div class="edu-meta">{institution}{(", " + location) if location else ""} · {start} – {end}</div>'
                f'</div>'
            )
        elif layout == "classic":
            parts.append(
                f'<div class="job">'
                f'<div class="job-date">{start}<br>– {end}</div>'
                f'<div class="job-content">'
                f'<div class="job-title">{degree}</div>'
                f'<div class="job-company">{institution}{(", " + location) if location else ""}</div>'
                f'{"<ul>" + det_html + "</ul>" if det_html else ""}'
                f'</div></div>'
            )
        else:
            meta_parts = [institution]
            if location:
                meta_parts.append(location)
            meta_parts.append(f"{start} – {end}")
            parts.append(
                f'<div class="job">'
                f'<div class="job-title">{degree}</div>'
                f'<div class="job-meta">{" · ".join(meta_parts)}</div>'
                f'{"<ul>" + det_html + "</ul>" if det_html else ""}'
                f'</div>'
            )
    return "\n".join(parts)


def _render_projects(projects_content: list, all_projects: list, language: str = "de") -> str:
    proj_map = {p["id"]: p for p in all_projects if p.get("id")}
    grade_label = "Grade" if language == "en" else "Note"
    items = []
    for item in projects_content:
        pid   = item if isinstance(item, str) else item.get("id", "")
        p     = proj_map.get(pid)
        if not p:
            continue
        title = (item.get("title") if isinstance(item, dict) else None) or p["title"]
        desc  = (item.get("description") if isinstance(item, dict) else None) or p["description"]
        grade = f" ({grade_label}: {p['grade']})" if p.get("grade") else ""
        items.append(f"<li><strong>{title}{grade}</strong>: {desc}</li>")
    return "\n".join(items)


def _render_skills_rows(skills: dict) -> str:
    return "\n".join(
        f'<div class="skills-row"><strong>{cat}:</strong><span>{val}</span></div>'
        for cat, val in skills.items()
    )


def _render_skills_dl(skills: dict) -> str:
    return "\n".join(f"<dt>{cat}:</dt><dd>{val}</dd>" for cat, val in skills.items())


def _render_skills_tags(skills: dict) -> str:
    all_s: list[str] = []
    for val in skills.values():
        all_s.extend(s.strip() for s in re.split(r"[,;·•]", val) if s.strip())
    return "".join(f'<span class="skill-tag">{s}</span>' for s in all_s[:12])


I18N = {
    "de": {
        "profile": "Profil", "experience": "Berufserfahrung", "education": "Ausbildung",
        "projects": "Projekte &amp; Erfolge", "skills": "Fähigkeiten &amp; Kenntnisse",
        "skills_classic": "Fähigkeiten", "contact": "Kontakt",
        "core_skills": "Kernkompetenzen", "languages": "Sprachen",
        "lang_de": "Deutsch – Muttersprache", "lang_en": "Englisch – C1",
        "signature": "Mit freundlichen Grüßen",
    },
    "en": {
        "profile": "Profile", "experience": "Work Experience", "education": "Education",
        "projects": "Projects &amp; Achievements", "skills": "Skills &amp; Competencies",
        "skills_classic": "Skills", "contact": "Contact",
        "core_skills": "Core Competencies", "languages": "Languages",
        "lang_de": "German – Native", "lang_en": "English – C1",
        "signature": "Yours sincerely",
    },
}


def render_cv_html(content: dict, layout: str, language: str, all_projects: list) -> str:
    profile   = load_profile()
    ldef      = LAYOUTS.get(layout, LAYOUTS["modern"])
    t         = I18N.get(language, I18N["de"])
    c         = get_contact()
    jobs_html = _render_jobs(content.get("experience", []), profile, layout, language)
    edu_html  = _render_education(content.get("education", []), profile, layout, language)
    proj_html = _render_projects(content.get("projects", []), all_projects, language)
    skills    = content.get("skills", {})
    prof_text = content.get("profile", "")

    if layout == "modern":
        body = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="contact">
    <div class="contact-item"><span>📍</span><span>{c["address_dot"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
  </div>
</div>
<div class="section"><h2>{t['profile']}</h2><p>{prof_text}</p></div>
<div class="section"><h2>{t['experience']}</h2>{jobs_html}</div>
<div class="section"><h2>{t['education']}</h2>{edu_html}</div>
<div class="section"><h2>{t['projects']}</h2><ul>{proj_html}</ul></div>
<div class="section"><h2>{t['skills']}</h2>{_render_skills_rows(skills)}</div>"""

    elif layout == "sidebar":
        all_edu = [e for e in profile.get("education", []) if e.get("visible", True)]
        all_edu.sort(key=_sort_key, reverse=True)
        edu_sidebar = _render_education([{"id": e["id"]} for e in all_edu], profile, "sidebar", language)
        body = f"""<div class="page">
  <div class="sidebar">
    <h1>{c["full_name"]}</h1>
    <h2>{t['contact']}</h2>
    <div class="contact-item"><span>📍</span><span>{c["address_sidebar_html"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
    <h2>{t['core_skills']}</h2>
    {_render_skills_tags(skills)}
    <h2>{t['languages']}</h2>
    <p>{t['lang_de']}</p><p>{t['lang_en']}</p>
    <h2>{t['education']}</h2>
    {edu_sidebar}
  </div>
  <div class="main">
    <h2>{t['profile']}</h2>
    <p>{prof_text}</p>
    <h2>{t['experience']}</h2>
    {jobs_html}
    <h2>{t['projects']}</h2>
    <ul>{proj_html}</ul>
  </div>
</div>"""

    else:  # classic
        body = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="header-sub">
    <span>{c["address_dot"]}</span>
    <span>{c["phone"]}</span>
    <span><a href="mailto:{c["email"]}">{c["email"]}</a></span>
  </div>
</div>
<h2>{t['profile']}</h2>
<p>{prof_text}</p>
<h2>{t['experience']}</h2>
{jobs_html}
<h2>{t['education']}</h2>
{edu_html}
<h2>{t['projects']}</h2>
<ul>{proj_html}</ul>
<h2>{t['skills_classic']}</h2>
<dl class="skills-block">{_render_skills_dl(skills)}</dl>"""

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{c["full_name"]} - Lebenslauf</title>
{ldef['style']}
</head>
<body>
{body}
</body>
</html>"""


def render_anschreiben_html(content: dict, language: str) -> str:
    company_name    = content.get("company_name", "")
    company_address = content.get("company_address", "")
    city_date       = content.get("city_date", "")
    subject         = content.get("subject", "")
    greeting        = content.get("greeting", "Sehr geehrte Damen und Herren,")
    paragraphs      = content.get("paragraphs", [])
    signer          = get_contact()["full_name"]

    company_block = f"<strong>{company_name}</strong>"
    if company_address:
        company_block += "<br/>" + company_address.replace("\n", "<br/>")

    paras_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{signer} - Anschreiben</title>
{ANSCHREIBEN_HTML_STYLE}
</head>
<body>
<div class="content-box">
  <div class="address-row">
    <div class="recipient-address">{company_block}</div>
    <div class="sender-address">{sender_address_html()}</div>
  </div>
  <p class="date-line">{city_date}</p>
</div>
<div class="content-box">
  <p class="subject-line">{subject}</p>
  <p><strong>{greeting}</strong></p>
  {paras_html}
  <p class="signature">{I18N.get(language, I18N["de"])["signature"]}<br>{signer}</p>
</div>
</body>
</html>"""


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/fetch-job", methods=["POST"])
def fetch_job():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "Keine URL angegeben."}), 400
    try:
        resp = http_requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        cleaned = "\n".join(lines)
        if len(cleaned) > 12000:
            cleaned = cleaned[:12000] + "\n[...]"
        return jsonify({"text": cleaned})
    except Exception as e:
        return jsonify({"error": f"Konnte URL nicht laden: {str(e)}"}), 500


@app.route("/layouts", methods=["GET"])
def get_layouts():
    return jsonify([{"id": k, "name": v["name"], "style": v["style"]} for k, v in LAYOUTS.items()])


@app.route("/test-connection", methods=["GET"])
def test_connection():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify({"ok": False, "error": "GEMINI_API_KEY nicht gesetzt"}), 500
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents="Say: OK",
            config=types.GenerateContentConfig(
                max_output_tokens=10,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return jsonify({"ok": True, "model": GEMINI_MODEL, "response": response.text.strip()})
    except Exception as e:
        return jsonify({"ok": False, "model": GEMINI_MODEL, "error": str(e)}), 500


@app.route("/generate", methods=["POST"])
def generate():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt. Prüfe deine .env Datei."}), 500

    data         = request.json
    job_posting  = data.get("job_posting", "").strip()
    if not job_posting:
        return jsonify({"error": "Bitte Stellenausschreibung einfügen."}), 400

    company         = data.get("company", "").strip()
    position        = data.get("position", "").strip()
    contact         = data.get("contact", "Sehr geehrte Damen und Herren").strip()
    city            = data.get("city", "Berlin").strip()
    language        = data.get("language", "de")
    doc_type        = data.get("doc_type", "both")
    custom_notes    = data.get("custom_notes", "").strip()
    layout          = data.get("layout", "modern")
    company_address = data.get("company_address", "").strip()
    resolved_layout = pick_layout(job_posting, company, position, layout)

    projects = load_projects()
    result   = {"layout_used": resolved_layout, "job_posting": job_posting}

    try:
        if doc_type in ("cv", "both"):
            result["cv_content"] = generate_cv_content(
                job_posting, company, position, language, custom_notes, projects
            )
        if doc_type in ("anschreiben", "both"):
            result["anschreiben_content"] = generate_anschreiben_content(
                job_posting, company, position, contact, city, language, custom_notes, projects,
                company_address=company_address
            )
        result["job_summary"] = generate_job_summary(job_posting, language)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500

    job_url = (data.get("job_url") or "").strip()
    logged = log_application(
        company, position, job_posting,
        job_url=job_url,
        cv_content          = result.get("cv_content"),
        anschreiben_content = result.get("anschreiben_content"),
        layout_used         = resolved_layout,
        language            = language,
    )
    if logged:
        result["application"] = logged

    return jsonify(result)


@app.route("/render", methods=["POST"])
def render_doc():
    data     = request.json
    doc_type = data.get("doc_type", "cv")
    language = data.get("language", "de")
    projects = load_projects()

    try:
        if doc_type == "cv":
            html = render_cv_html(data.get("content", {}), data.get("layout", "modern"), language, projects)
        elif doc_type == "anschreiben":
            html = render_anschreiben_html(data.get("content", {}), language)
        else:
            return jsonify({"error": "Unbekannter doc_type"}), 400
    except Exception as e:
        return jsonify({"error": f"Render-Fehler: {str(e)}"}), 500

    return jsonify({"html": html})


@app.route("/save", methods=["POST"])
def save_doc():
    data     = request.json
    doc_type = data.get("doc_type", "cv")
    filename = data.get("filename", "document.html")
    html     = data.get("html", "")

    if not html:
        return jsonify({"error": "Kein Inhalt."}), 400

    # Sanitise filename — keep only safe chars
    safe = re.sub(r'[^\w\-_\.]', '_', filename)
    if not safe.endswith(".html"):
        safe = safe.rsplit(".", 1)[0] + ".html"

    folder = ANSCHREIBEN_DIR if doc_type == "anschreiben" else CV_DIR
    path   = os.path.join(folder, safe)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    return jsonify({"ok": True, "path": path, "filename": safe})


@app.route("/extract-fields", methods=["POST"])
def extract_fields():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data        = request.json
    job_posting = (data.get("job_posting") or "").strip()
    if not job_posting:
        return jsonify({"error": "Kein Text angegeben."}), 400

    prompt = f"""Extrahiere folgende Informationen aus dieser Stellenausschreibung. Falls eine Information nicht vorhanden ist, gib null zurück.

STELLENAUSSCHREIBUNG:
{job_posting[:6000]}

Gib ein JSON-Objekt zurück:
{{
  "company": "Firmenname oder null",
  "position": "Genaue Stellenbezeichnung oder null",
  "contact": "Persönliche Anrede falls Name bekannt z.B. 'Sehr geehrte Frau Müller', sonst 'Sehr geehrte Damen und Herren'",
  "city": "Stadt des Unternehmensstandorts oder null",
  "company_address": "Vollständige Postanschrift mit Straße, PLZ und Stadt — nur wenn explizit in der Ausschreibung genannt, sonst null"
}}
"""
    try:
        result = _call_gemini_json(prompt, 512)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Fehler: {str(e)}"}), 500


@app.route("/improve-text", methods=["POST"])
def improve_text():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data        = request.json
    text        = (data.get("text") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    if not text or not instruction:
        return jsonify({"error": "Text und Anweisung erforderlich."}), 400

    prompt = f"""Du bist ein professioneller Bewerbungsschreiber. Überarbeite den folgenden Absatz eines Anschreibens basierend auf der Anweisung.

ORIGINAL-ABSATZ:
{text}

ANWEISUNG:
{instruction}

Regeln:
- Gib NUR den überarbeiteten Absatz zurück, ohne Erklärungen oder Anführungszeichen
- Behalte Stil und Länge ähnlich, außer die Anweisung sagt etwas anderes
- Keine neuen Fakten erfinden
"""
    try:
        result = call_gemini(prompt, 1024)
        return jsonify({"text": result})
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500


@app.route("/chat", methods=["POST"])
def chat():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500

    data         = request.json
    message      = data.get("message", "").strip()
    history      = data.get("history", [])   # [{role, text}, ...]
    cv_html      = data.get("cv_html", "")
    anschreiben  = data.get("anschreiben_html", "")
    job_posting  = data.get("job_posting", "")

    if not message:
        return jsonify({"error": "Keine Nachricht."}), 400

    from bs4 import BeautifulSoup

    def html_to_text(html):
        if not html:
            return ""
        return BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)

    cv_text          = html_to_text(cv_html)
    anschreiben_text = html_to_text(anschreiben)

    context_parts = [f"Du bist ein erfahrener HR-Berater und Bewerbungscoach für {get_contact()['full_name']}."]
    if job_posting:
        context_parts.append(f"STELLENAUSSCHREIBUNG:\n{job_posting[:3000]}")
    if cv_text:
        context_parts.append(f"AKTUELLER LEBENSLAUF (Text):\n{cv_text[:3000]}")
    if anschreiben_text:
        context_parts.append(f"AKTUELLES ANSCHREIBEN (Text):\n{anschreiben_text[:2000]}")
    context_parts.append(
        "Beantworte Fragen präzise und konkret. Gib bei Verbesserungsvorschlägen immer "
        "spezifische Beispiele. Antworte auf Deutsch außer der Nutzer schreibt Englisch. "
        "Nutze Markdown für Formatierung (Listen, Fett) – das wird im Chat gerendert."
    )
    system_prompt = "\n\n".join(context_parts)

    # Build contents list: system + history + new message
    contents = [{"role": "user", "parts": [{"text": system_prompt + "\n\nVerstanden? Dann warte auf die erste Frage."}]},
                {"role": "model", "parts": [{"text": "Verstanden! Ich habe den Kontext gelesen und helfe dir gerne mit konkreten Verbesserungsvorschlägen."}]}]

    for h in history:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["text"]}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    try:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return jsonify({"reply": response.text.strip()})
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500


@app.route("/profile", methods=["GET"])
def get_profile():
    return jsonify(load_profile())


@app.route("/profile/<section>", methods=["POST"])
def add_profile_entry(section):
    if section not in ("experience", "education"):
        return jsonify({"error": "Ungültiger Bereich."}), 400
    data    = request.json
    profile = load_profile()
    entry   = {**data, "id": data.get("id") or str(uuid.uuid4())[:8]}
    profile[section].append(entry)
    save_profile(profile)
    return jsonify(entry), 201


@app.route("/profile/<section>/<entry_id>", methods=["PUT"])
def update_profile_entry(section, entry_id):
    if section not in ("experience", "education"):
        return jsonify({"error": "Ungültiger Bereich."}), 400
    data    = request.json
    profile = load_profile()
    for e in profile[section]:
        if e["id"] == entry_id:
            e.update({k: v for k, v in data.items() if k != "id"})
            save_profile(profile)
            return jsonify(e)
    return jsonify({"error": "Eintrag nicht gefunden."}), 404


@app.route("/profile/<section>/<entry_id>", methods=["DELETE"])
def delete_profile_entry(section, entry_id):
    if section not in ("experience", "education"):
        return jsonify({"error": "Ungültiger Bereich."}), 400
    profile  = load_profile()
    original = len(profile[section])
    profile[section] = [e for e in profile[section] if e["id"] != entry_id]
    if len(profile[section]) == original:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    save_profile(profile)
    return jsonify({"ok": True})


@app.route("/profile/list/<list_name>", methods=["POST"])
def add_profile_list_item(list_name):
    if list_name not in ("hard_skills", "soft_skills", "languages"):
        return jsonify({"error": "Ungültige Liste."}), 400
    data = request.json or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name ist Pflicht."}), 400

    profile = load_profile()
    item = {
        "id": data.get("id") or str(uuid.uuid4())[:8],
        "name": name,
    }
    if list_name == "languages":
        item["level"] = (data.get("level") or "").strip()

    profile[list_name].append(item)
    save_profile(profile)
    return jsonify(item), 201


@app.route("/profile/list/<list_name>/<item_id>", methods=["PUT"])
def update_profile_list_item(list_name, item_id):
    if list_name not in ("hard_skills", "soft_skills", "languages"):
        return jsonify({"error": "Ungültige Liste."}), 400
    data = request.json or {}
    profile = load_profile()

    for item in profile[list_name]:
        if item["id"] == item_id:
            if "name" in data:
                item["name"] = (data.get("name") or "").strip()
            if list_name == "languages" and "level" in data:
                item["level"] = (data.get("level") or "").strip()
            save_profile(profile)
            return jsonify(item)
    return jsonify({"error": "Eintrag nicht gefunden."}), 404


@app.route("/profile/list/<list_name>/<item_id>", methods=["DELETE"])
def delete_profile_list_item(list_name, item_id):
    if list_name not in ("hard_skills", "soft_skills", "languages"):
        return jsonify({"error": "Ungültige Liste."}), 400
    profile = load_profile()
    original = len(profile[list_name])
    profile[list_name] = [i for i in profile[list_name] if i["id"] != item_id]
    if len(profile[list_name]) == original:
        return jsonify({"error": "Eintrag nicht gefunden."}), 404
    save_profile(profile)
    return jsonify({"ok": True})


@app.route("/projects", methods=["GET"])
def get_projects():
    return jsonify(load_projects())


@app.route("/projects", methods=["POST"])
def add_project():
    data = request.json
    if not data.get("title") or not data.get("description"):
        return jsonify({"error": "Titel und Beschreibung sind Pflicht."}), 400
    project = {
        "id":          data.get("id") or str(uuid.uuid4())[:8],
        "title":       data["title"].strip(),
        "description": data["description"].strip(),
        "tags":        [t.strip() for t in data.get("tags", []) if t.strip()],
        "grade":       data.get("grade") or None,
        "visible":     data.get("visible", True),
    }
    projects = load_projects()
    projects.append(project)
    save_projects(projects)
    return jsonify(project), 201


@app.route("/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    data = request.json
    projects = load_projects()
    for p in projects:
        if p["id"] == project_id:
            p["title"]       = data.get("title", p["title"]).strip()
            p["description"] = data.get("description", p["description"]).strip()
            p["tags"]        = [t.strip() for t in data.get("tags", p.get("tags", [])) if t.strip()]
            p["grade"]       = data.get("grade", p.get("grade")) or None
            p["visible"]     = data.get("visible", p.get("visible", True))
            save_projects(projects)
            return jsonify(p)
    return jsonify({"error": "Projekt nicht gefunden."}), 404


@app.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    projects = load_projects()
    new_list = [p for p in projects if p["id"] != project_id]
    if len(new_list) == len(projects):
        return jsonify({"error": "Projekt nicht gefunden."}), 404
    save_projects(new_list)
    return jsonify({"ok": True})


@app.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@app.route("/settings", methods=["PUT"])
def update_settings():
    data     = request.json or {}
    settings = load_settings()
    for field in ("style_examples", "style_analysis"):
        block = data.get(field)
        if isinstance(block, dict):
            for k in ("de", "en"):
                if k in block:
                    settings[field][k] = (block[k] or "").strip()
    save_settings(settings)
    return jsonify(settings)


@app.route("/analyze-style", methods=["POST"])
def analyze_style():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data     = request.json or {}
    example  = (data.get("example") or "").strip()
    language = data.get("language") or "de"
    if not example:
        return jsonify({"error": "Beispiel-Text ist leer."}), 400
    if language not in ("de", "en"):
        return jsonify({"error": "Sprache muss 'de' oder 'en' sein."}), 400

    lang_label = "auf Deutsch" if language == "de" else "in English"
    prompt = f"""Analysiere den Schreibstil des folgenden Beispiel-Anschreibens und beschreibe ihn {lang_label} so präzise, dass eine andere KI diesen Stil später nachahmen kann — ohne die Inhalte zu übernehmen.

BEISPIEL-TEXT:
\"\"\"
{example[:6000]}
\"\"\"

Gib 6–10 Stichpunkte zurück, die folgende Aspekte abdecken (sofern erkennbar):
- Tonfall (formell ↔ locker, direkt ↔ zurückhaltend, selbstbewusst ↔ bescheiden)
- Satzbau (Länge, Aktiv/Passiv, parataktisch/hypotaktisch)
- Wortwahl (Fachsprache, Anglizismen, branchenspezifische Begriffe, bewusst gemiedene Floskeln)
- Strukturmuster (Einstieg, Argumentationslogik, Abschluss)
- Wiederkehrende rhetorische Mittel oder Eigenheiten

Format: reine Markdown-Bullet-Liste (\"- …\"), kein Vor- oder Nachwort, keine Anrede an mich.
"""
    try:
        analysis = call_gemini(prompt, 1024).strip()
        return jsonify({"analysis": analysis})
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500


@app.route("/parse-cv-pdf", methods=["POST"])
def parse_cv_pdf():
    """Extract text from an uploaded CV PDF and ask Gemini to structure it
    into the same `cv_content` JSON shape that /generate produces.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500

    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "Keine Datei hochgeladen."}), 400
    if not upload.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Bitte eine PDF-Datei hochladen."}), 400

    try:
        from pypdf import PdfReader
    except ImportError:
        return jsonify({"error": "pypdf nicht installiert (pip install pypdf)."}), 500

    try:
        reader = PdfReader(upload.stream)
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        text = "\n".join(pages).strip()
    except Exception as e:
        return jsonify({"error": f"PDF konnte nicht gelesen werden: {e}"}), 400

    if not text:
        return jsonify({"error": "Aus der PDF konnte kein Text extrahiert werden."}), 400

    # Self-contained shape: experience/education carry company/institution inline
    # (not via profile ID lookup) because this PDF doesn't reference the user's
    # current profile.
    prompt = f"""Du erhältst den Rohtext eines Lebenslaufs (CV) aus einer PDF.
Extrahiere die Inhalte in folgendes JSON-Format. Wenn ein Feld nicht im Text
steht, lass es weg bzw. setze es auf null oder eine leere Liste.

CV-TEXT:
\"\"\"
{text[:14000]}
\"\"\"

Gib NUR ein JSON-Objekt zurück:
{{
  "profile": "2-4 Sätze Profil-Statement (falls nicht vorhanden, freilassen)",
  "experience": [
    {{
      "title":    "Berufsbezeichnung",
      "company":  "Unternehmen",
      "location": "Stadt (falls vorhanden)",
      "start":    "YYYY-MM (falls vorhanden, sonst null)",
      "end":      "YYYY-MM oder 'heute' (falls vorhanden)",
      "bullets":  ["bullet 1", "bullet 2"]
    }}
  ],
  "education": [
    {{
      "degree":      "Abschluss / Studiengang",
      "institution": "Universität / Schule",
      "location":    "Stadt",
      "start":       "YYYY-MM",
      "end":         "YYYY-MM"
    }}
  ],
  "projects": [
    {{
      "title":       "Projekttitel",
      "description": "1-2 Sätze"
    }}
  ],
  "skills": {{
    "Technisch": "kommagetrennte Liste",
    "Methoden":  "kommagetrennte Liste",
    "Sprachen":  "kommagetrennte Liste"
  }}
}}

Regeln:
- Nutze für skills die Kategorien aus dem CV; wenn keine vorhanden, fasse
  alle Hard-Skills unter "Technisch", Soft-Skills unter "Methoden", Sprachen
  unter "Sprachen" zusammen.
- Erfinde keine Inhalte. Wenn der Abschnitt im CV fehlt, gib eine leere Liste
  bzw. ein leeres Objekt zurück.
"""
    try:
        cv_content = _call_gemini_json(prompt, 4096)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {e}"}), 500

    # Sanity-default missing keys so the frontend can rely on the shape
    cv_content.setdefault("profile", "")
    for key in ("experience", "education", "projects"):
        if not isinstance(cv_content.get(key), list):
            cv_content[key] = []
    if not isinstance(cv_content.get("skills"), dict):
        cv_content["skills"] = {}

    summary = {
        "experience_count": len(cv_content["experience"]),
        "education_count":  len(cv_content["education"]),
        "project_count":    len(cv_content["projects"]),
        "skill_count":      sum(
            len([s for s in str(v).split(",") if s.strip()])
            for v in cv_content["skills"].values()
        ),
    }
    return jsonify({"cv_content": cv_content, "summary": summary})


@app.route("/applications", methods=["GET"])
def list_applications():
    return jsonify(load_applications())


@app.route("/applications/<app_id>", methods=["GET"])
def fetch_application(app_id):
    a = db.get_application(app_id)
    if not a:
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404
    return jsonify(a)


@app.route("/applications", methods=["POST"])
def create_application():
    data     = request.json or {}
    company  = (data.get("company") or "").strip()
    position = (data.get("position") or "").strip()
    if not company and not position:
        return jsonify({"error": "Unternehmen oder Position erforderlich."}), 400
    stage = data.get("stage") or "documents_created"
    if stage not in APPLICATION_STAGES:
        return jsonify({"error": "Ungültige Stage."}), 400

    now = _now_iso()
    applied_at = (data.get("applied_at") or "").strip() or None
    if not applied_at:
        sent_idx = APPLICATION_STAGES.index("application_sent")
        if APPLICATION_STAGES.index(stage) >= sent_idx:
            applied_at = _today_iso()
    cv_content          = data.get("cv_content")
    anschreiben_content = data.get("anschreiben_content")
    entry = {
        "id":                  str(uuid.uuid4())[:8],
        "company":             company,
        "position":            position,
        "stage":               stage,
        "stage_history":       [{"stage": stage, "at": now}],
        "applied_at":          applied_at,
        "feedback":            (data.get("feedback") or "").strip(),
        "job_posting":         (data.get("job_posting") or "")[:JOB_POSTING_MAX],
        "job_url":             (data.get("job_url") or "").strip()[:JOB_URL_MAX],
        "cv_content":          cv_content          if isinstance(cv_content,          dict) else None,
        "anschreiben_content": anschreiben_content if isinstance(anschreiben_content, dict) else None,
        "layout_used":         data.get("layout_used"),
        "language":            data.get("language"),
        "created_at":          now,
        "updated_at":          now,
    }
    db.upsert_application(entry)
    db.append_stage_event(entry["id"], stage, now)
    return jsonify(db.get_application(entry["id"]) or entry), 201


@app.route("/applications/<app_id>", methods=["PUT"])
def update_application(app_id):
    data = request.json or {}
    a = db.get_application(app_id)
    if not a:
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404

    new_event = None
    if "company" in data:
        a["company"] = (data.get("company") or "").strip()
    if "position" in data:
        a["position"] = (data.get("position") or "").strip()
    if "stage" in data:
        if data["stage"] not in APPLICATION_STAGES:
            return jsonify({"error": "Ungültige Stage."}), 400
        new_event = apply_stage_transition(a, data["stage"])
    if "feedback" in data:
        a["feedback"] = data.get("feedback") or ""
    if "applied_at" in data:
        v = (data.get("applied_at") or "").strip()
        a["applied_at"] = v or None
    if "job_posting" in data:
        a["job_posting"] = (data.get("job_posting") or "")[:JOB_POSTING_MAX]
    if "job_url" in data:
        a["job_url"] = (data.get("job_url") or "").strip()[:JOB_URL_MAX]
    a["updated_at"] = _now_iso()

    db.upsert_application(a)
    if new_event:
        db.append_stage_event(a["id"], new_event["stage"], new_event["at"])

    if "rejected_at" in data:
        if a.get("stage") != "rejected":
            return jsonify({"error": "„Abgesagt am“ ist nur bei Status „Abgesagt\" erlaubt."}), 400
        raw = (data.get("rejected_at") or "").strip()
        norm = _normalize_calendar_date(raw)
        if not norm:
            return jsonify({"error": "Ungültiges Datum für „Abgesagt am\" (erwartet JJJJ-MM-TT)."}), 400
        n = db.update_last_rejected_event_at(app_id, norm)
        if n == 0:
            db.append_stage_event(app_id, "rejected", norm)

    fresh = db.get_application(app_id)
    return jsonify(fresh if fresh else a)


@app.route("/applications/<app_id>", methods=["DELETE"])
def delete_application_route(app_id):
    if not db.delete_application(app_id):
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
