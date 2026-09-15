"""Secure credential storage with Fernet symmetric encryption.

Credentials are encrypted at rest using AES-128-CBC with HMAC
authentication (Fernet). The encryption key is stored in:
  1. Environment variable QUANTSYS_KEY (highest priority)
  2. ~/.quantsys/key (user home)
  3. Project root .secrets/key (fallback, for development)

Usage::

    mgr = CredentialManager()
    mgr.save_broker_credentials("galaxy", "user123", "pass456")
    user, pwd = mgr.get_broker_credentials("galaxy")
"""

import base64
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class CredentialManager:
    """Manage encrypted broker and API credentials."""

    _KEY_ENV = "QUANTSYS_KEY"
    _SECRETS_DIR = ".secrets"

    def __init__(self, project_root: str | Path = None):
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent
        self._project_root = Path(project_root)
        self._secrets_dir = self._project_root / self._SECRETS_DIR
        self._key = self._load_or_generate_key()
        self._fernet = None

    def _load_or_generate_key(self) -> bytes:
        """Load encryption key from env, home dir, or generate new one."""
        # 1. Environment variable (for production)
        env_key = os.environ.get(self._KEY_ENV)
        if env_key:
            logger.debug("Using encryption key from environment variable")
            return base64.urlsafe_b64decode(env_key.encode())

        # 2. User home directory
        home_key = Path.home() / ".quantsys" / "key"
        if home_key.exists():
            logger.debug("Using encryption key from home directory")
            return home_key.read_bytes()

        # 3. Project secrets directory (generate if needed)
        self._secrets_dir.mkdir(parents=True, exist_ok=True)
        project_key = self._secrets_dir / "key"
        if project_key.exists():
            logger.debug("Using encryption key from project secrets")
            return project_key.read_bytes()

        # Generate new key
        from cryptography.fernet import Fernet

        new_key = Fernet.generate_key()
        project_key.write_bytes(new_key)
        project_key.chmod(0o600)
        logger.info(f"Generated new encryption key at {project_key}")
        return new_key

    @property
    def _cipher(self):
        """Lazy-load Fernet cipher."""
        if self._fernet is None:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(self._key)
        return self._fernet

    # -- Broker credentials ------------------------------------------------

    def save_broker_credentials(
        self, broker: str, username: str, password: str, **kwargs
    ) -> Path:
        """Save encrypted broker login credentials.

        Args:
            broker: Broker name, e.g. 'galaxy', 'huatai'.
            username: Broker account username.
            password: Broker account password.
            **kwargs: Additional metadata (account_id, server, etc.).

        Returns:
            Path to the encrypted credential file.
        """
        data = {
            "username": username,
            "password": password,
            **kwargs,
        }
        plain = json.dumps(data, ensure_ascii=False).encode("utf-8")
        encrypted = self._cipher.encrypt(plain)

        filepath = self._secrets_dir / f"broker_{broker}.enc"
        filepath.write_bytes(encrypted)
        filepath.chmod(0o600)
        logger.info(f"Saved encrypted credentials for broker '{broker}' -> {filepath}")
        return filepath

    def get_broker_credentials(self, broker: str) -> dict | None:
        """Retrieve and decrypt broker login credentials.

        Returns:
            dict with 'username', 'password', and any extra kwargs, or None.
        """
        filepath = self._secrets_dir / f"broker_{broker}.enc"
        if not filepath.exists():
            logger.warning(f"No credentials found for broker '{broker}'")
            return None

        try:
            encrypted = filepath.read_bytes()
            plain = self._cipher.decrypt(encrypted)
            return json.loads(plain.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for '{broker}': {e}")
            return None

    def delete_broker_credentials(self, broker: str) -> bool:
        """Delete stored broker credentials."""
        filepath = self._secrets_dir / f"broker_{broker}.enc"
        if filepath.exists():
            filepath.unlink()
            logger.info(f"Deleted credentials for broker '{broker}'")
            return True
        return False

    def list_brokers(self) -> list[str]:
        """List broker names that have stored credentials."""
        brokers = []
        for f in self._secrets_dir.glob("broker_*.enc"):
            name = f.stem.replace("broker_", "")
            brokers.append(name)
        return brokers

    # -- API keys ----------------------------------------------------------

    def save_api_key(self, service: str, api_key: str, api_secret: str = "") -> Path:
        """Save encrypted API key for a third-party service.

        Args:
            service: Service name, e.g. 'tushare', 'joinquant'.
            api_key: API key string.
            api_secret: Optional API secret.

        Returns:
            Path to the encrypted file.
        """
        data = {"api_key": api_key, "api_secret": api_secret}
        plain = json.dumps(data).encode("utf-8")
        encrypted = self._cipher.encrypt(plain)

        filepath = self._secrets_dir / f"api_{service}.enc"
        filepath.write_bytes(encrypted)
        filepath.chmod(0o600)
        logger.info(f"Saved encrypted API key for '{service}'")
        return filepath

    def get_api_key(self, service: str) -> dict | None:
        """Retrieve and decrypt API key."""
        filepath = self._secrets_dir / f"api_{service}.enc"
        if not filepath.exists():
            return None

        try:
            encrypted = filepath.read_bytes()
            plain = self._cipher.decrypt(encrypted)
            return json.loads(plain.decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to decrypt API key for '{service}': {e}")
            return None
