import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_e2e_flow():
    print("=== STARTING END-TO-END API TEST ===")
    session = requests.Session()

    # 1. Fetch config and check demo accounts
    print("\n1. Fetching API config...")
    r = session.get(f"{BASE_URL}/api/config")
    if r.status_code != 200:
        print(f"FAILED to get config: {r.status_code} {r.text}")
        sys.exit(1)
    
    config = r.json()
    print("Config response:", config)
    assert config.get("demo_mode") is True
    assert "demo_accounts" in config
    accounts = {acc["role"]: acc for acc in config["demo_accounts"]}
    assert "VIP" in accounts
    assert "DOCTOR" in accounts
    print("Config verification: SUCCESS")

    # Capture CSRF token
    csrf_token = session.cookies.get("csrf_token")
    print(f"CSRF Token captured: {csrf_token}")
    headers = {"X-CSRF-Token": csrf_token}

    # 2. Login as VIP patient
    vip_cred = accounts["VIP"]
    print(f"\n2. Logging in as VIP Patient: {vip_cred['username']}...")
    login_payload = {
        "username": vip_cred["username"],
        "password": vip_cred["password"]
    }
    r = session.post(f"{BASE_URL}/api/auth/login", json=login_payload, headers=headers)
    if r.status_code != 200:
        print(f"FAILED to login as VIP: {r.status_code} {r.text}")
        sys.exit(1)
    
    vip_login_data = r.json()
    vip_token = vip_login_data["access_token"]
    vip_patient_id = vip_login_data["user"]["patient_id"]
    print(f"VIP Login Success! Username: {vip_login_data['user']['username']}, Patient ID: {vip_patient_id}")
    
    # 3. Check me endpoint for VIP
    session.headers.update({"Authorization": f"Bearer {vip_token}"})
    r = session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200
    print("Me response for VIP:", r.json())

    # 4. Grant consent to Doctor dr.smith for 'all' records
    doc_cred = accounts["DOCTOR"]
    doc_username = doc_cred["username"]
    print(f"\n4. Granting consent to Doctor '{doc_username}' for 'all' records...")
    consent_payload = {
        "patient_id": vip_patient_id,
        "doctor_username": doc_username,
        "record_type": "all",
        "duration_days": 30
    }
    
    # Update csrf token since session cookies might have updated
    csrf_token = session.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf_token}
    
    r = session.post(f"{BASE_URL}/api/consent", json=consent_payload, headers=headers)
    if r.status_code != 200:
        print(f"FAILED to grant consent: {r.status_code} {r.text}")
        sys.exit(1)
    print("Consent granted successfully:", r.json())

    # Verify consent in consents list
    r = session.get(f"{BASE_URL}/api/consent/{vip_patient_id}")
    assert r.status_code == 200
    consents_list = r.json().get("consents", [])
    print("Active Consents:", consents_list)
    has_consent = any(c["doctor_username"] == doc_username and c["record_type"] == "all" for c in consents_list)
    assert has_consent is True
    print("Active consent verification: SUCCESS")

    # 5. Logout VIP
    print("\n5. Logging out VIP patient...")
    r = session.post(f"{BASE_URL}/api/auth/logout", headers=headers)
    assert r.status_code == 200
    print("Logged out successfully.")

    # Reset session headers/auth
    session.headers.pop("Authorization", None)

    # 6. Login as Doctor
    print(f"\n6. Logging in as Doctor: {doc_username}...")
    login_payload = {
        "username": doc_username,
        "password": doc_cred["password"]
    }
    # Update csrf
    csrf_token = session.cookies.get("csrf_token")
    headers = {"X-CSRF-Token": csrf_token}
    r = session.post(f"{BASE_URL}/api/auth/login", json=login_payload, headers=headers)
    if r.status_code != 200:
        print(f"FAILED to login as Doctor: {r.status_code} {r.text}")
        sys.exit(1)
    
    doc_login_data = r.json()
    doc_token = doc_login_data["access_token"]
    print("Doctor Login Success!")

    # 7. Access Patient VIP-001 records as Doctor
    session.headers.update({"Authorization": f"Bearer {doc_token}"})
    print(f"\n7. Retrieving patient '{vip_patient_id}' records as Doctor '{doc_username}'...")
    r = session.get(f"{BASE_URL}/api/records/{vip_patient_id}")
    if r.status_code != 200:
        print(f"FAILED to access records: {r.status_code} {r.text}")
        sys.exit(1)
    
    records_data = r.json()
    print(f"Access SUCCESS! Doctor retrieved {len(records_data.get('records', []))} records.")

    # 8. Log out Doctor
    print("\n8. Logging out Doctor...")
    csrf_token = session.cookies.get("csrf_token")
    r = session.post(f"{BASE_URL}/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert r.status_code == 200
    session.headers.pop("Authorization", None)

    # 9. Login as VIP to Revoke Consent
    print("\n9. Logging in as VIP Patient to revoke consent...")
    login_payload = {
        "username": vip_cred["username"],
        "password": vip_cred["password"]
    }
    csrf_token = session.cookies.get("csrf_token")
    r = session.post(f"{BASE_URL}/api/auth/login", json=login_payload, headers={"X-CSRF-Token": csrf_token})
    vip_token = r.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {vip_token}"})

    print(f"Revoking consent for Doctor '{doc_username}'...")
    csrf_token = session.cookies.get("csrf_token")
    r = session.delete(f"{BASE_URL}/api/consent/{vip_patient_id}/{doc_username}/all", headers={"X-CSRF-Token": csrf_token})
    if r.status_code != 200:
        print(f"FAILED to revoke consent: {r.status_code} {r.text}")
        sys.exit(1)
    print("Consent revoked successfully.")

    # Log out VIP
    csrf_token = session.cookies.get("csrf_token")
    session.post(f"{BASE_URL}/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    session.headers.pop("Authorization", None)

    # 10. Login as Doctor again and verify access is DENIED
    print("\n10. Logging in as Doctor to verify access is denied...")
    login_payload = {
        "username": doc_username,
        "password": doc_cred["password"]
    }
    csrf_token = session.cookies.get("csrf_token")
    r = session.post(f"{BASE_URL}/api/auth/login", json=login_payload, headers={"X-CSRF-Token": csrf_token})
    doc_token = r.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {doc_token}"})

    print(f"Attempting to retrieve patient '{vip_patient_id}' records as Doctor '{doc_username}' (should return empty list due to revoked consent)...")
    r = session.get(f"{BASE_URL}/api/records/{vip_patient_id}")
    print(f"Status Code: {r.status_code}, Response: {r.text}")
    assert r.status_code == 200
    res_data = r.json()
    assert len(res_data.get("records", [])) == 0
    print("Consent revocation and records filtering verification: SUCCESS")

    print("\n=== ALL END-TO-END FLOW TESTS COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_e2e_flow()
