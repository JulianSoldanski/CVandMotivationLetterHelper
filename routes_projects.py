"""Projects CRUD and the long-form Projektliste.
"""
import json
import os
import uuid

from flask import Blueprint, jsonify, request

from gemini import _call_gemini_json
from render import render_project_list_html
from store import (
    load_projects, normalize_project_detail, save_projects,
)

bp = Blueprint("projects", __name__)


@bp.route("/projects", methods=["GET"])
def get_projects():
    # Hand out a fully-shaped `detail` even for entries stored before the
    # project list existed, so the editor never has to null-check its fields.
    projects = load_projects()
    for p in projects:
        p["detail"] = normalize_project_detail(p.get("detail"))
    return jsonify(projects)


@bp.route("/projects", methods=["POST"])
def add_project():
    data = request.get_json(silent=True) or {}
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


@bp.route("/projects/<project_id>", methods=["PUT"])
def update_project(project_id):
    data = request.get_json(silent=True) or {}
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


@bp.route("/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    projects = load_projects()
    new_list = [p for p in projects if p["id"] != project_id]
    if len(new_list) == len(projects):
        return jsonify({"error": "Projekt nicht gefunden."}), 404
    save_projects(new_list)
    return jsonify({"ok": True})


@bp.route("/project-list/render", methods=["POST"])
def render_project_list():
    data     = request.get_json(silent=True) or {}
    language = data.get("language", "de")
    layout   = data.get("layout", "modern")
    ids      = data.get("ids") if isinstance(data.get("ids"), list) else None
    try:
        html = render_project_list_html(load_projects(), language, layout, ids)
    except Exception as e:
        return jsonify({"error": f"Render-Fehler: {str(e)}"}), 500
    return jsonify({"html": html})


@bp.route("/project-list/draft", methods=["POST"])
def draft_project_detail():
    """Draft the long-form fields for one project from its short CV entry.

    Deliberately conservative: the model may rephrase what's there, but client,
    period and team size are left empty unless the source text names them —
    a project list with invented facts is worse than one with gaps.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY nicht gesetzt."}), 500

    data       = request.get_json(silent=True) or {}
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
