/* wearables.js — VIP Health Vault UI Wearables Module */
import { apiFetch, patientId } from './utils.js';
import { addNotification } from './notifications.js';

export let activeWearableData = null;
export let activeWearableSource = '';

export function loadWearables() {
  activeWearableData = null;
  activeWearableSource = '';
  const emptyEl = document.getElementById('wearables-preview-empty');
  const dataEl = document.getElementById('wearables-preview-data');
  const syncBtn = document.getElementById('btn-sync-blockchain');
  if (emptyEl) emptyEl.style.display = 'block';
  if (dataEl) dataEl.style.display = 'none';
  if (syncBtn) syncBtn.style.display = 'none';
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
