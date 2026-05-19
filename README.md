# CVCreater

A Flask web app that turns a job posting + your profile into a **tailored
CV and cover letter** using Google Gemini, with an editor, a job summary,
an application tracker, and an AI-distilled "writing style" the cover
letters mimic.

Originally a one-trick generator. Grew into a small personal toolchain for
managing the entire job-application loop end-to-end.

> Built solo as a side project. Development decisions are logged in
> [docs/JOURNAL.md](docs/JOURNAL.md) — the "why" behind each feature.

https://github.com/user-attachments/assets/cadc29bd-8636-4689-8e2c-d4ec5ad4f9a7

---

## What it does

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
  add/remove projects, tweak skills. Live preview iframe.
- Built-in KI-Feedback chat: ask "Was fehlt?", "Welche Keywords?", "Was
  fällt HR zuerst auf?" — Gemini answers with the full document context.

**Bewerbungen (Application tracker)**
- Every Generieren click auto-logs an application (deduped by company +
  position).
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

**Einstellungen (Settings)**
- Paste a motivation letter you like in DE and/or EN.
- Click **✨ Stil analysieren** — Gemini distills it into a bullet-point
  style guide (tone, sentence structure, word choice, idiosyncrasies).
- **Edit the analysis freely.** Future cover letters follow these rules,
  not the raw example. Lets you steer the AI's voice precisely.

---

## Why this is interesting

A few things that aren't obvious from the screenshot:

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
┌──────────────────────────────────────────────────────────────┐
│ Browser (single-page, vanilla JS)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐   │
│  │ Generator   │  │ Bewerbungen │  │ Einstellungen       │   │
│  │ + Stellen-  │  │ (tracker)   │  │ (style examples +   │   │
│  │   Übersicht │  │             │  │  AI-distilled rules)│   │
│  └─────────────┘  └─────────────┘  └─────────────────────┘   │
└────────────────────────────┬─────────────────────────────────┘
                             │ /generate, /applications, /settings,
                             │ /analyze-style, /chat, /improve-text …
┌────────────────────────────▼─────────────────────────────────┐
│ Flask app.py                                                 │
│  - Routes + request validation                               │
│  - call_gemini / _call_gemini_json helpers                   │
│  - Prompt builders for CV, Anschreiben, summary, analysis    │
└────┬──────────────────────────────────────────┬──────────────┘
     │                                          │
     ▼                                          ▼
┌──────────────────┐                  ┌────────────────────────┐
│ db.py (SQLite)   │                  │ JSON config files      │
│  applications    │                  │  profile.json          │
│  stage_events    │                  │  projects.json         │
│                  │                  │  settings.json         │
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

### Migrating from an older version

If you have an existing `data/applications.json` from before the SQLite
move, run once:

```bash
python3 scripts/migrate_applications_to_sqlite.py
```

It moves your applications into `data/cvcreater.db` and renames the source
to `applications.json.bak` (kept indefinitely as a safety net — delete
manually whenever you trust the migration).

---

## Roadmap

Tracked in [docs/JOURNAL.md](docs/JOURNAL.md) under each entry's
"Follow-up" notes. Next up:

- **Statistiken tab** — funnel chart, time-in-stage averages,
  interview-rate per role. Backend is ready (`stage_events` is indexed);
  just needs the endpoints and the frontend view.
- **PDF upload → profile** — drop in an existing CV PDF, have Gemini parse
  it into experience/education/skills entries.

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
├── scripts/
│   └── migrate_applications_to_sqlite.py
└── docs/
    └── JOURNAL.md            # Development log (idea → decision → outcome)
```

---

## License

No license set — add one (MIT, Apache-2.0, …) if you fork or share.
