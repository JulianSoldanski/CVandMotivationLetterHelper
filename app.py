import os
import json
import uuid
import re
import hashlib
import requests as http_requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, Response, make_response
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from html import escape as html_escape

from cv_layouts import ANSCHREIBEN_HTML_STYLE, LAYOUTS, PROJECT_LIST_STYLE
from personal_config import get_candidate_base, get_contact, sender_address_html
import db
import demo_mode

load_dotenv()

# Wire up demo workspace BEFORE init_schema() so the DB created on first run
# lands in the demo workdir (data/.demo/) instead of the real data/ dir.
DEMO_ACTIVE = demo_mode.bootstrap()
if DEMO_ACTIVE:
    print(f"[demo] DEMO_MODE active — using workspace {demo_mode.DEMO_WORK}")

app = Flask(__name__)

GEMINI_MODEL      = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
PROJECTS_FILE     = demo_mode.projects_path()
PROFILE_FILE      = demo_mode.profile_path()
APPLICATIONS_FILE = os.path.join(os.path.dirname(__file__), "data", "applications.json")  # legacy, only read by the JSON→SQLite migrator
SETTINGS_FILE     = demo_mode.settings_path()

db.init_schema()
JOB_POSTING_MAX = 50_000
JOB_URL_MAX = 500
JOB_QUEUE_NOTE_MAX  = 500
JOB_QUEUE_TITLE_MAX = 300

# Tracking-Parameter, die beim Hinzufügen zur Queue gestrippt werden, damit
# dieselbe Stelle nicht 3× drin landet, weil sie über verschiedene Quellen
# (LinkedIn-Ad, Google-Search, Newsletter) ankommt.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
    "ref", "ref_src", "ref_url", "referrer", "source",
    "trk", "trkCampaign", "trackingId",
}
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
PROJEKTLISTE_DIR  = os.path.join(os.path.dirname(__file__), "projektliste")
os.makedirs(CV_DIR, exist_ok=True)
os.makedirs(ANSCHREIBEN_DIR, exist_ok=True)
os.makedirs(PROJEKTLISTE_DIR, exist_ok=True)


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
# Projects per translation request — small enough that the reply can't hit the
# output token limit, large enough to keep a full list to a couple of calls.
PROJECT_TRANSLATE_BATCH = 6


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
        # Bookkeeping for the auto-translation: `auto` lists the fields that were
        # machine-written (only those may be refreshed later), `src` fingerprints
        # the source text they were derived from.
        loc["auto"] = [f for f in _list(block.get("auto")) if f in PROJECT_LOCALIZED_TEXT + PROJECT_LOCALIZED_LIST]
        loc["src"]  = _s(block.get("src"))
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


