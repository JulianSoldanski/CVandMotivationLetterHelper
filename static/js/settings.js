// Writing-style settings.

// ── Settings ──
function updateStyleCount() {
  const n = (document.getElementById('styleExample').value || '').length;
  document.getElementById('styleCount').textContent = `${n} Zeichen`;
}

async function saveSettings() {
  const btn    = document.getElementById('settingsSaveBtn');
  const status = document.getElementById('settingsStatus');
  btn.disabled = true; btn.textContent = 'Speichern…';
  status.classList.remove('show', 'error');
  try {
    const res = await fetch('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        style_example:  document.getElementById('styleExample').value,
        style_analysis: document.getElementById('styleAnalysis').value,
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Speichern fehlgeschlagen.');
    status.textContent = '✓ Stil gespeichert. Wirkt beim nächsten Generieren.';
    status.classList.add('show');
    setTimeout(() => status.classList.remove('show'), 2500);
  } catch (e) {
    status.textContent = '✗ ' + e.message;
    status.classList.add('show', 'error');
  } finally {
    btn.disabled = false; btn.textContent = 'Speichern';
  }
}

async function analyzeStyle() {
  const example = document.getElementById('styleExample').value.trim();
  const analysisEl = document.getElementById('styleAnalysis');
  const btn = document.getElementById('analyzeStyleBtn');
  const status = document.getElementById('settingsStatus');

  if (!example) {
    alert('Bitte zuerst ein Beispiel-Anschreiben einfügen.');
    return;
  }

  if (analysisEl.value.trim() && !confirm('Die bestehende Analyse wird überschrieben. Fortfahren?')) {
    return;
  }

  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = 'Analysiere…';
  status.classList.remove('show', 'error');

  try {
    const res = await fetch('/analyze-style', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ example })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Analyse fehlgeschlagen.');
    analysisEl.value = data.analysis || '';
    status.textContent = '✓ Stil analysiert. Du kannst die Punkte jetzt anpassen und dann speichern.';
    status.classList.add('show');
    setTimeout(() => status.classList.remove('show'), 3500);
  } catch (e) {
    status.textContent = '✗ ' + e.message;
    status.classList.add('show', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}
