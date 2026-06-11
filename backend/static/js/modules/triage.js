/* triage.js — VIP Health Vault UI AI Triage Chatbot Module */
import { apiFetch } from './utils.js';
import { addNotification } from './notifications.js';

export function loadTriage() {
  const container = document.getElementById('triage-chat-container');
  if (!container) return;

  container.innerHTML = `
    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); padding: 12px; border-radius: 8px; max-width: 80%; align-self: flex-start;">
      <span style="font-weight: 600; color: var(--gold); font-size: 12px; display: block; margin-bottom: 4px;">SYSTEM CLINICAL AI:</span>
      Welcome to the AI Triage Hub. Please describe your symptoms and how long they have persisted so we can assign a clinical prioritization level.
    </div>
  `;
  const inp = document.getElementById('triage-input');
  if (inp) inp.value = '';
  
  const badge = document.getElementById('triage-status-badge');
  if (badge) {
    badge.textContent = 'NO ACTIVE TRIAGE';
    badge.className = '';
    badge.style.background = 'rgba(255,255,255,0.03)';
    badge.style.border = '1px solid var(--border)';
    badge.style.color = 'var(--muted)';
  }
  
  const reason = document.getElementById('triage-reason');
  if (reason) reason.textContent = '—';
  const rec = document.getElementById('triage-recommendation');
  if (rec) rec.textContent = '—';
}

export async function sendTriageSymptom() {
  const input = document.getElementById('triage-input');
  const container = document.getElementById('triage-chat-container');
  if (!input || !container) return;
  const text = input.value.trim();
  if (!text) return;
  
  input.value = '';
  
  const userBubble = document.createElement('div');
  userBubble.className = 'triage-msg triage-msg-user';
  userBubble.innerHTML = `
    <span style="font-weight: 600; color: var(--gold); font-size: 12px; display: block; margin-bottom: 4px;">YOU:</span>
    ${text}
  `;
  container.appendChild(userBubble);
  container.scrollTop = container.scrollHeight;
  
  const thinkingBubble = document.createElement('div');
  thinkingBubble.className = 'triage-msg triage-msg-system';
  thinkingBubble.innerHTML = `
    <span style="font-weight: 600; color: var(--gold); font-size: 12px; display: block; margin-bottom: 4px;">SYSTEM CLINICAL AI:</span>
    <span class="spinner" style="width:12px; height:12px; border-width:1.5px; border-top-color:var(--gold);"></span> Analysing symptom taxonomy...
  `;
  container.appendChild(thinkingBubble);
  container.scrollTop = container.scrollHeight;
  
  try {
    const res = await apiFetch('/api/ai/triage', {
      method: 'POST',
      body: JSON.stringify({
        symptoms: text,
        duration_days: 1
      })
    });
    
    await new Promise(resolve => setTimeout(resolve, 800));
    
    container.removeChild(thinkingBubble);
    
    const sysBubble = document.createElement('div');
    sysBubble.className = 'triage-msg triage-msg-system';
    sysBubble.innerHTML = `
      <span style="font-weight: 600; color: var(--gold); font-size: 12px; display: block; margin-bottom: 4px;">SYSTEM CLINICAL AI:</span>
      <div><strong>Status:</strong> ${res.status}</div>
      <div style="margin-top:4px;"><strong>Reason:</strong> ${res.reason}</div>
      <div style="margin-top:4px;"><strong>Plan:</strong> ${res.recommendation}</div>
      <div style="font-size:10px; color:var(--muted); margin-top:8px;">${res.disclaimer}</div>
    `;
    container.appendChild(sysBubble);
    container.scrollTop = container.scrollHeight;
    
    const badge = document.getElementById('triage-status-badge');
    if (badge) {
      badge.textContent = res.status;
      badge.style.background = '';
      badge.style.border = '';
      badge.style.color = '';
      badge.className = '';
      if (res.level === 'red') {
        badge.classList.add('triage-badge-red');
        addNotification('EMERGENCY TRIAGE ALERT', 'Urgent symptoms detected. Plan: ' + res.recommendation, 'warning');
      } else if (res.level === 'orange') {
        badge.classList.add('triage-badge-orange');
      } else {
        badge.classList.add('triage-badge-green');
      }
    }
    
    const reasonEl = document.getElementById('triage-reason');
    if (reasonEl) reasonEl.textContent = res.reason;
    
    const recEl = document.getElementById('triage-recommendation');
    if (recEl) recEl.textContent = res.recommendation;
    
  } catch(ex) {
    if (thinkingBubble.parentNode) {
      container.removeChild(thinkingBubble);
    }
    const errBubble = document.createElement('div');
    errBubble.className = 'triage-msg triage-msg-system';
    errBubble.style.borderColor = 'var(--danger)';
    errBubble.innerHTML = `<span style="color:var(--danger)">Error: ${ex.message}</span>`;
    container.appendChild(errBubble);
  }
}
