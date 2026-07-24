import os
import sqlite3
import time
from typing import Optional

# Dynamic PostgreSQL import
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    POSTGRES_AVAILABLE = True
except ImportError:
    psycopg2 = None
    RealDictCursor = None
    POSTGRES_AVAILABLE = False

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQLITE_PATH = os.path.join(_PROJECT_ROOT, "database", "vault.db")

class SQLDatabaseManager:
    def __init__(self):
        self.db_url = os.getenv("VHV_DATABASE_URL")
        self.is_postgres = False
        
        # Check environment and try PostgreSQL
        if self.db_url and POSTGRES_AVAILABLE:
            try:
                # Test connection
                conn = psycopg2.connect(self.db_url)
                conn.close()
                self.is_postgres = True
                print("[SQL DB] Connected successfully to PostgreSQL database.")
            except Exception as e:
                print(f"[SQL DB Warning] Failed to connect to PostgreSQL ({e}). Falling back to SQLite.")
        elif self.db_url and not POSTGRES_AVAILABLE:
            print("[SQL DB Warning] VHV_DATABASE_URL is set but psycopg2 is not installed. Falling back to SQLite.")

        if not self.is_postgres:
            print(f"[SQL DB] Using SQLite database at: {DEFAULT_SQLITE_PATH}")
            # Ensure database directory exists
            os.makedirs(os.path.dirname(DEFAULT_SQLITE_PATH), exist_ok=True)
            
        self.init_db()

    def get_connection(self):
        if self.is_postgres:
            conn = psycopg2.connect(self.db_url)
            # Use RealDictCursor to act like dict-like objects
            return conn
        else:
            conn = sqlite3.connect(DEFAULT_SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def init_db(self):
        """Creates tables if they do not exist."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Determine syntax compatibility
        serial_type = "SERIAL" if self.is_postgres else "INTEGER"
        text_type = "TEXT"
        boolean_type = "BOOLEAN"
        double_type = "DOUBLE PRECISION" if self.is_postgres else "REAL"

        try:
            # Users Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR(100) PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    full_name VARCHAR(100) NOT NULL,
                    specialty VARCHAR(100),
                    institution VARCHAR(100),
                    patient_id VARCHAR(100),
                    clearance VARCHAR(50),
                    totp_secret VARCHAR(100),
                    totp_enabled {boolean_type} DEFAULT FALSE,
                    wallet_address VARCHAR(100)
                )
            """)
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(100)")
            except Exception:
                pass

            # Appointments Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS appointments (
                    id VARCHAR(100) PRIMARY KEY,
                    patient_id VARCHAR(100) NOT NULL,
                    doctor_name VARCHAR(100) NOT NULL,
                    department VARCHAR(100) NOT NULL,
                    appointment_date VARCHAR(50) NOT NULL,
                    appointment_time VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    notes {text_type}
                )
            """)

            # Notifications Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS notifications (
                    id VARCHAR(100) PRIMARY KEY,
                    patient_id VARCHAR(100) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message {text_type} NOT NULL,
                    severity VARCHAR(50) NOT NULL,
                    timestamp {double_type} NOT NULL,
                    read {boolean_type} DEFAULT FALSE
                )
            """)

            # Token Blacklist Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS blacklisted_tokens (
                    jti VARCHAR(255) PRIMARY KEY,
                    exp {double_type} NOT NULL
                )
            """)

            # Social Recovery Guardians Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS guardians (
                    username VARCHAR(100) NOT NULL,
                    guardian_identifier VARCHAR(255) NOT NULL,
                    PRIMARY KEY (username, guardian_identifier)
                )
            """)

            # Social Recovery Requests Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS recovery_requests (
                    recovery_id VARCHAR(100) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    new_wallet_address VARCHAR(100) NOT NULL,
                    guardians_json {text_type} NOT NULL,
                    approvals_json {text_type} NOT NULL,
                    created_at {double_type} NOT NULL,
                    status VARCHAR(50) NOT NULL
                )
            """)
            # WebAuthn / Passkeys Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS webauthn_credentials (
                    credential_id VARCHAR(255) PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    public_key {text_type} NOT NULL,
                    sign_count INTEGER DEFAULT 0,
                    created_at {double_type} NOT NULL
                )
            """)
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO webauthn_credentials (credential_id, username, public_key, created_at) VALUES (?, ?, ?, ?)",
                    ("passkey_default_demo", "vip001", "pubkey_secp256r1_demo_seed", time.time())
                )
            except Exception:
                pass

            # Emergency QR Sessions Table (hastanın ürettiği QR tokenlar)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS emergency_qr_sessions (
                    session_id   VARCHAR(100) PRIMARY KEY,
                    patient_id   VARCHAR(100) NOT NULL,
                    token_hash   VARCHAR(64)  NOT NULL,
                    issued_by    VARCHAR(100) NOT NULL,
                    issued_at    {double_type} NOT NULL,
                    expires_at   {double_type} NOT NULL,
                    status       VARCHAR(20) DEFAULT 'active'
                )
            """)

            # Emergency Activations Table (ambulans/acil servis aktivasyonları)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS emergency_activations (
                    activation_id VARCHAR(100) PRIMARY KEY,
                    session_id    VARCHAR(100) NOT NULL,
                    patient_id    VARCHAR(100) NOT NULL,
                    responder_id  VARCHAR(200),
                    location      VARCHAR(500),
                    reason        VARCHAR(500),
                    activated_at  {double_type} NOT NULL,
                    expires_at    {double_type} NOT NULL,
                    status        VARCHAR(20) DEFAULT 'active',
                    audit_json    {text_type}
                )
            """)

            # Dead-Man's Switch Configs Table (Miras Kilidi Yapılandırması)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS deadman_configs (
                    patient_id        VARCHAR(100) PRIMARY KEY,
                    inactivity_days   INTEGER DEFAULT 90,
                    last_heartbeat    {double_type} NOT NULL,
                    status            VARCHAR(20) DEFAULT 'active',
                    beneficiaries_json {text_type},
                    created_at        {double_type} NOT NULL,
                    updated_at        {double_type} NOT NULL
                )
            """)

            # Dead-Man's Switch Audit Logs Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS deadman_logs (
                    log_id       VARCHAR(100) PRIMARY KEY,
                    patient_id   VARCHAR(100) NOT NULL,
                    event_type   VARCHAR(50) NOT NULL,
                    timestamp    {double_type} NOT NULL,
                    details_json {text_type}
                )
            """)

            # ZKP Commitments Table (Sıfır Bilgi Kanıtı — Pedersen Commitment Kayıtları)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS zkp_commitments (
                    id                   VARCHAR(100) PRIMARY KEY,
                    patient_id           VARCHAR(100) NOT NULL,
                    claim_type           VARCHAR(100) NOT NULL,
                    claim_label          VARCHAR(200) NOT NULL,
                    commitment_hex       {text_type} NOT NULL,
                    proof_metadata_json  {text_type},
                    created_at           {double_type} NOT NULL
                )
            """)

            # Rate Limits Table


            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    ip VARCHAR(100) NOT NULL,
                    timestamp {double_type} NOT NULL
                )
            """)

            conn.commit()
            print("[SQL DB] Tables initialized successfully.")
        except Exception as e:
            conn.rollback()
            print(f"[SQL DB Error] Schema initialization failed: {e}")
            raise e
        finally:
            cursor.close()
            conn.close()

    def seed_default_users(self):
        """Seeds default users if database is empty."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'vip001'")
            row = cursor.fetchone()
            if row and row[0] > 0:
                return  # Default users already seeded
                
            from core.security import hash_password
            defaults = [
                (
                    "USR-ADMIN-001",
                    "admin",
                    hash_password("Admin@2026Secure!"),
                    "admin",
                    "System Administrator",
                    None,
                    None,
                    None,
                    None,
                    None,
                    False
                ),
                (
                    "USR-DOC-001",
                    "dr.smith",
                    hash_password("Doctor@2026Secure!"),
                    "doctor",
                    "Prof. Dr. James Smith",
                    "Cardiology",
                    "VIP Medical Center",
                    None,
                    None,
                    None,
                    False
                ),
                (
                    "USR-VIP-001",
                    "vip001",
                    hash_password("VIPPatient@2026!"),
                    "vip_patient",
                    "Ahmet Karataş",
                    None,
                    None,
                    "VIP-001",
                    "TOP_SECRET",
                    None,
                    False
                ),
            ]
            
            insert_sql = """
                INSERT INTO users (id, username, password_hash, role, full_name, specialty, institution, patient_id, clearance, totp_secret, totp_enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ if self.is_postgres else """
                INSERT INTO users (id, username, password_hash, role, full_name, specialty, institution, patient_id, clearance, totp_secret, totp_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            cursor.executemany(insert_sql, defaults)
            conn.commit()
            print("[SQL DB] Default users seeded successfully.")
            self.seed_default_appointments()
        except Exception as e:
            conn.rollback()
            print(f"[SQL DB Error] Seeding failed: {e}")
        finally:
            cursor.close()
            conn.close()

    def seed_default_appointments(self):
        """Seeds default appointments if database is empty."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM appointments")
            count = cursor.fetchone()[0]
            if count > 0:
                return
                
            defaults = [
                ("apt001", "VIP-001", "Prof. Dr. Ahmet Yilmaz", "Cardiology", "2026-06-12", "10:30", "scheduled", "Routine cardiology follow-up."),
                ("apt002", "VIP-001", "Dr. Sarah Smith", "Neurology", "2026-06-15", "14:00", "scheduled", "Migraine progress review.")
            ]
            
            insert_sql = """
                INSERT INTO appointments (id, patient_id, doctor_name, department, appointment_date, appointment_time, status, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """ if self.is_postgres else """
                INSERT INTO appointments (id, patient_id, doctor_name, department, appointment_date, appointment_time, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor.executemany(insert_sql, defaults)
            conn.commit()
            print("[SQL DB] Default appointments seeded successfully.")
        except Exception as e:
            conn.rollback()
            print(f"[SQL DB Error] Appointments seeding failed: {e}")
        finally:
            cursor.close()
            conn.close()

# Singleton instance
default_sql_db = SQLDatabaseManager()

def blacklist_token(jti: str, exp: float) -> None:
    from infrastructure.repositories.sql_repositories import _to_placeholder
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(_to_placeholder("SELECT 1 FROM blacklisted_tokens WHERE jti = ?"), (jti,))
        if cursor.fetchone():
            cursor.execute(_to_placeholder("UPDATE blacklisted_tokens SET exp = ? WHERE jti = ?"), (exp, jti))
        else:
            cursor.execute(_to_placeholder("INSERT INTO blacklisted_tokens (jti, exp) VALUES (?, ?)"), (jti, exp))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()


def is_token_blacklisted(jti: str) -> bool:
    from infrastructure.repositories.sql_repositories import _to_placeholder
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    try:
        sql = _to_placeholder("SELECT exp FROM blacklisted_tokens WHERE jti = ?")
        cursor.execute(sql, (jti,))
        row = cursor.fetchone()
        if row:
            try:
                exp = float(row[0])
            except (TypeError, KeyError, IndexError, ValueError):
                exp = float(dict(row)["exp"])
            if time.time() > exp:
                return False
            return True
        return False
    finally:
        cursor.close()
        conn.close()


def clean_expired_blacklisted_tokens() -> None:
    from infrastructure.repositories.sql_repositories import _to_placeholder
    conn = default_sql_db.get_connection()
    cursor = conn.cursor()
    try:
        sql = _to_placeholder("DELETE FROM blacklisted_tokens WHERE exp < ?")
        cursor.execute(sql, (time.time(),))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def get_sql_db() -> SQLDatabaseManager:
    return default_sql_db
