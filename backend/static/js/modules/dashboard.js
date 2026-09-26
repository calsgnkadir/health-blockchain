/* dashboard.js — Mahrem UI Dashboard Module */
import { apiFetch, patientId, formatTs, emptyState, escapeHtml, appState, getCurrentUser, roleText } from './utils.js';
import { addNotification, getNotifications } from './notifications.js';
import { recordTypes } from './records.js';
import { loadUpcomingAppointments } from './appointments.js';

let activityChartInstance = null;
let outcomeChartInstance = null;

/* -- Practitioner: client list --------------------------------------- */

const CLIENT_STATUS = {
  consented:           null,   // shown as the consent summary instead
  waiting_for_consent: 'Joined — waiting for consent',
  invited:             'Invitation not used yet',
};

function consentSummary(c) {
  const labels = c.consent_types.map(t =>
    t === 'all' ? 'All records' : ((recordTypes.find(rt => rt.value === t) || {}).label || t));
  return `${labels.join(', ')} · until ${formatTs(c.consent_expires_at)}`;  // xss-reviewed: plain text, escaped by the caller
}

function renderClientCard(c, selectedId) {
  const pid = escapeHtml(c.patient_id);
  const selected = c.patient_id === selectedId;
  const line = c.status === 'consented' ? consentSummary(c) : (CLIENT_STATUS[c.status] || c.status);
  // Only a client who gave consent can be opened; the others would answer 403.
  const button = c.status === 'consented'
    ? `<button type="button" class="btn ${selected ? 'btn-gold' : 'btn-ghost'} btn-sm" data-action="open-client" data-arg="${pid}" data-arg2="dashboard">${selected ? 'Selected' : 'Select'}</button>`
    : '';
  return `
    <div class="user-card glass" style="${selected ? 'border-color:var(--gold);' : ''}">
      <div class="user-avatar" style="background:linear-gradient(135deg,#C9A84C,#8B6914)">${escapeHtml(c.full_name.charAt(0))}</div>
      <div style="flex:1">
        <div style="font-weight:600">${escapeHtml(c.full_name)} <span style="font-size:12px;color:var(--muted);font-weight:400">${pid}</span></div>
        <div style="font-size:12px;color:var(--muted)">${escapeHtml(line)}</div>
      </div>
      ${button}
    </div>`;
}

// Renders the practitioner's clients and returns them ([] on error).
async function loadPractitionerClients(selectedId) {
  const list = document.getElementById('dashboard-clients');
  if (!list) return [];
  try {
    const d = await apiFetch('/api/practitioner/clients');
    list.innerHTML = d.clients.length
      ? d.clients.map(c => renderClientCard(c, selectedId)).join('')
      : emptyState('No clients yet. Invite a client, or ask a client to give you consent.');
    return d.clients;
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
    return [];
  }
}

/* -- Outcome measures (GAD-7, PHQ-9, ...) ---------------------------- */

// Scores from assessment records, grouped by instrument, oldest first.
export function outcomeSeries(records) {
  const byInstrument = {};
  records
    .filter(r => r.record_type === 'assessment' && r.data && r.data.instrument && r.record_date)
    .forEach(r => {
      const score = Number(r.data.score);
      const max = Number(r.data.max_score);
      if (!Number.isFinite(score)) return;
      const name = String(r.data.instrument);
      if (!byInstrument[name]) byInstrument[name] = { max: 0, points: [] };
      if (Number.isFinite(max)) byInstrument[name].max = Math.max(byInstrument[name].max, max);
      byInstrument[name].points.push({ date: r.record_date, score });
    });
  Object.values(byInstrument).forEach(s => s.points.sort((a, b) => a.date.localeCompare(b.date)));
  return byInstrument;
}

const LINE_COLORS = ['#C9A84C', '#0ABFBC', '#E57373', '#81C784'];

