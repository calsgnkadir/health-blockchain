/* wearables.js — VIP Health Vault UI Wearables Module */
import { apiFetch, patientId } from './utils.js';
import { addNotification } from './notifications.js';

export let activeWearableData = null;
export let activeWearableSource = '';

export let ecgRunning = true;
export let ecgSpeed = 1.0;
export let ecgState = 'normal';

window.ecgRunning = ecgRunning;
window.ecgSpeed = ecgSpeed;
window.ecgState = ecgState;

window.toggleEcgStream = function() {
  window.ecgRunning = !window.ecgRunning;
  const btnText = document.getElementById('btn-ecg-toggle-text');
  if (btnText) {
    btnText.textContent = window.ecgRunning ? 'Durdur' : 'Başlat';
  }
  updateEcgHud();
};

window.updateEcgSpeed = function(val) {
  window.ecgSpeed = parseFloat(val);
  const speedValEl = document.getElementById('ecg-speed-val');
  if (speedValEl) {
    speedValEl.textContent = val + 'x';
  }
};

window.updateEcgState = function(state) {
  window.ecgState = state;
  updateEcgHud();
};

let ecgAnimationId = null;
let ecgCanvas = null;
let ecgCtx = null;
let ecgPoints = [];
let ecgSweepX = 0;
let ecgHeartRate = 0;
let ecgCyclePhase = 0;

export function loadWearables() {
  activeWearableData = null;
  activeWearableSource = '';
  const emptyEl = document.getElementById('wearables-preview-empty');
  const dataEl = document.getElementById('wearables-preview-data');
  const syncBtn = document.getElementById('btn-sync-blockchain');
  if (emptyEl) emptyEl.style.display = 'block';
  if (dataEl) dataEl.style.display = 'none';
  if (syncBtn) syncBtn.style.display = 'none';

  // Initialize ECG monitor
  setTimeout(initEcgMonitor, 50);
}

