import secrets
from typing import Optional, List
from core.domain.entities import User, Block
from core.ports.repositories import IUserRepository, IBlockRepository, IAuditRepository
import database.storage as storage

class LMDBUserRepository(IUserRepository):
    def save_user(self, user: User) -> None:
        storage.save_user(user.to_dict())

    def load_user(self, username: str) -> Optional[User]:
        data = storage.load_user(username)
        if data:
            return User.from_dict(data)
        return None

    def load_all_users(self) -> List[User]:
        users_data = storage.load_all_users()
        return [User.from_dict(u) for u in users_data]

    def user_exists(self, username: str) -> bool:
        return storage.user_exists(username)

    def delete_user(self, username: str) -> bool:
        return storage.delete_user(username)


class LMDBBlockRepository(IBlockRepository):
    def save_block(self, project_name: str, block: Block) -> None:
        storage.save_block_to_db(project_name, block.index, block.to_dict())

    def load_all_blocks(self, project_name: str) -> List[Block]:
        raw_blocks = storage.load_all_blocks(project_name)
        blocks = []
        for b in raw_blocks:
            pwd_hash = self.load_block_pwd_hash(project_name, b["index"])
            block = Block(
                index=b["index"],
                timestamp=b["timestamp"],
                data=b["data"],
                previous_hash=b["previous_hash"],
                signature=b["signature"],
                is_protected=b.get("is_protected", False),
                protection_password=pwd_hash,
                nonce=b.get("nonce", secrets.token_hex(16)),
                device_id=b.get("device_id"),
                hash=b.get("hash"),
                merkle_root=b.get("merkle_root"),
            )
            blocks.append(block)
        return blocks

    def get_last_index(self, project_name: str) -> int:
        if not self.project_exists(project_name):
            return -1
        try:
            env = storage.open_db(project_name)
            with env.begin(write=False) as txn:
                val = txn.get(b"meta_last_index")
                if val:
                    return int(val.decode("utf-8"))
        except Exception:
            pass
        
        # Fallback
        blocks = storage.load_all_blocks(project_name)
        if blocks:
            return blocks[-1]["index"]
        return -1

    def project_exists(self, project_name: str) -> bool:
        return storage.project_exists(project_name)

    def create_project(self, project_name: str) -> bool:
        return storage.create_project(project_name)

    def list_projects(self) -> List[str]:
        return storage.list_projects()

    def reset_db(self, project_name: str) -> None:
        storage.reset_db(project_name)

    def save_block_salt(self, project_name: str, block_index: int, salt: bytes) -> None:
        storage.save_block_salt(project_name, block_index, salt)

    def load_block_salt(self, project_name: str, block_index: int) -> Optional[bytes]:
        return storage.load_block_salt(project_name, block_index)

    def get_patient_salt(self, project_name: str) -> bytes:
        return storage.get_patient_salt(project_name)

    def save_patient_salt(self, project_name: str, salt: bytes) -> None:
        storage.save_patient_salt(project_name, salt)

    def save_block_pwd_hash(self, project_name: str, block_index: int, pwd_hash: str) -> None:
        storage.save_block_pwd_hash(project_name, block_index, pwd_hash)

    def load_block_pwd_hash(self, project_name: str, block_index: int) -> Optional[str]:
        return storage.load_block_pwd_hash(project_name, block_index)

    def get_by_date_range(self, project_name: str, start_date: str, end_date: str) -> List[Block]:
        blocks = self.load_all_blocks(project_name)
        result = []
        for b in blocks:
            if isinstance(b.data, dict) and "record_date" in b.data:
                rec_date = b.data["record_date"]
                if start_date <= rec_date <= end_date:
                    result.append(b)
        return result

    def get_by_type(self, project_name: str, record_type: str) -> List[Block]:
        blocks = self.load_all_blocks(project_name)
        result = []
        for b in blocks:
            if isinstance(b.data, dict) and b.data.get("record_type") == record_type:
                result.append(b)
        return result


class LMDBAuditRepository(IAuditRepository):
    def append_audit_log(
        self,
        project_name: str,
        action: str,
        username: str,
        block_index: Optional[int] = None,
        device_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        storage.append_audit_log(project_name, action, username, block_index, device_id, extra)

    def load_audit_logs(self, project_name: str, limit: int = 100) -> List[dict]:
        return storage.load_audit_logs(project_name, limit)

    def append_access_log(
        self,
        project_name: str,
        username: str,
        action: str,
        device_id: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        storage.append_access_log(project_name, username, action, device_id, extra)

    def load_access_logs(self, project_name: str, limit: int = 100) -> List[dict]:
        return storage.load_access_logs(project_name, limit)