export function renderOutcomeChart(records) {
  const panel = document.getElementById('outcome-chart-panel');
  if (!panel) return;
  const series = outcomeSeries(records);
  const names = Object.keys(series);
  panel.hidden = names.length === 0;
  if (outcomeChartInstance) { outcomeChartInstance.destroy(); outcomeChartInstance = null; }
  if (!names.length || typeof Chart === 'undefined') return;

  // One line per instrument: first score → latest score.
  document.getElementById('outcome-summary').textContent = names.map(name => {
    const pts = series[name].points;
    const first = pts[0].score;
    const last = pts[pts.length - 1].score;
    const change = last - first;
    return pts.length > 1
      ? `${name}: ${first} → ${last} (${change > 0 ? '+' : ''}${change})`
      : `${name}: ${last}`;
  }).join(' · ');

  const dates = [...new Set(names.flatMap(n => series[n].points.map(p => p.date)))].sort();
  outcomeChartInstance = new Chart(document.getElementById('outcomeChart').getContext('2d'), {
    type: 'line',
    data: {
      labels: dates.map(d => new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })),
      datasets: names.map((name, i) => ({
        label: name,
        data: dates.map(d => {
          const p = series[name].points.find(pt => pt.date === d);
          return p ? p.score : null;
        }),
        spanGaps: true,
        borderColor: LINE_COLORS[i % LINE_COLORS.length],
        backgroundColor: LINE_COLORS[i % LINE_COLORS.length],
        tension: 0.25,
        pointRadius: 4,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892A4', font: { family: 'Inter', size: 11 } } } },
      scales: {
        x: { grid: { color: 'rgba(255, 255, 255, 0.03)' }, ticks: { color: '#8892A4', font: { size: 10 } } },
        y: {
          min: 0,
          suggestedMax: Math.max(...names.map(n => series[n].max)) || undefined,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#8892A4', font: { size: 10 } },
        },
      },
    },
  });
}

export function updateChainPill(valid) {
  appState.updateChain(valid);
}

export function renderActivityChart(records) {
  const canvas = document.getElementById('activityChart');
  if (!canvas) return;

  if (typeof Chart === 'undefined') return;

  const days = 7;
  const labels = [];
  const commitCounts = [];

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];
    labels.push(d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }));

    // Only real ledger activity is plotted. A tamper-evidence dashboard that pads
    // quiet days with invented numbers is worse than an empty one.
    const dayRecords = records.filter(r => {
      const recDate = r.timestamp_iso ? r.timestamp_iso.split('T')[0] : new Date(r.timestamp * 1000).toISOString().split('T')[0];
      return recDate === dateStr;
    });
    commitCounts.push(dayRecords.length);
  }

  if (activityChartInstance) {
    activityChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');
  activityChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Block Commits',
          data: commitCounts,
          backgroundColor: 'rgba(10, 191, 188, 0.65)',
          borderColor: '#0ABFBC',
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: '#8892A4',
            font: { family: 'Inter', size: 11 }
          }
        }
      },
      scales: {
        x: {
          stacked: true,
          grid: { color: 'rgba(255, 255, 255, 0.03)' },
          ticks: { color: '#8892A4', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          stacked: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#8892A4', font: { family: 'JetBrains Mono', size: 10 }, stepSize: 1 },
          min: 0
        }
      }
    }
  });
}

