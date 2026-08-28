"""Application tracker routes.
"""
import uuid

from flask import Blueprint, jsonify, request

from core import config
from core import db
from core.tracker import apply_stage_transition, load_applications
from core.util import _normalize_calendar_date, _now_iso, _today_iso

bp = Blueprint("applications", __name__)


@bp.route("/applications", methods=["GET"])
def list_applications():
    return jsonify(load_applications())


@bp.route("/applications/<app_id>", methods=["GET"])
def fetch_application(app_id):
    a = db.get_application(app_id)
    if not a:
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404
    return jsonify(a)


@bp.route("/applications", methods=["POST"])
def create_application():
    data     = request.get_json(silent=True) or {}
    company  = (data.get("company") or "").strip()
    position = (data.get("position") or "").strip()
    if not company and not position:
        return jsonify({"error": "Unternehmen oder Position erforderlich."}), 400
    stage = data.get("stage") or "documents_created"
    if stage not in config.APPLICATION_STAGES:
        return jsonify({"error": "Ungültige Stage."}), 400

    now = _now_iso()
    applied_at = (data.get("applied_at") or "").strip() or None
    if not applied_at:
        sent_idx = config.APPLICATION_STAGES.index("application_sent")
        if config.APPLICATION_STAGES.index(stage) >= sent_idx:
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
        "job_posting":         (data.get("job_posting") or "")[:config.JOB_POSTING_MAX],
        "job_url":             (data.get("job_url") or "").strip()[:config.JOB_URL_MAX],
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


@bp.route("/applications/<app_id>", methods=["PUT"])
def update_application(app_id):
    data = request.get_json(silent=True) or {}
    a = db.get_application(app_id)
    if not a:
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404

    new_event = None
    if "company" in data:
        a["company"] = (data.get("company") or "").strip()
    if "position" in data:
        a["position"] = (data.get("position") or "").strip()
    if "stage" in data:
        if data["stage"] not in config.APPLICATION_STAGES:
            return jsonify({"error": "Ungültige Stage."}), 400
        new_event = apply_stage_transition(a, data["stage"])
    if "feedback" in data:
        a["feedback"] = data.get("feedback") or ""
    if "applied_at" in data:
        v = (data.get("applied_at") or "").strip()
        a["applied_at"] = v or None
    if "job_posting" in data:
        a["job_posting"] = (data.get("job_posting") or "")[:config.JOB_POSTING_MAX]
    if "job_url" in data:
        a["job_url"] = (data.get("job_url") or "").strip()[:config.JOB_URL_MAX]
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


@bp.route("/applications/<app_id>", methods=["DELETE"])
def delete_application_route(app_id):
    if not db.delete_application(app_id):
        return jsonify({"error": "Bewerbung nicht gefunden."}), 404
    return jsonify({"ok": True})
