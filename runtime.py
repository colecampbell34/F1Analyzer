"""Small, dependency-free runtime policy helpers.

This module is deliberately the single place that knows whether the process is
running locally or in a Vercel function.  Application features can use it
without spreading host-specific checks throughout the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path


def is_serverless() -> bool:
    """Return whether this process has the constraints of a Vercel function."""
    return bool(os.getenv("VERCEL"))


def runtime_directory(environment_variable: str, local_name: str) -> str:
    """Return a writable directory for non-source runtime data.

    Vercel's filesystem is writable only in ``/tmp`` and is ephemeral.  Callers
    should treat data stored there as an optimisation, never durable storage.
    """
    configured = os.getenv(environment_variable)
    if configured:
        return configured
    if is_serverless():
        return str(Path("/tmp") / local_name)
    return local_name


def storage_scope() -> str:
    """Describe how long runtime filesystem data can be expected to survive."""
    return "ephemeral" if is_serverless() else "local"

