import threading
from typing import Dict, List, Type, Callable, Any, Optional
from dataclasses import dataclass

class Event:
    pass

@dataclass
class RecordAddedEvent(Event):
    project_name: str
    username: str
    block_index: int
    device_id: str
    is_protected: bool

@dataclass
class RecordReadEvent(Event):
    project_name: str
    username: str
    block_index: int
    device_id: str
    action: str  # e.g., 'BLOCK_READ_ATTEMPT', 'BLOCK_READ_SUCCESS', 'BLOCK_READ_FAILED'
    extra: Optional[dict] = None

@dataclass
class SystemAuditEvent(Event):
    project_name: str
    action: str
    username: str
    device_id: str
    extra: Optional[dict] = None


class EventBus:
    def __init__(self):
        self._listeners: Dict[Type[Event], List[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: Type[Event], listener: Callable[[Any], None]) -> None:
        with self._lock:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(listener)

    def publish(self, event: Event) -> None:
        event_type = type(event)
        listeners = []
        with self._lock:
            if event_type in self._listeners:
                listeners = list(self._listeners[event_type])
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[EventBus] Error in event listener {listener.__name__}: {e}")

# Create global event bus instance
event_bus = EventBus()

# --- Observer handlers for logging ---

def handle_record_added(event: RecordAddedEvent):
    from infrastructure.repositories.lmdb_repositories import LMDBAuditRepository
    audit_repo = LMDBAuditRepository()
    
    audit_repo.append_audit_log(
        event.project_name,
        action="BLOCK_ADDED",
        username=event.username,
        block_index=event.block_index,
        device_id=event.device_id,
        extra={"is_protected": event.is_protected},
    )
    audit_repo.append_access_log(
        event.project_name,
        username=event.username,
        action="BLOCK_ADDED",
        device_id=event.device_id,
        extra={"block_index": event.block_index, "is_protected": event.is_protected},
    )

def handle_record_read(event: RecordReadEvent):
    from infrastructure.repositories.lmdb_repositories import LMDBAuditRepository
    audit_repo = LMDBAuditRepository()
    
    audit_repo.append_audit_log(
        event.project_name,
        action=event.action,
        username=event.username,
        block_index=event.block_index,
        device_id=event.device_id,
        extra=event.extra,
    )
    audit_repo.append_access_log(
        event.project_name,
        username=event.username,
        action=event.action,
        device_id=event.device_id,
        extra={"block_index": event.block_index, **(event.extra or {})},
    )

def handle_system_audit(event: SystemAuditEvent):
    from infrastructure.repositories.lmdb_repositories import LMDBAuditRepository
    audit_repo = LMDBAuditRepository()
    
    audit_repo.append_audit_log(
        event.project_name,
        action=event.action,
        username=event.username,
        device_id=event.device_id,
        extra=event.extra,
    )

# Subscribe audit handlers to events
event_bus.subscribe(RecordAddedEvent, handle_record_added)
event_bus.subscribe(RecordReadEvent, handle_record_read)
event_bus.subscribe(SystemAuditEvent, handle_system_audit)
