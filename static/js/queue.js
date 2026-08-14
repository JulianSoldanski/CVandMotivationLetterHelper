// Job queue: the URL list fed by the bookmarklet.

// ── Queue ──
let queue = [];

function updateQueueBadge() {
  const n = queue.filter(q => q.status === 'pending').length;
  const badge = document.getElementById('queueCountBadge');
  if (badge) badge.textContent = n;
}

async function refreshQueue() {
  try {
    const res = await fetch('/queue');
    queue = await res.json();
  } catch (e) {
    queue = [];
  }
  renderQueue();
  updateQueueBadge();
}

function renderQueue() {
  const list    = document.getElementById('queueList');
  const archive = document.getElementById('queueArchive');
  const archBody = document.getElementById('queueArchiveList');
  const sub     = document.getElementById('queueSub');
  if (!list) return;

  const pending = queue.filter(q => q.status === 'pending');
  const others  = queue.filter(q => q.status !== 'pending');

  sub.textContent = pending.length === 0
    ? 'Keine offenen Einträge — leg dir das Bookmarklet an und füg Stellen hinzu, während du surfst.'
    : `${pending.length} ${pending.length === 1 ? 'Stelle wartet' : 'Stellen warten'} auf Bearbeitung.`;

  if (pending.length === 0) {
    list.innerHTML = `
      <div class="queue-empty">
        Noch nichts in der Queue.<br>
        Richte das <a href="/queue/install" target="_blank">Bookmarklet</a> ein,
        oder paste eine URL oben rein.
      </div>`;
  } else {
    list.innerHTML = pending.map(renderQueueCard).join('');
  }

  if (others.length === 0) {
    archive.style.display = 'none';
  } else {
    archive.style.display = '';
    archive.querySelector('summary').textContent =
      `Erledigt & übersprungen (${others.length})`;
    archBody.innerHTML = others.map(renderQueueCard).join('');
  }
}

function renderQueueCard(q) {
  const title = q.title || domainOf(q.url);
  const meta  = [
    `<span>${escapeHtml(domainOf(q.url))}</span>`,
    `<span>${timeAgo(q.added_at)}</span>`,
  ];
  if (q.status === 'done')    meta.push('<span style="color:#27ae60;font-weight:600">✓ erledigt</span>');
  if (q.status === 'skipped') meta.push('<span>↷ übersprungen</span>');
  if (q.status === 'failed')  meta.push('<span style="color:#c0392b;font-weight:600">⚠ fehlgeschlagen</span>');

  const actions = q.status === 'pending'
    ? `
      <button class="queue-btn primary" onclick="openInGenerator('${q.id}')" title="Im Generator öffnen">→ Generieren</button>
      <button class="queue-btn" onclick="markQueueStatus('${q.id}','skipped')" title="Überspringen">↷</button>
      <button class="queue-btn danger" onclick="deleteQueueItem('${q.id}')" title="Löschen">✕</button>
    `
    : `
      <button class="queue-btn" onclick="markQueueStatus('${q.id}','pending')" title="Zurück in die Queue">↩</button>
      <button class="queue-btn danger" onclick="deleteQueueItem('${q.id}')" title="Löschen">✕</button>
    `;

  return `
    <div class="queue-card ${q.status}">
      <div class="queue-card-body">
        <div class="queue-card-title">${escapeHtml(title)}</div>
        <a class="queue-card-url" href="${escapeHtml(q.url)}" target="_blank" rel="noopener">${escapeHtml(q.url)}</a>
        <div class="queue-card-meta">${meta.join('·&nbsp;')}</div>
        ${q.note ? `<div class="queue-card-note">${escapeHtml(q.note)}</div>` : ''}
      </div>
      <div class="queue-card-actions">${actions}</div>
    </div>`;
}

async function addQueueFromInput() {
  const urlEl  = document.getElementById('queueAddUrl');
  const noteEl = document.getElementById('queueAddNote');
  const url    = (urlEl.value  || '').trim();
  const note   = (noteEl.value || '').trim();
  if (!url) { urlEl.focus(); return; }
  try {
    const res = await fetch('/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, note })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Hinzufügen fehlgeschlagen.');
    urlEl.value = ''; noteEl.value = '';
    await refreshQueue();
  } catch (e) {
    alert('Fehler: ' + e.message);
  }
}

async function markQueueStatus(qid, status) {
  try {
    const res = await fetch('/queue/' + encodeURIComponent(qid), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Update fehlgeschlagen.');
    }
    await refreshQueue();
  } catch (e) {
    alert('Fehler: ' + e.message);
  }
}

async function deleteQueueItem(qid) {
  if (!confirm('Eintrag wirklich löschen?')) return;
  try {
    const res = await fetch('/queue/' + encodeURIComponent(qid), { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.error || 'Löschen fehlgeschlagen.');
    }
    await refreshQueue();
  } catch (e) {
    alert('Fehler: ' + e.message);
  }
}

async function markQueueDoneSilently(qid, applicationId) {
  try {
    const body = { status: 'done' };
    if (applicationId) body.application_id = applicationId;
    await fetch('/queue/' + encodeURIComponent(qid), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    // Lokalen State updaten ohne Refresh
    const item = queue.find(q => q.id === qid);
    if (item) {
      item.status = 'done';
      if (applicationId) item.application_id = applicationId;
    }
    updateQueueBadge();
  } catch (_) {
    // Silent fail — der Generator hat funktioniert, das ist nur Buchführung.
  }
}

async function openInGenerator(qid) {
  const item = queue.find(q => q.id === qid);
  if (!item) return;
  showView('generator');
  // URL-Mode aktivieren und URL eintragen
  const urlBtn = document.querySelector('.mode-btn[data-mode="url"]');
  if (urlBtn) switchInputMode('url', urlBtn);
  const urlInput = document.getElementById('job_url');
  if (urlInput) urlInput.value = item.url;
  // Stellenanzeige automatisch laden + Felder extrahieren
  try { await fetchJobUrl(); } catch (_) {}
  // Eintrag als erledigt markieren (nach Generieren wäre sauberer, aber der
  // User entscheidet ab hier selbst — diesen Schritt automatisieren wir
  // bewusst NICHT, damit Generator-Klick weiterhin manuell bleibt)
}
