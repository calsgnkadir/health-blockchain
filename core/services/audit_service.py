from typing import List
from core.ports.repositories import IAuditRepository
from core.services.record_service import RecordService

class AuditService:
    def __init__(self, audit_repo: IAuditRepository, record_service: RecordService):
        self.audit_repo = audit_repo
        self.record_service = record_service

    def get_audit_logs(self, patient_id: str, limit: int = 50, source: str = "db") -> List[dict]:
        project_name = self.record_service._get_project_name(patient_id)
        if source == "blockchain":
            chain = self.record_service.get_chain(patient_id)
            logs = []
            for block in reversed(chain):
                if isinstance(block.data, dict) and block.data.get("type") == "audit":
                    logs.append({
                        "timestamp": block.timestamp,
                        "action": block.data.get("action"),
                        "username": block.data.get("username"),
                        "block_index": block.data.get("target_block_index"),
                        "device_id": block.device_id,
                        **{k: v for k, v in block.data.items() if k not in ("type", "action", "username", "target_block_index", "device_id")}
                    })
            return logs[:limit]
        
        logs = self.audit_repo.load_audit_logs(project_name, limit)
        if not logs:
            return self.get_audit_logs(patient_id, limit, source="blockchain")
        return logs

    def get_access_logs(self, patient_id: str, limit: int = 100, source: str = "db") -> List[dict]:
        project_name = self.record_service._get_project_name(patient_id)
        if source == "blockchain":
            return self.get_audit_logs(patient_id, limit, source="blockchain")
            
        logs = self.audit_repo.load_access_logs(project_name, limit)
        if not logs:
            return self.get_audit_logs(patient_id, limit, source="blockchain")
        return logs
