"""
Environment file loader for .denv / .genv files.

Reads key=value pairs from env files and populates os.environ
WITHOUT overwriting values that are already set (explicit env wins).
Supports # comments, blank lines, and optional quoting.
"""

import os
from pathlib import Path
from typing import Optional


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env-style file into a dict."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip optional surrounding quotes
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            result[key] = value
    return result


def load_env_files(
    repo_root: Optional[Path] = None,
    *,
    drone: bool = True,
    gcs: bool = True,
) -> dict[str, str]:
    """
    Load .denv and .genv from the repo root into os.environ.

    - Existing env vars take precedence (never overwritten).
    - .denv.local / .genv.local override base files (for site config).
    - Returns dict of all loaded key-value pairs (for debugging).

    Parameters
    ----------
    repo_root : Path, optional
        Repository root directory. Auto-detected if omitted.
    drone : bool
        Whether to load .denv (drone-side config).
    gcs : bool
        Whether to load .genv (GCS-side config).
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    loaded: dict[str, str] = {}

    # Load order: base file first, then .local override (later values win
    # in the dict, but os.environ is only set if key is NOT already present).
    files = []
    if drone:
        files.append(repo_root / ".denv")
        files.append(repo_root / ".denv.local")
    if gcs:
        files.append(repo_root / ".genv")
        files.append(repo_root / ".genv.local")

    for env_file in files:
        pairs = _parse_env_file(env_file)
        loaded.update(pairs)

    # Inject into os.environ (existing values NOT overwritten)
    for key, value in loaded.items():
        if key not in os.environ:
            os.environ[key] = value

    return loaded
