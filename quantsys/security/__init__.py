"""Credential encryption and secure storage.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC) from the
cryptography library. Keys are stored locally and never committed.
"""

from quantsys.security.credential import CredentialManager

__all__ = ["CredentialManager"]
