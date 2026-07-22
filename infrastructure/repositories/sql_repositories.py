from typing import Optional, List
from core.domain.entities import User
from core.ports.repositories import IUserRepository, IAppointmentRepository, INotificationRepository
from database.sql_db import default_sql_db

def _to_placeholder(sql: str) -> str:
    """Helper to convert standard sqlite ? placeholders to PostgreSQL %s if active."""
    if default_sql_db.is_postgres:
        return sql.replace("?", "%s")
    return sql

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    try:
        # For sqlite Row
        return dict(row)
    except (TypeError, ValueError):
        # For postgres/dict row or cursor return
        return dict(row)

class SQLUserRepository(IUserRepository):
    def save_user(self, user: User) -> None:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            # Check if user exists by username
            sql_check = _to_placeholder("SELECT id FROM users WHERE username = ?")
            cursor.execute(sql_check, (user.username,))
            exists = cursor.fetchone()
            
            if exists:
                # Update
                sql_update = _to_placeholder("""
                    UPDATE users 
                    SET password_hash = ?, role = ?, full_name = ?, specialty = ?, 
                        institution = ?, patient_id = ?, clearance = ?, totp_secret = ?, totp_enabled = ?, wallet_address = ?
                    WHERE username = ?
                """)
                cursor.execute(sql_update, (
                    user.password_hash,
                    user.role,
                    user.full_name,
                    user.specialty,
                    user.institution,
                    user.patient_id,
                    user.clearance,
                    user.totp_secret,
                    user.totp_enabled,
                    user.wallet_address,
                    user.username
                ))
            else:
                # Insert
                sql_insert = _to_placeholder("""
                    INSERT INTO users (id, username, password_hash, role, full_name, specialty, institution, patient_id, clearance, totp_secret, totp_enabled, wallet_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """)
                cursor.execute(sql_insert, (
                    user.id,
                    user.username,
                    user.password_hash,
                    user.role,
                    user.full_name,
                    user.specialty,
                    user.institution,
                    user.patient_id,
                    user.clearance,
                    user.totp_secret,
                    user.totp_enabled,
                    user.wallet_address
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def load_user(self, username: str) -> Optional[User]:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("SELECT * FROM users WHERE username = ?")
            cursor.execute(sql, (username,))
            row = cursor.fetchone()
            if row:
                d = _row_to_dict(row)
                # Map db row to User
                # In PostgreSQL, custom cursors return dict, in SQLite,Row returns Row
                # Ensure boolean conversion
                totp_enabled = bool(d.get("totp_enabled"))
                return User(
                    id=d.get("id"),
                    username=d.get("username"),
                    password_hash=d.get("password_hash"),
                    role=d.get("role"),
                    full_name=d.get("full_name"),
                    specialty=d.get("specialty"),
                    institution=d.get("institution"),
                    patient_id=d.get("patient_id"),
                    clearance=d.get("clearance"),
                    totp_secret=d.get("totp_secret"),
                    totp_enabled=totp_enabled,
                    wallet_address=d.get("wallet_address")
                )
            return None
        finally:
            cursor.close()
            conn.close()

    def load_all_users(self) -> List[User]:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users")
            rows = cursor.fetchall()
            users = []
            for row in rows:
                d = _row_to_dict(row)
                totp_enabled = bool(d.get("totp_enabled"))
                users.append(User(
                    id=d.get("id"),
                    username=d.get("username"),
                    password_hash=d.get("password_hash"),
                    role=d.get("role"),
                    full_name=d.get("full_name"),
                    specialty=d.get("specialty"),
                    institution=d.get("institution"),
                    patient_id=d.get("patient_id"),
                    clearance=d.get("clearance"),
                    totp_secret=d.get("totp_secret"),
                    totp_enabled=totp_enabled,
                    wallet_address=d.get("wallet_address")
                ))
            return users
        finally:
            cursor.close()
            conn.close()

    def user_exists(self, username: str) -> bool:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("SELECT 1 FROM users WHERE username = ?")
            cursor.execute(sql, (username,))
            return cursor.fetchone() is not None
        finally:
            cursor.close()
            conn.close()

    def delete_user(self, username: str) -> bool:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("DELETE FROM users WHERE username = ?")
            cursor.execute(sql, (username,))
            # rowcount check
            # For sqlite: cursor.rowcount
            # For postgres: cursor.rowcount
            affected = cursor.rowcount > 0
            conn.commit()
            return affected
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()


class SQLAppointmentRepository(IAppointmentRepository):
    def save_appointment(self, appointment: dict) -> None:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql_check = _to_placeholder("SELECT 1 FROM appointments WHERE id = ?")
            cursor.execute(sql_check, (appointment["id"],))
            exists = cursor.fetchone()
            
            if exists:
                sql_update = _to_placeholder("""
                    UPDATE appointments 
                    SET patient_id = ?, doctor_name = ?, department = ?, appointment_date = ?, 
                        appointment_time = ?, status = ?, notes = ?
                    WHERE id = ?
                """)
                cursor.execute(sql_update, (
                    appointment["patient_id"],
                    appointment["doctor_name"],
                    appointment["department"],
                    appointment["appointment_date"],
                    appointment["appointment_time"],
                    appointment["status"],
                    appointment["notes"],
                    appointment["id"]
                ))
            else:
                sql_insert = _to_placeholder("""
                    INSERT INTO appointments (id, patient_id, doctor_name, department, appointment_date, appointment_time, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """)
                cursor.execute(sql_insert, (
                    appointment["id"],
                    appointment["patient_id"],
                    appointment["doctor_name"],
                    appointment["department"],
                    appointment["appointment_date"],
                    appointment["appointment_time"],
                    appointment["status"],
                    appointment["notes"]
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def load_appointments_by_patient(self, patient_id: str) -> List[dict]:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("SELECT * FROM appointments WHERE patient_id = ?")
            cursor.execute(sql, (patient_id,))
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def delete_appointment(self, appointment_id: str) -> bool:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("DELETE FROM appointments WHERE id = ?")
            cursor.execute(sql, (appointment_id,))
            affected = cursor.rowcount > 0
            conn.commit()
            return affected
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def load_appointment(self, appointment_id: str) -> Optional[dict]:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("SELECT * FROM appointments WHERE id = ?")
            cursor.execute(sql, (appointment_id,))
            row = cursor.fetchone()
            if row:
                return _row_to_dict(row)
            return None
        finally:
            cursor.close()
            conn.close()


class SQLNotificationRepository(INotificationRepository):
    def save_notification(self, notification: dict) -> None:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql_check = _to_placeholder("SELECT 1 FROM notifications WHERE id = ?")
            cursor.execute(sql_check, (notification["id"],))
            exists = cursor.fetchone()
            
            if exists:
                sql_update = _to_placeholder("""
                    UPDATE notifications 
                    SET patient_id = ?, title = ?, message = ?, severity = ?, timestamp = ?, read = ?
                    WHERE id = ?
                """)
                cursor.execute(sql_update, (
                    notification["patient_id"],
                    notification["title"],
                    notification["message"],
                    notification["severity"],
                    notification["timestamp"],
                    notification["read"],
                    notification["id"]
                ))
            else:
                sql_insert = _to_placeholder("""
                    INSERT INTO notifications (id, patient_id, title, message, severity, timestamp, read)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """)
                cursor.execute(sql_insert, (
                    notification["id"],
                    notification["patient_id"],
                    notification["title"],
                    notification["message"],
                    notification["severity"],
                    notification["timestamp"],
                    notification["read"]
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def load_notifications_by_patient(self, patient_id: str) -> List[dict]:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("SELECT * FROM notifications WHERE patient_id = ? ORDER BY timestamp DESC")
            cursor.execute(sql, (patient_id,))
            rows = cursor.fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            cursor.close()
            conn.close()

    def mark_as_read(self, patient_id: str, notification_id: str) -> bool:
        conn = default_sql_db.get_connection()
        cursor = conn.cursor()
        try:
            sql = _to_placeholder("UPDATE notifications SET read = ? WHERE patient_id = ? AND id = ?")
            cursor.execute(sql, (True, patient_id, notification_id))
            affected = cursor.rowcount > 0
            conn.commit()
            return affected
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
