"""
scripts/e2e_smoke.py — end-to-end smoke test against a running demo.

Walks the consent lifecycle through the real HTTP API, the way a browser would
(httpOnly cookie + CSRF double-submit token):

  1. the demo accounts are advertised by /config;
  2. the client gives the practitioner consent for all records;
  3. the practitioner sees the client on their list and can read the file;
  4. the client revokes consent;
  5. the practitioner's access to the file is closed (403);
  6. consent is given back, so the demo is left as it was found.

It signs in only twice (one session per account), well within the demo's limit
of 5 sign-ins per IP per minute.

Usage (against the Docker demo on :8000):
    python scripts/e2e_smoke.py
    python scripts/e2e_smoke.py http://127.0.0.1:8093
"""

import sys

import httpx

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000") + "/api/v1"
CLIENT_ID = "CL-001"


def session(accounts: dict, role: str) -> httpx.Client:
    """A signed-in session for the demo account with this role."""
    account = accounts[role]
    s = httpx.Client(base_url=BASE_URL, timeout=120)
    s.get("/config")                                  # sets the csrf_token cookie
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf_token")
    r = s.post("/auth/login", json={"username": account["username"], "password": account["password"]})
    check(r.status_code == 200, f"{role} signs in", r)
    return s


def check(ok: bool, what: str, response=None):
    if not ok:
        detail = f" -> {response.status_code} {response.text[:200]}" if response is not None else ""
        print(f"FAILED: {what}{detail}")
        sys.exit(1)
    print(f"ok  {what}")


def grant_all(client_session: httpx.Client, practitioner: str, days: int):
    r = client_session.post("/consent", json={
        "patient_id": CLIENT_ID, "doctor_username": practitioner,
        "record_type": "all", "duration_days": days})
    check(r.status_code == 200, f"client gives {practitioner} consent for all records", r)


def main():
    print(f"=== Mahrem end-to-end smoke test against {BASE_URL} ===")

    r = httpx.get(f"{BASE_URL}/config", timeout=30)
    config = r.json()
    check(r.status_code == 200 and config.get("demo_mode") is True, "demo mode is on", r)
    accounts = {a["role"]: a for a in config.get("demo_accounts", [])}
    check({"CLIENT", "PRACTITIONER"} <= set(accounts), "demo client and practitioner accounts exist")
    practitioner = accounts["PRACTITIONER"]["username"]

    client = session(accounts, "CLIENT")
    prac = session(accounts, "PRACTITIONER")

    # Consent opens the file.
    grant_all(client, practitioner, days=1)
    r = prac.get("/practitioner/clients")
    listed = {c["patient_id"]: c["status"] for c in r.json().get("clients", [])}
    check(listed.get(CLIENT_ID) == "consented", "the client is on the practitioner's list", r)
    r = prac.get(f"/records/{CLIENT_ID}")
    check(r.status_code == 200 and r.json().get("records"), "the practitioner reads the client's records", r)

    # Revoking consent closes it.
    r = client.delete(f"/consent/{CLIENT_ID}/{practitioner}/all")
    check(r.status_code == 200, "client revokes consent", r)
    r = prac.get(f"/records/{CLIENT_ID}")
    check(r.status_code == 403, "the practitioner's access is closed after revocation", r)

    # Leave the demo as we found it.
    grant_all(client, practitioner, days=90)

    for s in (client, prac):
        s.post("/auth/logout")
    print("=== all end-to-end checks passed ===")


if __name__ == "__main__":
    main()
