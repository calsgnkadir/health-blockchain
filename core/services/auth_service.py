from datetime import datetime, timezone
import uuid as _uuid
from typing import Optional, List
from core.domain.entities import User
from core.ports.repositories import IUserRepository
from core.security import verify_password, hash_password, get_device_id
import core.totp as totp
from core.events.event_bus import event_bus, SystemAuditEvent

class AuthService:
    def __init__(self, user_repo: IUserRepository):
        self.user_repo = user_repo

    def authenticate(self, username: str, password: str, client_ip: str) -> Optional[User]:
        user = self.user_repo.load_user(username)
        device_id = get_device_id()
        if not user or not verify_password(password, user.password_hash):
            if user:
                event_bus.publish(SystemAuditEvent(
                    project_name="__system__",
                    action="LOGIN_FAILED",
                    username=username,
                    device_id=device_id,
                    extra={"ip": client_ip}
                ))
            return None
        return user

    def authenticate_wallet(self, wallet_address: str, client_ip: str) -> Optional[User]:
        all_users = self.user_repo.load_all_users()
        clean_addr = wallet_address.lower().strip()
        matched_user = None
        for u in all_users:
            if u.wallet_address and u.wallet_address.lower().strip() == clean_addr:
                matched_user = u
                break
        
        device_id = get_device_id()
        if not matched_user:
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="WALLET_LOGIN_FAILED",
                username=wallet_address,
                device_id=device_id,
                extra={"ip": client_ip, "reason": "No user linked to wallet address"}
            ))
            return None

        return matched_user

    def link_wallet(self, user: User, wallet_address: str) -> None:
        user.wallet_address = wallet_address.strip()
        self.user_repo.save_user(user)
        event_bus.publish(SystemAuditEvent(
            project_name="__system__",
            action="WALLET_LINKED",
            username=user.username,
            device_id=get_device_id(),
            extra={"wallet_address": wallet_address}
        ))

    def login_success(self, user: User, client_ip: str) -> None:
        event_bus.publish(SystemAuditEvent(
            project_name="__system__",
            action="LOGIN_SUCCESS",
            username=user.username,
            device_id=get_device_id(),
            extra={"ip": client_ip, "role": user.role, "mfa": bool(user.totp_enabled)}
        ))

    def setup_2fa(self, user: User) -> dict:
        secret = totp.generate_totp_secret()
        user.totp_secret = secret
        self.user_repo.save_user(user)
        
        uri = totp.get_totp_uri(user.username, secret)
        qr_code = totp.get_totp_qr_base64(uri)
        return {
            "secret": secret,
            "qr_code": qr_code
        }

    def enable_2fa(self, user: User, code: str) -> bool:
        secret = user.totp_secret
        if not secret:
            return False
            
        if totp.verify_totp(secret, code):
            user.totp_enabled = True
            self.user_repo.save_user(user)
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="2FA_ENABLED",
                username=user.username,
                device_id=get_device_id()
            ))
            return True
        return False

    def disable_2fa(self, user: User, code: str) -> bool:
        if not user.totp_enabled:
            return False
            
        secret = user.totp_secret
        if not secret:
            return False
            
        if totp.verify_totp(secret, code):
            user.totp_enabled = False
            user.totp_secret = None
            self.user_repo.save_user(user)
            event_bus.publish(SystemAuditEvent(
                project_name="__system__",
                action="2FA_DISABLED",
                username=user.username,
                device_id=get_device_id()
            ))
            return True
        return False

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        full_name: str,
        patient_id: Optional[str] = None,
        specialty: Optional[str] = None,
        institution: Optional[str] = None,
        creator_username: str = "system"
    ) -> User:
        user_id = f"USR-{role.upper()}-{_uuid.uuid4().hex[:6].upper()}"
        new_user = User(
            id=user_id,
            username=username,
            password_hash=hash_password(password),
            role=role,
            full_name=full_name,
            patient_id=patient_id,
            specialty=specialty,
            institution=institution,
            totp_secret=None,
            totp_enabled=False
        )
        self.user_repo.save_user(new_user)
        event_bus.publish(SystemAuditEvent(
            project_name="__system__",
            action="USER_CREATED",
            username=creator_username,
            device_id=get_device_id(),
            extra={"new_user": username, "role": role}
        ))
        return new_user
