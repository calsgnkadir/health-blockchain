from abc import ABC, abstractmethod
from typing import Optional, Tuple

class IEncryptionStrategy(ABC):
    @abstractmethod
    def encrypt_data(self, data: str, password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        """
        Encrypts plaintext data using a password and optional salt.
        Returns a tuple of (base64_encoded_ciphertext, salt_used).
        """
        pass

    @abstractmethod
    def decrypt_data(self, encrypted_data: str, password: str, salt: bytes) -> str:
        """
        Decrypts base64_encoded_ciphertext using a password and salt.
        Returns the plaintext string.
        """
        pass
