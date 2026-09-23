/* dashboard.js — Mahrem UI Dashboard Module */
import { apiFetch, patientId, formatTs, emptyState, escapeHtml, appState } from './utils.js';
import { addNotification, getNotifications } from './notifications.js';

let activityChartInstance = null;

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
  const pid = patientId();

  // Clear first: on a failed or blocked load the panel must not keep showing the
  // previous session's figures as if they belonged to the current user.
  ['stat-total-blocks', 'stat-total-records', 'stat-encrypted'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '—';
  });

  // Privileged operators pick a patient before any chart loads (no hardcoded
  // default), so prompt for a selection instead of firing a forbidden request.
  if (!pid) {
    const integ = document.getElementById('stat-integrity');
    if (integ) integ.textContent = 'SELECT PATIENT';
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
    records:        'Client Records',
    'add-record':   'Add Record',
    'chain-status': 'Chain Status Verification',
    users:          'User Management',
    audit:          'Access & Audit History',
    security:       'Security & 2FA Settings',
    'dual-control': 'Dual-Control Access',
    'my-access':    'Who Accessed My Records',
    consent:        'Consent Management',
  };
  
  document.getElementById('topbar-title').textContent = titles[page] || page;
  
  if (page === 'dashboard')     loadDashboard();
  if (page === 'records')       if (window.loadRecords) window.loadRecords();
  if (page === 'chain-status')  if (window.loadChainStatus) window.loadChainStatus();
  if (page === 'users')         if (window.loadUsers) window.loadUsers();
  if (page === 'audit')         if (window.switchLogTab) window.switchLogTab(window.currentLogTab || 'audit');
  if (page === 'security')      if (window.loadSecuritySettings) window.loadSecuritySettings();
  if (page === 'dual-control')  if (window.loadDualControl) window.loadDualControl();
  if (page === 'my-access')     if (window.loadMyAccessLog) window.loadMyAccessLog();
  if (page === 'consent')       if (window.loadConsents) window.loadConsents();
}
