"""One-shot: backfill missing earlier linear stages into stage_events.

Background.
-----------
Applications added retrospectively (e.g. ones I manually logged as already
``rejected`` or already in ``interview_1``) only have a single ``stage_events``
row — the current stage. That breaks the funnel/statistics view, which counts
how many applications *reached* each linear stage by inspecting the full
history.

This script materializes the implied earlier stages:

* If current stage is ``rejected``  → assume at least ``documents_created`` and
  ``application_sent`` were done. If history already contains a higher
  ``interview_*`` stage, every stage up to that one is materialized.
* If current stage is ``interview_N`` → materialize ``documents_created``,
  ``application_sent`` and every intermediate ``interview_*`` that's missing.
* If current stage is ``application_sent`` → materialize ``documents_created``.

Pre-existing events are never touched.

Usage
-----
    python scripts/backfill_stage_history.py            # dry-run (prints plan)
    python scripts/backfill_stage_history.py --apply    # actually insert events
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402

LINEAR_STAGES = [
    "documents_created",
    "application_sent",
    "interview_1",
    "interview_2",
    "interview_3",
]
# Hour offsets per stage so events on the same anchor date sort in the right
# order via the (at, id) index used by stage_events.
STAGE_HOUR = {
    "documents_created": 8,
    "application_sent":  9,
    "interview_1":       10,
    "interview_2":       11,
    "interview_3":       12,
}


def _max_linear_idx(history_stages: list[str], current_stage: str) -> int:
    """Highest LINEAR_STAGES index implied by the existing data."""
    max_idx = -1
    for s in history_stages:
        if s in LINEAR_STAGES:
            i = LINEAR_STAGES.index(s)
            if i > max_idx:
                max_idx = i
    if current_stage in LINEAR_STAGES:
        i = LINEAR_STAGES.index(current_stage)
        if i > max_idx:
            max_idx = i
    if current_stage == "rejected":
        # User's rule: a rejection always implies the application was at least sent.
        sent_idx = LINEAR_STAGES.index("application_sent")
        if max_idx < sent_idx:
            max_idx = sent_idx
    return max_idx


def _anchor_date(applied_at: str | None, created_at: str | None) -> str:
    """YYYY-MM-DD anchor for synthesized event timestamps."""
    if applied_at and len(applied_at) >= 10:
        return applied_at[:10]
    if created_at and len(created_at) >= 10:
        return created_at[:10]
    # Should never happen — every row has created_at — but be defensive.
    return "1970-01-01"


def _synth_ts(anchor_date: str, stage: str) -> str:
    return f"{anchor_date}T{STAGE_HOUR[stage]:02d}:00:00"


def plan_backfill(apps: list[dict]) -> list[tuple[str, str, str, str, str]]:
    """Return list of (app_id, company, position, stage, at) to insert."""
    plan: list[tuple[str, str, str, str, str]] = []
    for app in apps:
        history_stages = [h["stage"] for h in (app.get("stage_history") or [])]
        max_idx = _max_linear_idx(history_stages, app.get("stage", ""))
        if max_idx < 0:
            continue
        anchor = _anchor_date(app.get("applied_at"), app.get("created_at"))
        for i in range(max_idx + 1):
            stage = LINEAR_STAGES[i]
            if stage in history_stages:
                continue
            plan.append((
                app["id"],
                app.get("company", ""),
                app.get("position", ""),
                stage,
                _synth_ts(anchor, stage),
            ))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Actually insert events. Without this flag, prints the plan only.")
    args = parser.parse_args()

    db.init_schema()
    apps = db.list_applications()
    plan = plan_backfill(apps)

    if not plan:
        print("Nothing to backfill — every application already has a complete linear history.")
        return 0

    by_app: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for item in plan:
        by_app.setdefault(item[0], []).append(item)

    print(f"{'Would add' if not args.apply else 'Adding'} {len(plan)} stage event(s) "
          f"across {len(by_app)} application(s):\n")
    for app_id, items in by_app.items():
        _, company, position, _, _ = items[0]
        label = f"{company} — {position}" if position else company
        print(f"  [{app_id}] {label}")
        for _, _, _, stage, at in items:
            print(f"      + {stage:<20} @ {at}")
        print()

    if not args.apply:
        print("Dry-run. Re-run with --apply to commit.")
        return 0

    for app_id, _, _, stage, at in plan:
        db.append_stage_event(app_id, stage, at)
    print(f"Inserted {len(plan)} stage event(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