export function connectWearable(platform) {
  const title = 'Connect Wearable Hub';
  const w = 480, h = 540;
  const left = (screen.width/2)-(w/2);
  const top = (screen.height/2)-(h/2);
  
  const mockTelemetry = {
    fitbit: {
      hr: '72',
      temp: '36.8',
      spo2: '98',
      bp: '118/79',
      source: 'Fitbit Sense 2'
    },
    google: {
      hr: '68',
      temp: '36.5',
      spo2: '99',
      bp: '120/80',
      source: 'Google Pixel Watch'
    },
    apple: {
      hr: '70',
      temp: '36.6',
      spo2: '97',
      bp: '115/75',
      source: 'Apple Watch Ultra'
    }
  };
  
  window.onOAuthCallback = function(p) {
    if (p !== platform) return;
    activeWearableSource = mockTelemetry[platform].source;
    activeWearableData = mockTelemetry[platform];
    
    const emptyEl = document.getElementById('wearables-preview-empty');
    const dataEl = document.getElementById('wearables-preview-data');
    const syncBtn = document.getElementById('btn-sync-blockchain');
    
    if (emptyEl) emptyEl.style.display = 'none';
    if (dataEl) dataEl.style.display = 'block';
    if (syncBtn) syncBtn.style.display = 'block';
    
    document.getElementById('wearable-hr').textContent = activeWearableData.hr + ' bpm';
    document.getElementById('wearable-temp').textContent = activeWearableData.temp + ' °C';
    document.getElementById('wearable-spo2').textContent = activeWearableData.spo2 + ' %';
    document.getElementById('wearable-bp').textContent = activeWearableData.bp + ' mmHg';
    document.getElementById('wearable-source-name').textContent = activeWearableSource;
    document.getElementById('wearable-timestamp').textContent = new Date().toLocaleTimeString('en-US') + ' ' + new Date().toLocaleDateString('en-GB');
    
    addNotification('Sensor Connected', `Successfully connected to ${activeWearableSource}. Data preview loaded.`, 'success');
    
    // Update ECG monitor HUD
    updateEcgHud();
  };
  
  const popup = window.open('', title, `width=${w},height=${h},top=${top},left=${left}`);
  if (!popup) {
    showOAuthModalFallback(platform, mockTelemetry[platform]);
    return;
  }
  
  popup.document.write(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>OAuth Connection Hub</title>
      <style>
        body { background: #07070F; color: #EDE8E0; font-family: sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; padding: 20px; }
        .card { background: #12122A; border: 1px solid rgba(201,168,76,0.25); border-radius: 12px; padding: 30px; text-align: center; max-width: 380px; box-shadow: 0 8px 30px rgba(0,0,0,0.5); }
        .btn { background: linear-gradient(135deg, #C9A84C, #8B6914); color: #000; border: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 20px; width: 100%; transition: opacity 0.2s; }
        .btn:hover { opacity: 0.9; }
        .logo { font-size: 48px; margin-bottom: 15px; }
        h2 { color: #C9A84C; margin-top: 0; }
        p { color: #6B6882; font-size: 14px; line-height: 1.5; }
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">⌚</div>
        <h2>Connect ${platform.toUpperCase()}</h2>
        <p>VIP Health Vault requests permission to access your medical telemetry stream (Heart Rate, Temperature, SpO2, and Blood Pressure).</p>
        <button class="btn" onclick="authorize()">AUTHORIZE SYNC</button>
      </div>
      <script>
        function authorize() {
          if (window.opener && !window.opener.closed) {
            window.opener.onOAuthCallback('${platform}');
          }
          window.close();
        }
      <\/script>
    </body>
    </html>
  `);
  popup.document.close();
}

export function showOAuthModalFallback(platform, telemetry) {
  document.getElementById('modal-content').innerHTML = `
    <div style="text-align: center; padding: 20px;">
      <div style="font-size: 48px; margin-bottom: 16px;">⌚</div>
      <h2 style="color: var(--gold); font-size: 20px; margin-bottom: 12px;">Connect ${platform.toUpperCase()}</h2>
      <p style="color: var(--muted); font-size: 14px; line-height: 1.5; margin-bottom: 24px;">
        VIP Health Vault requests permission to access your medical telemetry stream (Heart Rate, Temperature, SpO2, and Blood Pressure).
      </p>
      <button class="btn btn-gold btn-full" onclick="authorizeFallback('${platform}')">AUTHORIZE SYNC</button>
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
  
  window.authorizeFallback = function(p) {
    if (window.closeModal) window.closeModal();
    window.onOAuthCallback(p);
  };
}

export async function commitWearablesToBlockchain() {
  if (!activeWearableData) return;
  const btn = document.getElementById('btn-sync-blockchain');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Syncing...';
  }
  
  const payload = {
    patient_id: patientId(),
    record_type: 'vital_signs',
    title: `Wearables Sensor Telemetry (${activeWearableSource})`,
    doctor_name: 'Device Sensor Auto-Sync',
    institution: 'Connected Vitals Core',
    record_date: new Date().toISOString().split('T')[0],
    access_level: 'private',
    is_confidential: false,
    data: {
      heart_rate: activeWearableData.hr,
      temperature: activeWearableData.temp,
      oxygen_sat: activeWearableData.spo2,
      blood_pressure: activeWearableData.bp
    },
    notes: `Cryptographically verified vital block synchronization from health wearables via OAuth Gateway.`
  };
  
  try {
    const res = await apiFetch('/api/records', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    addNotification('Sensor Vitals Synced', `Wearable sensor stream successfully verified and committed to block #${res.block_index}.`, 'success');
    loadWearables();
    if (window.loadDashboard) window.loadDashboard();
  } catch(ex) {
    alert("Blockchain sync failed: " + ex.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'COMMIT TELEMETRY TO BLOCKCHAIN';
    }
  }
}

/* -- ECG Animation Engine -- */
export function initEcgMonitor() {
  ecgCanvas = document.getElementById('ecg-canvas');
  if (!ecgCanvas) return;
  ecgCtx = ecgCanvas.getContext('2d');
  
  const rect = ecgCanvas.getBoundingClientRect();
  ecgCanvas.width = rect.width || 400;
  ecgCanvas.height = rect.height || 100;
  
  ecgPoints = new Array(ecgCanvas.width).fill(ecgCanvas.height / 2);
  ecgSweepX = 0;
  ecgCyclePhase = 0;
  
  updateEcgHud();

  if (ecgAnimationId) {
    cancelAnimationFrame(ecgAnimationId);
  }
  
  animateEcg();
}

export function updateEcgHud() {
  const dot = document.getElementById('ecg-status-dot');
  const text = document.getElementById('ecg-status-text');
  
  if (!window.ecgRunning) {
    if (dot) dot.style.background = 'var(--warn)';
    if (text) text.textContent = 'MONITOR PAUSED';
    return;
  }

  let rate = 72;
  if (window.ecgState === 'bradycardia') rate = 48;
  else if (window.ecgState === 'tachycardia') rate = 130;
  else if (window.ecgState === 'arrhythmia') rate = 85;

  if (activeWearableData) {
    ecgHeartRate = parseInt(activeWearableData.hr) || rate;
  } else {
    ecgHeartRate = rate;
  }

  if (dot) dot.style.background = 'var(--accent-integrations)';
  if (text) text.textContent = `TELEMETRY ACTIVE · ${ecgHeartRate} BPM (${(window.ecgState || 'NORMAL').toUpperCase()})`;
}

function animateEcg() {
  if (!ecgCanvas || !ecgCtx) return;
  
  if (!window.ecgRunning) {
    ecgAnimationId = requestAnimationFrame(animateEcg);
    return;
  }

  const w = ecgCanvas.width;
  const h = ecgCanvas.height;
  const baseline = h / 2;
  const speed = 2.5 * (window.ecgSpeed || 1.0);
  
  for (let i = 0; i < speed; i++) {
    const targetX = Math.floor((ecgSweepX + i) % w);
    let targetY = baseline;
    
    if (ecgHeartRate > 0) {
      const cycleDurationFrames = (60 / ecgHeartRate) * 60; 
      const phase = ecgCyclePhase % cycleDurationFrames;
      const pct = phase / cycleDurationFrames;
      
      if (pct > 0.0 && pct < 0.08) {
        // P-wave
        const pPhase = pct / 0.08;
        targetY -= Math.sin(pPhase * Math.PI) * 4;
      } else if (pct >= 0.10 && pct < 0.13) {
        // Q-wave
        const qPhase = (pct - 0.10) / 0.03;
        targetY += qPhase * 5;
      } else if (pct >= 0.13 && pct < 0.17) {
        // R-wave (spike)
        const rPhase = (pct - 0.13) / 0.04;
        if (rPhase < 0.5) {
          targetY -= (rPhase / 0.5) * 35;
        } else {
          targetY -= 35 - ((rPhase - 0.5) / 0.5) * 45;
        }
      } else if (pct >= 0.17 && pct < 0.20) {
        // S-wave
        const sPhase = (pct - 0.17) / 0.03;
        targetY += 10 - sPhase * 10;
      } else if (pct >= 0.28 && pct < 0.40) {
        // T-wave
        const tPhase = (pct - 0.28) / 0.12;
        targetY -= Math.sin(tPhase * Math.PI) * 6;
      }
      
      targetY += (Math.random() - 0.5) * 0.8;
      ecgCyclePhase += 1;
    } else {
      // Idle baseline noise
      targetY += (Math.random() - 0.5) * 1.2;
    }
    
    ecgPoints[targetX] = targetY;
  }
  
  ecgSweepX = (ecgSweepX + speed) % w;
  
  ecgCtx.fillStyle = '#06060c';
  ecgCtx.fillRect(0, 0, w, h);
  
  ecgCtx.strokeStyle = 'rgba(16, 185, 129, 0.03)';
  ecgCtx.lineWidth = 1;
  for (let x = 0; x < w; x += 20) {
    ecgCtx.beginPath();
    ecgCtx.moveTo(x, 0);
    ecgCtx.lineTo(x, h);
    ecgCtx.stroke();
  }
  for (let y = 0; y < h; y += 20) {
    ecgCtx.beginPath();
    ecgCtx.moveTo(0, y);
    ecgCtx.lineTo(w, y);
    ecgCtx.stroke();
  }
  
  ecgCtx.beginPath();
  ecgCtx.lineWidth = 1.8;
  ecgCtx.strokeStyle = '#10B981';
  ecgCtx.shadowBlur = 6;
  ecgCtx.shadowColor = '#10B981';
  
  let started = false;
  
  for (let x = 0; x < w; x++) {
    const distanceToSweep = (x - ecgSweepX + w) % w;
    if (distanceToSweep < 15) {
      if (started) {
        ecgCtx.stroke();
        ecgCtx.beginPath();
        started = false;
      }
      continue;
    }
    
    if (!started) {
      ecgCtx.moveTo(x, ecgPoints[x]);
      started = true;
    } else {
      ecgCtx.lineTo(x, ecgPoints[x]);
    }
  }
  
  if (started) {
    ecgCtx.stroke();
  }
  
  ecgCtx.shadowBlur = 12;
  ecgCtx.fillStyle = '#10B981';
  ecgCtx.beginPath();
  const leadIdx = Math.floor(ecgSweepX);
  ecgCtx.arc(leadIdx, ecgPoints[leadIdx], 3, 0, Math.PI * 2);
  ecgCtx.fill();
  ecgCtx.shadowBlur = 0;
  
  ecgAnimationId = requestAnimationFrame(animateEcg);
}

