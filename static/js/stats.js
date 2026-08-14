// Statistics view: funnel, durations, monthly breakdown.

// ── Statistics ──
function isoToDate(s) {
  if (!s) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function daysBetween(a, b) {
  if (!a || !b) return null;
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

function median(nums) {
  const arr = nums.filter(n => Number.isFinite(n)).slice().sort((a, b) => a - b);
  if (!arr.length) return null;
  const mid = Math.floor(arr.length / 2);
  return arr.length % 2 ? arr[mid] : Math.round((arr[mid - 1] + arr[mid]) / 2);
}

function highestReachedIdx(app) {
  const hist = app.stage_history || [];
  let maxIdx = -1;
  hist.forEach(h => {
    const idx = LINEAR_STAGES.findIndex(s => s.key === h.stage);
    if (idx > maxIdx) maxIdx = idx;
  });
  if (app.stage && app.stage !== 'rejected') {
    const cur = LINEAR_STAGES.findIndex(s => s.key === app.stage);
    if (cur > maxIdx) maxIdx = cur;
  }
  return maxIdx;
}

function firstEventAt(app, stageKey) {
  const hit = (app.stage_history || []).find(h => h.stage === stageKey);
  return hit ? isoToDate(hit.at) : null;
}

function lastEventAt(app, stageKey) {
  const arr = (app.stage_history || []).filter(h => h.stage === stageKey);
  return arr.length ? isoToDate(arr[arr.length - 1].at) : null;
}

function monthKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(key) {
  const [y, m] = key.split('-');
  const months = ['Jan', 'Feb', 'Mrz', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  return `${months[parseInt(m, 10) - 1]}\n${y.slice(2)}`;
}

function computeStats(apps) {
  const total = apps.length;
  const reached = LINEAR_STAGES.map(() => 0);
  apps.forEach(a => {
    const top = highestReachedIdx(a);
    for (let i = 0; i <= top; i++) reached[i] += 1;
  });

  const sentCount = reached[LINEAR_STAGES.findIndex(s => s.key === 'application_sent')] || 0;
  const interview1 = reached[LINEAR_STAGES.findIndex(s => s.key === 'interview_1')] || 0;
  const interview2 = reached[LINEAR_STAGES.findIndex(s => s.key === 'interview_2')] || 0;
  const interview3 = reached[LINEAR_STAGES.findIndex(s => s.key === 'interview_3')] || 0;

  const rejectedTotal = apps.filter(a => a.stage === 'rejected').length;
  const openCount = apps.filter(a =>
    a.stage !== 'rejected' && a.stage !== 'documents_created'
  ).length;
  const inInterview = apps.filter(a => {
    if (a.stage === 'rejected') return false;
    const top = highestReachedIdx(a);
    return top >= LINEAR_STAGES.findIndex(s => s.key === 'interview_1');
  }).length;

  // Display-only merge: beide Keys landen in einem Donut-Segment.
  const stageDistribution = APP_STAGES
    .filter(s => s.key !== MERGED_AWAY_KEY)
    .map(s => {
      const keys = s.key === MERGED_SENT_KEY ? [MERGED_SENT_KEY, MERGED_AWAY_KEY] : [s.key];
      return {
        key: s.key,
        label: s.key === MERGED_SENT_KEY ? MERGED_SENT_LABEL : s.label,
        count: apps.filter(a => keys.includes(a.stage)).length,
      };
    });

  // Median days between stages
  const sentToInterview = [];
  const sentToRejected = [];
  const interviewToOffer = [];
  apps.forEach(a => {
    const sent = firstEventAt(a, 'application_sent') || isoToDate(a.applied_at);
    const iv1 = firstEventAt(a, 'interview_1');
    const iv2 = firstEventAt(a, 'interview_2');
    if (sent && iv1) {
      const d = daysBetween(sent, iv1);
      if (d != null && d >= 0) sentToInterview.push(d);
    }
    if (iv1 && iv2) {
      const d = daysBetween(iv1, iv2);
      if (d != null && d >= 0) interviewToOffer.push(d);
    }
    if (a.stage === 'rejected') {
      const rej = lastEventAt(a, 'rejected');
      if (sent && rej) {
        const d = daysBetween(sent, rej);
        if (d != null && d >= 0) sentToRejected.push(d);
      }
    }
  });

  // Monthly trend (last 6 months, anchored to applied_at, fallback created_at)
  const months = {};
  const now = new Date();
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months[monthKey(d)] = 0;
  }
  apps.forEach(a => {
    const when = isoToDate(a.applied_at) || isoToDate(a.created_at);
    if (!when) return;
    const key = monthKey(when);
    if (key in months) months[key] += 1;
  });

  // Absagen: wann sind sie in 'rejected' gerutscht? Quelle ist der letzte
  // 'rejected'-Eintrag der Stage-Historie, Fallback aufs Bewerbungsdatum.
  const rejections = [];
  apps.filter(a => a.stage === 'rejected').forEach(a => {
    const hits = (a.stage_history || []).filter(h => h.stage === 'rejected');
    const hist = a.stage_history || [];
    // Letzte Absage zählt: eine Bewerbung kann abgesagt, erneut versendet
    // und wieder abgesagt worden sein — dann gilt der jüngste Verlauf.
    let lastIdx = -1;
    hist.forEach((h, i) => { if (h.stage === 'rejected') lastIdx = i; });
    const before = hist
      .slice(0, lastIdx < 0 ? 0 : lastIdx)
      .filter(h => h.stage !== 'rejected');
    const fromKey = before.length ? before[before.length - 1].stage : null;

    const iso = hits.length ? hits[hits.length - 1].at : null;
    const when = lastEventAt(a, 'rejected');
    const sent = firstEventAt(a, 'application_sent') || isoToDate(a.applied_at);
    rejections.push({
      company: a.company,
      position: a.position,
      at: when,
      atIso: iso,
      fromKey,
      days: (when && sent) ? daysBetween(sent, when) : null,
    });
  });
  rejections.sort((x, y) => {
    if (!x.at) return 1;
    if (!y.at) return -1;
    return y.at - x.at;
  });

  // Aus welcher Stufe heraus wurde abgesagt? Gruppiert nach der Stufe, die
  // unmittelbar vor der Absage in der Historie stand.
  const rejectionsByStage = LINEAR_STAGES.map(st => ({
    key: st.key,
    label: st.key === MERGED_SENT_KEY ? MERGED_SENT_LABEL : st.label,
    count: rejections.filter(r => r.fromKey === st.key).length,
  }));
  // Display-Merge: 'Erstellt' fällt mit 'Versendet' in einen Topf.
  const mergedSentIdx = rejectionsByStage.findIndex(x => x.key === MERGED_SENT_KEY);
  const awayIdx = rejectionsByStage.findIndex(x => x.key === MERGED_AWAY_KEY);
  if (mergedSentIdx >= 0 && awayIdx >= 0) {
    rejectionsByStage[mergedSentIdx].count += rejectionsByStage[awayIdx].count;
    rejectionsByStage.splice(awayIdx, 1);
  }
  const rejectionsUnknownStage = rejections.filter(r => !r.fromKey).length;

  // Rates
  const interviewRate = sentCount ? Math.round((interview1 / sentCount) * 100) : null;
  const offerRate     = interview1 ? Math.round((interview2 / interview1) * 100) : null;
  const responsesAfterSent = apps.filter(a => {
    if (a.stage === 'rejected') {
      // counted as response only if sent had been reached
      const top = Math.max(highestReachedIdx(a), 0);
      return top >= LINEAR_STAGES.findIndex(s => s.key === 'application_sent');
    }
    const top = highestReachedIdx(a);
    return top >= LINEAR_STAGES.findIndex(s => s.key === 'interview_1');
  }).length;
  const responseRate = sentCount ? Math.round((responsesAfterSent / sentCount) * 100) : null;

  return {
    total, sentCount, interview1, interview2, interview3,
    rejectedTotal, openCount, inInterview,
    stageDistribution, reached,
    months,
    rejections, rejectionsByStage, rejectionsUnknownStage,
    medSentToInterview: median(sentToInterview),
    medInterviewToFollow: median(interviewToOffer),
    medSentToRejected: median(sentToRejected),
    interviewRate, offerRate, responseRate,
  };
}

function renderStats() {
  const sub  = document.getElementById('statsSub');
  const body = document.getElementById('statsBody');
  if (!body) return;
  if (!applications.length) {
    sub.textContent = 'Noch keine Bewerbungen erfasst.';
    body.innerHTML = '<div class="stats-empty">Sobald du Bewerbungen anlegst oder generierst, erscheinen hier Auswertungen.</div>';
    return;
  }
  const s = computeStats(applications);
  sub.textContent = `${s.total} ${s.total === 1 ? 'Bewerbung' : 'Bewerbungen'} insgesamt · ${s.sentCount} versendet`;

  const fmtPct = v => (v == null ? '–' : `${v} %`);
  const fmtDays = v => (v == null ? '–' : `${v} Tag${v === 1 ? '' : 'e'}`);

  const kpiHtml = `
    <div class="stats-kpi-grid">
      <div class="stats-card accent">
        <span class="stats-card-label">Gesamt</span>
        <span class="stats-card-value">${s.total}</span>
        <span class="stats-card-sub">${s.openCount} aktiv · ${s.rejectedTotal} abgesagt</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-label">Versendet</span>
        <span class="stats-card-value">${s.sentCount}</span>
        <span class="stats-card-sub">${s.total ? Math.round(s.sentCount / s.total * 100) : 0} % der Bewerbungen</span>
      </div>
      <div class="stats-card success">
        <span class="stats-card-label">Im Gespräch</span>
        <span class="stats-card-value">${s.inInterview}</span>
        <span class="stats-card-sub">aktuell aktiv ab 1. Gespräch</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-label">Antwortquote</span>
        <span class="stats-card-value">${fmtPct(s.responseRate)}</span>
        <span class="stats-card-sub">Reaktion auf versendete</span>
      </div>
      <div class="stats-card">
        <span class="stats-card-label">Einladungsquote</span>
        <span class="stats-card-value">${fmtPct(s.interviewRate)}</span>
        <span class="stats-card-sub">Versendet → 1. Gespräch</span>
      </div>
      <div class="stats-card danger">
        <span class="stats-card-label">Absagen</span>
        <span class="stats-card-value">${s.rejectedTotal}</span>
        <span class="stats-card-sub">${s.total ? Math.round(s.rejectedTotal / s.total * 100) : 0} % der Bewerbungen</span>
      </div>
    </div>
  `;

  // Funnel — 'Erstellt' und 'Versendet' teilen sich eine Zeile; sie zeigt die
  // Zahl der erreichten 'Erstellt'-Stufe, weil auch eine nicht versendete
  // Bewerbung die zusammengelegte Stufe erreicht hat.
  const funnelCounts = FUNNEL_STAGES.map(stage => {
    const srcKey = stage.key === MERGED_SENT_KEY ? MERGED_AWAY_KEY : stage.key;
    return s.reached[LINEAR_STAGES.findIndex(x => x.key === srcKey)] || 0;
  });
  const funnelMax = Math.max(...funnelCounts, 1);
  const funnelHtml = FUNNEL_STAGES.map((stage, i) => {
    const count = funnelCounts[i];
    const pctOfTotal = s.total ? Math.round((count / s.total) * 100) : 0;
    const widthPct = (count / funnelMax) * 100;
    return `
      <div class="funnel-row">
        <div class="funnel-meta">
          <span>${esc(stage.label)}</span>
          <span class="funnel-meta-right">${count} · ${pctOfTotal} %</span>
        </div>
        <div class="funnel-bar-track">
          <div class="funnel-bar-fill" style="width:${widthPct}%"></div>
        </div>
      </div>`;
  }).join('');

  // Status donut
  const palette = {
    documents_created: '#9aa7b1',
    application_sent: '#4B5D67',
    interview_1: '#5b8db8',
    interview_2: '#3f7ea6',
    interview_3: '#2e8b57',
    rejected: '#c0392b',
  };
  const totalForDonut = s.stageDistribution.reduce((a, x) => a + x.count, 0);
  let cursor = 0;
  const donutSegments = [];
  s.stageDistribution.forEach(d => {
    if (!d.count || !totalForDonut) return;
    const next = cursor + (d.count / totalForDonut) * 360;
    donutSegments.push(`${palette[d.key]} ${cursor}deg ${next}deg`);
    cursor = next;
  });
  const donutBg = donutSegments.length
    ? `conic-gradient(${donutSegments.join(', ')})`
    : '#eef1f4';
  const legendHtml = s.stageDistribution
    .filter(d => d.count > 0)
    .map(d => {
      const pct = totalForDonut ? Math.round((d.count / totalForDonut) * 100) : 0;
      return `<div class="donut-legend-row">
        <span class="legend-swatch" style="background:${palette[d.key]}"></span>
        <span class="legend-name">${esc(d.label)}</span>
        <span class="legend-count">${d.count} · ${pct} %</span>
      </div>`;
    }).join('') || '<div class="stats-empty" style="padding:1rem">Keine Daten.</div>';

  const donutHtml = `
    <div class="donut-wrap">
      <div class="donut" style="background:${donutBg}">
        <div class="donut-center"><span class="num">${s.total}</span><span class="lbl">Bewerbungen</span></div>
      </div>
      <div class="donut-legend">${legendHtml}</div>
    </div>`;

  // Monthly trend
  const monthEntries = Object.entries(s.months);
  const monthMax = Math.max(1, ...monthEntries.map(([, v]) => v));
  const monthsHtml = monthEntries.map(([k, v]) => {
    const h = Math.max(2, Math.round((v / monthMax) * 130));
    return `
      <div class="month-bar-cell">
        <div class="month-bar" style="height:${h}px">
          ${v ? `<span class="month-bar-count">${v}</span>` : ''}
        </div>
        <div class="month-bar-label">${esc(monthLabel(k)).replace('\n', '<br>')}</div>
      </div>`;
  }).join('');

  // Absagen nach Ausgangsstufe: aus welcher Stufe heraus kam die Absage?
  const rejTotal = s.rejections.length;
  const rejStageMax = Math.max(1, ...s.rejectionsByStage.map(x => x.count));
  const rejStageHtml = s.rejectionsByStage.map(x => {
    const pct = rejTotal ? Math.round((x.count / rejTotal) * 100) : 0;
    const widthPct = (x.count / rejStageMax) * 100;
    const active = rejFilterStage === x.key;
    return `
      <div class="funnel-row rej-clickable${active ? ' active' : ''}"
           onclick="toggleRejFilter('${x.key}')"
           title="${active ? 'Filter aufheben' : 'Nur diese Absagen zeigen'}">
        <div class="funnel-meta">
          <span>${esc(x.label)}${active ? ' <span class="rej-filter-tag">gefiltert ✕</span>' : ''}</span>
          <span class="funnel-meta-right">${x.count} · ${pct} %</span>
        </div>
        <div class="funnel-bar-track">
          <div class="funnel-bar-fill warn" style="width:${widthPct}%"></div>
        </div>
      </div>`;
  }).join('');

  const stageLabelFor = key => {
    if (!key) return 'unbekannt';
    if (key === MERGED_AWAY_KEY) return MERGED_SENT_LABEL;
    const hit = APP_STAGES.find(x => x.key === key);
    return hit ? (key === MERGED_SENT_KEY ? MERGED_SENT_LABEL : hit.label) : key;
  };

  // Der zusammengelegte Balken sammelt beide Keys ein.
  const rejFilterKeys = rejFilterStage === MERGED_SENT_KEY
    ? [MERGED_SENT_KEY, MERGED_AWAY_KEY]
    : (rejFilterStage ? [rejFilterStage] : null);
  const rejVisible = rejFilterKeys
    ? s.rejections.filter(r => rejFilterKeys.includes(r.fromKey))
    : s.rejections;

  const rejFilterBar = rejFilterStage
    ? `<div class="rej-filter-bar">
         <span>Gefiltert: <strong>${esc(stageLabelFor(rejFilterStage))}</strong> · ${rejVisible.length} von ${rejTotal}</span>
         <button type="button" class="rej-filter-reset" onclick="toggleRejFilter(null)">Alle zeigen</button>
       </div>`
    : '';

  const rejListHtml = rejVisible.length
    ? rejVisible.map(r => `
        <div class="rej-row">
          <div style="min-width:0">
            <div class="rej-row-name">${esc(r.company || '—')}</div>
            <div class="rej-row-meta">${esc(r.position || '')}</div>
          </div>
          <div class="rej-row-right">
            <div class="rej-row-date">aus: ${esc(stageLabelFor(r.fromKey))}</div>
            <div class="rej-row-days">${r.atIso ? esc(formatAppDate(r.atIso)) : 'ohne Datum'}</div>
          </div>
        </div>`).join('')
    : `<div class="stats-empty" style="padding:1rem">${
        rejFilterStage ? 'Keine Absagen aus dieser Stufe.' : 'Keine Absagen erfasst.'
      }</div>`;

  const rejectionsHtml = `
    ${rejStageHtml}
    ${rejFilterBar}
    <div class="rej-list" style="margin-top:${rejFilterStage ? '0.5rem' : '1rem'}">${rejListHtml}</div>`;

  // Median time list
  const medianHtml = `
    <div class="median-list">
      <div class="median-row">
        <div>
          <div class="median-row-label">Versendet → 1. Gespräch</div>
          <div class="median-row-meta">Median über alle Bewerbungen mit beiden Events</div>
        </div>
        <div class="median-row-value">${fmtDays(s.medSentToInterview)}</div>
      </div>
      <div class="median-row">
        <div>
          <div class="median-row-label">1. Gespräch → 2. Gespräch</div>
          <div class="median-row-meta">Wie schnell Folgegespräche kommen</div>
        </div>
        <div class="median-row-value">${fmtDays(s.medInterviewToFollow)}</div>
      </div>
      <div class="median-row">
        <div>
          <div class="median-row-label">Versendet → Absage</div>
          <div class="median-row-meta">Reaktionszeit bei negativen Entscheidungen</div>
        </div>
        <div class="median-row-value warn">${fmtDays(s.medSentToRejected)}</div>
      </div>
    </div>`;

  body.innerHTML = `
    ${kpiHtml}
    <div class="stats-grid-2">
      <div class="stats-panel">
        <div class="stats-panel-title">Bewerbungs-Funnel</div>
        <div class="stats-panel-sub">Wie viele Bewerbungen erreichen welche Stufe (jeweils kumuliert).</div>
        ${funnelHtml}
      </div>
      <div class="stats-panel">
        <div class="stats-panel-title">Status-Verteilung</div>
        <div class="stats-panel-sub">Aktueller Stand aller Bewerbungen.</div>
        ${donutHtml}
      </div>
    </div>
    <div class="stats-grid-2">
      <div class="stats-panel">
        <div class="stats-panel-title">Bewerbungen pro Monat</div>
        <div class="stats-panel-sub">Basierend auf Bewerbungsdatum (Fallback: Erstellungsdatum) — letzte 6 Monate.</div>
        <div class="month-bars">${monthsHtml}</div>
      </div>
      <div class="stats-panel">
        <div class="stats-panel-title">Reaktionszeiten</div>
        <div class="stats-panel-sub">Median in Tagen zwischen den Stufen.</div>
        ${medianHtml}
      </div>
    </div>
    <div class="stats-panel" style="margin-top:1rem">
      <div class="stats-panel-title">Absagen nach Ausgangsstufe</div>
      <div class="stats-panel-sub">
        Aus welcher Stufe heraus die Absage kam — also wie weit die Bewerbung vor dem „Abgesagt“ gekommen war.${
          s.rejectionsUnknownStage ? ` ${s.rejectionsUnknownStage} ohne erkennbare Vorstufe.` : ''
        }
      </div>
      ${rejectionsHtml}
    </div>
  `;
}

// Klick auf einen Balken im Absagen-Panel: gleiche Stufe erneut = Filter aus.
function toggleRejFilter(key) {
  rejFilterStage = (key && rejFilterStage !== key) ? key : null;
  renderStats();
}

function getFilteredSortedApplications() {
  const stageFilter = (document.getElementById('appsFilterStage') || {}).value || '';
  const sortKey = (document.getElementById('appsFilterSort') || {}).value || 'updated_desc';
  const search = ((document.getElementById('appsFilterSearch') || {}).value || '').trim().toLowerCase();
  let list = applications.slice();
  if (stageFilter) {
    list = list.filter(a => a.stage === stageFilter);
  }
  if (search) {
    list = list.filter(a =>
      (a.company  || '').toLowerCase().includes(search) ||
      (a.position || '').toLowerCase().includes(search)
    );
  }
  const cmpStr = (a, b) => (a || '').localeCompare(b || '', 'de');
  const noDate = '\uffff';
  list.sort((a, b) => {
    if (sortKey === 'applied_desc') {
      return cmpStr(b.applied_at || noDate, a.applied_at || noDate);
    }
    if (sortKey === 'applied_asc') {
      const av = a.applied_at || noDate;
      const bv = b.applied_at || noDate;
      if (av === noDate && bv !== noDate) return 1;
      if (bv === noDate && av !== noDate) return -1;
      return cmpStr(av, bv);
    }
    if (sortKey === 'company_asc') {
      const ac = (a.company || '') + (a.position || '');
      const bc = (b.company || '') + (b.position || '');
      return cmpStr(ac, bc);
    }
    return cmpStr(b.updated_at || '', a.updated_at || '');
  });
  return list;
}

function renderJobPostingBlock(app) {
  const raw = (app.job_posting || '').trim();
  if (!raw) return '';
  const { preview, hasMore } = jobPostingPreview(raw, 3);
  const full = prettyJobPostingText(raw);
  const suffix = hasMore ? ' …' : '';
  return `
    <details class="job-posting-details">
      <summary>
        <span class="job-posting-label">Stellenausschreibung</span>
        <span class="job-posting-preview">${esc(preview)}${suffix}</span>
      </summary>
      <div class="job-posting-full">${esc(full)}</div>
    </details>`;
}

function stageIndex(stageKey) {
  const idx = APP_STAGES.findIndex(s => s.key === stageKey);
  return idx < 0 ? 0 : idx;
}

function renderApplications() {
  initAppsFilterControls();
  const list = document.getElementById('applicationsList');
  const sub  = document.getElementById('appsSub');
  const countEl = document.getElementById('appsFilterCount');
  const total = applications.length;
  sub.textContent = total
    ? `${total} ${total === 1 ? 'Bewerbung' : 'Bewerbungen'} insgesamt`
    : 'Noch keine Bewerbungen erfasst.';
  if (!total) {
    if (countEl) countEl.textContent = '';
    list.innerHTML = '<div class="apps-empty">Klicke auf <strong>Generieren</strong>, um eine Bewerbung automatisch anzulegen, oder füge eine bereits versendete Bewerbung manuell hinzu.</div>';
    return;
  }
  const filtered = getFilteredSortedApplications();
  if (countEl) {
    countEl.textContent = filtered.length === total
      ? `${filtered.length} angezeigt`
      : `${filtered.length} von ${total}`;
  }
  if (!filtered.length) {
    list.innerHTML = '<div class="apps-empty">Keine Bewerbungen für diesen Filter.</div>';
    return;
  }
  list.innerHTML = filtered.map(renderApplicationCard).join('');
}

function durationInCurrentStage(app) {
  const hist = app.stage_history || [];
  if (!hist.length) return '';
  const last = hist[hist.length - 1];
  const from = new Date(last.at);
  if (isNaN(from.getTime())) return '';
  const days = Math.floor((Date.now() - from.getTime()) / 86_400_000);
  if (days <= 0)  return 'seit heute';
  if (days === 1) return 'seit 1 Tag';
  return `seit ${days} Tagen`;
}

function formatResearchDuration(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  if (s < 60)    return '< 1 min investiert';
  const m = Math.round(s / 60);
  if (m < 60)    return `${m} min investiert`;
  const h    = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `${h}h ${rest} min investiert` : `${h}h investiert`;
}

function stageLabel(key) {
  const s = APP_STAGES.find(x => x.key === key);
  return s ? s.label : key;
}

function renderCvSnapshot(app) {
  const cv = app.cv_content;
  if (!cv) return '';

  const profileHtml = cv.profile
    ? `<p class="cv-snap-profile">${esc(cv.profile)}</p>`
    : '';

  const expHtml = (cv.experience || []).map(e => {
    const entry = (profile.experience || []).find(x => x.id === e.id) || {};
    const company = entry.company ? ' @ ' + esc(entry.company) : '';
    const bullets = (e.bullets || []).map(b => `<li>${esc(b)}</li>`).join('');
    return `<div class="cv-snap-exp"><strong>${esc(e.title || entry.title || '')}</strong>${company}${bullets ? `<ul>${bullets}</ul>` : ''}</div>`;
  }).join('');

  const eduHtml = (cv.education || []).map(e => {
    const entry = (profile.education || []).find(x => x.id === e.id) || {};
    const inst = entry.institution ? ' — ' + esc(entry.institution) : '';
    return `<li>${esc(e.degree || entry.degree || '')}${inst}</li>`;
  }).join('');

  const projsHtml = (cv.projects || []).map(p => {
    const proj = projects.find(x => x.id === p.id);
    const linkHtml = proj && proj.link
      ? ` (<a href="${esc(proj.link)}" target="_blank" rel="noopener noreferrer">${esc(proj.link.replace(/^https?:\/\//, '').replace(/\/$/, ''))}</a>)`
      : '';
    return `<li><strong>${esc(p.title || '')}</strong>${p.description ? ': ' + esc(p.description) : ''}${linkHtml}</li>`;
  }).join('');

  const skillsHtml = Object.entries(cv.skills || {}).map(([cat, val]) =>
    `<div class="cv-snap-skill"><strong>${esc(cat)}:</strong> ${esc(val)}</div>`
  ).join('');

  const langLabel = app.language === 'en' ? 'EN' : 'DE';
  const layoutLabel = app.layout_used ? esc(app.layout_used) : '–';

  const section = (title, body) => body
    ? `<div class="cv-snap-section"><div class="cv-snap-title">${title}</div>${body}</div>`
    : '';

  return `
    <details class="cv-snap-details">
      <summary>📄 Erstellte CV-Inhalte anzeigen <span class="cv-snap-meta">Layout: ${layoutLabel} · ${langLabel}</span></summary>
      <div class="cv-snap">
        ${section('Profil-Statement', profileHtml)}
        ${section('Berufserfahrung (ausgewählt + zugeschnitten)', expHtml)}
        ${section('Ausbildung', eduHtml ? `<ul>${eduHtml}</ul>` : '')}
        ${section('Projekte (ausgewählt + zugeschnitten)', projsHtml ? `<ul>${projsHtml}</ul>` : '')}
        ${section('Skills', skillsHtml)}
      </div>
    </details>
  `;
}

function renderAnschreibenSnapshot(app) {
  const an = app.anschreiben_content;
  if (!an) return '';
  const subject  = an.subject  ? `<p class="cv-snap-subject">${esc(an.subject)}</p>` : '';
  const greeting = an.greeting ? `<p>${esc(an.greeting)}</p>` : '';
  const paras = (an.paragraphs || []).map(p => `<p>${esc(p)}</p>`).join('');
  if (!subject && !greeting && !paras) return '';
  return `
    <details class="cv-snap-details">
      <summary>✉️ Anschreiben-Text anzeigen</summary>
      <div class="cv-snap">
        ${subject}${greeting}${paras}
      </div>
    </details>
  `;
}

function renderApplicationCard(app) {
  const isRejected = app.stage === 'rejected';

  // For rejected entries, determine the last progress stage reached
  // (everything up to and including it is "completed"; nothing is "current").
  let currentLinearIdx = LINEAR_STAGES.findIndex(s => s.key === app.stage);
  if (isRejected) {
    const hist = app.stage_history || [];
    const lastProgress = [...hist].reverse().find(h => h.stage !== 'rejected');
    currentLinearIdx = lastProgress
      ? LINEAR_STAGES.findIndex(s => s.key === lastProgress.stage)
      : -1;
  }

  const stepsHtml = LINEAR_STAGES.map((s, i) => {
    let state = '';
    if (isRejected) {
      state = i <= currentLinearIdx ? 'completed' : '';
    } else {
      state = i < currentLinearIdx ? 'completed' : (i === currentLinearIdx ? 'current' : '');
    }
    const lineState = (i < currentLinearIdx) ? 'completed' : '';
    const line = i < LINEAR_STAGES.length - 1
      ? `<div class="step-line ${lineState}"></div>`
      : '';
    return `
      <div class="step ${state}" onclick="setApplicationStage('${app.id}', '${s.key}')" title="${esc(s.label)}">
        <div class="step-circle">${i + 1}</div>
        <div class="step-label">${esc(s.label)}</div>
      </div>${line}
    `;
  }).join('');

  const title = esc(app.company || '(kein Unternehmen)');
  const pos   = app.position ? `<span class="app-card-pos">— ${esc(app.position)}</span>` : '';
  const jobUrl = (app.job_url || '').trim();
  const jobLink = jobUrl
    ? ` <a class="app-job-link" href="${esc(jobUrl)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">↗ Ausschreibung</a>`
    : '';
  const applied = app.applied_at
    ? `<span class="app-meta-pill">📨 Bewerbung: ${formatAppDate(app.applied_at)}</span>`
    : '';
  const researchPill = (app.research_seconds && app.research_seconds > 0)
    ? `<span class="app-meta-pill">⏱ ${esc(formatResearchDuration(app.research_seconds))}</span>`
    : '';

  let statusPill;
  if (isRejected) {
    const rejectedAt = (app.stage_history || []).slice().reverse().find(h => h.stage === 'rejected');
    const when = rejectedAt ? formatAppDate(rejectedAt.at) : '';
    statusPill = `<span class="app-meta-pill rejected">❌ Abgesagt${when ? ' am ' + when : ''}</span>`;
  } else {
    const duration = durationInCurrentStage(app);
    statusPill = duration
      ? `<span class="app-meta-pill">⏱ ${esc(duration)} in „${esc(stageLabel(app.stage))}"</span>`
      : '';
  }

  const rejectAction = isRejected
    ? `<button class="action-btn" onclick="reactivateApplication('${app.id}')">↺ Reaktivieren</button>`
    : `<button class="action-btn reject" onclick="rejectApplication('${app.id}')">❌ Als abgesagt markieren</button>`;

  return `
    <div class="app-card ${isRejected ? 'rejected' : ''}" data-id="${app.id}">
      <div class="app-card-header">
        <div class="app-card-title">${title} ${pos}${jobLink}</div>
        <div class="app-card-date">${formatAppDate(app.updated_at)}</div>
      </div>
      <div class="app-meta">${applied}${researchPill}${statusPill}</div>
      ${renderJobPostingBlock(app)}
      <div class="stepper">${stepsHtml}</div>
      ${renderCvSnapshot(app)}
      ${renderAnschreibenSnapshot(app)}
      <textarea class="app-feedback" id="appFb-${app.id}" placeholder="Feedback / Notizen…">${esc(app.feedback || '')}</textarea>
      <div class="app-actions">
        <span class="feedback-saved" id="appFbSaved-${app.id}">✓ gespeichert</span>
        <button class="action-btn primary" onclick="saveApplicationFeedback('${app.id}')">Feedback speichern</button>
        ${rejectAction}
        <button class="action-btn" onclick="openApplicationModal('${app.id}')">Bearbeiten</button>
        <button class="action-btn danger" onclick="deleteApplication('${app.id}')">Löschen</button>
      </div>
    </div>
  `;
}

async function rejectApplication(id) {
  await setApplicationStage(id, 'rejected');
}

async function reactivateApplication(id) {
  const app = applications.find(a => a.id === id);
  if (!app) return;
  // Restore to last non-rejected stage from history, or default to documents_created
  const hist = app.stage_history || [];
  const lastProgress = [...hist].reverse().find(h => h.stage !== 'rejected');
  const restoreTo = lastProgress ? lastProgress.stage : 'documents_created';
  await setApplicationStage(id, restoreTo);
}

async function setApplicationStage(id, stage) {
  const res = await fetch('/applications/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ stage })
  });
  if (!res.ok) return;
  const updated = await res.json();
  const i = applications.findIndex(a => a.id === id);
  if (i >= 0) applications[i] = updated;
  renderApplications();
}

async function saveApplicationFeedback(id) {
  const ta = document.getElementById('appFb-' + id);
  if (!ta) return;
  const res = await fetch('/applications/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback: ta.value })
  });
  if (!res.ok) return;
  const updated = await res.json();
  const i = applications.findIndex(a => a.id === id);
  if (i >= 0) applications[i] = updated;
  const flash = document.getElementById('appFbSaved-' + id);
  if (flash) {
    flash.classList.add('show');
    setTimeout(() => flash.classList.remove('show'), 1500);
  }
}