def _project_source_fingerprint(project: dict, detail: dict) -> str:
    """Fingerprint of the text a translation is derived from.

    Changes when the author edits the project's title, description or team
    size, which is exactly when a cached machine translation goes stale.
    """
    raw = "\x1f".join([
        project.get("title", "") or "",
        project.get("description", "") or "",
        detail.get("team_size", "") or "",
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _project_needs_translation(project: dict, detail: dict, language: str) -> bool:
    """True if printing this project in `language` would fall back to source text.

    Also true when the source text changed since the cached translation was
    made — otherwise an edited description keeps showing its stale translation.
    """
    loc   = detail[language]
    other = detail["en" if language == "de" else "de"]

    # Once a block has been machine-filled, the fingerprint alone decides: same
    # source text means nothing to do (so a field the model happened to drop
    # isn't retried on every single render), changed source means redo it.
    if loc["src"]:
        return loc["src"] != _project_source_fingerprint(project, detail)
    if project.get("title") and not loc["title"]:
        return True
    if project.get("description") and not loc["summary"]:
        return True
    if detail["team_size"] and not loc["team_size"]:
        return True
    # Long-form content drafted in one language only.
    if any(other[field] and not loc[field] for field in ("role", "situation", "result", "contributions")):
        return True
    return False


def _translate_project_blocks(pending: list, language: str) -> dict:
    """Translate every pending project into `language` in a single Gemini call.

    Source material is each project's own text plus whatever was already
    drafted in the other language, so a project with a full long-form German
    entry comes back as a full English one instead of a bare title.

    Returns {project_id: localized_block}.
    """
    target = "German" if language == "de" else "English"
    other  = "en" if language == "de" else "de"

    items = []
    for project, detail in pending:
        src = detail[other]
        items.append({
            "id":            project.get("id", ""),
            "title":         project.get("title", ""),
            "description":   project.get("description", ""),
            "team_size":     detail["team_size"],
            "role":          src["role"],
            "situation":     src["situation"],
            "contributions": src["contributions"],
            "result":        src["result"],
        })

    prompt = f"""You translate CV project entries. Output language: {target}.

Translate every field of every project below into {target}. Source text may
already be in {target} — then return it unchanged apart from obvious fixes.

PROJECTS (JSON):
{json.dumps(items, ensure_ascii=False, indent=1)}

Respond with JSON only, in exactly this structure:
{{
  "projects": [
    {{
      "id": "the id from the input, unchanged",
      "title": "project title in {target}",
      "summary": "the description in {target}, same length and level of detail",
      "role": "in {target}, or \\"\\" if the input field was empty",
      "situation": "in {target}, or \\"\\"",
      "contributions": ["in {target}, same number of bullets, [] if input was empty"],
      "result": "in {target}, or \\"\\"",
      "team_size": "in {target} (e.g. \\"4 Personen\\" <-> \\"4 people\\"), or \\"\\""
    }}
  ]
}}

Rules:
- One object per input project, same ids, nothing invented, nothing dropped.
- Translate, do not rewrite: keep every fact, number, grade and claim as-is.
- Keep proper nouns untranslated (companies, universities, product and tool
  names, technologies like React or Python). Translate degree names, course
  titles, roles and generic descriptions.
- An empty input field stays empty in the output — never fill a gap.
"""
    result = _call_gemini_json(prompt, 8192)
    blocks = {}
    for entry in (result.get("projects") or []):
        if isinstance(entry, dict) and entry.get("id"):
            blocks[str(entry["id"])] = entry
    return blocks


def ensure_project_language(projects: list, language: str) -> list:
    """Guarantee every project can be printed entirely in `language`.

    Missing (or stale) localized text is translated once and cached back into
    projects.json, so later renders and the project editor reuse it. Only
    machine-written fields are ever overwritten — anything typed by hand in the
    editor stays untouched.

    Best-effort by design: without an API key, or when the call fails, the
    projects come back with their source text and the renderers fall back to it
    as before. A document is never blocked on a translation.
    """
    if language not in PROJECT_DETAIL_LANGS:
        language = "de"
    for p in projects:
        p["detail"] = normalize_project_detail(p.get("detail"))

    pending = [(p, p["detail"]) for p in projects if _project_needs_translation(p, p["detail"], language)]
    if not pending or not os.environ.get("GEMINI_API_KEY"):
        return projects

    # Chunked so a long project list can't run into the output token limit and
    # come back truncated — a half-parsed batch would translate nothing at all.
    blocks: dict = {}
    for start in range(0, len(pending), PROJECT_TRANSLATE_BATCH):
        chunk = pending[start:start + PROJECT_TRANSLATE_BATCH]
        try:
            blocks.update(_translate_project_blocks(chunk, language))
        except Exception as e:
            print(f"[projects] translation to {language} failed for {len(chunk)} project(s), using source text: {e}")

    changed = False
    for project, detail in pending:
        block = blocks.get(str(project.get("id", "")))
        if not block:
            continue
        loc   = detail[language]
        fresh = normalize_project_detail({language: block})[language]
        auto  = list(loc["auto"])
        for field in PROJECT_LOCALIZED_TEXT + PROJECT_LOCALIZED_LIST:
            # Hand-written text wins: only empty fields and earlier machine
            # output get replaced.
            if loc[field] and field not in auto:
                continue
            if not fresh[field]:
                continue
            loc[field] = fresh[field]
            if field not in auto:
                auto.append(field)
        loc["auto"] = auto
        loc["src"]  = _project_source_fingerprint(project, detail)
        changed = True

    if changed:
        _persist_project_details(projects)
    return projects


def _persist_project_details(projects: list):
    """Cache the freshly translated blocks without clobbering concurrent edits.

    Only the `detail` of known ids is written back; everything else on disk
    (including projects added or edited in another tab meanwhile) is kept.
    """
    details = {p["id"]: p["detail"] for p in projects if p.get("id")}
    try:
        stored = load_projects()
        for p in stored:
            if p.get("id") in details:
                p["detail"] = details[p["id"]]
        save_projects(stored)
    except OSError as e:
        print(f"[projects] could not cache translations: {e}")


def load_settings() -> dict:
    """Settings hold a single, language-agnostic writing style.

    The style example may be in any language; the distilled analysis is an
    English style guide applied to both German and English generation.
    Legacy files used per-language dicts ({"de": ..., "en": ...}); those are
    migrated on read by collapsing to whichever language had content.
    """
    defaults = {"style_example": "", "style_analysis": ""}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
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
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today_iso() -> str:
    return date.today().isoformat()


def _normalize_queue_url(url: str) -> str:
    """Lowercase scheme/host, strip tracking params, drop fragment.

    Best-effort dedup: turns linkedin.com/...?utm_source=newsletter#fragment
    into linkedin.com/... so the same posting through two channels collapses.
    Leaves the path + meaningful query params intact.
    """
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url[:JOB_URL_MAX]
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    kept = [
        (k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
        and not any(k.lower().startswith(p) for p in _TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(kept)
    cleaned = urlunsplit((scheme, netloc, parts.path, query, ""))
    return cleaned[:JOB_URL_MAX]


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
    company_info: dict | None = None,
    fit_score: dict | None = None,
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
            existing["job_posting"] = job_posting[:JOB_POSTING_MAX]
        if job_url:
            existing["job_url"] = job_url[:JOB_URL_MAX]
        if cv_content is not None:
            existing["cv_content"] = cv_content
        if anschreiben_content is not None:
            existing["anschreiben_content"] = anschreiben_content
        if company_info is not None:
            existing["company_info"] = company_info
        if fit_score is not None:
            existing["fit_score"] = fit_score
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
        "job_posting":         job_posting[:JOB_POSTING_MAX] if job_posting else "",
        "job_url":             job_url[:JOB_URL_MAX] if job_url else "",
        "cv_content":          cv_content,
        "anschreiben_content": anschreiben_content,
        "company_info":        company_info,
        "fit_score":           fit_score,
        "layout_used":         layout_used,
        "language":            language,
        "created_at":          now,
        "updated_at":          now,
        "research_seconds":    tracked_seconds,
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


def _call_gemini_with_search(prompt: str, max_tokens: int = 2048) -> tuple[str, list[str]]:
    """Call Gemini with the Google Search grounding tool enabled.

    Returns (raw_text, [citation_urls]). Grounding is mutually exclusive
    with response_mime_type='application/json' on the API, so callers
    must extract JSON from the text themselves (strip_code_fence helps).

    `thinking_budget=0` is critical here: on gemini-2.5-flash thinking-mode
    is on by default and silently consumes tokens before the visible text,
    which means longer grounded prompts come back empty. Other helpers in
    this file disable it for the same reason.
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=max_tokens,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    citations: list[str] = []
    try:
        for cand in (response.candidates or []):
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            for chunk in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(chunk, "web", None)
                if web and getattr(web, "uri", None):
                    citations.append(web.uri)
    except Exception:
        # Citations are nice-to-have; never let extraction errors break the call.
        pass
    # Dedupe while preserving order
    seen = set(); deduped = []
    for u in citations:
        if u not in seen:
            seen.add(u); deduped.append(u)
    return (response.text or "", deduped)


def generate_cv_content(
    job_posting: str, company: str, position: str,
    language: str, custom_notes: str, projects: list
) -> dict:
    out_lang = "German" if language == "de" else "English"
    projects_text = projects_to_text(projects, language)
    notes_block = f"\nAPPLICANT NOTES (must be incorporated):\n{custom_notes}\n" if custom_notes.strip() else ""
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

    # Skill-category keys are rendered as labels in the CV, so they follow the
    # output language. Everything else in the instruction layer stays English.
    cat_tech = "Tech & Methoden" if language == "de" else "Tech & methods"
    cat_soft = "Soft Skills"
    cat_lang = "Sprachen" if language == "de" else "Languages"
    lang_example = "Deutsch (Muttersprache), Englisch (C1)" if language == "de" else "German (Native), English (C1)"

    applicant = get_contact()["full_name"]
    prompt = f"""You are a professional CV writer. Produce structured CV content for {applicant}.

OUTPUT LANGUAGE: {out_lang}. Write ALL content values in {out_lang}.

APPLICANT PROFILE:
{profile_text}

PROJECTS & ACHIEVEMENTS:
{projects_text}
{notes_block}
JOB POSTING:
{job_posting}

COMPANY: {company or "infer from the job posting"}
POSITION: {position or "infer from the job posting"}

Return a JSON object with exactly this structure:
{{
  "profile": "2-3 sentence profile statement tailored to this position",
  "experience": [
    {{
      "id": "original ID from profile",
      "title": "job title",
      "company": "company name",
      "location": "city, country",
      "bullets": ["bullet 1 tailored to position", "bullet 2"]
    }}
  ],
  "education": [
    {{
      "id": "original ID from profile",
      "degree": "degree name",
      "institution": "school/university name",
      "location": "city, country",
      "details": ["focus / minor / honors"]
    }}
  ],
  "projects": [
    {{
      "id": "project id",
      "title": "project title",
      "description": "project description"
    }}
  ],
  "skills": {{
    "{cat_tech}": "React, TypeScript, Python, ...",
    "{cat_soft}": "...",
    "{cat_lang}": "{lang_example}"
  }}
}}

RULES (this instruction layer is written in English on purpose — it does NOT
change the OUTPUT LANGUAGE defined above; all content values stay {out_lang}):

IDs & coverage:
- Experience: include EVERY entry below, exactly one object per ID, in this
  same order. Do NOT omit, merge, or combine entries — even if two look
  similar or seem less relevant: {exp_ids}
- Education: include EVERY entry below, exactly one object per ID, in this
  same order. Do NOT omit any: {edu_ids}
- Projects: from this list, select ONLY the 3-4 most relevant: {proj_ids}
- Use only the IDs listed above; never invent or alter an ID.

Translation:
- Translate ALL content into {out_lang}: titles, degrees, locations/countries
  (e.g. Deutschland <-> Germany, Norwegen <-> Norway), skill categories,
  project descriptions, education details (focus/minor/honors).
- Do NOT translate proper nouns (company names, university names). Translate a
  legal/company suffix (GmbH/Inc./Ltd.) only when it reads naturally.

Structure & format:
- Return valid JSON only, exactly matching the structure above.
- Keep all structural keys in English as shown. The keys inside "skills" are
  display labels — use them exactly as provided.

Style limits:
- Bullets: concrete activities and results ONLY. Never append "— which
  proves/shows/underlines my XY skills".
- Do not repeat information that already appears elsewhere.
- Do not invent facts.
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


def _extract_json_object(text: str) -> dict | None:
    """Best-effort JSON extraction from text that may include prose + fences."""
    text = strip_code_fence(text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back: find the first {...} block
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    return None


def extract_company_from_posting(job_posting: str) -> str | None:
    """Best-effort: pull the company name out of a fetched posting text.

    Reuses the same prompt shape as the /extract-fields route so behavior
    stays consistent. Returns None if extraction fails or the model is
    uncertain — caller is expected to handle that gracefully.
    """
    if not job_posting.strip():
        return None
    prompt = f"""Extrahiere den Firmennamen aus dieser Stellenausschreibung.

STELLENAUSSCHREIBUNG:
{job_posting[:4000]}

Gib EIN JSON-Objekt zurück: {{ "company": "Firmenname oder null" }}
"""
    try:
        data = _call_gemini_json(prompt, 128)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    val = data.get("company")
    if not isinstance(val, str):
        return None
    val = val.strip()
    return val or None


def generate_company_info(company: str, position: str, job_posting: str, language: str) -> dict | None:
    """Two-stage company enrichment:

    1. **Grounded research call** — Gemini + Google Search produces a
       prose summary of the company (description, employees, founded, HQ,
       Kununu rating + reviews, etc.) along with citation URLs. The search
       tool is mutually exclusive with strict JSON output, so the model
       responds in prose.
    2. **Non-grounded JSON distillation** — pass that prose plus the
       posting context into a normal `_call_gemini_json` call that emits
       the structured shape we store.

    Returns None only when both stages fail or no fields can be filled.
    Fields the research couldn't substantiate stay null — never invented.
    """
    company = (company or "").strip()
    if not company:
        return None

    # ── Stage 1: grounded research ────────────────────────────────────
    # Always English: English search queries return better-indexed results
    # for company facts (Wikipedia, Crunchbase, LinkedIn, company sites are
    # all primarily English-indexed). The distillation stage below will
    # translate / localize into the user's chosen language.
    research_prompt = f"""Use Google Search to research the company "{company}" briefly.

Reply CONCISELY (no preamble, no repetition) to the following seven points,
in exactly this order, one point per line with the given prefix:

1) DESCRIPTION: 2 short sentences — industry, product, mission.
2) EMPLOYEES: a range like "50-200", "1,000-5,000", "10,000+", or "unknown".
3) FOUNDED: 4-digit year, or "unknown".
4) HEADQUARTERS: city, country, or "unknown".
5) WEBSITE: single URL like https://…, or "unknown".
6) KUNUNU: search explicitly on kununu.com for this employer. If a profile
   exists, answer "<stars>/5 from <reviews> reviews — <URL>". If not,
   answer "no profile found".
7) KUNUNU_SENTIMENT: 1 sentence on what employees praise / criticize, if a
   Kununu page exists; otherwise "n/a".

Context from a current job posting (use it to disambiguate which company
this is, especially for common names):
\"\"\"
{job_posting[:1500]}
\"\"\""""
    try:
        research_text, sources = _call_gemini_with_search(research_prompt, max_tokens=2048)
    except Exception as e:
        print(f"[company_info] grounded research failed: {e}", flush=True)
        return None
    if not (research_text or "").strip():
        print("[company_info] grounded research returned empty text", flush=True)
        return None

    # ── Stage 2: distill prose → structured JSON ──────────────────────
    # The research above is English; the distillation translates description
    # / industry / kununu-summary into the user's language while keeping
    # neutral fields (URLs, years, ranges, headquarters) as-is.
    if language == "de":
        distill_prompt = f"""Aus folgendem englischen Recherche-Text extrahiere strukturierte
Fakten über das Unternehmen "{company}". Übersetze description, industry und
kununu.summary ins Deutsche; übernimm URLs, Jahreszahlen und Spannweiten
unverändert.

RECHERCHE-TEXT (englisch, aus Google-Search-Grounding):
\"\"\"
{research_text[:6000]}
\"\"\"

Gib NUR ein JSON-Objekt mit dieser exakten Struktur zurück:

{{
  "description":    "2-3 Sätze (Deutsch): Branche, Produkt, Mission",
  "industry":       "z. B. 'Fintech', 'SaaS', 'E-Mobilität'",
  "employee_count": "z. B. '200-500', '1.000-5.000', '10.000+' oder null",
  "founded":        "Gründungsjahr als String (z. B. '2017') oder null",
  "hq":             "Stadt, Land (z. B. 'Berlin, Deutschland') oder null",
  "website":        "Hauptwebsite (https://...) oder null",
  "kununu": {{
    "rating":        <Float 1.0-5.0> oder null,
    "reviews_count": <Ganzzahl> oder null,
    "url":           "kununu-URL oder null",
    "summary":       "1 Satz Deutsch: was Mitarbeitende loben/kritisieren, oder null"
  }}
}}

Regeln:
- Setze ein Feld auf null, wenn die Recherche es als "unknown" / "no profile
  found" / "n/a" markiert oder es schlicht nicht nennt.
- "kununu" als gesamtes Objekt null, wenn keine Sterne in der Recherche stehen.
- Keine Zahlen erfinden."""
    else:
        distill_prompt = f"""Extract structured facts about the company "{company}" from
the following research text.

RESEARCH TEXT (from Google Search grounding):
\"\"\"
{research_text[:6000]}
\"\"\"

Return ONLY a JSON object with exactly this structure:

{{
  "description":    "2-3 sentences: industry, product, mission",
  "industry":       "e.g. 'Fintech', 'SaaS', 'E-Mobility'",
  "employee_count": "e.g. '200-500', '1,000-5,000', '10,000+' or null",
  "founded":        "founding year as a string (e.g. '2017') or null",
  "hq":             "city, country or null",
  "website":        "main website (https://...) or null",
  "kununu": {{
    "rating":        <float 1.0-5.0> or null,
    "reviews_count": <integer> or null,
    "url":           "kununu URL or null",
    "summary":       "1 sentence on praise/criticism, or null"
  }}
}}

Rules:
- Set a field to null when the research marks it 'unknown' / 'no profile
  found' / 'n/a' or simply doesn't mention it.
- Set the entire 'kununu' object to null when no Kununu rating is in the
  research. Don't invent numbers."""
    try:
        data = _call_gemini_json(distill_prompt, max_tokens=1024)
    except Exception as e:
        print(f"[company_info] distillation failed: {e}", flush=True)
        return None
    if not isinstance(data, dict):
        print(f"[company_info] distillation returned non-dict: {type(data).__name__}", flush=True)
        return None

    def _clean_str(v):
        if isinstance(v, str):
            v = v.strip()
            if v.lower() in {"null", "none", "n/a", "unbekannt", "unknown", ""}:
                return None
            return v
        return None

    out: dict = {}
    for key in ("description", "industry", "employee_count", "founded", "hq", "website"):
        out[key] = _clean_str(data.get(key))

    kununu_raw = data.get("kununu")
    kununu: dict | None = None
    if isinstance(kununu_raw, dict):
        rating = kununu_raw.get("rating")
        try:
            rating_f = float(rating) if rating is not None else None
        except (TypeError, ValueError):
            rating_f = None
        if rating_f is not None and not (0.0 <= rating_f <= 5.0):
            rating_f = None
        reviews = kununu_raw.get("reviews_count")
        try:
            reviews_i = int(reviews) if reviews is not None else None
        except (TypeError, ValueError):
            reviews_i = None
        kununu_url = _clean_str(kununu_raw.get("url"))
        kununu_summary = _clean_str(kununu_raw.get("summary"))
        if rating_f is not None or reviews_i or kununu_url or kununu_summary:
            kununu = {
                "rating":        rating_f,
                "reviews_count": reviews_i,
                "url":           kununu_url,
                "summary":       kununu_summary,
            }
    out["kununu"]     = kununu
    out["sources"]    = sources[:8]
    out["fetched_at"] = _now_iso()

    # If literally everything is null, treat as "no info".
    has_anything = any(out.get(k) for k in
                       ("description", "industry", "employee_count",
                        "founded", "hq", "website", "kununu"))
    return out if has_anything else None


def generate_fit_score(
    profile_text: str,
    job_posting: str,
    job_summary: dict | None,
    language: str,
) -> dict | None:
    """Score how well the user's profile matches the posting.

    Returns {score: 0-100, summary, strengths[], gaps[]} or None on failure.
    """
    lang = "auf Deutsch" if language == "de" else "in English"
    js = job_summary or {}
    searching = js.get("searching_for") or []
    technologies = js.get("technologies") or []
    extras = ""
    if searching:
        extras += "\nWAS DIE FIRMA SUCHT (bereits extrahiert):\n- " + "\n- ".join(searching[:10])
    if technologies:
        extras += "\nGENANNTE TECHNOLOGIEN:\n- " + "\n- ".join(technologies[:20])

    prompt = f"""Bewerte, wie gut der Bewerber zur Stelle passt. Antworte {lang}.

PROFIL DES BEWERBERS:
{profile_text[:6000]}

STELLENAUSSCHREIBUNG:
{job_posting[:6000]}
{extras}

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück:
{{
  "score":     <Ganzzahl 0-100>,
  "summary":   "1 Satz: warum diese Bewertung",
  "strengths": ["3-5 konkrete Übereinstimmungen (Skill X aus Profil ↔ Anforderung Y aus Posting)"],
  "gaps":      ["2-4 konkrete Lücken: was die Stelle verlangt, das im Profil fehlt/schwach ist"]
}}

Regeln:
- Score-Kalibrierung: 90+ = hervorragender Fit, 70-89 = solide, 50-69 = möglich aber mit Abstrichen,
  unter 50 = klare Schiefstand. Verzerre NICHT optimistisch.
- "strengths" und "gaps" müssen KONKRET sein (Skill/Erfahrung/Domain), keine Floskeln.
- Wenn etwas im Profil und Posting beidseits genannt wird, gehört es zu strengths, nicht zu gaps.
"""
    try:
        data = _call_gemini_json(prompt, 768)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    raw_score = data.get("score")
    try:
        score = int(round(float(raw_score)))
    except (TypeError, ValueError):
        return None
    score = max(0, min(100, score))

    def _list_of_strings(val) -> list[str]:
        if not isinstance(val, list):
            return []
        return [s.strip() for s in val if isinstance(s, str) and s.strip()]

    return {
        "score":     score,
        "summary":   (data.get("summary") or "").strip(),
        "strengths": _list_of_strings(data.get("strengths"))[:6],
        "gaps":      _list_of_strings(data.get("gaps"))[:6],
    }


def generate_anschreiben_content(
    job_posting: str, company: str, position: str,
    contact: str, city: str, language: str,
    custom_notes: str, projects: list,
    company_address: str = ""
) -> dict:
    lang = "auf Deutsch" if language == "de" else "in English"
    today = date.today().strftime("%d. %B %Y") if language == "de" else date.today().strftime("%B %d, %Y")
    projects_text = projects_to_text(projects, language)
    notes_block = f"\nEIGENE HINWEISE (unbedingt einarbeiten):\n{custom_notes}\n" if custom_notes.strip() else ""
    profile_text = profile_to_text(load_profile())

    settings_data  = load_settings()
    style_analysis = (settings_data.get("style_analysis") or "").strip()
    style_example  = (settings_data.get("style_example") or "").strip()
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
        company  = item.get("company") or entry.get("company", "")
        location = item.get("location") or entry.get("location", "")
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
        institution = item.get("institution") or entry.get("institution", "")
        location    = item.get("location") or entry.get("location", "")
        start       = fmt_date(entry.get("start"), language=language)
        end         = fmt_date(entry.get("end"), entry.get("current", False), language=language)
        details     = list(item.get("details") or entry.get("details", []))
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
        # Fall back to the localized entry, not to the raw source fields — those
        # are in whichever language the project happened to be written in.
        loc   = project_locale(p, language)
        title = (item.get("title") if isinstance(item, dict) else None) or loc["title"] or p["title"]
        desc  = (item.get("description") if isinstance(item, dict) else None) or loc["summary"] or p["description"]
        grade = f" ({grade_label}: {p['grade']})" if p.get("grade") else ""
        link_html = ""
        if p.get("link"):
            # Strip protocol for display ("github.com/..." reads cleaner on a CV
            # than the full https URL), but keep the full URL in href so the
            # link still works when the rendered HTML is exported / printed.
            display = re.sub(r"^https?://", "", p["link"]).rstrip("/")
            link_html = f' (<a href="{p["link"]}" target="_blank" rel="noopener noreferrer">{display}</a>)'
        items.append(f"<li><strong>{title}{grade}</strong>: {desc}{link_html}</li>")
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


PROJECT_LIST_I18N = {
    "de": {
        "doc_title":  "Projektliste",
        "intro":      "Ausgewählte Projekte im Detail — Ausgangslage, eigener Beitrag, eingesetzte Technologien und Ergebnis.",
        "client":     "Kunde/Arbeitgeber",
        "period":     "Zeitraum",
        "role":       "Rolle",
        "team":       "Team",
        "situation":  "Ausgangslage",
        "contrib":    "Mein Beitrag",
        "tech":       "Technologien",
        "result":     "Ergebnis",
        "summary":    "Kurzbeschreibung",
        "link":       "Link",
        "grade":      "Note",
    },
    "en": {
        "doc_title":  "Project List",
        "intro":      "Selected projects in detail — starting point, my contribution, technologies used and outcome.",
        "client":     "Client/Employer",
        "period":     "Period",
        "role":       "Role",
        "team":       "Team",
        "situation":  "Starting point",
        "contrib":    "My contribution",
        "tech":       "Technologies",
        "result":     "Outcome",
        "summary":    "Summary",
        "link":       "Link",
        "grade":      "Grade",
    },
}


def _pl_link_html(url: str) -> str:
    """Link cell: full URL in href, protocol stripped for display (as on the CV)."""
    display = re.sub(r"^https?://", "", url).rstrip("/")
    return f'<a href="{html_escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{html_escape(display)}</a>'


def _render_project_list_entry(project: dict, index: int, t: dict, language: str) -> str:
    """One project as a clearly delimited block.

    Falls back to the short CV data (description as summary, tags as
    technologies) for projects whose long-form fields aren't filled in yet, so
    the list is usable before every entry has been elaborated.
    """
    detail = normalize_project_detail(project.get("detail"))
    loc    = detail.get(language) or detail["de"]

    title = loc["title"] or project.get("title", "")
    head_right = f'<span class="pl-badge">{t["grade"]} {html_escape(str(project["grade"]))}</span>' if project.get("grade") else ""

    meta_bits = []
    for label, value in (
        (t["client"], detail["client"]),
        (t["period"], detail["period"]),
        (t["role"],   loc["role"]),
        (t["team"],   loc["team_size"] or detail["team_size"]),
    ):
        if value:
            meta_bits.append(f'<span class="pl-meta-item"><strong>{label}:</strong> {html_escape(value)}</span>')
    meta_html = f'<div class="pl-meta">{"".join(meta_bits)}</div>' if meta_bits else ""

    rows = []
    if loc["situation"]:
        rows.append((t["situation"], html_escape(loc["situation"])))
    if loc["contributions"]:
        bullets = "".join(f"<li>{html_escape(c)}</li>" for c in loc["contributions"])
        rows.append((t["contrib"], f"<ul>{bullets}</ul>"))
    if not loc["situation"] and not loc["contributions"]:
        summary = loc["summary"] or project.get("description", "")
        if summary:
            rows.append((t["summary"], html_escape(summary)))

    techs = detail["technologies"] or project.get("tags", [])
    if techs:
        tags_html = "".join(f"<span>{html_escape(tech)}</span>" for tech in techs)
        rows.append((t["tech"], f'<span class="pl-tech">{tags_html}</span>'))
    if loc["result"]:
        rows.append((t["result"], f'<span class="pl-result">{html_escape(loc["result"])}</span>'))
    if project.get("link"):
        rows.append((t["link"], _pl_link_html(project["link"])))

    fields_html = "".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in rows)

    return f"""<div class="pl-project">
  <div class="pl-head">
    <div class="pl-title"><span class="pl-num">{index:02d}</span>{html_escape(title)}</div>
    {head_right}
  </div>
  {meta_html}
  <dl class="pl-fields">{fields_html}</dl>
</div>"""


def select_project_list_entries(all_projects: list, ids: list | None) -> list:
    """Resolve which projects go into the list, preserving the requested order.

    With explicit ids the caller decides (order included); without, everything
    flagged for the list is used, falling back to the CV-visible projects so a
    fresh install still prints something.
    """
    by_id = {p["id"]: p for p in all_projects if p.get("id")}
    if ids:
        return [by_id[pid] for pid in ids if pid in by_id]
    flagged = [p for p in all_projects if normalize_project_detail(p.get("detail"))["in_list"]]
    return flagged or [p for p in all_projects if p.get("visible", True)]


def render_project_list_html(all_projects: list, language: str, layout: str, ids: list | None = None) -> str:
    t = PROJECT_LIST_I18N.get(language, PROJECT_LIST_I18N["de"])
    c = get_contact()
    # Only "modern" and "classic" have a base style that works standalone —
    # "sidebar" is built around a two-column .page shell the list doesn't use.
    layout   = layout if layout in ("modern", "classic") else "modern"
    base     = LAYOUTS[layout]["style"]
    entries  = select_project_list_entries(all_projects, ids)
    body     = "\n".join(
        _render_project_list_entry(p, i, t, language) for i, p in enumerate(entries, start=1)
    )

    header = f"""<div class="header">
  <h1>{c["full_name"]}</h1>
  <div class="pl-doc-title">{t["doc_title"]}</div>
  <p class="pl-intro">{t["intro"]}</p>
  <div class="contact">
    <div class="contact-item"><span>📍</span><span>{c["address_dot"]}</span></div>
    <div class="contact-item"><span>📞</span><span>{c["phone"]}</span></div>
    <div class="contact-item"><span>✉️</span><a href="mailto:{c["email"]}">{c["email"]}</a></div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{c["full_name"]} - {t["doc_title"]}</title>
{base}
{PROJECT_LIST_STYLE}
</head>
<body class="pl-{layout}">
{header}
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
    # The entire frontend (HTML + CSS + JS) lives inline in this template.
    # Without no-store, browsers reuse the cached copy across template edits
    # which manifests as "the new feature I just shipped is invisible in the
    # UI". For a single-user local dev app the re-fetch cost is trivial.
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp


def fetch_job_posting(url: str, timeout: int = 10) -> str:
    """Fetch + clean a job-posting HTML page into plain text.

    Raises on network/HTTP errors; trims to 12k chars to stay within Gemini
    context budgets. Shared by /fetch-job, queue-add scoring, etc.
    """
    resp = http_requests.get(url, timeout=timeout, headers={
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
    return cleaned


@app.route("/fetch-job", methods=["POST"])
def fetch_job():
    url = request.json.get("url", "").strip()
    if not url:
        return jsonify({"error": "Keine URL angegeben."}), 400
    try:
        return jsonify({"text": fetch_job_posting(url)})
    except Exception as e:
        return jsonify({"error": f"Konnte URL nicht laden: {str(e)}"}), 500


@app.route("/layouts", methods=["GET"])
def get_layouts():
    return jsonify([{"id": k, "name": v["name"], "style": v["style"]} for k, v in LAYOUTS.items()])


@app.route("/mode", methods=["GET"])
def get_mode():
    """Tiny endpoint so the frontend can show a "DEMO" badge when the app
    was started with DEMO_MODE=1. The frontend polls this once on load."""
    return jsonify({"demo": demo_mode.is_demo_mode()})


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

    projects = ensure_project_language(load_projects(), language)
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

    # Fit score and company info are best-effort: if either Gemini call
    # fails we still want the CV/Anschreiben to ship.
    try:
        result["fit_score"] = generate_fit_score(
            profile_to_text(load_profile()),
            job_posting,
            result.get("job_summary"),
            language,
        )
    except Exception:
        result["fit_score"] = None
    try:
        result["company_info"] = generate_company_info(
            company, position, job_posting, language,
        )
    except Exception:
        result["company_info"] = None

    job_url = (data.get("job_url") or "").strip()
    try:
        tracked_seconds = int(data.get("tracked_seconds") or 0)
    except (TypeError, ValueError):
        tracked_seconds = 0
    logged = log_application(
        company, position, job_posting,
        job_url=job_url,
        cv_content          = result.get("cv_content"),
        anschreiben_content = result.get("anschreiben_content"),
        company_info        = result.get("company_info"),
        fit_score           = result.get("fit_score"),
        layout_used         = resolved_layout,
        language            = language,
        tracked_seconds     = tracked_seconds,
    )
    if logged:
        result["application"] = logged

    return jsonify(result)


@app.route("/render", methods=["POST"])
def render_doc():
    data     = request.json
    doc_type = data.get("doc_type", "cv")
    language = data.get("language", "de")
    projects = ensure_project_language(load_projects(), language)

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

    folder = {
        "anschreiben":  ANSCHREIBEN_DIR,
        "projektliste": PROJEKTLISTE_DIR,
    }.get(doc_type, CV_DIR)
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
    # Hand out a fully-shaped `detail` even for entries stored before the
    # project list existed, so the editor never has to null-check its fields.
    projects = load_projects()
    for p in projects:
        p["detail"] = normalize_project_detail(p.get("detail"))
    return jsonify(projects)


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
        "link":        (data.get("link") or "").strip() or None,
        "visible":     data.get("visible", True),
        "detail":      normalize_project_detail(data.get("detail")),
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
            if "link" in data:
                p["link"]    = (data.get("link") or "").strip() or None
            p["visible"]     = data.get("visible", p.get("visible", True))
            if "detail" in data:
                p["detail"]  = normalize_project_detail(data["detail"])
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


@app.route("/project-list/render", methods=["POST"])
def render_project_list():
    data     = request.json or {}
    language = data.get("language", "de")
    layout   = data.get("layout", "modern")
    ids      = data.get("ids") if isinstance(data.get("ids"), list) else None
    try:
        projects = ensure_project_language(load_projects(), language)
        html = render_project_list_html(projects, language, layout, ids)
    except Exception as e:
        return jsonify({"error": f"Render-Fehler: {str(e)}"}), 500
    return jsonify({"html": html})


@app.route("/project-list/draft", methods=["POST"])
def draft_project_detail():
    """Draft the long-form fields for one project from its short CV entry.

    Deliberately conservative: the model may rephrase what's there, but client,
    period and team size are left empty unless the source text names them —
    a project list with invented facts is worse than one with gaps.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500

    data       = request.json or {}
    project_id = data.get("id")
    project    = next((p for p in load_projects() if p["id"] == project_id), None) if project_id else None
    title      = (data.get("title")       or (project or {}).get("title", "")).strip()
    desc       = (data.get("description") or (project or {}).get("description", "")).strip()
    if not title or not desc:
        return jsonify({"error": "Titel und Beschreibung erforderlich."}), 400

    tags     = data.get("tags") or (project or {}).get("tags", [])
    grade    = data.get("grade") or (project or {}).get("grade")
    existing = normalize_project_detail(data.get("detail") or (project or {}).get("detail"))

    prompt = f"""Du bereitest eine Projektliste (Referenzliste) für Bewerbungen bei Beratungen auf.
Wandle den folgenden Kurzeintrag in strukturierte Projektangaben um — auf Deutsch UND auf Englisch.

PROJEKT-TITEL: {title}
BESCHREIBUNG: {desc}
TAGS: {", ".join(tags) if tags else "-"}
NOTE: {grade or "-"}
BEREITS ERFASST (falls gefüllt, übernehmen statt neu erfinden):
{json.dumps(existing, ensure_ascii=False)}

Antworte NUR mit JSON in exakt dieser Struktur:
{{
  "client": "Auftraggeber/Arbeitgeber/Hochschule, sonst \\"\\"",
  "period": "z.B. 03/2024 – 07/2024, sonst \\"\\"",
  "team_size": "z.B. 4 Personen, sonst \\"\\"",
  "technologies": ["konkrete Technologien, Methoden, Tools"],
  "de": {{
    "title": "sachlicher Projekttitel (was es war, nicht der interne Name)",
    "summary": "die Kurzbeschreibung auf Deutsch (wird im Lebenslauf genutzt)",
    "role": "z.B. Fullstack-Entwickler, Requirements Engineer",
    "situation": "EIN Satz zum Ausgangsproblem",
    "contributions": ["2-3 aktiv formulierte Stichpunkte, beginnend mit einem Verb"],
    "result": "EIN Satz: was sich messbar oder erkennbar geändert hat",
    "team_size": "Teamgröße auf Deutsch, z.B. \\"4 Personen\\", sonst \\"\\""
  }},
  "en": {{ "title": "...", "summary": "...", "role": "...", "situation": "...", "contributions": ["..."], "result": "...", "team_size": "e.g. \\"4 people\\"" }}
}}

Regeln:
- KEINE Fakten erfinden. Wenn Kunde, Zeitraum oder Teamgröße nicht aus dem Text hervorgehen: leerer String.
- "result" nur aus Belegbarem ableiten (z.B. Note, Hackathon-Sieg, ausgelieferter Prototyp) — keine erfundenen Prozentzahlen.
- Stichpunkte kurz halten (max. ~15 Wörter), aktiv, ohne "Ich".
- Die englische Fassung ist eine Übersetzung derselben Aussagen, keine neue Version.
- JEDES Textfeld muss in der Sprache seines Blocks stehen: der "de"-Block
  vollständig auf Deutsch, der "en"-Block vollständig auf Englisch — auch dann,
  wenn Titel oder Beschreibung oben in der jeweils anderen Sprache verfasst sind.
"""
    try:
        result = _call_gemini_json(prompt, 2048)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500

    detail = normalize_project_detail(result)
    detail["in_list"] = existing["in_list"]
    return jsonify({"detail": detail})


@app.route("/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())


@app.route("/settings", methods=["PUT"])
def update_settings():
    data     = request.json or {}
    settings = load_settings()
    for field in ("style_example", "style_analysis"):
        if isinstance(data.get(field), str):
            settings[field] = data[field].strip()
    save_settings(settings)
    return jsonify(settings)


@app.route("/analyze-style", methods=["POST"])
def analyze_style():
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500
    data    = request.json or {}
    example = (data.get("example") or "").strip()
    if not example:
        return jsonify({"error": "Beispiel-Text ist leer."}), 400

    # The analysis is the instruction layer: always English, language-agnostic,
    # so it can be applied to both German and English generation. The example
    # itself may be in either language.
    prompt = f"""Analyze the writing style of the example cover letter below and describe it in English, precisely enough that another AI can imitate this style later without copying the content. The example may be in German or English — describe the style itself, which carries over regardless of the language a letter is later written in.

EXAMPLE TEXT:
\"\"\"
{example[:6000]}
\"\"\"

Return 6–10 bullet points covering these aspects (where recognizable):
- Tone (formal ↔ casual, direct ↔ reserved, confident ↔ modest)
- Sentence structure (length, active/passive, parataxis/hypotaxis)
- Word choice (jargon, anglicisms, industry terms, deliberately avoided filler phrases)
- Structural patterns (opening, line of argument, closing)
- Recurring rhetorical devices or quirks

Format: plain markdown bullet list (\"- …\"), no preamble or closing remark, no salutation to me.
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
    company_info        = data.get("company_info")
    fit_score           = data.get("fit_score")
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
        "company_info":        company_info        if isinstance(company_info,        dict) else None,
        "fit_score":           fit_score           if isinstance(fit_score,           dict) else None,
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


# ─── Queue ───────────────────────────────────────────────────────────────────

def _queue_close_page(message: str, sub: str = "", auto_close: bool = True) -> Response:
    """Tiny self-closing HTML page returned by the bookmarklet flow.

    The bookmarklet does window.open(...) which lands the user on this page;
    after a short delay it tries to close itself. Looks like a toast.
    """
    close_js = "<script>setTimeout(()=>window.close(), 900)</script>" if auto_close else ""
    html = f"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><title>Queue</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    margin: 0; padding: 28px 24px;
    background: #f7f8fa; color: #2c3e50; text-align: center;
  }}
  h2 {{ margin: 0 0 0.5rem; font-size: 1.05rem; font-weight: 700; }}
  p  {{ margin: 0.15rem 0; color: #6a7a86; font-size: 0.82rem; }}
  .check {{ font-size: 2.2rem; line-height: 1; margin-bottom: 0.45rem; }}
  .err   {{ color: #c0392b; }}
</style></head>
<body>
  <div class="check">{'✓' if not message.lower().startswith('fehler') else '⚠️'}</div>
  <h2>{message}</h2>
  {f'<p>{sub}</p>' if sub else ''}
  <p style="margin-top:0.9rem;font-size:0.72rem;color:#9aa5af">
    Schließt sich automatisch …
  </p>
  {close_js}
</body></html>"""
    return Response(html, mimetype="text/html")


def _enrich_queue_item_async(qid: str, url: str):
    """Background: fetch the posting, compute fit_score + company_info,
    update the queue row.

    Fire-and-forget so the API response (and the bookmarklet's auto-closing
    popup) isn't blocked by 5-15 s of fetch + Gemini latency. Fit score
    and company info are computed independently — one failing won't void
    the other.
    """
    import threading

    def _run():
        try:
            try:
                posting = fetch_job_posting(url)
            except Exception as e:
                db.update_queue_item(qid, error=f"Fetch fehlgeschlagen: {e}"[:300])
                return
            if not os.environ.get("GEMINI_API_KEY"):
                db.update_queue_item(qid, error="GEMINI_API_KEY nicht gesetzt")
                return

            # Fit score
            fit_err = ""
            try:
                fit = generate_fit_score(
                    profile_to_text(load_profile()),
                    posting,
                    None,    # no job_summary at queue-time; the prompt handles None
                    "de",    # queue-time has no language hint — default to German
                )
            except Exception as e:
                fit, fit_err = None, f"Scoring fehlgeschlagen: {e}"
            if fit:
                db.update_queue_item(qid, fit_score=fit)
            elif fit_err:
                db.update_queue_item(qid, error=fit_err[:300])

            # Company info — independent enrichment.
            company_name = extract_company_from_posting(posting)
            if company_name:
                try:
                    info = generate_company_info(company_name, "", posting, "de")
                except Exception:
                    info = None
                if info:
                    db.update_queue_item(qid, company_info=info)
        finally:
            # Always mark the enrichment attempt as finished, even on failure —
            # this is the signal the frontend uses to stop polling. Without
            # this, items whose company couldn't be extracted (and thus never
            # got a company_info) would have the queue view polling forever.
            db.update_queue_item(qid, enriched_at=_now_iso())

    threading.Thread(target=_run, daemon=True).start()


@app.route("/queue", methods=["GET"])
def list_queue_route():
    status = (request.args.get("status") or "").strip() or None
    return jsonify(db.list_queue(status=status))


@app.route("/queue", methods=["POST"])
def add_queue_route():
    """JSON endpoint used by the in-app paste-field (Queue-Tab).

    Body: { url, title?, note? }. Returns the created/existing queue row.
    """
    data  = request.json or {}
    raw   = (data.get("url") or "").strip()
    if not raw:
        return jsonify({"error": "Keine URL angegeben."}), 400
    url = _normalize_queue_url(raw)
    if not url:
        return jsonify({"error": "Ungültige URL."}), 400

    title = (data.get("title") or "").strip()[:JOB_QUEUE_TITLE_MAX]
    note  = (data.get("note")  or "").strip()[:JOB_QUEUE_NOTE_MAX]

    existing = db.find_queue_item_by_url(url)
    if existing and existing["status"] == "pending":
        return jsonify({"item": existing, "duplicate": True}), 200

    qid = str(uuid.uuid4())[:8]
    item = db.add_queue_item(qid, url, title, note, _now_iso())
    _enrich_queue_item_async(qid, url)
    return jsonify({"item": item, "duplicate": False}), 201


@app.route("/queue/<qid>", methods=["PATCH"])
def update_queue_route(qid):
    """Partial update: status / note. Used by the UI for done / skipped / note edits."""
    if not db.get_queue_item(qid):
        return jsonify({"error": "Queue-Eintrag nicht gefunden."}), 404
    data = request.json or {}
    kwargs = {}
    if "status" in data:
        st = (data.get("status") or "").strip()
        if st not in db.QUEUE_STATUSES:
            return jsonify({"error": "Ungültiger Status."}), 400
        kwargs["status"] = st
        if st in ("done", "skipped", "failed"):
            kwargs["processed_at"] = _now_iso()
    if "note" in data:
        kwargs["note"] = (data.get("note") or "").strip()[:JOB_QUEUE_NOTE_MAX]
    if "application_id" in data:
        kwargs["application_id"] = (data.get("application_id") or "").strip() or None
    item = db.update_queue_item(qid, **kwargs)
    return jsonify(item)


@app.route("/queue/<qid>/enrich", methods=["POST"])
def reenrich_queue_route(qid):
    """Re-run the background enrichment for a single queue row.

    Useful when (a) the initial enrichment failed quietly, (b) we improved
    the prompt and want a fresh result, or (c) the user pasted a URL whose
    server was temporarily down.
    """
    item = db.get_queue_item(qid)
    if not item:
        return jsonify({"error": "Queue-Eintrag nicht gefunden."}), 404
    # Clear sentinels so the polling logic picks the row up again.
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE job_queue SET enriched_at = NULL, error = NULL WHERE id = ?",
            (qid,),
        )
    _enrich_queue_item_async(qid, item["url"])
    return jsonify({"ok": True})


@app.route("/queue/<qid>", methods=["DELETE"])
def delete_queue_route(qid):
    if not db.delete_queue_item(qid):
        return jsonify({"error": "Queue-Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@app.route("/queue/add", methods=["GET"])
def queue_add_via_bookmarklet():
    """GET endpoint hit by the bookmarklet's `window.open(...)`.

    Returns a tiny HTML page that auto-closes — no CORS theater because it's
    a regular navigation, not a cross-origin fetch.
    """
    raw_url   = (request.args.get("url")   or "").strip()
    raw_title = (request.args.get("title") or "").strip()
    if not raw_url:
        return _queue_close_page("Fehler: keine URL übergeben.", auto_close=False), 400

    url = _normalize_queue_url(raw_url)
    title = raw_title[:JOB_QUEUE_TITLE_MAX]

    existing = db.find_queue_item_by_url(url)
    if existing and existing["status"] == "pending":
        return _queue_close_page(
            "Schon in der Queue",
            sub=existing.get("title") or url,
        )

    qid = str(uuid.uuid4())[:8]
    db.add_queue_item(qid, url, title, "", _now_iso())
    _enrich_queue_item_async(qid, url)
    return _queue_close_page(
        "Zur Queue hinzugefügt",
        sub=title or url,
    )


@app.route("/queue/install", methods=["GET"])
def queue_install_page():
    """Drag-and-drop install page for the bookmarklet.

    Visit http://localhost:5050/queue/install in the browser, drag the button
    into the bookmarks bar, done.
    """
    base = request.host_url.rstrip("/")  # e.g. http://localhost:5050
    # IMPORTANT: keep this on one line — bookmarks don't tolerate newlines.
    bookmarklet = (
        "javascript:(()=>{const u=location.href,t=document.title;"
        f"window.open('{base}/queue/add?url='+encodeURIComponent(u)+"
        "'&title='+encodeURIComponent(t),"
        "'_blank','width=420,height=240')})();"
    )
    html = f"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><title>Queue-Bookmarklet installieren</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    max-width: 640px; margin: 0 auto; padding: 3rem 1.5rem;
    color: #2c3e50; line-height: 1.55;
  }}
  h1 {{ font-size: 1.5rem; margin: 0 0 0.5rem; }}
  p  {{ color: #4a5568; }}
  .drag {{
    display: inline-block; margin: 1.5rem 0;
    background: #4B5D67; color: #fff; padding: 0.65rem 1.2rem;
    border-radius: 8px; font-weight: 700; text-decoration: none;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
    cursor: grab;
  }}
  .drag:active {{ cursor: grabbing; }}
  ol {{ padding-left: 1.4rem; }}
  ol li {{ margin: 0.5rem 0; }}
  code {{
    background: #f1f3f5; padding: 0.1em 0.4em; border-radius: 4px;
    font-size: 0.88em;
  }}
  .hint {{
    background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px;
    padding: 0.75rem 1rem; font-size: 0.88rem; color: #5d4e1f; margin-top: 1.5rem;
  }}
  details {{ margin-top: 1.5rem; }}
  details pre {{
    background: #2c3e50; color: #f5f6f7; padding: 0.9rem 1rem; border-radius: 6px;
    font-size: 0.78rem; overflow-x: auto; white-space: pre-wrap; word-break: break-all;
  }}
</style></head>
<body>
  <h1>→ Queue Bookmarklet</h1>
  <p>
    Zieh den Button unten in deine <strong>Lesezeichenleiste</strong>
    (sichtbar machen mit <code>Cmd+Shift+B</code>).
    Wenn du auf einer Stellenausschreibung bist, klick das Lesezeichen an —
    die URL landet in deiner Queue.
  </p>

  <a class="drag" href="{bookmarklet}" onclick="event.preventDefault();
     alert('Bitte den Button per Drag-and-Drop in deine Lesezeichenleiste ziehen — direkt anklicken hat keinen Effekt.')">
    → Queue
  </a>

  <ol>
    <li>Lesezeichenleiste einblenden (<code>Cmd+Shift+B</code>).</li>
    <li>Den blauen <strong>→ Queue</strong>-Button oben in die Leiste ziehen.</li>
    <li>Auf einer Job-Seite (StepStone, LinkedIn, …) das Lesezeichen anklicken.</li>
    <li>Im Queue-Tab der App nachschauen — Eintrag ist da.</li>
  </ol>

  <div class="hint">
    <strong>Wichtig:</strong> Das funktioniert nur, solange der Server läuft
    (<code>python3 app.py</code>). Wenn du auf einer <code>https://</code>-Seite bist
    und Mixed-Content-Warnungen siehst, erlaube sie für <code>localhost</code>.
  </div>

  <details>
    <summary>Code des Bookmarklets (falls Drag-and-Drop nicht klappt)</summary>
    <pre>{bookmarklet}</pre>
    <p style="font-size:0.82rem;color:#666">
      Manuell: neues Lesezeichen anlegen, Adresse durch obigen Code ersetzen, Name = <em>→ Queue</em>.
    </p>
  </details>
</body></html>"""
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
