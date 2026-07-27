"""
core/services/alert_service.py — Real-Time Security Alert & Anomaly Engine
==========================================================================
Captures critical security events (Break-Glass triggers, rapid failed auth,
unauthorized IP attempts) and records them into an immutable alert queue.
"""

import time
import json
import secrets
from typing import List, Dict, Optional
from database.sql_db import get_sql_db


class AlertService:
    """
    Centralized Security Alert Manager & Anomaly Detection Pipeline.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        db = get_sql_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS security_alerts (
                    alert_id TEXT PRIMARY KEY,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    username TEXT,
                    client_ip TEXT,
                    created_at REAL NOT NULL,
                    acknowledged INTEGER DEFAULT 0,
                    metadata_json TEXT
                )
            """)
            conn.commit()

    def raise_alert(
        self,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        username: Optional[str] = None,
        client_ip: Optional[str] = None,
        extra: Optional[dict] = None
    ) -> str:
        self._ensure_table()
        alert_id = f"alt_{secrets.token_hex(10)}"
        now = time.time()
        meta_json = json.dumps(extra or {})

        db = get_sql_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO security_alerts (alert_id, alert_type, severity, title, description, username, client_ip, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (alert_id, alert_type, severity, title, description, username, client_ip, now, meta_json)
            )
            conn.commit()

        print(f"[SECURITY ALERT - {severity}] {title}: {description} (User: {username}, IP: {client_ip})")
        return alert_id

    def get_recent_alerts(self, limit: int = 50, severity_filter: Optional[str] = None) -> List[Dict]:
        db = get_sql_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            if severity_filter:
                cursor.execute(
                    "SELECT alert_id, alert_type, severity, title, description, username, client_ip, created_at, acknowledged, metadata_json FROM security_alerts WHERE severity = ? ORDER BY created_at DESC LIMIT ?",
                    (severity_filter.upper(), limit)
                )
            else:
                cursor.execute(
                    "SELECT alert_id, alert_type, severity, title, description, username, client_ip, created_at, acknowledged, metadata_json FROM security_alerts ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            rows = cursor.fetchall()

        alerts = []
        for r in rows:
            alerts.append({
                "alert_id": r[0],
                "alert_type": r[1],
                "severity": r[2],
                "title": r[3],
                "description": r[4],
                "username": r[5],
                "client_ip": r[6],
                "created_at": r[7],
                "acknowledged": bool(r[8]),
                "metadata": json.loads(r[9]) if r[9] else {}
            })
        return alerts

    def acknowledge_alert(self, alert_id: str) -> bool:
        db = get_sql_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE security_alerts SET acknowledged = 1 WHERE alert_id = ?", (alert_id,))
            conn.commit()
            return cursor.rowcount > 0


# Global singleton instance
alert_service = AlertService()