async function deleteApplication(id) {
  if (!confirm('Bewerbung wirklich löschen?')) return;
  const res = await fetch('/applications/' + id, { method: 'DELETE' });
  if (!res.ok) return;
  applications = applications.filter(a => a.id !== id);
  initAppsFilterControls();
  updateAppsCount();
  renderApplications();
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function stageIsSentOrLater(stage) {
  return APP_STAGES.findIndex(s => s.key === stage)
       >= APP_STAGES.findIndex(s => s.key === 'application_sent');
}

function onAppModalStageChange() {
  const stage = document.getElementById('appModalStage').value;
  const dateEl = document.getElementById('appModalAppliedAt');
  if (stageIsSentOrLater(stage) && !dateEl.value) {
    dateEl.value = todayIso();
  }
  if (stage === 'rejected') {
    const rej = document.getElementById('appModalRejectedAt');
    if (rej && !rej.value) rej.value = todayIso();
  }
  syncAppModalRejectedVisibility();
}

let appModalPdfCvContent = null; // staged cv_content from PDF parse, sent on save

function openApplicationModal(id) {
  const isEdit = !!id;
  document.getElementById('appModalTitle').textContent = isEdit ? 'Bewerbung bearbeiten' : 'Bewerbung hinzufügen';
  document.getElementById('appModalId').value = id || '';
  if (isEdit) {
    const a = applications.find(x => x.id === id) || {};
    document.getElementById('appModalCompany').value   = a.company    || '';
    document.getElementById('appModalPosition').value  = a.position   || '';
    document.getElementById('appModalStage').value     = a.stage      || 'documents_created';
    document.getElementById('appModalFeedback').value  = a.feedback   || '';
    document.getElementById('appModalAppliedAt').value = a.applied_at || '';
    const urlEl = document.getElementById('appModalJobUrl');
    const postEl = document.getElementById('appModalJobPosting');
    if (urlEl) urlEl.value = a.job_url || '';
    if (postEl) postEl.value = a.job_posting || '';
    const rejEl = document.getElementById('appModalRejectedAt');
    if (rejEl) {
      rejEl.value = a.stage === 'rejected'
        ? (getRejectedDateForInput(a) || todayIso())
        : '';
    }
    syncAppModalRejectedVisibility();
  } else {
    document.getElementById('appModalCompany').value   = '';
    document.getElementById('appModalPosition').value  = '';
    document.getElementById('appModalStage').value     = 'application_sent';
    document.getElementById('appModalFeedback').value  = '';
    document.getElementById('appModalAppliedAt').value = todayIso();
    const rejEl = document.getElementById('appModalRejectedAt');
    if (rejEl) rejEl.value = '';
    const urlEl = document.getElementById('appModalJobUrl');
    const postEl = document.getElementById('appModalJobPosting');
    if (urlEl) urlEl.value = '';
    if (postEl) postEl.value = '';
    syncAppModalRejectedVisibility();
  }
  clearPdfSelection();
  // Editing existing apps doesn't re-upload PDFs for now — hide the drop zone
  document.getElementById('appModalPdfDrop').parentElement.style.display = isEdit ? 'none' : '';
  document.getElementById('appModalOverlay').classList.add('open');
}

function clearPdfSelection() {
  appModalPdfCvContent = null;
  const fileInput = document.getElementById('appModalPdfFile');
  if (fileInput) fileInput.value = '';
  document.getElementById('appModalPdfIdle').style.display     = 'flex';
  document.getElementById('appModalPdfLoading').style.display  = 'none';
  document.getElementById('appModalPdfResult').style.display   = 'none';
  document.getElementById('appModalPdfError').style.display    = 'none';
}

function showPdfError(msg) {
  const el = document.getElementById('appModalPdfError');
  el.textContent = msg;
  el.style.display = 'block';
  document.getElementById('appModalPdfLoading').style.display = 'none';
}

async function onPdfPicked(ev) {
  const file = ev.target.files && ev.target.files[0];
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    showPdfError('Bitte eine PDF-Datei wählen.');
    return;
  }
  document.getElementById('appModalPdfIdle').style.display     = 'none';
  document.getElementById('appModalPdfError').style.display    = 'none';
  document.getElementById('appModalPdfResult').style.display   = 'none';
  document.getElementById('appModalPdfLoading').style.display  = 'flex';

  const form = new FormData();
  form.append('file', file);
  try {
    const res  = await fetch('/parse-cv-pdf', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) { showPdfError(data.error || 'PDF konnte nicht verarbeitet werden.'); return; }
    appModalPdfCvContent = data.cv_content;
    const s = data.summary || {};
    document.getElementById('appModalPdfFileName').textContent = file.name;
    document.getElementById('appModalPdfSummary').textContent =
      `${s.experience_count || 0} Erfahrungen · ${s.education_count || 0} Ausbildungen · `
      + `${s.project_count || 0} Projekte · ${s.skill_count || 0} Skills extrahiert`;
    document.getElementById('appModalPdfLoading').style.display = 'none';
    document.getElementById('appModalPdfResult').style.display  = 'block';
  } catch (e) {
    showPdfError('Verbindungsfehler: ' + e.message);
  }
}

