"""Local, vault-free credential store.

The original project fetched login credentials from a HashiCorp Vault server.
For a standalone/local setup we read them from a JSON file on disk instead,
while keeping the exact same async interface (`get_keys`, `get_secret`) that the
browser agent's tools call.

Secrets file format (config.LOCAL_SECRETS_FILE, default secrets/local_secrets.json):

    {
      "default": {
        "github_username": "alice",
        "github_password": "s3cr3t"
      },
      "another-namespace": { ... }
    }

The top-level keys are "namespaces" (`vault_ns`). A flat mapping (no namespaces)
is also accepted and treated as the "default" namespace.
"""

import json
import os
from typing import Dict, Union

from config import LOCAL_SECRETS_FILE
from core.utils.logger import Logger

logger = Logger()


def _load_namespace(vault_ns: str) -> Dict[str, str]:
    if not os.path.exists(LOCAL_SECRETS_FILE):
        logger.warn(f"Local secrets file not found at {LOCAL_SECRETS_FILE}")
        return {}
    try:
        with open(LOCAL_SECRETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read local secrets file: {e}")
        return {}

    if not isinstance(data, dict):
        return {}

    # If the file looks namespaced, index into it; otherwise treat it as flat.
    ns = vault_ns or "default"
    if ns in data and isinstance(data[ns], dict):
        return data[ns]
    if all(isinstance(v, dict) for v in data.values()) and data:
        # Namespaced file but the requested namespace is missing.
        return data.get("default", {})
    # Flat file: every value is a secret string.
    return {k: v for k, v in data.items() if isinstance(v, str)}


async def get_keys(vault_ns) -> Dict[str, Union[str, int]]:
    """Return all available credential keys for the given namespace."""
    try:
        secrets = _load_namespace(vault_ns)
        keys = list(secrets.keys())
        return {
            "vault_keys": ", ".join(keys),
            "total_count": len(keys),
            "context": "These are the available keys in the local secrets store",
        }
    except Exception as e:
        return f"Error: {e}"


async def get_secret(vault_ns, key: str) -> str:
    """Return the secret value for a given key in the given namespace."""
    if not isinstance(key, str) or not key.strip():
        return "Error: Invalid key provided"
    try:
        secrets = _load_namespace(vault_ns)
        if key not in secrets:
            return f"Error: key '{key}' not found in local secrets store"
        return secrets[key]
    except Exception as e:
        return f"Error: {e}"
