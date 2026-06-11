/* records.js — VIP Health Vault UI Records Module */
import { apiFetch, patientId, formatTs, emptyState, ROLE_LABEL } from './utils.js';
import { addNotification } from './notifications.js';

export let allRecords = [];
export let recordTypes = [];

/* -- Record type labels (no icons) ------------------- */
export const TYPE_LABELS = {
  diagnosis:   'Diagnosis',
  lab_result:  'Lab Result',
  prescription:'Prescription',
  surgery:     'Surgery',
  vaccination: 'Vaccination',
  imaging:     'Imaging',
  vital_signs: 'Vital Signs',
  allergy:     'Allergy',
  psychology:  'Psychology',
  genetic:     'Genetics',
  emergency:   'Emergency',
  other:       'Other',
  correction:  'Correction',
  unknown:     'Unknown',
};

const ACCESS_COLORS = { private:'badge-private', doctor_shared:'badge-shared', emergency:'badge-emergency' };
const ACCESS_LABELS = { private:'Patient Only', doctor_shared:'Patient + Doctor', emergency:'Emergency Access' };

export async function loadRecordTypes() {
  try {
    const d = await apiFetch('/api/record-types');
    recordTypes = d.types;
    
    const sel = document.getElementById('rec-type');
    if (sel) {
      sel.innerHTML = '<option value="">Select...</option>';
      d.types.forEach(t => { 
        const o = document.createElement('option'); 
        o.value = t.value; 
        o.textContent = t.label; 
        sel.appendChild(o); 
      });
    }
    
    const typeFilter = document.getElementById('rec-type-filter');
    if (typeFilter) {
      typeFilter.innerHTML = '<option value="">All Types</option>';
      d.types.forEach(t => { 
        const o = document.createElement('option'); 
        o.value = t.value; 
        o.textContent = t.label; 
        typeFilter.appendChild(o); 
      });
    }
  } catch(e) { 
    console.error(e); 
  }
}

