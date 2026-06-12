import os
import threading
import lmdb
import contextvars
from typing import Dict, Any, List

active_txn = contextvars.ContextVar("active_txn", default=None)
active_project = contextvars.ContextVar("active_project", default=None)


class LMDBConnectionManager:
    """
    Manages process-wide LMDB Environments.
    Provides thread-safe access, environment caching, and automatic resizing on MapFullError.
    """
    def __init__(self, base_dir: str, default_map_size: int = 2 * 1024 * 1024 * 1024):
        self.base_dir = base_dir
        self.default_map_size = default_map_size
        self._envs: Dict[str, lmdb.Environment] = {}
        self._map_sizes: Dict[str, int] = {}
        self._lock = threading.Lock()

    def ensure_projects_dir(self) -> str:
        os.makedirs(self.base_dir, exist_ok=True)
        return self.base_dir

    def get_project_path(self, project_name: str) -> str:
        self.ensure_projects_dir()
        return os.path.join(self.base_dir, project_name)

    def get_db_path(self, project_name: str) -> str:
        project_path = self.get_project_path(project_name)
        os.makedirs(project_path, exist_ok=True)
        return os.path.join(project_path, "chaindata.lmdb")

    def project_exists(self, project_name: str) -> bool:
        return os.path.exists(self.get_project_path(project_name))

    def create_project(self, project_name: str) -> bool:
        project_path = self.get_project_path(project_name)
        if not os.path.exists(project_path):
            os.makedirs(project_path)
            return True
        return False

    def list_projects(self) -> List[str]:
        self.ensure_projects_dir()
        return [
            d for d in os.listdir(self.base_dir)
            if os.path.isdir(os.path.join(self.base_dir, d))
            and not d.startswith("__")
        ]

    def open_db(self, project_name: str) -> lmdb.Environment:
        with self._lock:
            if project_name not in self._envs:
                path = self.get_db_path(project_name)
                if project_name not in self._map_sizes:
                    self._map_sizes[project_name] = self.default_map_size
                
                while True:
                    try:
                        self._envs[project_name] = lmdb.open(path, map_size=self._map_sizes[project_name], subdir=True)
                        break
                    except lmdb.MapFullError:
                        self._map_sizes[project_name] += 100 * 1024 * 1024
            return self._envs[project_name]

    def close_db(self, project_name: str) -> None:
        with self._lock:
            if project_name in self._envs:
                try:
                    self._envs[project_name].close()
                except Exception:
                    pass
                del self._envs[project_name]

    def close_all(self) -> None:
        with self._lock:
            for project_name, env in list(self._envs.items()):
                try:
                    env.close()
                except Exception:
                    pass
                del self._envs[project_name]

    def run_write_transaction(self, project_name: str, txn_func) -> Any:
        current_txn = active_txn.get()
        current_project = active_project.get()
        if current_txn is not None and current_project == project_name:
            return txn_func(current_txn)

        if project_name not in self._map_sizes:
            self._map_sizes[project_name] = self.default_map_size
        
        for attempt in range(5):
            try:
                env = self.open_db(project_name)
                with env.begin(write=True) as txn:
                    result = txn_func(txn)
                return result
            except lmdb.MapFullError:
                self.close_db(project_name)
                self._map_sizes[project_name] += 100 * 1024 * 1024
        raise lmdb.MapFullError("LMDB map size reached and could not be increased.")
