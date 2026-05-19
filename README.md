# CVCreater

A Flask web app that turns a job posting + your profile into a **tailored
CV and cover letter** using Google Gemini, with an editor, a job summary,
an application tracker, and an AI-distilled "writing style" the cover
letters mimic.

Originally a one-trick generator. Grew into a small personal toolchain for
managing the entire job-application loop end-to-end.

> Built solo as a side project. Development decisions are logged in
> [docs/JOURNAL.md](docs/JOURNAL.md) — the "why" behind each feature.

---

## Walkthrough

A four-part screencast of the full loop, from clipping a posting to
landing the interview tracker. Each clip is ~30–60 seconds.


### Part 1 — Capture: bookmarklet → queue → AI job summary

Install the `→ Queue` bookmarklet, click it from any job page, watch the
posting land in the central queue, and see Gemini's **Stellen-Übersicht**
condense the company, the role, and the requested tech stack into a
glance-able summary.



https://github.com/user-attachments/assets/33ebf7e9-95f9-4c34-a288-7bad265faa12




### Part 2 — Generate the CV (and cover letter)

One click turns the queued posting into a tailored CV in your chosen
layout (Modern / Sidebar / Classic) plus a matching Anschreiben in DE or
EN. Edit the profile statement, swap experience bullets, toggle projects
— live preview updates as you go.


https://github.com/user-attachments/assets/59d5b5fa-ba97-4d4e-ae2b-8045e06081ed



https://github.com/user-attachments/assets/46c0b6bc-1f36-475b-affe-67ab88aeb7bd




### Part 3 — Track applications & statistics

Every Generieren auto-logs an application. The Bewerbungen view shows
the funnel stepper (Erstellt → Versendet → 1./2./3. Gespräch · Abgesagt)
with per-card timestamps and a per-application snapshot of exactly what
got sent. The Statistik tab turns the underlying `stage_events` history
into a funnel chart and time-in-stage averages.



### Part 4 — Profile & AI writing-style analysis

Build out the profile (experience, education, skills, languages,
projects), then paste an example cover letter and let Gemini **distill
your writing style** into editable bullet rules. Future Anschreiben
follow those rules, not the raw example — so you can steer the AI's
voice without rewriting letters from scratch.



https://github.com/user-attachments/assets/3888dbe1-4a1f-4bcf-8de6-60cfc58fe635



---

## What it does

**Queue + Bookmarklet**
- Hit a `→ Queue` bookmarklet from any job page (StepStone, LinkedIn, etc.)
  and the URL lands in a central queue. Install once by drag-and-dropping
  the button from `/queue/install` into your bookmarks bar.
- Queue view shows pending postings as cards; one click on **→ Generieren**
  opens the saved URL in the Generator, prefills the input, and
  auto-marks the queue item as done after generation.
- Statuses: pending / done / skipped / failed. Done + skipped collapse
  into an archive section.
- Inline add (paste URL + optional note + Enter) for cases where the
  bookmarklet wasn't handy.

**Generator**
- Paste a job posting or fetch from a URL (StepStone, LinkedIn, …).
- One click → tailored CV (German or English) in three layouts (Modern /
  Sidebar / Classic) plus a matching cover letter (Anschreiben).
- "Auto-Ausfüllen" extracts company, position, contact line, and city from
  the posting text via a structured Gemini call.
- **Stellen-Übersicht** — AI summary of *what the company does*, *what
  they're looking for*, *which technologies* — pinned to the left panel
  so it stays visible while you edit on the right.
- Editor tab: edit the profile statement, swap in/out experience bullets,
  add/remove projects, tweak skills. Live preview iframe. Projects can carry
  a link (GitHub, live demo, …) which renders as a clickable inline reference
  in the CV.
- Built-in KI-Feedback chat: ask "Was fehlt?", "Welche Keywords?", "Was
  fällt HR zuerst auf?" — Gemini answers with the full document context.

**Profil (Profile + writing-style)**
- One tab for everything that defines *you*: experience, education,
  hard / soft skills, languages, and projects (with optional GitHub /
  demo links rendered inline in the CV).
- Bottom of the same tab: paste a motivation letter you like in DE
  and/or EN, click **✨ Stil analysieren** — Gemini distills it into a
  bullet-point style guide (tone, sentence structure, word choice,
  idiosyncrasies).
- **Edit the analysis freely.** Future cover letters follow these rules,
  not the raw example. Lets you steer the AI's voice precisely.

**Bewerbungen (Application tracker)**
- Every Generieren click auto-logs an application (deduped by company +
  position). The original posting URL is stored too — one click on the card
  reopens the source.
- Visual stepper: Erstellt → Versendet → 1. Gespräch → 2. Gespräch → 3.
  Gespräch. Plus a separate **Abgesagt** terminal state.
- Per-card pills: 📨 application date · ⏱ time-in-current-stage.
- Every stage transition is timestamped (`stage_events` table) — sets up
  future analytics (avg days between stages, funnel by role, rejection
  breakdown).
