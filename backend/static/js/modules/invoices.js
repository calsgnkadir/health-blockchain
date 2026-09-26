/* invoices.js — session invoices
 *
 * Practitioner and secretary: issue an invoice for a completed session (from
 * the appointment book) and see their invoices. Client: see and print their own.
 * An invoice holds no clinical content and no payment state.
 */
import { apiFetch, escapeHtml, emptyState, getCurrentUser } from './utils.js';

function money(amount) {
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(Number(amount));
}

function day(iso) {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function isClient() {
  return (getCurrentUser() || {}).role === 'client';
}

/* -- Invoices page ---------------------------------------------------- */

export async function loadInvoices() {
  const list = document.getElementById('invoices-list');
  if (!list) return;
  list.innerHTML = '<div class="loading-spinner">Loading...</div>';
  try {
    const d = await apiFetch('/api/invoices');
    if (!d.invoices.length) {
      list.innerHTML = emptyState(isClient()
        ? 'No invoices yet.'
        : 'No invoices yet. Issue one from a completed session in the appointment book.');
      return;
    }
    list.innerHTML = d.invoices.map(inv => `
      <div class="record-card appt-row" style="cursor:default">
        <div class="record-main">
          <div class="record-title">${escapeHtml(inv.number)} · ${escapeHtml(money(inv.total_amount))}</div>
          <div class="record-meta">${escapeHtml(isClient() ? inv.practitioner_name : inv.client_name)} · session of ${escapeHtml(day(inv.session_date))}</div>
        </div>
        <button type="button" class="btn btn-ghost btn-sm" data-action="open-invoice" data-arg="${escapeHtml(inv.id)}">View</button>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<div class="alert alert-error">${escapeHtml(e.message)}</div>`;
  }
}

/* -- One invoice, printable ------------------------------------------- */

export async function openInvoice(id) {
  const overlay = document.getElementById('invoice-overlay');
  const doc = document.getElementById('invoice-doc');
  if (!overlay || !doc) return;
  try {
    const { invoice: inv } = await apiFetch(`/api/invoices/${encodeURIComponent(id)}`);
    doc.innerHTML = `
      <div class="invoice-head">
        <div>
          <div class="invoice-practice">${escapeHtml(inv.practice_name || inv.practitioner_name)}</div>
          <div class="invoice-muted">${escapeHtml(inv.practitioner_name)}</div>
        </div>
        <div class="invoice-title">
          <div>INVOICE</div>
          <div class="invoice-muted">No. ${escapeHtml(inv.number)}</div>
          <div class="invoice-muted">Issued ${escapeHtml(day(inv.issued_at))}</div>
        </div>
      </div>
      <div class="invoice-to">
        <div class="invoice-muted">Billed to</div>
        <div>${escapeHtml(inv.client_name)} <span class="invoice-muted">(${escapeHtml(inv.patient_id)})</span></div>
      </div>
      <table class="invoice-lines">
        <thead><tr><th>Service</th><th>Session date</th><th>Duration</th><th class="num">Amount</th></tr></thead>
        <tbody><tr>
          <td>${escapeHtml(inv.service)}</td>
          <td>${escapeHtml(day(inv.session_date))}</td>
          <td>${escapeHtml(String(inv.duration_min))} min</td>
          <td class="num">${escapeHtml(money(inv.net_amount))}</td>
        </tr></tbody>
        <tfoot>
          <tr><td colspan="3">VAT ${escapeHtml(String(inv.vat_rate))}%</td><td class="num">${escapeHtml(money(inv.vat_amount))}</td></tr>
          <tr class="invoice-total"><td colspan="3">Total</td><td class="num">${escapeHtml(money(inv.total_amount))}</td></tr>
        </tfoot>
      </table>
      <p class="invoice-muted invoice-foot">This invoice lists the service only. It contains no clinical information.</p>`;
    overlay.hidden = false;
  } catch (e) {
    alert('Could not open the invoice: ' + e.message);
  }
}

export function closeInvoice() {
  const overlay = document.getElementById('invoice-overlay');
  if (overlay) overlay.hidden = true;
}

export function printInvoice() {
  window.print();
}

/* -- Issuing, from a completed session in the appointment book ------- */

export function startInvoice(appointmentId) {
  const box = document.getElementById(`appt-actions-${appointmentId}`);
  if (!box) return;
  const id = escapeHtml(appointmentId);
  box.innerHTML = `
    <input type="number" id="inv-amount" min="0.01" step="0.01" placeholder="Net TRY" style="width:110px" />
    <select id="inv-vat">
      <option value="20" selected>VAT 20%</option>
      <option value="10">VAT 10%</option>
      <option value="1">VAT 1%</option>
      <option value="0">VAT 0%</option>
    </select>
    <button type="button" class="btn btn-gold btn-sm" data-action="issue-invoice" data-arg="${id}">Issue</button>
    <button type="button" class="btn btn-ghost btn-sm" data-action="appt-move-cancel">Back</button>`;
  document.getElementById('inv-amount').focus();
}

export async function issueInvoice(appointmentId) {
  const amount = document.getElementById('inv-amount');
  const vat = document.getElementById('inv-vat');
  if (!amount || !amount.value) return;
  try {
    const d = await apiFetch('/api/invoices', {
      method: 'POST',
      body: JSON.stringify({ appointment_id: appointmentId, net_amount: amount.value, vat_rate: Number(vat.value) }),
    });
    if (window.loadAppointments) await window.loadAppointments();
    openInvoice(d.invoice.id);
  } catch (e) {
    alert('Could not issue the invoice: ' + e.message);
  }
}
