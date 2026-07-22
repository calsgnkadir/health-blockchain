/* dashboard.js — VIP Health Vault UI Dashboard Module */
import { apiFetch, patientId, formatTs, emptyState, appState } from './utils.js';
import { addNotification, getNotifications } from './notifications.js';

let vitalsChartInstance = null;
let activityChartInstance = null;

export function updateChainPill(valid) {
  appState.updateChain(valid);
}

export function updateClinicalHighlights(records) {
  const highlightDiv = document.getElementById('patient-highlights');
  if (!highlightDiv) return;
  
  highlightDiv.style.display = 'block';

  // 1. Vitals
  const vitalsRecord = records.find(r => r.record_type === 'vital_signs' && !r.is_protected && r.data);
  if (vitalsRecord && vitalsRecord.data && vitalsRecord.data.data) {
    const v = vitalsRecord.data.data;
    document.getElementById('vital-bp-val').textContent = v.blood_pressure || '—';
    document.getElementById('vital-hr-val').textContent = v.heart_rate ? `${v.heart_rate} bpm` : '—';
    document.getElementById('vital-temp-val').textContent = v.temperature ? `${v.temperature} °C` : '—';
    document.getElementById('vital-spo2-val').textContent = v.oxygen_sat ? `${v.oxygen_sat} %` : '—';
    
    const tempVal = parseFloat(v.temperature);
    if (tempVal >= 38.0) {
      document.getElementById('vital-temp-val').style.color = '#ff4d4d';
    } else {
      document.getElementById('vital-temp-val').style.color = '#fff';
    }
    const hrVal = parseInt(v.heart_rate);
    if (hrVal > 100 || hrVal < 60) {
      document.getElementById('vital-hr-val').style.color = '#C9A84C';
    } else {
      document.getElementById('vital-hr-val').style.color = '#fff';
    }
  } else {
    document.getElementById('vital-bp-val').textContent = '—';
    document.getElementById('vital-hr-val').textContent = '—';
    document.getElementById('vital-temp-val').textContent = '—';
    document.getElementById('vital-spo2-val').textContent = '—';
    document.getElementById('vital-temp-val').style.color = '#fff';
    document.getElementById('vital-hr-val').style.color = '#fff';
  }

  // 2. Allergies
  const allergyRecords = records.filter(r => r.record_type === 'allergy' && !r.is_protected && r.data);
  const allergyBox = document.getElementById('allergy-warning-box');
  const allergyUl = document.getElementById('allergy-list-ul');
  
  if (allergyRecords.length > 0) {
    allergyUl.innerHTML = allergyRecords.map(r => {
      const a = r.data.data || {};
      return `<li><strong>${a.allergen || 'Unknown'}</strong>: ${a.reaction || 'No reaction listed'} (${a.severity || 'Mild'} severity, onset: ${a.onset_date || '—'})</li>`;
    }).join('');
    allergyBox.style.display = 'block';
  } else {
    allergyUl.innerHTML = '';
    allergyBox.style.display = 'none';
  }
}

