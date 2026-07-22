from abc import ABC, abstractmethod
from typing import Any

class IUnitOfWork(ABC):
    @abstractmethod
    def __enter__(self) -> 'IUnitOfWork':
        """Starts a new transaction/unit of work."""
        pass

    @abstractmethod
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Commits if no exception, otherwise rolls back."""
        pass