- Per-application snapshot: 📄 see exactly which skills, projects, profile
  statement, and tailored experience bullets went out for *that*
  application. ✉️ see the exact Anschreiben paragraphs.
- Feedback / notes textarea per card. Manual-add for applications you sent
  before using the tool.

**Statistik**
- Funnel view over the application lifecycle: how many got sent, how
  many reached each interview stage, how many were rejected.
- Time-in-stage averages and monthly throughput, all derived from the
  append-only `stage_events` history — so the chart is always consistent
  with what the tracker shows.

---

## Why this is interesting

A few things that aren't obvious from the screenshot:

- **Browser-native job capture.** The bookmarklet is the smallest possible
  integration with the rest of the web — no extension store, no
  permissions, just a `javascript:` URL the browser already trusts. From
  any job page it fires a `window.open` to my Flask app's `/queue/add`
  endpoint, which inserts the URL into the queue and auto-closes the
  popup. ~60 lines of code total, no third-party services.

- **Two-tier style transfer.** Most AI cover-letter tools just dump an
  example into the prompt. I let Gemini distill the example into editable
  style rules, which I then refine. The prompt uses the *rules*, not the
  raw example — which means I can steer the AI's voice without rewriting
  letters from scratch.

- **Append-only stage history.** Application stages aren't a single
  string; they're a `stage_events` table with timestamps. This is the
  foundation for the analytics view I'm adding next: "average days from
  Versendet → 1. Gespräch", "interview rate by role", etc. The
  schema-first approach means each new metric is one SQL query, not a
  nested Python loop.

- **Snapshot-per-application.** When you regenerate documents for the
  same opening multiple times, the latest CV + Anschreiben gets pinned to
  that application record. Months later you can see exactly which version
  you sent.

- **Hybrid storage.** Operational data (applications, stage history) is in
  SQLite for queries. Config-shaped data (profile, projects, settings,
  contact info) stays as JSON because it's small, edited manually, and
  benefits from being human-readable in a `git diff`. Picked the right
  tool per file.

---

## Tech stack

- **Backend**: Flask · Python 3.11+ · `google-genai` SDK · BeautifulSoup
  (job-posting scraping) · stdlib `sqlite3`.
- **Frontend**: vanilla HTML/CSS/JS — no build step, no framework. Single
  `templates/index.html` (~2000 lines including styles + script).
- **AI**: Google Gemini (default `gemini-2.5-flash`). Multiple structured
  prompts: CV generation, Anschreiben generation, job summary, field
  extraction, style analysis, chat.
- **Storage**:
  - `data/cvcreater.db` — applications + stage_events
  - `data/profile.json`, `data/projects.json`, `data/settings.json` — config
  - `config/cv_personal.json` — contact info (kept separate from profile)

---

## Architecture at a glance

```
        ┌───────────────────────────────┐
        │ Any job site (StepStone, …)   │
        │   click "→ Queue" bookmarklet │
        └──────────────┬────────────────┘
                       │ window.open → /queue/add
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ Browser (single-page, vanilla JS)                            │
│  ┌────────┐ ┌──────┐ ┌──────┐ ┌──────────┐ ┌────────────┐    │
│  │Generat.│ │Queue │ │Profil│ │Bewerbung.│ │ Statistik  │    │
│  │+ Stel- │ │+book-│ │+CV   │ │ (tracker │ │ (funnel +  │    │
│  │ lenübs.│ │marklt│ │+style│ │  +snap-  │ │  stage-    │    │
│  │        │ │      │ │rules │ │   shots) │ │  time avg) │    │
│  └────────┘ └──────┘ └──────┘ └──────────┘ └────────────┘    │
└────────────────────────────┬─────────────────────────────────┘
                             │ /generate, /applications, /queue,
                             │ /settings, /analyze-style, /chat …
┌────────────────────────────▼─────────────────────────────────┐
│ Flask app.py                                                 │
│  - Routes + request validation                               │
│  - call_gemini / _call_gemini_json helpers                   │
│  - Prompt builders for CV, Anschreiben, summary, analysis    │
│  - /queue/install (bookmarklet drag-and-drop page)           │
└────┬──────────────────────────────────────────┬──────────────┘
     │                                          │
     ▼                                          ▼
┌──────────────────┐                  ┌────────────────────────┐
│ db.py (SQLite)   │                  │ JSON config files      │
│  applications    │                  │  profile.json          │
│  stage_events    │                  │  projects.json         │
│  job_queue       │                  │  settings.json         │
│                  │                  │  cv_personal.json      │
└──────────────────┘                  └────────────────────────┘
                                                ▲
                                                │
                                      ┌─────────┴──────────┐
                                      │ Google Gemini API  │
                                      └────────────────────┘
```

---

## Setup

