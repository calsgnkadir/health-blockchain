/* kvkk.js — KVKK screens
 *
 * Client: the privacy notice with explicit consent (asked once per notice
 * version, before the app can be used), "My Data" to download a copy of their
 * file and to request erasure.
 * Operators (admin, KVKK officer): the erasure requests, carried out with the
 * dual-control-gated crypto-shred, and the security alerts.
 */
import { API, apiFetch, escapeHtml, emptyState, getCurrentUser } from './utils.js';

function day(iso) {
  return iso ? new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }) : '—';
}

function showMessage(id, message) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = message;
  el.style.display = message ? 'block' : 'none';
}

/* -- Privacy notice gate (client) ------------------------------------- */

// Who accepted in this page. A check that was already in flight when the
// client accepted must not reopen the notice when its answer arrives late.
let acceptedBy = null;

// Called after a client signs in: if the current notice has not been
// accepted yet, the app stays behind the notice until it is.
export async function checkPrivacyNotice() {
  const user = getCurrentUser() || {};
  if (user.role !== 'client') return;
  try {
    const n = await apiFetch('/api/kvkk/notice');
    if (n.accepted_at || acceptedBy === user.username) return;
    document.getElementById('kvkk-notice-text').textContent = n.text;
    document.getElementById('kvkk-notice-version').textContent = n.version;
    document.getElementById('kvkk-consent-check').checked = false;
    document.getElementById('kvkk-notice-overlay').hidden = false;
  } catch (e) {
    console.error('Could not load the privacy notice:', e);
  }
}

export async function acceptPrivacyNotice() {
  if (!document.getElementById('kvkk-consent-check').checked) {
    showMessage('kvkk-notice-error', 'Tick the box to give your explicit consent.');
    return;
  }
  try {
    await apiFetch('/api/kvkk/notice/accept', { method: 'POST' });
    acceptedBy = (getCurrentUser() || {}).username;
    document.getElementById('kvkk-notice-overlay').hidden = true;
  } catch (e) {
    showMessage('kvkk-notice-error', e.message);
  }
}

/* -- My Data (client) ------------------------------------------------- */

export async function loadMyData() {
  showMessage('mydata-error', '');
  showMessage('mydata-success', '');
  try {
    const n = await apiFetch('/api/kvkk/notice');
    const notice = document.getElementById('mydata-notice');
    notice.textContent = n.accepted_at ? `Privacy notice ${n.version} accepted on ${day(n.accepted_at)}.` : `Privacy notice ${n.version} not accepted yet.`;
    const d = await apiFetch('/api/kvkk/erasure-requests');
    const list = document.getElementById('mydata-requests');
    list.innerHTML = d.requests.length
      ? d.requests.map(r => `
          <div class="appt-mini"><strong>Erasure request · ${escapeHtml(r.status)}</strong>
          <span>${escapeHtml(day(r.requested_at))}</span></div>`).join('')
      : '<div class="appt-muted">No erasure request.</div>';
    document.getElementById('mydata-erase-btn').disabled = d.requests.some(r => r.status === 'open');
  } catch (e) {
    showMessage('mydata-error', e.message);
  }
}