export async function loadRecords() {
  const container = document.getElementById('all-records');
  if (!container) return;
  container.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch(`/api/records/${patientId()}`);
    allRecords = d.records;
    renderAllRecords();
  } catch(e) { 
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`; 
  }
}

export function filterRecords() { 
  renderAllRecords(); 
}

export function renderAllRecords() {
  const qEl = document.getElementById('rec-search');
  const q = qEl ? (qEl.value || '').toLowerCase() : '';
  const typeEl = document.getElementById('rec-type-filter');
  const type = typeEl ? typeEl.value : '';
  
  const filtered = allRecords.filter(r => {
    const d = r.data || {};
    const txt = (r.title + (d.doctor_name||'') + (d.institution||'')).toLowerCase();
    const matchQ = !q || txt.includes(q);
    const matchT = !type || (d.record_type === type);
    return matchQ && matchT;
  });
  
  const container = document.getElementById('all-records');
  if (container) {
    container.innerHTML = filtered.length ? filtered.map(renderRecordCard).join('') : emptyState('No records found');
  }
}

export function renderRecordCard(r) {
  const d = r.data || {};
  const type = d.record_type || 'unknown';
  const typeAbbr = (TYPE_LABELS[type] || type).substring(0, 3).toUpperCase();
  const al = d.access_level || 'private';
  const date = d.record_date ? new Date(d.record_date).toLocaleDateString('en-GB') : formatTs(r.timestamp);
  const encBadge = r.is_protected ? '<span class="badge badge-encrypted">ENCRYPTED</span>' : '';
  const corrBadge = r.is_correction ? '<span class="badge badge-private">CORRECTION</span>' : '';
  const typLabel = recordTypes.find(t => t.value === type)?.label || TYPE_LABELS[type] || type;
  const alBadge = `<span class="badge ${ACCESS_COLORS[al]||''}">${ACCESS_LABELS[al]||al}</span>`;
  return `
  <div class="record-card ${r.is_protected?'is-encrypted':''} ${r.is_correction?'is-correction':''}"
       onclick="window.openRecord(${r.block_index})">
    <div class="record-type-icon record-type-text">${typeAbbr}</div>
    <div class="record-main">
      <div class="record-title">${r.title}</div>
      <div class="record-meta">${d.doctor_name||'—'} · ${d.institution||'—'}</div>
      <div class="record-badges">${alBadge}${encBadge}${corrBadge}
        <span class="badge badge-private" style="background:rgba(255,255,255,0.05);color:var(--muted)">${typLabel}</span>
      </div>
    </div>
    <div class="record-right">
      <div class="record-date">${date}</div>
      <div class="record-hash">#${r.block_index} · ${r.hash_preview}</div>
    </div>
  </div>`;
}

export function renderAttachmentHtml(fileName, fileType, fileData, patientIdVal, blockIndexVal, passwordVal = null) {
  if (!fileData && !fileName) return '';

  let previewHtml = '';
  // Check if we have off-chain hash instead of inline base64 data
  const hasOffchain = !fileData && fileName;

  if (hasOffchain) {
    previewHtml = `
      <div style="margin-top: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 12px; background: rgba(255,255,255,0.02); display:flex; justify-content:space-between; align-items:center;">
        <div style="text-align:left">
          <div style="font-weight:600; font-size:13px; color:#fff;">📄 ${fileName} [Off-chain Blockchain Locked]</div>
          <div style="font-size:11px; color:var(--muted); margin-top:2px;">Type: ${fileType || 'Unknown'}</div>
        </div>
        <button class="btn btn-gold btn-sm" onclick="window.downloadOffchainFile('${patientIdVal}', ${blockIndexVal}, '${passwordVal || ''}', '${fileName}')">Download Secure File</button>
      </div>
    `;
  } else if (fileType && fileType.startsWith('image/')) {
    previewHtml = `
      <div style="margin-top: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 10px; background: rgba(255,255,255,0.02);">
        <div style="font-size:11px; color:var(--muted); margin-bottom:8px;">IMAGE ATTACHMENT: ${fileName}</div>
        <img src="data:${fileType};base64,${fileData}" style="max-width:100%; max-height:240px; border-radius:4px; display:block; margin:0 auto;" />
        <button class="btn btn-gold btn-sm" style="margin-top:10px; width:100%" onclick="window.downloadBase64File('${fileName}', '${fileType}', '${fileData}')">Download Image</button>
      </div>
    `;
  } else {
    previewHtml = `
      <div style="margin-top: 14px; border: 1px solid var(--border); border-radius: 6px; padding: 12px; background: rgba(255,255,255,0.02); display:flex; justify-content:space-between; align-items:center;">
        <div style="text-align:left">
          <div style="font-weight:600; font-size:13px; color:#fff;">📄 ${fileName}</div>
          <div style="font-size:11px; color:var(--muted); margin-top:2px;">Type: ${fileType || 'Unknown'}</div>
        </div>
        <button class="btn btn-gold btn-sm" onclick="window.downloadBase64File('${fileName}', '${fileType}', '${fileData}')">Download File</button>
      </div>
    `;
  }
  return `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">ATTACHMENT</h4>${previewHtml}`;
}

export function downloadBase64File(fileName, fileType, fileData) {
  const linkSource = `data:${fileType};base64,${fileData}`;
  const downloadLink = document.createElement("a");
  downloadLink.href = linkSource;
  downloadLink.download = fileName;
  downloadLink.click();
}

