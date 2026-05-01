# CVCreater

Kleine **Flask-Webapp**, mit der du aus Stellenausschreibungen und deinem Profil **Lebenslauf** und **Anschreiben** per Google Gemini generieren und im Browser bearbeiten kannst.

## Voraussetzungen

- Python 3.11+ (getestet mit 3.13)
- [Google AI Studio](https://aistudio.google.com/) API-Key für Gemini

## Installation

```bash
cd CVCreater
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Konfiguration

### 1. Umgebungsvariablen

Lege eine **`.env`** im Projektroot an (liegt in `.gitignore`):

```env
GEMINI_API_KEY=dein_key_hier
# optional:
# GEMINI_MODEL=gemini-2.5-flash
```

### 2. Persönliche Daten 

```bash
cp config/cv_personal.example.json config/cv_personal.json
```

`config/cv_personal.json` bearbeiten: Name, Adresse, Telefon, E-Mail, `candidate_base` für den LLM-Kontext. Die Datei ist in `.gitignore` vorgesehen.

### 3. Profil & Projekte

Die App liest `data/profile.json` und `data/projects.json`. Fehlen die Dateien, startet die App mit leeren Listen; beim Speichern über die UI sollte der Ordner `data/` existieren (falls nötig: `mkdir -p data`).

## Starten

```bash
python app.py
```

Im Browser: **http://127.0.0.1:5050**

## Öffentlich auf GitHub

- **Neues Repository** mit frischer Historie: Projekt kopieren, alten Ordner **`.git` löschen**, dann `git init`, Commit, mit einem neuen leeren Repo auf GitHub verbinden und pushen. So verschwinden alte Commits, in denen noch Klartext in `app.py` stand.
- Niemals committen: **`.env`**, **`config/cv_personal.json`**, sensible Inhalte unter **`data/`**, falls du sie ignorierst.

## Lizenz

Keine Lizenz gesetzt — bei Bedarf z. B. MIT ergänzen.
