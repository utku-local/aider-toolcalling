"""Recognizes files that usually hold secrets: env files, private keys, credential and token stores.
read_file asks before reading them (every time, never approved by --yes-always) and search_code skips their content,
so a model cannot quietly pull secrets into the conversation or the session file.
Matching uses the file name and path parts only; nothing is opened to decide.
"""

import fnmatch
from pathlib import PurePosixPath

SENSITIVE_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "*credentials*",
    "*secret*",
    "*.keystore",
)
SENSITIVE_DIRS = frozenset({".ssh", ".aws", ".gnupg"})
EXAMPLE_SUFFIXES = (".example", ".sample", ".template")


def is_sensitive(path: str) -> bool:
    """True for paths whose name or directory suggests secrets; example and template files are not."""
    parts = PurePosixPath(path).parts
    name = parts[-1].lower() if parts else ""
    if name.endswith(EXAMPLE_SUFFIXES):
        return False
    if SENSITIVE_DIRS & set(parts[:-1]):
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_NAMES)
