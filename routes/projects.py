"""Projects CRUD and the long-form Projektliste.
"""
import json
import os
import uuid

from flask import Blueprint, jsonify, request

import prompts
from ai.gemini import _call_gemini_json
from render.documents import render_project_list_html
from core.store import (
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

    prompt = prompts.render(
        "project_detail",
        title=title,
        description=desc,
        tags=", ".join(tags) if tags else "-",
        grade=grade or "-",
        existing=json.dumps(existing, ensure_ascii=False),
    )
    try:
        result = _call_gemini_json(prompt, 2048)
    except Exception as e:
        return jsonify({"error": f"Gemini-Fehler: {str(e)}"}), 500

    detail = normalize_project_detail(result)
    detail["in_list"] = existing["in_list"]
    return jsonify({"detail": detail})
