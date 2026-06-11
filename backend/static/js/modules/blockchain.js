/* blockchain.js — VIP Health Vault UI Blockchain Module */
import { apiFetch, patientId, formatTs } from './utils.js';
import { updateChainPill } from './dashboard.js';

export async function loadChainStatus() {
  const box = document.getElementById('chain-status-content');
  const vis = document.getElementById('chain-visual');
  if (!box || !vis) return;

  box.innerHTML = '<div class="loading-spinner">Verifying chain...</div>';
  vis.innerHTML = '';
  try {
    const pid = patientId();
    const [status, records] = await Promise.all([
      apiFetch(`/api/blockchain/${pid}/status`),
      apiFetch(`/api/records/${pid}`)
    ]);
    const valid = status.is_valid;
    updateChainPill(valid);
    box.innerHTML = `
      <div class="chain-stat"><div class="chain-stat-val">${status.chain_length}</div><div class="chain-stat-lbl">Total Blocks</div></div>
      <div class="chain-stat">
        <div class="chain-stat-val" style="color:${valid?'var(--success)':'var(--danger)'}; font-size:18px; font-weight:700">
          ${valid ? 'VALID' : 'BROKEN'}
        </div>
        <div class="chain-stat-lbl">Integrity</div>
      </div>
      <div class="chain-stat">
        <div class="chain-stat-val" style="color:${valid?'var(--success)':'var(--danger);font-size:20px'}">
          ${valid ? '100%' : 'ERROR #' + status.broken_at}
        </div>
        <div class="chain-stat-lbl">Status</div>
      </div>`;

    // Visual chain (show last 8 blocks)
    const recs = records.records.slice(0, 8);
    recs.forEach((r, i) => {
      const broken = status.broken_at !== null && r.block_index >= status.broken_at;
      vis.innerHTML += `
        <div class="chain-block-viz ${broken?'broken-block':'valid-block'}">
          <div class="blk-header">BLOCK #${r.block_index} · ${formatTs(r.timestamp)}</div>
          <div class="blk-hash">${r.hash_preview}</div>
          <div style="margin-top:4px;font-size:11px;color:var(--muted)">${r.title}</div>
        </div>
        ${i < recs.length-1 ? '<div class="chain-connector"></div>' : ''}`;
    });
  } catch(e) { 
    box.innerHTML = `<div class="alert alert-error">${e.message}</div>`; 
  }
}