// Drag-and-drop onto the drop zone
(function wirePdfDnD() {
  const drop = document.getElementById('appModalPdfDrop');
  if (!drop) return;
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => {
    e.preventDefault(); drop.classList.add('dragover');
  }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => {
    e.preventDefault(); drop.classList.remove('dragover');
  }));
  drop.addEventListener('drop', e => {
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!file) return;
    const input = document.getElementById('appModalPdfFile');
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    onPdfPicked({ target: input });
  });
})();

function closeApplicationModal() {
  document.getElementById('appModalOverlay').classList.remove('open');
}

function closeAppModalOnBackdrop(e) {
  if (e.target.id === 'appModalOverlay') closeApplicationModal();
}

async function saveApplicationFromModal() {
  const id       = document.getElementById('appModalId').value;
  const company  = document.getElementById('appModalCompany').value.trim();
  const position = document.getElementById('appModalPosition').value.trim();
  if (!company && !position) {
    alert('Bitte Unternehmen oder Position angeben.');
    return;
  }
  const payload = {
    company,
    position,
    stage:      document.getElementById('appModalStage').value,
    feedback:   document.getElementById('appModalFeedback').value,
    applied_at: document.getElementById('appModalAppliedAt').value || null,
    job_url:    (document.getElementById('appModalJobUrl') || {}).value.trim(),
    job_posting:(document.getElementById('appModalJobPosting') || {}).value.trim(),
  };
  const st = payload.stage;
  if (st === 'rejected') {
    const rej = document.getElementById('appModalRejectedAt');
    if (rej && rej.value) payload.rejected_at = rej.value;
  }
  const url    = id ? '/applications/' + id : '/applications';
  const method = id ? 'PUT' : 'POST';
  const res    = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (!res.ok) { alert(data.error || 'Speichern fehlgeschlagen.'); return; }
  if (id) {
    const i = applications.findIndex(a => a.id === id);
    if (i >= 0) applications[i] = data;
  } else {
    applications.push(data);
  }
  closeApplicationModal();
  updateAppsCount();
  renderApplications();
}
