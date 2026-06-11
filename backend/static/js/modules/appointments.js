/* appointments.js — VIP Health Vault UI Appointments Module */
import { apiFetch, patientId, emptyState } from './utils.js';
import { addNotification } from './notifications.js';

export async function loadAppointments() {
  const listEl = document.getElementById('appointments-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="loading-spinner">Loading appointments...</div>';
  
  try {
    const res = await apiFetch(`/api/appointments/${patientId()}`);
    if (res.length === 0) {
      listEl.innerHTML = emptyState('No scheduled appointments.');
      return;
    }
    
    listEl.innerHTML = res.map(apt => {
      return `
        <div class="appointment-card glass">
          <div>
            <div style="font-weight: 700; color: #fff; font-size: 15px;">${apt.doctor_name}</div>
            <div style="font-size: 12px; color: var(--gold); margin-top: 4px;">${apt.department}</div>
            <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">Notes: ${apt.notes || 'No notes'}</div>
          </div>
          <div style="text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 8px;">
            <div style="font-size: 13px; font-weight: 600;">📅 ${apt.appointment_date} @ ${apt.appointment_time}</div>
            <span class="badge badge-shared" style="margin-top:2px;">${apt.status.toUpperCase()}</span>
            <button class="btn btn-error btn-sm" style="padding: 4px 10px; font-size: 11px;" onclick="cancelAppointment('${apt.id}')">Cancel</button>
          </div>
        </div>
      `;
    }).join('');
  } catch(ex) {
    listEl.innerHTML = `<div class="alert alert-error">Failed to load appointments: ${ex.message}</div>`;
  }
}

export function showBookAppointmentModal() {
  const modalContent = document.getElementById('modal-content');
  if (!modalContent) return;

  modalContent.innerHTML = `
    <h2 style="font-size:20px;font-weight:700;margin-bottom:20px">Book Specialist Appointment</h2>
    <div id="booking-error" class="alert alert-error" style="display:none;margin-bottom:12px"></div>
    <form id="booking-form" onsubmit="bookAppointment(event)">
      <div class="field-group" style="margin-bottom:14px">
        <label>Department</label>
        <input type="text" id="book-dept" placeholder="Cardiology, Neurology, General Medicine..." required />
      </div>
      <div class="field-group" style="margin-bottom:14px">
        <label>Specialist Doctor</label>
        <select id="book-doctor" required>
          <option value="Prof. Dr. Ahmet Yilmaz">Prof. Dr. Ahmet Yilmaz (Cardiologist)</option>
          <option value="Dr. Sarah Smith">Dr. Sarah Smith (Neurologist)</option>
          <option value="Dr. Elena Carter">Dr. Elena Carter (General Practitioner)</option>
        </select>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:14px">
        <div class="field-group">
          <label>Date</label>
          <input type="date" id="book-date" required />
        </div>
        <div class="field-group">
          <label>Time</label>
          <input type="time" id="book-time" required />
        </div>
      </div>
      <div class="field-group" style="margin-bottom:20px">
        <label>Consultation Notes</label>
        <textarea id="book-notes" placeholder="Please describe clinical symptoms or follow-up reason..." rows="3"></textarea>
      </div>
      <button type="submit" class="btn btn-gold btn-full">CONFIRM CLINIC BOOKING</button>
    </form>
  `;
  
  const today = new Date().toISOString().split('T')[0];
  document.getElementById('book-date').min = today;
  document.getElementById('book-date').value = today;
  
  document.getElementById('modal-overlay').classList.add('open');
}

export async function bookAppointment(event) {
  if (event) event.preventDefault();
  const errEl = document.getElementById('booking-error');
  if (errEl) errEl.style.display = 'none';
  
  const payload = {
    patient_id: patientId(),
    doctor_name: document.getElementById('book-doctor').value,
    department: document.getElementById('book-dept').value.trim(),
    appointment_date: document.getElementById('book-date').value,
    appointment_time: document.getElementById('book-time').value,
    notes: document.getElementById('book-notes').value.trim()
  };
  
  try {
    await apiFetch('/api/appointments', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    if (window.closeModal) window.closeModal();
    addNotification('Appointment Booked', `Appointment scheduled with ${payload.doctor_name} for ${payload.appointment_date} at ${payload.appointment_time}.`, 'success');
    loadAppointments();
  } catch(ex) {
    if (errEl) {
      errEl.textContent = ex.message;
      errEl.style.display = 'block';
    }
  }
}

export async function cancelAppointment(id) {
  if (!confirm("Are you sure you want to cancel this appointment?")) return;
  
  try {
    await apiFetch(`/api/appointments/${id}`, {
      method: 'DELETE'
    });
    addNotification('Appointment Cancelled', 'Your appointment has been successfully cancelled.', 'info');
    loadAppointments();
  } catch(ex) {
    alert("Failed to cancel: " + ex.message);
  }
}