### Requirements
- Python 3.11+ (tested with 3.13)
- A [Google AI Studio](https://aistudio.google.com/) API key for Gemini

### Install

```bash
cd CVCreater
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure

**1. Environment variables** — create `.env` (already in `.gitignore`):

```env
GEMINI_API_KEY=your_key_here
# optional:
# GEMINI_MODEL=gemini-2.5-flash
```

**2. Personal contact info:**

```bash
cp config/cv_personal.example.json config/cv_personal.json
```

Edit `config/cv_personal.json` — name, address, phone, email in the CV /
Anschreiben header come from here. Changes are picked up without a server
restart, but you have to **regenerate** (Beide / Nur CV / Nur Anschreiben)
for the preview to show the new header.

**3. Profile & projects:**

```bash
mkdir -p data
cp examples/profile.example.json data/profile.json
cp examples/projects.example.json data/projects.json
```

Examples are versioned under `examples/`; the live `data/` dir is in
`.gitignore` so your real profile doesn't get committed.

### Run

```bash
python app.py
```

Open <http://127.0.0.1:5050>.

### Install the queue bookmarklet (optional)

Visit <http://127.0.0.1:5050/queue/install>, show your bookmarks bar
(`Cmd+Shift+B` / `Ctrl+Shift+B`), then drag the **→ Queue** button onto
the bar. From then on, clicking that bookmark on any job page sends the
URL into your queue.

> Works as long as `python app.py` is running. If you're on an `https://`
> page and see Mixed-Content warnings, allow them for `localhost`.

### Migrating from an older version

If you have an existing `data/applications.json` from before the SQLite
move, run once:

```bash
python3 scripts/migrate_applications_to_sqlite.py
```

It moves your applications into `data/cvcreater.db` and renames the source
to `applications.json.bak` (kept indefinitely as a safety net — delete
manually whenever you trust the migration).

### Demo mode for screencasts and live demos

There are two ways to serve the bundled Max-Mustermann demo instead of your
real data. They solve slightly different problems — pick whichever fits:

**Option A — `DEMO_MODE=1` (recommended for most cases).** Add to `.env`,
restart the app, done. The app reads from an isolated workspace at
`data/.demo/` that's seeded once from [`examples/demo/`](examples/demo/).
Your real `data/` and `config/cv_personal.json` are **never touched**, so
toggling back is just removing the env var and restarting. Demo edits
persist across restarts (within the demo workspace) so you can prepare
your screencast state once and replay it.

```env
DEMO_MODE=1
```

The header shows an orange **DEMO** badge while this mode is on so you
can't forget you're not on real data. To wipe the demo workspace and
re-seed it fresh, delete `data/.demo/` and restart.

**Option B — physical file swap via `swap_profile.py`.** Use this when
you want git-visible profile state, or when running offline tooling
(scripts/manual edits) against the demo data.

```bash
python3 scripts/swap_profile.py demo      # swap in demo, back up your real data
python3 scripts/swap_profile.py mine      # restore your real data
python3 scripts/swap_profile.py status    # show current owner
```

Real files are moved to `data/.mine_backup/` while demo is active; `mine`
restores them bit-for-bit. The script refuses to run while `DEMO_MODE=1`
is set, so the two modes don't fight each other.

---

## Roadmap

Tracked in [docs/JOURNAL.md](docs/JOURNAL.md) under each entry's
"Follow-up" notes. Next up:

- **Statistiken tab** — funnel chart, time-in-stage averages,
  interview-rate per role. Backend is ready (`stage_events` is indexed);
  just needs the endpoints and the frontend view.
- **PDF upload → application snapshot** — drop an old CV PDF into
  "Bewerbung hinzufügen" and the parsed skills/projects/text attach to
  that historic application. (Backend `POST /parse-cv-pdf` is live;
  modal wiring is in progress.)
- **"Generate all pending" batch from the queue** — turn the queue into a
  one-click bulk-tailoring tool. Deferred until the AI-cost UX is right.

---

## Project layout

```
CVCreater/
├── app.py                    # Flask routes, prompt builders, generation
├── db.py                     # SQLite DAL (applications + stage_events)
├── cv_layouts.py             # CV layout templates (Modern / Sidebar / Classic)
├── personal_config.py        # Contact loader (cv_personal.json)
├── templates/index.html      # Entire frontend (HTML + CSS + JS)
├── data/                     # Live data (gitignored)
│   ├── cvcreater.db
│   ├── profile.json
│   ├── projects.json
│   └── settings.json
├── examples/                 # Demo profile/projects (fictional)
│   └── demo/                 # Max-Mustermann demo (used by swap_profile.py)
├── scripts/
│   ├── migrate_applications_to_sqlite.py   # one-shot: applications.json → SQLite
│   ├── backfill_stage_history.py           # synthesize missing earlier stage_events
│   ├── reseed_demo_db.py                   # rebuild data/.demo/cvcreater.db from JSON
│   └── swap_profile.py                     # swap live ↔ demo data with backup/restore
└── docs/
    └── JOURNAL.md            # Development log (idea → decision → outcome)
```

---

## License

No license set — add one (MIT, Apache-2.0, …) if you fork or share.