export async function loadDashboard() {
  let pid = patientId();
  const role = (getCurrentUser() || {}).role;
  const isPractitioner = role === 'practitioner';

  // Clear first: on a failed or blocked load the panel must not keep showing the
  // previous session's figures as if they belonged to the current user.
  ['stat-total-blocks', 'stat-total-records', 'stat-encrypted'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });
  const outcomePanel = document.getElementById('outcome-chart-panel');
  if (outcomePanel) outcomePanel.hidden = true;
  const heading = document.getElementById('dashboard-client-heading');
  if (heading) heading.hidden = true;

  // A practitioner works from their client list, not from a typed client ID.
  // The ledger activity chart is for operators; a practitioner gets progress.
  const clientsPanel = document.getElementById('practitioner-clients-panel');
  if (clientsPanel) clientsPanel.hidden = !isPractitioner;
  const activityPanel = document.getElementById('activity-chart-panel');
  if (activityPanel) activityPanel.hidden = isPractitioner;
  if (isPractitioner) {
    loadUpcomingAppointments();
    const clients = await loadPractitionerClients(pid);
    const current = clients.find(c => c.patient_id === pid);
    if (!current) {
      // Nothing selected yet (or the selected client withdrew consent): open
      // the first client who gave consent, if there is one.
      const first = clients.find(c => c.status === 'consented');
      if (first) {
        window.openClientInPlace(first.patient_id);
        return;   // openClientInPlace reloads the dashboard for that client
      }
      pid = null;
    } else if (heading) {
      heading.textContent = `${current.full_name} · ${current.patient_id}`;
      heading.hidden = false;
    }
  }

  // Privileged operators pick a client before any chart loads (no hardcoded
  // default), so prompt for a selection instead of firing a forbidden request.
  if (!pid) {
    const integ = document.getElementById('stat-integrity');
    if (integ) integ.textContent = 'SELECT CLIENT';
    const recent = document.getElementById('recent-records');
    if (recent) recent.innerHTML = emptyState(isPractitioner
      ? 'Select a client above to see their file.'
      : 'Choose a client to see their file.');
    return;
  }

  try {
    const [recData, statusData] = await Promise.all([
      apiFetch(`/api/records/${pid}`),
      apiFetch(`/api/blockchain/${pid}/status`)
    ]);
    
    document.getElementById('stat-total-blocks').textContent  = statusData.chain_length;
    document.getElementById('stat-total-records').textContent = recData.records.length;
    
    const encrypted = recData.records.filter(r => r.is_protected).length;
    document.getElementById('stat-encrypted').textContent = encrypted;
    
    const valid = statusData.is_valid;
    document.getElementById('stat-integrity').textContent = valid ? 'VALID' : 'BROKEN!';

    // Update sidebar widget
    const widgetBlock = document.getElementById('widget-block-count');
    if (widgetBlock) widgetBlock.textContent = statusData.chain_length;
    const widgetIntegrity = document.getElementById('widget-integrity-status');
    if (widgetIntegrity) {
      widgetIntegrity.textContent = valid ? 'SECURED' : 'COMPROMISED';
      widgetIntegrity.style.color = valid ? 'var(--success)' : 'var(--danger)';
    }
    const widgetCheck = document.getElementById('widget-last-check');
    if (widgetCheck) {
      widgetCheck.textContent = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    // Update integrity icon color
    const iconEl = document.getElementById('stat-integrity-icon');
    if (iconEl) {
      iconEl.querySelector('svg').setAttribute('stroke', valid ? '#2CC985' : '#E57373');
    }

    updateChainPill(valid);
    
    const recent = recData.records.slice(0, 5);
    document.getElementById('recent-records').innerHTML =
      recent.length ? recent.map(r => window.renderRecordCard(r)).join('') : emptyState('No records yet');

    renderActivityChart(recData.records);
    renderOutcomeChart(recData.records);

    // Trigger chain failure notification if broken
    if (!valid) {
      const notis = getNotifications();
      const hasAlert = notis.some(n => n.title === 'Chain Integrity Compromised' && n.text.includes(`#${statusData.broken_at}`));
      if (!hasAlert) {
        addNotification('Chain Integrity Compromised', `Integrity check failed. Block #${statusData.broken_at} is broken!`, 'warning');
      }
    }
  } catch(e) {
    console.error(e);
    // Never leave the dashboard silently showing em-dashes: say why it is empty.
    const recent = document.getElementById('recent-records');
    if (recent) {
      const isPolicyBlock = /Dual-Control/i.test(e.message || '');
      recent.innerHTML = `
        <div class="alert alert-error" style="line-height:1.5">
          <strong>${isPolicyBlock ? 'Client records are locked by policy' : 'Could not load dashboard data'}</strong><br>
          ${escapeHtml(e.message || 'Unknown error')}
          ${isPolicyBlock ? "<br><br><button class='btn btn-gold btn-sm' data-action=\"navigate\" data-arg=\"dual-control\">Open Dual-Control Access</button>" : ''}
        </div>`;
    }
  }
}

export function navigate(page) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const view = document.getElementById('view-' + page);
  if (view) view.classList.add('active');
  const navEl = document.querySelector(`[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');
  
  const titles = {
    dashboard:      'Dashboard Overview',
    records:        roleText('records-title'),
    clients:        'My Clients',
    appointments:   'Appointments',
    'add-record':   'Add Record',
    'chain-status': 'Chain Status Verification',
    users:          'User Management',
    audit:          'Access & Audit History',
    security:       'Security & 2FA Settings',
    'dual-control': 'Dual-Control Access',
    'my-access':    'Who Accessed My Records',
    consent:        roleText('consent-title'),
  };
  
  document.getElementById('topbar-title').textContent = titles[page] || page;
  
  if (page === 'dashboard')     loadDashboard();
  if (page === 'records')       if (window.loadRecords) window.loadRecords();
  if (page === 'clients')       if (window.loadClients) window.loadClients();
  if (page === 'appointments')  if (window.loadAppointments) window.loadAppointments();
  if (page === 'chain-status')  if (window.loadChainStatus) window.loadChainStatus();
  if (page === 'users')         if (window.loadUsers) window.loadUsers();
  if (page === 'audit')         if (window.switchLogTab) window.switchLogTab(window.currentLogTab || 'audit');
  if (page === 'security')      if (window.loadSecuritySettings) window.loadSecuritySettings();
  if (page === 'dual-control')  if (window.loadDualControl) window.loadDualControl();
  if (page === 'my-access')     if (window.loadMyAccessLog) window.loadMyAccessLog();
  if (page === 'consent')       if (window.loadConsents) window.loadConsents();
}
