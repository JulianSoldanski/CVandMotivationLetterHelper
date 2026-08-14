"""Job queue: the URL list fed by the bookmarklet.
"""
import uuid

from flask import Blueprint, Response, jsonify, request

from core import config

from core import db

from core.util import _normalize_queue_url, _now_iso

bp = Blueprint("queue", __name__)


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


@bp.route("/queue", methods=["GET"])
def list_queue_route():
    status = (request.args.get("status") or "").strip() or None
    return jsonify(db.list_queue(status=status))


@bp.route("/queue", methods=["POST"])
def add_queue_route():
    """JSON endpoint used by the in-app paste-field (Queue-Tab).

    Body: { url, title?, note? }. Returns the created/existing queue row.
    """
    data  = request.get_json(silent=True) or {}
    raw   = (data.get("url") or "").strip()
    if not raw:
        return jsonify({"error": "Keine URL angegeben."}), 400
    url = _normalize_queue_url(raw)
    if not url:
        return jsonify({"error": "Ungültige URL."}), 400

    title = (data.get("title") or "").strip()[:config.JOB_QUEUE_TITLE_MAX]
    note  = (data.get("note")  or "").strip()[:config.JOB_QUEUE_NOTE_MAX]

    existing = db.find_queue_item_by_url(url)
    if existing and existing["status"] == "pending":
        return jsonify({"item": existing, "duplicate": True}), 200

    qid = str(uuid.uuid4())[:8]
    item = db.add_queue_item(qid, url, title, note, _now_iso())
    return jsonify({"item": item, "duplicate": False}), 201


@bp.route("/queue/<qid>", methods=["PATCH"])
def update_queue_route(qid):
    """Partial update: status / note. Used by the UI for done / skipped / note edits."""
    if not db.get_queue_item(qid):
        return jsonify({"error": "Queue-Eintrag nicht gefunden."}), 404
    data = request.get_json(silent=True) or {}
    kwargs = {}
    if "status" in data:
        st = (data.get("status") or "").strip()
        if st not in db.QUEUE_STATUSES:
            return jsonify({"error": "Ungültiger Status."}), 400
        kwargs["status"] = st
        if st in ("done", "skipped", "failed"):
            kwargs["processed_at"] = _now_iso()
    if "note" in data:
        kwargs["note"] = (data.get("note") or "").strip()[:config.JOB_QUEUE_NOTE_MAX]
    if "application_id" in data:
        kwargs["application_id"] = (data.get("application_id") or "").strip() or None
    item = db.update_queue_item(qid, **kwargs)
    return jsonify(item)


@bp.route("/queue/<qid>", methods=["DELETE"])
def delete_queue_route(qid):
    if not db.delete_queue_item(qid):
        return jsonify({"error": "Queue-Eintrag nicht gefunden."}), 404
    return jsonify({"ok": True})


@bp.route("/queue/add", methods=["GET"])
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
    title = raw_title[:config.JOB_QUEUE_TITLE_MAX]

    existing = db.find_queue_item_by_url(url)
    if existing and existing["status"] == "pending":
        return _queue_close_page(
            "Schon in der Queue",
            sub=existing.get("title") or url,
        )

    qid = str(uuid.uuid4())[:8]
    db.add_queue_item(qid, url, title, "", _now_iso())
    return _queue_close_page(
        "Zur Queue hinzugefügt",
        sub=title or url,
    )


@bp.route("/queue/install", methods=["GET"])
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
