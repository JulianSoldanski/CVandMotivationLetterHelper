
# CVCreater

Kleine **Flask-Webapp**, mit der du aus Stellenausschreibungen und deinem Profil **Lebenslauf** und **Anschreiben** per Google Gemini generieren und im Browser bearbeiten kannst.



https://github.com/user-attachments/assets/cadc29bd-8636-4689-8e2c-d4ec5ad4f9a7





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

`config/cv_personal.json` bearbeiten: **Name, Adresse, Telefon und E-Mail im Lebenslauf/Anschreiben-Kopf** kommen nur aus dieser Datei – nicht aus `profile.json`. Nach Änderungen einmal **neu generieren** (Beide / Nur CV / Nur Anschreiben), damit die Vorschau den neuen Kopf zeigt.

Die Datei ist in `.gitignore` vorgesehen; Änderungen werden ohne Server-Neustart übernommen.

### 3. Profil & Projekte

Die App liest `data/profile.json` und `data/projects.json`. Fehlen die Dateien, startet die App mit leeren Listen.

**Demo-Daten (fiktiv: Max Mustermann)** – ins Arbeitsverzeichnis kopieren:

```bash
mkdir -p data
cp examples/profile.example.json data/profile.json
cp examples/projects.example.json data/projects.json
```

Die Beispiele liegen versioniert unter `examples/`; der Ordner `data/` ist in `.gitignore`, damit dein echtes Profil nicht ins Repo rutscht.

## Starten

```bash
python app.py
```

Im Browser: **http://127.0.0.1:5050**


## Lizenz

Keine Lizenz gesetzt — bei Bedarf z. B. MIT ergänzen.
