// Small formatting/escaping helpers used across the views.

function timeAgo(iso) {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (!isFinite(then)) return '';
  const sec = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (sec <  60)    return `vor ${sec}s`;
  if (sec <  3600)  return `vor ${Math.round(sec/60)}min`;
  if (sec <  86400) return `vor ${Math.round(sec/3600)}h`;
  return `vor ${Math.round(sec/86400)}d`;
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return url; }
}

function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
