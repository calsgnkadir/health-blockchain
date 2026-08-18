from typing import Any, Callable, List
from core.ports.unit_of_work import IUnitOfWork
import database.storage as storage

class LMDBUnitOfWork(IUnitOfWork):
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.env = None
        self.txn = None
        self.token_txn = None
        self.token_project = None
        self.token_hooks = None
        self.hooks: List[Callable[[], Any]] = []

    def __enter__(self) -> 'LMDBUnitOfWork':
        self.env = storage.open_db(self.project_name)
        self.txn = self.env.begin(write=True)
        self.token_txn = storage.active_txn.set(self.txn)
        self.token_project = storage.active_project.set(self.project_name)
        self.token_hooks = storage.after_commit_hooks.set(self.hooks)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self.txn.abort()
            else:
                self.txn.commit()
        finally:
            storage.active_txn.reset(self.token_txn)
            storage.active_project.reset(self.token_project)
            storage.after_commit_hooks.reset(self.token_hooks)

        # Work that must read the chain as it now stands on disk — a reader inside
        # the transaction above would still see the pre-write snapshot.
        if exc_type is None:
            for hook in self.hooks:
                try:
                    hook()
                except Exception as e:
                    print(f"[UnitOfWork Warning] after-commit hook failed: {e}")
        self.hooks = []