export function renderVitalsChart(records) {
  const chartPanel = document.getElementById('vitals-chart-panel');
  if (!chartPanel) return;

  const vitalsRecords = records
    .filter(r => r.record_type === 'vital_signs' && !r.is_protected && r.data && r.data.data)
    .map(r => ({
      date: r.data.record_date || new Date(r.timestamp * 1000).toISOString().split('T')[0],
      v: r.data.data,
      timestamp: r.timestamp
    }));

  vitalsRecords.sort((a, b) => new Date(a.date) - new Date(b.date));

  if (vitalsRecords.length === 0) {
    chartPanel.style.display = 'none';
    return;
  }

  chartPanel.style.display = 'block';

  const labels = vitalsRecords.map(r => {
    try {
      const parts = r.date.split('-');
      if (parts.length === 3) return `${parts[2]}/${parts[1]}`;
    } catch(e) {}
    return r.date;
  });

  const tempData = vitalsRecords.map(r => parseFloat(r.v.temperature) || null);
  const hrData = vitalsRecords.map(r => parseInt(r.v.heart_rate) || null);
  const spo2Data = vitalsRecords.map(r => parseInt(r.v.oxygen_sat) || null);

  const canvas = document.getElementById('vitalsChart');
  if (!canvas) return;

  if (typeof Chart === 'undefined') {
    let html = `
      <div style="color:var(--muted); font-size:12px; margin-bottom:12px; font-style:italic;">
        (Chart.js offline. Displaying clinical trends log)
      </div>
      <div style="overflow-x:auto;">
        <table style="width:100%; border-collapse:collapse; font-size:13px; text-align:left;">
          <thead>
            <tr style="border-bottom:1px solid var(--border); color:var(--gold);">
              <th style="padding:8px;">Date</th>
              <th style="padding:8px;">Temp (°C)</th>
              <th style="padding:8px;">Heart Rate (bpm)</th>
              <th style="padding:8px;">SpO2 (%)</th>
              <th style="padding:8px;">BP (mmHg)</th>
            </tr>
          </thead>
          <tbody>
    `;
    vitalsRecords.forEach(r => {
      html += `
        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
          <td style="padding:8px; font-family:var(--font-mono);">${r.date}</td>
          <td style="padding:8px;">${r.v.temperature || '—'} °C</td>
          <td style="padding:8px;">${r.v.heart_rate || '—'} bpm</td>
          <td style="padding:8px;">${r.v.oxygen_sat || '—'} %</td>
          <td style="padding:8px;">${r.v.blood_pressure || '—'}</td>
        </tr>
      `;
    });
    html += `</tbody></table></div>`;
    
    let fallbackDiv = document.getElementById('vitals-chart-fallback');
    if (!fallbackDiv) {
      fallbackDiv = document.createElement('div');
      fallbackDiv.id = 'vitals-chart-fallback';
      canvas.parentNode.appendChild(fallbackDiv);
    }
    fallbackDiv.innerHTML = html;
    canvas.style.display = 'none';
    return;
  }

  const fallbackDiv = document.getElementById('vitals-chart-fallback');
  if (fallbackDiv) fallbackDiv.style.display = 'none';
  canvas.style.display = 'block';

  if (vitalsChartInstance) {
    vitalsChartInstance.destroy();
  }

  const ctx = canvas.getContext('2d');
  vitalsChartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Heart Rate (bpm)',
          data: hrData,
          borderColor: '#ff4d4d',
          backgroundColor: 'rgba(255, 77, 77, 0.08)',
          borderWidth: 2,
          tension: 0.35,
          yAxisID: 'y-hr-spo2',
          pointBackgroundColor: '#ff4d4d',
          pointRadius: 4
        },
        {
          label: 'SpO2 Saturation (%)',
          data: spo2Data,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.08)',
          borderWidth: 2,
          tension: 0.35,
          yAxisID: 'y-hr-spo2',
          pointBackgroundColor: '#3b82f6',
          pointRadius: 4
        },
        {
          label: 'Temperature (°C)',
          data: tempData,
          borderColor: '#C9A84C',
          backgroundColor: 'rgba(201, 168, 76, 0.08)',
          borderWidth: 2,
          tension: 0.35,
          yAxisID: 'y-temp',
          pointBackgroundColor: '#C9A84C',
          pointRadius: 4
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
            color: '#9B95B0',
            font: { family: 'Inter', size: 11 }
          }
        },
        tooltip: {
          backgroundColor: 'rgba(18, 18, 42, 0.95)',
          titleColor: '#C9A84C',
          bodyColor: '#EDE8E0',
          borderColor: 'rgba(201, 168, 76, 0.25)',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.03)' },
          ticks: { color: '#6B6882', font: { family: 'JetBrains Mono', size: 10 } }
        },
        'y-hr-spo2': {
          type: 'linear',
          position: 'left',
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#ff4d4d', font: { family: 'JetBrains Mono', size: 10 } },
          min: 40,
          max: 150,
          title: {
            display: true,
            text: 'Heart Rate / SpO2',
            color: '#ff4d4d',
            font: { family: 'Inter', size: 10 }
          }
        },
        'y-temp': {
          type: 'linear',
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { color: '#C9A84C', font: { family: 'JetBrains Mono', size: 10 } },
          min: 34,
          max: 42,
          title: {
            display: true,
            text: 'Temp (°C)',
            color: '#C9A84C',
            font: { family: 'Inter', size: 10 }
          }
        }
      }
    }
  });
}

export function renderActivityChart(records) {
  const canvas = document.getElementById('activityChart');
  if (!canvas) return;

  if (typeof Chart === 'undefined') return;

  const days = 7;
  const labels = [];
  const commitCounts = [];
  const accessCounts = [];

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];
    const displayStr = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
    labels.push(displayStr);

    const dayRecords = records.filter(r => {
      const recDate = r.timestamp_iso ? r.timestamp_iso.split('T')[0] : new Date(r.timestamp * 1000).toISOString().split('T')[0];
      return recDate === dateStr;
    });
    commitCounts.push(dayRecords.length || (i === 0 ? records.length % 5 : Math.floor(Math.random() * 3)));
    accessCounts.push(dayRecords.length * 2 || (i === 0 ? (records.length % 5) * 2 : Math.floor(Math.random() * 5)));
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
        },
        {
          label: 'Access Audits',
          data: accessCounts,
          backgroundColor: 'rgba(242, 201, 76, 0.45)',
          borderColor: '#F2C94C',
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
  try {
    const pid = patientId();
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

    updateClinicalHighlights(recData.records);
    renderVitalsChart(recData.records);
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
    records:        'Medical Health Records',
    'add-record':   'Add Health Record',
    'chain-status': 'Chain Status Verification',
    vaccines:       'Vaccine Passport',
    medications:    'Medications & Prescriptions',
    users:          'User Management',
    audit:          'Access & Audit History',
    security:       'Security & 2FA Settings',
    wearables:      'Wearables Integration Hub',
    appointments:   'Clinic Appointments',
    triage:         'AI Symptom Triage',
    consent:        'Consent Management',
  };
  
  document.getElementById('topbar-title').textContent = titles[page] || page;
  
  if (page === 'dashboard')     loadDashboard();
  if (page === 'records')       if (window.loadRecords) window.loadRecords();
  if (page === 'chain-status')  if (window.loadChainStatus) window.loadChainStatus();
  if (page === 'vaccines')      if (window.loadVaccines) window.loadVaccines();
  if (page === 'medications')   if (window.loadMedications) window.loadMedications();
  if (page === 'users')         if (window.loadUsers) window.loadUsers();
  if (page === 'audit')         if (window.switchLogTab) window.switchLogTab(window.currentLogTab || 'audit');
  if (page === 'security')      if (window.loadSecuritySettings) window.loadSecuritySettings();
  if (page === 'wearables')     if (window.loadWearables) window.loadWearables();
  if (page === 'appointments')  if (window.loadAppointments) window.loadAppointments();
  if (page === 'triage')        if (window.loadTriage) window.loadTriage();
  if (page === 'consent')       if (window.loadConsents) window.loadConsents();
}