export async function downloadOffchainFile(patientIdVal, blockIndexVal, passwordVal, fileName) {
  try {
    let url = `/api/records/offchain/download/${patientIdVal}/${blockIndexVal}`;
    if (passwordVal) {
      url += `?password=${encodeURIComponent(passwordVal)}`;
    }
    const res = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('vhv_token')}`
      }
    });
    if (!res.ok) {
      const json = await res.json().catch(() => ({}));
      throw new Error(json.detail || 'Download failed');
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const downloadLink = document.createElement("a");
    downloadLink.href = blobUrl;
    downloadLink.download = fileName;
    downloadLink.click();
    URL.revokeObjectURL(blobUrl);
  } catch (ex) {
    alert("File download failed: " + ex.message);
  }
}

export async function openRecord(idx) {
  const r = allRecords.find(x => x.block_index === idx);
  if (!r) return;

  if (r.is_protected) {
    document.getElementById('modal-content').innerHTML = `
      <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">Encrypted VIP Record</h2>
      <p style="margin-bottom:16px;color:var(--muted)">This record is encrypted with AES-256. Enter the password to decrypt:</p>
      <div id="modal-decrypt-error" class="alert alert-error" style="display:none;margin-bottom:12px"></div>
      <div class="field-group">
        <label>Record Password</label>
        <div class="input-wrap">
          <input type="password" id="modal-decrypt-password" placeholder="••••••••" style="width:100%;margin-bottom:12px;padding:8px 12px;border-radius:4px;border:1px solid var(--border);background:rgba(255,255,255,0.05);color:white;" />
        </div>
      </div>
      <button class="btn btn-gold btn-full" onclick="window.decryptRecord(${idx})">Decrypt &amp; View</button>
      <hr style="border-color:var(--border);margin:16px 0">
      <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${r.block_index}</div></div>
      <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r.hash_preview}</div></div>
    `;
    document.getElementById('modal-overlay').classList.add('open');
    return;
  }

  const d = r.data || {};
  const typLabel = recordTypes.find(t => t.value === d.record_type)?.label || d.record_type || '—';

  let dataFields = '';
  if (d.data && typeof d.data === 'object') {
    dataFields = Object.entries(d.data).map(([k,v]) =>
      `<div class="modal-field"><div class="modal-field-label">${k}</div><div class="modal-field-value">${v}</div></div>`
    ).join('');
  }

  const attachmentHtml = renderAttachmentHtml(r.file_name, r.file_type, r.file_data, patientId(), r.block_index);
  const isImaging = d.record_type === 'imaging';
  const dicomViewerHtml = isImaging ? getDicomViewerHtml() : '';

  document.getElementById('modal-content').innerHTML = `
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">${r.title}</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
      <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${r.block_index}</div></div>
      <div class="modal-field"><div class="modal-field-label">Record Type</div><div class="modal-field-value">${typLabel}</div></div>
      <div class="modal-field"><div class="modal-field-label">Doctor</div><div class="modal-field-value">${d.doctor_name||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Institution</div><div class="modal-field-value">${d.institution||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Date</div><div class="modal-field-value">${d.record_date||'—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Access</div><div class="modal-field-value">${ACCESS_LABELS[d.access_level]||d.access_level||'—'}</div></div>
    </div>
    ${dataFields ? `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">DATA FIELDS</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">${dataFields}</div>` : ''}
    ${d.notes ? `<div class="modal-field" style="margin-top:14px"><div class="modal-field-label">Notes</div><div class="modal-field-value">${d.notes}</div></div>` : ''}
    ${dicomViewerHtml}
    ${attachmentHtml}
    <hr style="border-color:var(--border);margin:16px 0">
    <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r.hash_preview}</div></div>
    <div class="modal-field"><div class="modal-field-label">Created By</div><div class="modal-field-value">${d.created_by||'—'}</div></div>
  `;
  document.getElementById('modal-overlay').classList.add('open');

  if (isImaging) {
    initDicomViewer(d.data || {});
  }
}

export async function decryptRecord(idx) {
  const pwdEl = document.getElementById('modal-decrypt-password');
  const errEl = document.getElementById('modal-decrypt-error');
  if (!pwdEl) return;
  const pwd = pwdEl.value;
  if (!pwd) {
    errEl.textContent = 'Please enter the password.';
    errEl.style.display = 'block';
    return;
  }
  errEl.style.display = 'none';

  try {
    const res = await apiFetch(`/api/records/${patientId()}/${idx}/decrypt`, {
      method: 'POST',
      body: JSON.stringify({ password: pwd })
    });
    const decData = res.data;

    const r = allRecords.find(x => x.block_index === idx);
    const d = decData || {};
    const typLabel = recordTypes.find(t => t.value === d.record_type)?.label || d.record_type || '—';

    let dataFields = '';
    if (d.data && typeof d.data === 'object') {
      dataFields = Object.entries(d.data).map(([k,v]) =>
        `<div class="modal-field"><div class="modal-field-label">${k}</div><div class="modal-field-value">${v}</div></div>`
      ).join('');
    }

    const attachmentHtml = renderAttachmentHtml(d.file_name, d.file_type, d.file_data, patientId(), idx, pwd);
    const isImaging = d.record_type === 'imaging';
    const dicomViewerHtml = isImaging ? getDicomViewerHtml() : '';

    document.getElementById('modal-content').innerHTML = `
      <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">${d.title || (r ? r.title : '')}</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div class="modal-field"><div class="modal-field-label">Block #</div><div class="modal-field-value">${idx}</div></div>
        <div class="modal-field"><div class="modal-field-label">Record Type</div><div class="modal-field-value">${typLabel}</div></div>
        <div class="modal-field"><div class="modal-field-label">Doctor</div><div class="modal-field-value">${d.doctor_name||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Institution</div><div class="modal-field-value">${d.institution||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Date</div><div class="modal-field-value">${d.record_date||'—'}</div></div>
        <div class="modal-field"><div class="modal-field-label">Access</div><div class="modal-field-value">${ACCESS_LABELS[d.access_level]||d.access_level||'—'}</div></div>
      </div>
      ${dataFields ? `<hr style="border-color:var(--border);margin:16px 0"><h4 style="color:var(--muted-hi);font-size:12px;margin-bottom:12px">DATA FIELDS</h4><div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">${dataFields}</div>` : ''}
      ${d.notes ? `<div class="modal-field" style="margin-top:14px"><div class="modal-field-label">Notes</div><div class="modal-field-value">${d.notes}</div></div>` : ''}
      ${dicomViewerHtml}
      ${attachmentHtml}
      <hr style="border-color:var(--border);margin:16px 0">
      <div class="modal-field"><div class="modal-field-label">Block Hash</div><div class="modal-field-value mono">${r ? r.hash_preview : '—'}</div></div>
      <div class="modal-field"><div class="modal-field-label">Created By</div><div class="modal-field-value">${d.created_by||'—'}</div></div>
    `;

    if (isImaging) {
      initDicomViewer(d.data || {});
    }
  } catch (ex) {
    errEl.textContent = ex.message;
    errEl.style.display = 'block';
  }
}

export function closeModal() { 
  document.getElementById('modal-overlay').classList.remove('open'); 
}

/* -- Add Record Dynamic Fields --------------------------------- */
export const DYNAMIC_FIELDS = {
  diagnosis:    [{id:'icd_code',label:'ICD Code'},{id:'severity',label:'Severity (Mild/Moderate/Severe)'},{id:'symptoms',label:'Symptoms'}],
  lab_result:   [{id:'test_name',label:'Test Name'},{id:'result_value',label:'Result Value'},{id:'reference_range',label:'Reference Range'},{id:'unit',label:'Unit'}],
  prescription: [{id:'medication',label:'Medication Name'},{id:'dose',label:'Dose'},{id:'frequency',label:'Frequency'},{id:'duration',label:'Duration (days)'}],
  surgery:      [{id:'procedure',label:'Procedure'},{id:'anesthesia',label:'Anesthesia Type'},{id:'duration_min',label:'Duration (min)'},{id:'outcome',label:'Outcome'}],
  vaccination:  [{id:'vaccine_name',label:'Vaccine Name'},{id:'lot_number',label:'Lot Number'},{id:'dose_number',label:'Dose Number'},{id:'next_dose',label:'Next Dose Date'}],
  imaging:      [{id:'modality',label:'Modality (MRI/CT/X-Ray)'},{id:'body_part',label:'Body Part'},{id:'findings',label:'Findings'},{id:'radiologist',label:'Radiologist'}],
  vital_signs:  [{id:'blood_pressure',label:'Blood Pressure (mmHg)'},{id:'heart_rate',label:'Heart Rate (bpm)'},{id:'temperature',label:'Temperature (C)'},{id:'oxygen_sat',label:'SpO2 (%)'}],
  allergy:      [{id:'allergen',label:'Allergen'},{id:'reaction',label:'Reaction Type'},{id:'severity',label:'Severity'},{id:'onset_date',label:'Onset Date'}],
};

export function renderDynamicFields() {
  const type = document.getElementById('rec-type').value;
  const container = document.getElementById('dynamic-fields');
  if (!container) return;
  const fields = DYNAMIC_FIELDS[type] || [];
  container.innerHTML = fields.map(f =>
    `<div class="field-group">
      <label>${f.label}</label>
      <input type="text" id="dyn-${f.id}" placeholder="${f.label}...">
    </div>`
  ).join('');
}

/* -- DICOM Engine Logic -- */
export let dicomWidth = 240;
export let dicomLevel = 120;
export let dicomZoom = 1.0;
export let dicomPanX = 0;
export let dicomPanY = 0;
export let dicomInverted = false;
export let dicomRawPixels = null;
export let dicomCanvasInstance = null;
export let dicomModalityText = 'CT';
export let dicomBodyPartText = 'CHEST';

export function getDicomViewerHtml() {
  return `
    <div id="dicom-viewer-container" style="margin-top:16px;">
      <hr style="border-color:var(--border);margin:16px 0">
      <h4 style="color:var(--muted-hi); font-size:12px; margin-bottom:10px; text-transform:uppercase; letter-spacing:0.5px;">DICOM IMAGE VIEWPORT</h4>
      <div class="dicom-viewport-box">
        <canvas id="dicom-canvas" class="dicom-canvas"></canvas>
        <div class="dicom-controls">
          <button onclick="window.zoomDicom(1.2)">Zoom +</button>
          <button onclick="window.zoomDicom(0.8)">Zoom -</button>
          <button onclick="window.invertDicom()">Invert Colors</button>
          <button onclick="window.resetDicom()">Reset</button>
        </div>
        <div class="dicom-overlay-text top-left">MODALITY: <span id="dicom-modality">-</span></div>
        <div class="dicom-overlay-text bottom-left"><span id="dicom-wl">-</span></div>
        <div class="dicom-overlay-text top-right">SCALE: <span id="dicom-scale">1.0x</span></div>
        <div class="dicom-overlay-text bottom-right">512 x 512px<br>8-BIT MONO</div>
      </div>
      <span style="font-size:11px; color:var(--muted); margin-top:8px; display:block; line-height:1.4;">
        * Left-click + drag to adjust Window/Level (Contrast/Brightness). Scroll wheel or right-click drag to Zoom. Middle-click drag to Pan.
      </span>
    </div>
  `;
}

export function initDicomViewer(data) {
  const canvas = document.getElementById('dicom-canvas');
  if (!canvas) return;

  dicomCanvasInstance = canvas;
  const modality = data.modality || 'CT';
  const bodyPart = data.body_part || 'CHEST';
  dicomModalityText = modality;
  dicomBodyPartText = bodyPart;

  const modEl = document.getElementById('dicom-modality');
  if (modEl) modEl.textContent = `${modality} (${bodyPart})`;
  
  if (modality.toLowerCase().includes('mri')) {
    dicomWidth = 180;
    dicomLevel = 90;
  } else {
    dicomWidth = 240;
    dicomLevel = 120;
  }
  dicomZoom = 1.0;
  dicomPanX = 0;
  dicomPanY = 0;
  dicomInverted = false;

  updateDicomHudText();

  dicomRawPixels = generateSimulatedImaging(modality, bodyPart);

  // Setup Event Listeners
  canvas.removeEventListener('mousedown', onDicomMouseDown);
  canvas.removeEventListener('mousemove', onDicomMouseMove);
  canvas.removeEventListener('mouseup', onDicomMouseUp);
  canvas.removeEventListener('mouseleave', onDicomMouseLeave);
  canvas.removeEventListener('wheel', onDicomWheel);
  canvas.removeEventListener('contextmenu', onDicomContextMenu);

  canvas.addEventListener('mousedown', onDicomMouseDown);
  canvas.addEventListener('mousemove', onDicomMouseMove);
  canvas.addEventListener('mouseup', onDicomMouseUp);
  canvas.addEventListener('mouseleave', onDicomMouseLeave);
  canvas.addEventListener('wheel', onDicomWheel, { passive: false });
  canvas.addEventListener('contextmenu', onDicomContextMenu);

  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width || 512;
  canvas.height = rect.height || 320;

  drawDicomFrame();
}

export function updateDicomHudText() {
  const wlEl = document.getElementById('dicom-wl');
  if (wlEl) {
    wlEl.innerHTML = `W: <strong>${Math.round(dicomWidth)}</strong> L: <strong>${Math.round(dicomLevel)}</strong>${dicomInverted ? ' <span style="color:#ff3333">[INV]</span>' : ''}`;
  }
  const scaleEl = document.getElementById('dicom-scale');
  if (scaleEl) {
    scaleEl.textContent = `${dicomZoom.toFixed(1)}x`;
  }
}

let isDicomDragging = false;
let dicomDragStart = { x: 0, y: 0 };
let dicomDragMode = 'window'; 

export function onDicomMouseDown(e) {
  e.preventDefault();
  isDicomDragging = true;
  dicomDragStart.x = e.clientX;
  dicomDragStart.y = e.clientY;
  
  if (e.button === 2) {
    dicomDragMode = 'zoom';
  } else if (e.button === 1) {
    dicomDragMode = 'pan';
  } else {
    dicomDragMode = 'window';
  }
}

export function onDicomMouseMove(e) {
  if (!isDicomDragging) return;
  const dx = e.clientX - dicomDragStart.x;
  const dy = e.clientY - dicomDragStart.y;
  dicomDragStart.x = e.clientX;
  dicomDragStart.y = e.clientY;

  if (dicomDragMode === 'window') {
    dicomWidth += dx * 1.5;
    dicomLevel -= dy * 1.5;
    dicomWidth = Math.max(10, Math.min(1024, dicomWidth));
    dicomLevel = Math.max(-512, Math.min(512, dicomLevel));
    updateDicomHudText();
  } else if (dicomDragMode === 'zoom') {
    dicomZoom *= (1 - dy * 0.01);
    dicomZoom = Math.max(0.2, Math.min(8.0, dicomZoom));
    updateDicomHudText();
  } else if (dicomDragMode === 'pan') {
    dicomPanX += dx;
    dicomPanY += dy;
  }
  drawDicomFrame();
}

export function onDicomMouseUp(e) { isDicomDragging = false; }
export function onDicomMouseLeave(e) { isDicomDragging = false; }
export function onDicomContextMenu(e) { e.preventDefault(); }

export function onDicomWheel(e) {
  e.preventDefault();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  dicomZoom *= factor;
  dicomZoom = Math.max(0.2, Math.min(8.0, dicomZoom));
  updateDicomHudText();
  drawDicomFrame();
}

export function zoomDicom(factor) {
  dicomZoom *= factor;
  dicomZoom = Math.max(0.2, Math.min(8.0, dicomZoom));
  updateDicomHudText();
  drawDicomFrame();
}

export function invertDicom() {
  dicomInverted = !dicomInverted;
  updateDicomHudText();
  drawDicomFrame();
}

export function resetDicom() {
  if (dicomModalityText.toLowerCase().includes('mri')) {
    dicomWidth = 180;
    dicomLevel = 90;
  } else {
    dicomWidth = 240;
    dicomLevel = 120;
  }
  dicomZoom = 1.0;
  dicomPanX = 0;
  dicomPanY = 0;
  dicomInverted = false;
  updateDicomHudText();
  drawDicomFrame();
}

export function generateSimulatedImaging(modality, bodyPart) {
  const off = document.createElement('canvas');
  off.width = 512;
  off.height = 512;
  const ctx = off.getContext('2d');
  
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, 512, 512);

  const m = (modality || '').toLowerCase();
  const bp = (bodyPart || '').toLowerCase();

  if (m.includes('mri') || bp.includes('brain') || bp.includes('head')) {
    // Brain MRI Outline
    ctx.strokeStyle = '#888';
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.ellipse(256, 256, 170, 210, 0, 0, Math.PI * 2);
    ctx.stroke();

    ctx.strokeStyle = '#444';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.ellipse(256, 256, 180, 220, 0, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = '#777';
    ctx.beginPath();
    ctx.ellipse(256, 256, 155, 195, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#222';
    for (let angle = 0; angle < Math.PI * 2; angle += 0.15) {
      const x = 256 + Math.cos(angle) * 145;
      const y = 256 + Math.sin(angle) * 185;
      ctx.beginPath();
      ctx.arc(x, y, 12, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = '#999';
    ctx.beginPath();
    ctx.ellipse(256, 256, 120, 160, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#000';
    ctx.beginPath();
    ctx.moveTo(256, 180);
    ctx.bezierCurveTo(210, 180, 210, 280, 250, 280);
    ctx.bezierCurveTo(240, 250, 240, 200, 256, 180);
    ctx.moveTo(256, 180);
    ctx.bezierCurveTo(302, 180, 302, 280, 262, 280);
    ctx.bezierCurveTo(272, 250, 272, 200, 256, 180);
    ctx.fill();

    ctx.strokeStyle = '#333';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(256, 60);
    ctx.lineTo(256, 450);
    ctx.stroke();

  } else if (m.includes('x-ray') || bp.includes('chest') || bp.includes('lung') || bp.includes('heart')) {
    // Lung fields
    ctx.fillStyle = '#1c1c1c';
    ctx.beginPath();
    ctx.ellipse(170, 256, 75, 170, -0.05, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(342, 256, 75, 170, 0.05, 0, Math.PI * 2);
    ctx.fill();

    // Spine
    ctx.fillStyle = '#888';
    ctx.fillRect(244, 80, 24, 350);

    // Rib cage overlay
    ctx.strokeStyle = 'rgba(180, 180, 180, 0.35)';
    ctx.lineWidth = 8;
    for (let y = 110; y < 400; y += 30) {
      ctx.beginPath();
      ctx.arc(130, y, 90, Math.PI * 1.8, Math.PI * 0.3);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(382, y, 90, Math.PI * 0.7, Math.PI * 1.2);
      ctx.stroke();
    }

    // Clavicles
    ctx.strokeStyle = 'rgba(200, 200, 200, 0.5)';
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.moveTo(244, 110);
    ctx.quadraticCurveTo(170, 100, 100, 130);
    ctx.moveTo(268, 110);
    ctx.quadraticCurveTo(342, 100, 412, 130);
    ctx.stroke();

    // Heart silhouette
    ctx.fillStyle = 'rgba(160, 160, 160, 0.7)';
    ctx.beginPath();
    ctx.ellipse(220, 280, 55, 75, -0.2, 0, Math.PI * 2);
    ctx.fill();

    // Diaphragm
    ctx.fillStyle = '#555';
    ctx.beginPath();
    ctx.moveTo(60, 430);
    ctx.quadraticCurveTo(170, 390, 244, 420);
    ctx.quadraticCurveTo(342, 390, 452, 430);
    ctx.lineTo(452, 512);
    ctx.lineTo(60, 512);
    ctx.closePath();
    ctx.fill();

  } else {
    // Hand/Bone X-Ray
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, 512, 512);

    ctx.fillStyle = '#a0a0a0';
    ctx.fillRect(236, 40, 40, 180);
    ctx.beginPath();
    ctx.arc(256, 220, 36, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillRect(236, 292, 40, 180);
    ctx.beginPath();
    ctx.arc(256, 292, 36, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#000';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(210, 256);
    ctx.lineTo(302, 256);
    ctx.stroke();
    
    ctx.strokeStyle = 'rgba(80, 80, 80, 0.2)';
    ctx.lineWidth = 60;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(256, 20);
    ctx.lineTo(256, 492);
    ctx.stroke();
  }

  const imgData = ctx.getImageData(0, 0, 512, 512);
  const rawIntensity = new Uint8Array(512 * 512);
  for (let i = 0; i < imgData.data.length; i += 4) {
    rawIntensity[i / 4] = Math.round(
      0.299 * imgData.data[i] +
      0.587 * imgData.data[i + 1] +
      0.114 * imgData.data[i + 2]
    );
  }
  return rawIntensity;
}

export function drawDicomFrame() {
  const canvas = dicomCanvasInstance;
  if (!canvas || !dicomRawPixels) return;

  const ctx = canvas.getContext('2d');
  const cw = canvas.width;
  const ch = canvas.height;

  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, cw, ch);

  const offscreen = document.createElement('canvas');
  offscreen.width = 512;
  offscreen.height = 512;
  const octx = offscreen.getContext('2d');
  const oimgData = octx.createImageData(512, 512);

  const lut = new Uint8Array(256);
  const lowBound = dicomLevel - dicomWidth / 2;
  const range = dicomWidth;

  for (let i = 0; i < 256; i++) {
    let val = ((i - lowBound) / range) * 255;
    if (val < 0) val = 0;
    if (val > 255) val = 255;
    lut[i] = dicomInverted ? (255 - val) : val;
  }

  for (let i = 0; i < 512 * 512; i++) {
    const rawVal = dicomRawPixels[i];
    const displayVal = lut[rawVal];
    const pixelIdx = i * 4;
    oimgData.data[pixelIdx] = displayVal;     
    oimgData.data[pixelIdx + 1] = displayVal; 
    oimgData.data[pixelIdx + 2] = displayVal; 
    oimgData.data[pixelIdx + 3] = 255;        
  }
  octx.putImageData(oimgData, 0, 0);

  ctx.save();
  ctx.translate(cw / 2 + dicomPanX, ch / 2 + dicomPanY);
  ctx.scale(dicomZoom, dicomZoom);
  ctx.drawImage(offscreen, -256, -256);
  ctx.restore();
}

export function initRecordsListeners() {
  // Confidential Checkbox Toggle
  const confCheckbox = document.getElementById('rec-confidential');
  if (confCheckbox) {
    confCheckbox.addEventListener('change', function() {
      const group = document.getElementById('confidential-password-group');
      if (group) {
        group.style.display = this.checked ? 'block' : 'none';
      }
      const pwInput = document.getElementById('rec-confidential-password');
      if (pwInput && !this.checked) pwInput.value = '';
    });
  }

  // Add Record Form Submit
  const addRecordForm = document.getElementById('add-record-form');
  if (addRecordForm) {
    addRecordForm.addEventListener('submit', async e => {
      e.preventDefault();
      const errEl = document.getElementById('add-error');
      const okEl  = document.getElementById('add-success');
      errEl.style.display = 'none'; okEl.style.display = 'none';

      const type = document.getElementById('rec-type').value;
      const isConfidential = document.getElementById('rec-confidential').checked;
      const confPassword = document.getElementById('rec-confidential-password').value.trim();

      if (isConfidential && !confPassword) {
        errEl.textContent = 'A password is required for confidential (encrypted) records.';
        errEl.style.display = 'block';
        return;
      }

      const dynData = {};
      (DYNAMIC_FIELDS[type]||[]).forEach(f => {
        const el = document.getElementById('dyn-'+f.id);
        if (el && el.value.trim()) dynData[f.id] = el.value.trim();
      });

      const fileInput = document.getElementById('rec-file');
      let file_name = null;
      let file_type = null;
      let file_data = null;

      if (fileInput && fileInput.files && fileInput.files.length > 0) {
        const file = fileInput.files[0];
        if (file.size > 2 * 1024 * 1024) {
          errEl.textContent = 'Attachment size exceeds the 2MB limit.';
          errEl.style.display = 'block';
          return;
        }
        file_name = file.name;
        file_type = file.type;

        const getBase64 = (f) => new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.readAsDataURL(f);
          reader.onload = () => resolve(reader.result);
          reader.onerror = error => reject(error);
        });

        try {
          const dataUrl = await getBase64(file);
          file_data = dataUrl.split(',')[1];
        } catch(err) {
          errEl.textContent = 'Failed to read file attachment.';
          errEl.style.display = 'block';
          return;
        }
      }

      const payload = {
        patient_id:             document.getElementById('rec-patient-id').value.trim(),
        record_type:            type,
        title:                  document.getElementById('rec-title').value.trim(),
        doctor_name:            document.getElementById('rec-doctor').value.trim(),
        institution:            document.getElementById('rec-institution').value.trim(),
        record_date:            document.getElementById('rec-date').value,
        access_level:           document.getElementById('rec-access').value,
        is_confidential:        isConfidential,
        confidential_password:  isConfidential ? confPassword : null,
        data:                   dynData,
        notes:                  document.getElementById('rec-notes').value.trim(),
        file_name:              file_name,
        file_type:              file_type,
        file_data:              file_data,
      };

      const btn = document.getElementById('btn-add-rec');
      btn.disabled = true; btn.textContent = 'Saving...';
      try {
        const res = await apiFetch('/api/records', { method:'POST', body: JSON.stringify(payload) });
        okEl.textContent = `${res.message} (Block #${res.block_index})`;
        okEl.style.display = 'block';
        
        addNotification('Record Saved', `New ${payload.record_type} record successfully added to block #${res.block_index}.`, 'success');

        document.getElementById('add-record-form').reset();
        document.getElementById('dynamic-fields').innerHTML = '';
        if (fileInput) fileInput.value = '';
        document.getElementById('rec-confidential-password').value = '';
        document.getElementById('confidential-password-group').style.display = 'none';
        
        const user = JSON.parse(localStorage.getItem('vhv_user') || '{}');
        if (user.role === 'vip_patient') {
          document.getElementById('rec-patient-id').value = user.patient_id || '';
        }
        document.getElementById('rec-date').value = new Date().toISOString().split('T')[0];
      } catch(ex) {
        errEl.textContent = ex.message; errEl.style.display = 'block';
      } finally {
        btn.disabled = false; btn.textContent = 'Save to Blockchain';
      }
    });
  }
}
