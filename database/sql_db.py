import os
import sqlite3
import time

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
            # NOTE: No passkey credential is ever seeded here. A pre-seeded
            # credential would let anyone authenticate as its owner straight from
            # the login screen. Passkeys must be enrolled per device by the
            # account holder via POST /api/v1/auth/webauthn/register.
            cursor.execute(
                "DELETE FROM webauthn_credentials WHERE credential_id = 'passkey_default_demo'"
            )

            # Rate Limits Table
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    ip VARCHAR(100) NOT NULL,
                    timestamp {double_type} NOT NULL
                )
            """)

            # Patient Pseudonyms Table (Identity Decoupling)
            # Maps real patient IDs to cryptographic anonymous identifiers.
            # If the clinical data store is breached, records cannot be
            # linked back to real identities without this mapping table.
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS patient_pseudonyms (
                    patient_id   VARCHAR(100) PRIMARY KEY,
                    anon_id      VARCHAR(100) UNIQUE NOT NULL,
                    created_at   {double_type} NOT NULL
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
                # The Security Officer exists so the M-of-N Dual-Control policy is
                # actually satisfiable: an administrator cannot co-sign their own
                # request, so a second privileged principal is required.
                (
                    "USR-SECOFF-001",
                    "sec.officer",
                    hash_password("SecOfficer@2026!"),
                    "security_officer",
                    "Security Officer",
                    None,
                    None,
                    None,
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

            # Seed per account rather than all-or-nothing, so an existing database
            # picks up accounts added in later versions.
            seeded = 0
            for account in defaults:
                cursor.execute(
                    "SELECT COUNT(*) FROM users WHERE username = %s" if self.is_postgres
                    else "SELECT COUNT(*) FROM users WHERE username = ?",
                    (account[1],)
                )
                row = cursor.fetchone()
                if row and row[0] > 0:
                    continue
                cursor.execute(insert_sql, account)
                seeded += 1
            conn.commit()
            if seeded:
                print(f"[SQL DB] Default users seeded successfully ({seeded} account(s)).")
        except Exception as e:
            conn.rollback()
            print(f"[SQL DB Error] Seeding failed: {e}")
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