// The export is a file: fetched with the session cookie and saved from a blob.
export async function downloadMyData() {
  showMessage('mydata-error', '');
  try {
    const res = await fetch(API + '/api/v1/kvkk/export', { credentials: 'same-origin' });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Export failed');
    const blob = await res.blob();
    const match = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = match ? match[1] : 'mahrem-export.json';
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (e) {
    showMessage('mydata-error', e.message);
  }
}

export async function requestErasure() {
  if (!confirm('Ask the practice to erase your data? Your practitioner may have a legal duty to keep some records; the practice will tell you.')) return;
  try {
    await apiFetch('/api/kvkk/erasure-requests', { method: 'POST' });
    await loadMyData();   // clears old messages, so the new one comes after
    showMessage('mydata-success', 'Your erasure request has been sent to the practice.');
  } catch (e) {
    showMessage('mydata-error', e.message);
  }
}

/* -- Erasure requests (operators) ------------------------------------- */

export async function loadErasureRequests() {
  const list = document.getElementById('erasure-requests-list');
  if (!list) return;
  showMessage('erasure-error', '');
  list.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch('/api/kvkk/erasure-requests');
    list.innerHTML = d.requests.length ? d.requests.map(r => {
      const id = escapeHtml(r.id);
      const pid = escapeHtml(r.patient_id);
      const actions = r.status === 'open' ? `
        <button type="button" class="btn btn-error btn-sm" data-action="kvkk-erase" data-arg="${pid}">Erase (dual control)</button>
        <button type="button" class="btn btn-ghost btn-sm" data-action="kvkk-close" data-arg="${id}" data-arg2="done">Mark done</button>
        <button type="button" class="btn btn-ghost btn-sm" data-action="kvkk-close" data-arg="${id}" data-arg2="rejected">Reject</button>` : '';
      return `
        <div class="record-card appt-row" style="cursor:default">
          <div class="record-main">
            <div class="record-title">${pid} · ${escapeHtml(r.status)}</div>
            <div class="record-meta">Requested ${escapeHtml(day(r.requested_at))} by ${escapeHtml(r.requested_by)}${r.handled_by ? ` · closed by ${escapeHtml(r.handled_by)}` : ''}</div>
          </div>
          <div class="appt-actions">${actions}</div>
        </div>`;
    }).join('') : emptyState('No erasure requests.');
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

export async function eraseClient(patientId) {
  if (!confirm(`Crypto-shred ${patientId}? This destroys the client's key: their records become unreadable for good. It needs an active dual-control token for this client.`)) return;
  try {
    await apiFetch(`/api/erasure/${encodeURIComponent(patientId)}`, { method: 'POST' });
    loadErasureRequests();
  } catch (e) {
    showMessage('erasure-error', e.message);
  }
}

export async function closeErasureRequest(requestId, status) {
  try {
    await apiFetch(`/api/kvkk/erasure-requests/${encodeURIComponent(requestId)}/${encodeURIComponent(status)}`,
                   { method: 'POST' });
    loadErasureRequests();
  } catch (e) {
    showMessage('erasure-error', e.message);
  }
}

/* -- Security alerts (operators) -------------------------------------- */

const SEVERITY = { CRITICAL: 'badge-encrypted', HIGH: 'badge-encrypted', MEDIUM: 'badge-private', LOW: 'badge-shared' };

export async function loadSecurityAlerts() {
  const list = document.getElementById('alerts-list');
  if (!list) return;
  list.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch('/api/security/alerts?limit=100');
    list.innerHTML = d.alerts.length ? d.alerts.map(a => `
      <div class="record-card appt-row" style="cursor:default">
        <div class="record-main">
          <div class="record-title">${escapeHtml(a.title)}</div>
          <div class="record-meta">${escapeHtml(a.description || '')}</div>
          <div class="record-meta appt-muted">${escapeHtml(a.username || '—')} · ${escapeHtml(a.client_ip || '—')} · ${escapeHtml(day(new Date(Number(a.created_at) * 1000).toISOString()))}</div>
        </div>
        <span class="badge ${SEVERITY[a.severity] || ''}">${escapeHtml(a.severity)}</span>
        <div class="appt-actions">${a.acknowledged
          ? '<span class="appt-muted">Acknowledged</span>'
          : `<button type="button" class="btn btn-ghost btn-sm" data-action="ack-alert" data-arg="${escapeHtml(a.alert_id)}">Acknowledge</button>`}</div>
      </div>`).join('') : emptyState('No security alerts.');
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

export async function acknowledgeAlert(alertId) {
  try {
    await apiFetch(`/api/security/alerts/acknowledge/${encodeURIComponent(alertId)}`, { method: 'POST' });
    loadSecurityAlerts();
  } catch (e) {
    alert('Could not acknowledge: ' + e.message);
  }
}
