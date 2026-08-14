// Application tracker: filters, stage changes, feedback.

// ── Applications ──
function updateAppsCount() {
  document.getElementById('appsCountBadge').textContent = applications.length;
}

function formatAppDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso.slice(0, 10);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

function getRejectedDateForInput(app) {
  if (!app || app.stage !== 'rejected') return '';
  const rejectedAt = (app.stage_history || []).slice().reverse().find(h => h.stage === 'rejected');
  if (!rejectedAt || !rejectedAt.at) return '';
  const iso = String(rejectedAt.at);
  return iso.length >= 10 ? iso.slice(0, 10) : '';
}

function syncAppModalRejectedVisibility() {
  const wrap = document.getElementById('appModalRejectedWrap');
  if (!wrap) return;
  const stage = document.getElementById('appModalStage').value;
  wrap.style.display = stage === 'rejected' ? 'block' : 'none';
}


function plainJobPostingText(raw) {
  if (!raw) return '';
  const s = String(raw).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  return s;
}

// Like plainJobPostingText, but preserves paragraph structure: only
// intra-line whitespace gets collapsed, newlines stay, and runs of 3+
// blank lines fold to a single blank line so scraped postings render
// with readable structure (rendered via CSS `white-space: pre-wrap`).
function prettyJobPostingText(raw) {
  if (!raw) return '';
  return String(raw)
    .replace(/<[^>]+>/g, ' ')
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .replace(/[ \t]*\n[ \t]*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function jobPostingPreview(raw, maxSentences = 3) {
  const plain = plainJobPostingText(raw);
  if (!plain) return { preview: '', hasMore: false };
  const sentences = plain.match(/[^.!?…]+[.!?…]+|[^.!?…]+$/g) || [plain];
  const taken = sentences.slice(0, maxSentences).join(' ').trim();
  const hasMore = sentences.length > maxSentences || plain.length > taken.length + 8;
  return { preview: taken, hasMore };
}

function initAppsFilterControls() {
  const sel = document.getElementById('appsFilterStage');
  if (!sel || sel.options.length > 1) return;
  APP_STAGES.forEach(s => {
    const o = document.createElement('option');
    o.value = s.key;
    o.textContent = s.label;
    sel.appendChild(o);
  });
}

function onAppsFilterChange() {
  renderApplications();
}
