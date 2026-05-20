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

https://github.com/user-attachments/assets/46c0b6bc-1f36-475b-affe-67ab88aeb7bd




### Part 3 — Track applications & statistics

Every Generieren auto-logs an application. The Bewerbungen view shows
the funnel stepper (Erstellt → Versendet → 1./2./3. Gespräch · Abgesagt)
with per-card timestamps and a per-application snapshot of exactly what
got sent. The Statistik tab turns the underlying `stage_events` history
into a funnel chart and time-in-stage averages.

https://github.com/user-attachments/assets/59d5b5fa-ba97-4d4e-ae2b-8045e06081ed



### Part 4 — Profile & AI writing-style analysis

Build out the profile (experience, education, skills, languages,
projects), then paste an example cover letter and let Gemini **distill
your writing style** into editable bullet rules. Future Anschreiben
follow those rules, not the raw example — so you can steer the AI's
voice without rewriting letters from scratch.



https://github.com/user-attachments/assets/3888dbe1-4a1f-4bcf-8de6-60cfc58fe635

---

## Roadmap

Tracked in [docs/JOURNAL.md](docs/JOURNAL.md) under each entry's
"Follow-up" notes. Next up:

- **Statistiken tab** — funnel chart, time-in-stage averages,
  interview-rate per role. Backend is ready (`stage_events` is indexed);
  just needs the endpoints and the frontend view. Also categorizing job descriptions based with genai, is a good idea to see in which jobs the cv is best suited for
- **Create Profile based on PDF upload** — Upload CV, Upload motivationletter -> Create profile from this

- **"Generate all pending" batch from the queue** — turn the queue into a
  one-click bulk-tailoring tool. Question is do I want this to be easier? After all, the human still has to look over the application, since there are often misrepresented by AI. Automating it further could decrease quality.
- **UI Overhaul** - Right now UI is rather functional and not much time was spent on it.
  In the future this can be improved further
- **UX Overhaul** - Some steps need to be changed. Goal must be as little clicks as possible to get through the whole workflow. First cv -> then Motivation letter ( not go back and forth ), add subpages so user stays on them, when reloading
- **Offer Comparison** - Incoming deals are not built yet. A comparison page based on offers is possible.
- **Automatically change Status of Applications** - An Ai agent could look through emails to identify invitations / declines and update the status automatically. Either as a cronjob or with mail programm api
- **Automatically queue interesting offers** - Scraping job portals is often a difficult tasks, since they are very well protected. However an idea could be to create an email, which receives automatic job recommendations from stepstone, linkedin and co. This could be handled by an AI agent. 
- **Add Authentication** Add authentication to run this on a server
- **Make it public** The idea to publish this online as a saas is interesting, since the data gathered from the software could be analyzed and give great information about the job market. However very generous problem: I dont think this could be monetized well
- **Database optimization** DB architecture needs to be inspected further to decrease redundancy.

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
  you sent. Analyzing different CV approaches is possible.

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
