"""Date and URL helpers shared by the routes.
"""
from datetime import date, datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from core import config


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
        return url[:config.JOB_URL_MAX]
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    kept = [
        (k, v) for (k, v) in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in config._TRACKING_PARAMS
        and not any(k.lower().startswith(p) for p in config._TRACKING_PARAM_PREFIXES)
    ]
    query = urlencode(kept)
    cleaned = urlunsplit((scheme, netloc, parts.path, query, ""))
    return cleaned[:config.JOB_URL_MAX]


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
