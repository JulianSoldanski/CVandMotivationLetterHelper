# Development Journal

A chronological log of ideas → decisions → outcomes for CVCreater.
Each entry captures the *why*, not just the *what*. Useful for tracing how
the project evolved and for explaining design decisions later.

Format per entry:
- **Idea** — the prompt or problem I started with
- **Decision** — the path I chose and what I rejected
- **Outcome** — what shipped, files touched, follow-ups

---

## 2026-05-19 — Project links on the CV

**Idea.** Projects should be able to carry a URL (GitHub repo, live demo,
case study) and that link should render in the generated CV — not as a
separate field, but as a subtle inline reference after the project title.

**Decision.** Add an optional `link` field on each project. In the CV
HTML, render as `Title (github.com/foo/bar)` with the visible label
stripped of `https://` and trailing slashes so it doesn't get too noisy.
The project-manager card also gets a 🔗 quick-action that opens the link
in a new tab.

**Outcome.**
- New `link` field on projects in [app.py](../app.py) (`add_project` /
  `update_project`).
- CV render hint at [app.py:684-689](../app.py#L684-L689) — link only
  rendered when present, otherwise no parens.
- Project card 🔗 button in [templates/index.html:3271-3272](../templates/index.html#L3271-L3272).

---

## 2026-05-19 — Job-posting queue + bookmarklet

**Idea.** I keep stumbling on interesting job postings while browsing and
losing them in browser tabs / "ich schau später"-WhatsApp messages. I
want a one-click capture from any page that lands the URL in a central
to-do list, so I can come back later and Generieren in batch.

**Decision.** A bookmarklet — not a browser extension. Rationale:
- Zero install friction (drag a button into the bookmarks bar).
- No browser-store review process.
- No permissions / no privacy footprint to explain.
- It's just `javascript:(()=>{ window.open('http://localhost:5050/queue/add?url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title), '_blank', 'width=420,height=240') })()`
  — ~one line.

On the backend: new `job_queue` table (`id, url, title, note, status,
added_at, processed_at, error, application_id`). Status state machine:
`pending → done | skipped | failed`. URL is normalized (strip
`utm_*`/tracking params) before dedupe so the same posting from two
referrals collapses.

`/queue/install` is a tiny standalone HTML page with a draggable styled
anchor — it generates the bookmarklet inline so the host URL matches
wherever Flask is bound. `/queue/add` does the actual insert and returns
a self-closing HTML "Eintrag gespeichert ✓" popup.

In the Queue tab, **→ Generieren** on a pending card opens the saved
URL in the Generator, prefills the input, and after the generation
finishes the queue item is silently marked `done` and linked to the
created application via `application_id`.

**Outcome.**
- New `job_queue` table + `application_id` FK in [db.py](../core/db.py).
- `/queue` GET/POST, `/queue/<id>` PATCH/DELETE, `/queue/add` (bookmarklet
  target), `/queue/install` (drag-and-drop install page) in
  [app.py:1595-1771](../app.py#L1595-L1771).
- New 📥 Queue tab in the header nav with badge count, inline-add row,
  status cards, archive `<details>` for done/skipped/failed.
- `markQueueDoneSilently()` ties Generieren completion back to the
  originating queue item.
- `applications.job_url` now stores the source URL so the application
  card links back to the original posting.

**Follow-up.** Could add a "Generate all pending" batch button later, but
that needs careful UX around AI cost — best left manual for now.

---

## 2026-05-19 — Persist generated CV/Anschreiben per application

**Idea.** When I click Generieren, an application should be auto-logged, and
later I should be able to look at that application and see exactly which
skills, projects, and CV text were sent for it. The "frozen" version of what
I actually applied with.

**Decision.** Bundle this into the SQLite migration since I was extending
the schema anyway. Add `cv_content`, `anschreiben_content`, `layout_used`,
`language` columns to `applications`. Store the raw JSON dicts that `/generate`
returns — same shape the frontend already renders from, so no transformation
needed on read.

Use `COALESCE` in the upsert so regenerating only the Anschreiben doesn't
wipe the existing CV snapshot (and vice versa).

**Outcome.**
- New columns in [db.py](../core/db.py) schema + `ALTER TABLE` migration for any
  existing DB.
- `log_application(...)` gained kwargs for cv_content, anschreiben_content,
  layout_used, language.
- `/generate` passes the resolved layout + language + content snapshots into
  `log_application`.
- Frontend cards have two new `<details>` expanders: 📄 **Erstellte CV-Inhalte
  anzeigen** (profile statement, tailored experience bullets, education,
  tailored project descriptions, skills) and ✉️ **Anschreiben-Text anzeigen**
  (subject + greeting + paragraphs).
- Files: [db.py](../core/db.py), [app.py](../app.py), [templates/index.html](../templates/index.html).

---

## 2026-05-19 — JSON → SQLite migration (Phase A)

**Idea.** I want to see statistics eventually — which roles got me more
interviews, average days between stages, rejection breakdown. The
stage_history is already a one-to-many shape that's awkward in JSON.

**Decision.** Move applications to SQLite. Plain `sqlite3` stdlib, no ORM,
no extra deps. Two tables: `applications` (with `current_stage` denormalized
for fast list rendering) and `stage_events` (FK to applications, indexed on
`(application_id, at)` and on `stage`).

Kept JSON for `profile.json`, `projects.json`, `settings.json`,
`cv_personal.json` — they're config, never queried, and small. Hybrid
storage is the right tradeoff for a single-user local app.

Rejected:
- Postgres (overkill, needs a server)
- SQLAlchemy (boilerplate isn't worth it at 4–6 tables)
- Staying on JSON (we'd already paid the schemaless tax twice — `_ensure_history`
  backfill on every load, applied_at synthesis)

**Outcome.**
- New [db.py](../core/db.py) — connection pool, schema init, CRUD helpers.
- [scripts/migrate_applications_to_sqlite.py](../scripts/migrate_applications_to_sqlite.py)
  — one-shot, refuses to run if DB already has data, renames source to
  `applications.json.bak` for safety.
- [app.py](../app.py) persistence helpers (`load_applications`, `log_application`,
  `_set_stage` → `apply_stage_transition`) rewritten as thin wrappers over `db.py`.
- `_ensure_history` and `save_applications` deleted — the schema makes them
  unnecessary.
- `init_schema()` runs at module load, idempotent.
- Plan doc: [~/.claude/plans/ok-so-rn-we-tender-frog.md](../../.claude/plans/ok-so-rn-we-tender-frog.md).

**Follow-up (Phase B).** Add `/stats/funnel`, `/stats/time-between-stages`,
`/stats/by-role`, `/stats/rejection-rate` endpoints + a Statistiken tab in
the frontend. Not done yet; intentionally deferred.

---

## 2026-05-19 — Rejection as terminal status

**Idea.** Applications can get rejected at any point — after sending, after
1st interview, etc. Need a status for it.

**Decision.** Add `rejected` to `APPLICATION_STAGES` but **don't** render it
as a 6th step in the linear stepper — rejection isn't a linear progression.
Instead: keep the 5-step linear stepper, add a red `❌ Abgesagt am DD.MM.YYYY`
pill in the meta row when rejected, dim the stepper, and use the
`stage_history` to determine which linear step was the *last reached*.

Reactivation restores to the last non-rejected stage from history, so I
don't lose the path.

**Outcome.**
- Backend: just added `"rejected"` to the constant — every existing route
  works because stage history was already append-only.
- Frontend stepper renderer now history-aware (uses `stage_history` instead
  of pure linear index when stage == rejected).
- Quick-action buttons: **❌ Als abgesagt markieren** / **↺ Reaktivieren** on
  the card.

---

## 2026-05-19 — Editable AI-distilled writing style

**Idea.** I want the AI to match my writing style. Pasting an example letter
helps, but I want to *see and edit* what the AI is "thinking" about my style,
not just throw the raw example into the prompt.

**Decision.** Two-step: (1) AI analyzes the example into a bullet-point style
description (tone, sentence structure, word choice, structure patterns,
idiosyncrasies), (2) I can edit those bullets freely. The edited bullets
become the actual style guide injected into the Anschreiben prompt.

Fallback chain in the prompt: prefer `style_analysis` (the distilled rules);
if empty, fall back to raw `style_example`; if both empty, no style block.

**Outcome.**
- `POST /analyze-style` endpoint that calls Gemini with a structured
  analysis prompt.
- Settings tab: each language card now has Beispiel-Text → "✨ Stil
  analysieren" button → editable analyzed-style textarea.
- `data/settings.json` stores both `style_examples` and `style_analysis`
  per language.

---

## 2026-05-19 — Settings tab + motivation letter examples

**Idea.** I want a place to configure things, starting with motivation
letter examples in DE and EN so the AI can match my voice.

**Decision.** Add a third top-level view ("⚙️ Einstellungen") next to
Generator and Bewerbungen. Persist to `data/settings.json`. Inject the
example into the Anschreiben prompt as a "STIL-BEISPIEL" block with
instructions to mimic tone/sentence-length/word-choice but **not** copy
content verbatim.

(This entry seeded the next one — once I had examples, I wanted to see what
the AI was distilling from them.)

**Outcome.**
- `GET /settings`, `PUT /settings`.
- Settings view in [templates/index.html](../templates/index.html) with two
  side-by-side language cards.
- Anschreiben prompt extended with conditional style block.

---

## 2026-05-19 — Application date + stage history with timestamps

**Idea.** I want to track the date I sent each application — defaulted
automatically but editable. Eventually I want to see how long I was in each
stage. That means stages need to live in their own structure with timestamps,
not just a single `stage` string.

**Decision.** Add `stage_history: [{stage, at}]` — append-only log per
application. Current stage is derived (or denormalized to `stage` for
performance). When stage moves to `application_sent`, auto-set `applied_at`
to today unless already set. Modal gets a date input that pre-fills today.

Cards show two pills under the title: 📨 **Bewerbung: DD.MM.YYYY** and ⏱
**seit X Tagen in „1. Gespräch"** — duration auto-computed from the latest
history entry.

**Outcome.**
- Backend: `_ensure_history`, `_set_stage`, migration-on-load for legacy
  rows. (Later replaced by the SQLite schema — see Phase A entry.)
- Frontend: date input in modal, duration formatter, two new meta pills.

This was the entry that made me think "this should probably be a real DB"
— see the SQLite entry above.

---

## 2026-05-19 — Bewerbungs-Tracker (initial)

**Idea.** Every time I click Generieren I want it tracked: which job, which
company. I want a screen showing the application process from Documents →
Sent → 1st Interview → 2nd → 3rd, plus a feedback field. Also let me
manually add applications I already sent.

**Decision.** New top-level view "Bewerbungen" in the header. Auto-log on
`/generate` with dedupe by (company, position) so iteration doesn't spawn
duplicates. Visual stepper component with five circles, click any to set
that stage. Feedback textarea per card. Manual-add modal with stage selector.

**Outcome.**
- `data/applications.json` + CRUD routes (later moved to SQLite).
- New view with kanban-ish card list, stepper component, modal.
- `/generate` now also returns `data.application` so the badge updates
  immediately.

---

## 2026-05-15 — Stellen-Übersicht (job summary)

**Idea.** While I'm editing the CV and Anschreiben, I want a visible
summary of the job posting: what the company does, what they want, what
technologies they use.

**Decision.** Generate a structured summary via Gemini bundled into
`/generate` (one extra call, but keeps the API simple). Show it in the
**left panel** under the input — not as a right-panel tab — so it stays
visible while I edit on the right.

(First built it as a right-panel tab; immediately moved it to the left
after realizing the whole point was to see it *while* editing. Good
reminder that "where to put it" matters as much as "what it is".)

**Outcome.**
- `generate_job_summary()` returns `{company_does, searching_for[],
  technologies[]}`.
- "Stellen-Übersicht" block on the left panel with three cards + a
  collapsible `<details>` for the original cleaned text.

---

## How I use this journal

When I'm about to make a non-trivial change, I open this file and write an
entry first — even before coding. The act of writing "Idea / Decision /
Outcome" forces me to articulate the *why* and surface tradeoffs I'd
otherwise gloss over. After shipping, I update the Outcome section with
what actually happened (which is often slightly different from what I
planned, and that's the most interesting part to capture).
