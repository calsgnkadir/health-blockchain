from typing import Optional, Tuple
from core.ports.cryptography import IEncryptionStrategy
from core.security import (
    encrypt_data as aes_encrypt_data,
    decrypt_data as aes_decrypt_data,
    encrypt_data_legacy as fernet_encrypt_data,
    decrypt_data_legacy as fernet_decrypt_data,
)

class AESGCMStrategy(IEncryptionStrategy):
    def encrypt_data(self, data: str, password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        return aes_encrypt_data(data, password, salt)

    def decrypt_data(self, encrypted_data: str, password: str, salt: bytes) -> str:
        return aes_decrypt_data(encrypted_data, password, salt)


class FernetLegacyStrategy(IEncryptionStrategy):
    def encrypt_data(self, data: str, password: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
        encrypted = fernet_encrypt_data(data, password)
        return encrypted, salt or b""

    def decrypt_data(self, encrypted_data: str, password: str, salt: bytes) -> str:
        return fernet_decrypt_data(encrypted_data, password)
