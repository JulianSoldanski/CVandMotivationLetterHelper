"""CRUD for profile entries (experience / education) and skill lists.
"""
import uuid

from flask import Blueprint, jsonify, request

from store import load_profile, save_profile

bp = Blueprint("profile", __name__)


@bp.route("/profile", methods=["GET"])
def get_profile():
    return jsonify(load_profile())


@bp.route("/profile/<section>", methods=["POST"])
def add_profile_entry(section):
    if section not in ("experience", "education"):
        return jsonify({"error": "Ungültiger Bereich."}), 400
    data    = request.get_json(silent=True) or {}
    profile = load_profile()
    entry   = {**data, "id": data.get("id") or str(uuid.uuid4())[:8]}
    profile[section].append(entry)
    save_profile(profile)
    return jsonify(entry), 201


@bp.route("/profile/<section>/<entry_id>", methods=["PUT"])
def update_profile_entry(section, entry_id):
    if section not in ("experience", "education"):
        return jsonify({"error": "Ungültiger Bereich."}), 400
    data    = request.get_json(silent=True) or {}
    profile = load_profile()
    for e in profile[section]:
        if e["id"] == entry_id:
            e.update({k: v for k, v in data.items() if k != "id"})
            save_profile(profile)
            return jsonify(e)
    return jsonify({"error": "Eintrag nicht gefunden."}), 404


@bp.route("/profile/<section>/<entry_id>", methods=["DELETE"])
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


@bp.route("/profile/list/<list_name>", methods=["POST"])
def add_profile_list_item(list_name):
    if list_name not in ("hard_skills", "soft_skills", "languages"):
        return jsonify({"error": "Ungültige Liste."}), 400
    data = request.get_json(silent=True) or {}
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


@bp.route("/profile/list/<list_name>/<item_id>", methods=["PUT"])
def update_profile_list_item(list_name, item_id):
    if list_name not in ("hard_skills", "soft_skills", "languages"):
        return jsonify({"error": "Ungültige Liste."}), 400
    data = request.get_json(silent=True) or {}
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


@bp.route("/profile/list/<list_name>/<item_id>", methods=["DELETE"])
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
