"""
tests/test_invoices.py — invoices for completed sessions
========================================================
One invoice per completed appointment, numbered per practitioner and year,
with nothing clinical on it and no payment tracking. The practitioner and
their secretary issue invoices; a client sees only their own.
"""

import os
import random
import sys
import time
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app
from core.services import appointment_book, invoicing
from database.sql_db import default_sql_db
from tests.test_appointments import _sql

CLIENT_ID = "CL-001"
PRACTITIONER = "psk.elif"
STRONG = "Enrolled@2026Secure!"
ACCOUNTS = {
    "practitioner": (PRACTITIONER, "Practitioner@2026!"),
    "secretary": ("secretary.ayse", "Secretary@2026!"),
    "client": ("client001", "Client@2026Secure!"),
    "admin": ("admin", "Admin@2026Secure!"),
}


class TestInvoices(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["TESTING"] = "true"
        default_sql_db.seed_default_users()
        cls.client = TestClient(app)
        cls.headers = {}
        for actor, (username, password) in ACCOUNTS.items():
            res = cls.client.post("/api/v1/auth/login", json={"username": username, "password": password})
            assert res.status_code == 200, res.text
            cls.headers[actor] = {"Authorization": f"Bearer {res.json()['access_token']}"}

    def setUp(self):
        os.environ["TESTING"] = "true"
        self.appointments, self.users = [], []

    def tearDown(self):
        for appointment_id in self.appointments:
            _sql("DELETE FROM invoices WHERE appointment_id = ?", (appointment_id,))
            _sql("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        for username in self.users:
            _sql("DELETE FROM users WHERE username = ?", (username,))
            _sql("DELETE FROM enrollment_tokens WHERE username = ?", (username,))

    def _session(self, status="completed", practitioner=PRACTITIONER, days_ago=None):
        appointment_id = appointment_book.add_existing(
            practitioner=practitioner, patient_id=CLIENT_ID,
            starts_at=time.time() - 86400 * (days_ago or random.randint(2, 300)),
            duration_min=50, session_format="In-person", status=status, created_by="test")
        self.appointments.append(appointment_id)
        return appointment_id

    def _issue(self, appointment_id, actor="practitioner", amount="1500", vat=20, headers=None):
        return self.client.post("/api/v1/invoices", headers=headers or self.headers[actor], json={
            "appointment_id": appointment_id, "net_amount": amount, "vat_rate": vat})

    def test_invoice_a_completed_session(self):
        res = self._issue(self._session())
        self.assertEqual(res.status_code, 200, res.text)
        inv = res.json()["invoice"]
        self.assertEqual((inv["net_amount"], inv["vat_amount"], inv["total_amount"]),
                         ("1500.00", "300.00", "1800.00"))
        self.assertEqual(inv["client_name"], "Ahmet Karataş")
        self.assertEqual(inv["practitioner_name"], "Uzm. Psk. Elif Yılmaz")
        self.assertRegex(inv["number"], r"^\d{4}-\d{4}$")
        # Nothing clinical and no payment state on an invoice.
        self.assertEqual(inv["service"], invoicing.SERVICE_LINE)
        for field in ("notes", "diagnosis", "summary", "paid", "payment_status"):
            self.assertNotIn(field, inv)

    def test_numbers_run_in_sequence(self):
        first = self._issue(self._session()).json()["invoice"]["number"]
        second = self._issue(self._session()).json()["invoice"]["number"]
        year, seq = first.split("-")
        self.assertEqual(second, f"{year}-{int(seq) + 1:04d}")

    def test_one_invoice_per_session(self):
        appointment_id = self._session()
        self.assertEqual(self._issue(appointment_id).status_code, 200)
        self.assertEqual(self._issue(appointment_id).status_code, 409)

    def test_only_completed_sessions(self):
        for status in ("scheduled", "cancelled", "no_show"):
            with self.subTest(status=status):
                self.assertEqual(self._issue(self._session(status=status)).status_code, 409)

    def test_amount_and_vat_rules(self):
        appointment_id = self._session()
        for amount, vat in (("0", 20), ("-5", 20), ("10.555", 20), ("1500", 18), ("2000000", 20)):
            with self.subTest(amount=amount, vat=vat):
                self.assertEqual(self._issue(appointment_id, amount=amount, vat=vat).status_code, 422)
        res = self._issue(appointment_id, amount="1234.56", vat=10)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["invoice"]["vat_amount"], "123.46")   # 123.456 rounded half up

    def test_secretary_issues_and_client_sees_own(self):
        res = self._issue(self._session(), actor="secretary")
        self.assertEqual(res.status_code, 200, res.text)
        invoice_id = res.json()["invoice"]["id"]
        mine = {i["id"] for i in self.client.get("/api/v1/invoices", headers=self.headers["client"]).json()["invoices"]}
        self.assertIn(invoice_id, mine)
        self.assertEqual(self.client.get(f"/api/v1/invoices/{invoice_id}", headers=self.headers["client"]).status_code, 200)
        # A client cannot issue one.
        self.assertEqual(self._issue(self._session(), actor="client").status_code, 403)

    def test_the_appointment_list_shows_the_invoice(self):
        appointment_id = self._session(days_ago=3)
        invoice_id = self._issue(appointment_id).json()["invoice"]["id"]
        listed = {a["id"]: a for a in self.client.get("/api/v1/appointments",
                                                      headers=self.headers["practitioner"]).json()["appointments"]}
        self.assertEqual(listed[appointment_id]["invoice_id"], invoice_id)

    def test_another_practitioner_sees_nothing(self):
        invoice_id = self._issue(self._session()).json()["invoice"]["id"]
        username = f"psk.inv{random.randint(1000, 9999)}"
        self.users.append(username)
        res = self.client.post("/api/v1/onboarding/provision", headers=self.headers["admin"], json={
            "username": username, "full_name": "Other Practitioner", "role": "practitioner"})
        self.client.post("/api/v1/onboarding/redeem", json={
            "enrollment_token": res.json()["enrollment_token"], "new_password": STRONG})
        other = {"Authorization": "Bearer " + self.client.post("/api/v1/auth/login", json={
            "username": username, "password": STRONG}).json()["access_token"]}
        self.assertEqual(self.client.get(f"/api/v1/invoices/{invoice_id}", headers=other).status_code, 404)
        self.assertNotIn(invoice_id, {i["id"] for i in self.client.get("/api/v1/invoices", headers=other).json()["invoices"]})
        # ...nor invoice this practitioner's session.
        self.assertEqual(self._issue(self._session(), headers=other).status_code, 404)

    def test_operators_have_no_invoices(self):
        self.assertEqual(self.client.get("/api/v1/invoices", headers=self.headers["admin"]).status_code, 403)

    def test_vat_rounding(self):
        self.assertEqual(invoicing.vat_of(1, 20), 0)      # 0.2 kuruş -> 0
        self.assertEqual(invoicing.vat_of(3, 20), 1)      # 0.6 kuruş -> 1
        self.assertEqual(invoicing.vat_of(150000, 20), 30000)


if __name__ == "__main__":
    unittest.main()
