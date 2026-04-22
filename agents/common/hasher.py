"""Deterministic payload hasher.

The hash committed on-chain and the hash computed by any third-party tool
MUST agree on every byte. That requires **canonical** JSON:

- ``sort_keys=True``  — object keys sorted ascending
- ``ensure_ascii=False`` — UTF-8 rather than \\u-escaped
- ``separators=(',', ':')`` — no whitespace

Dropping any one of these silently breaks on-chain verification. Do not
use ``json.dumps`` directly anywhere in the pipeline — always go through
``canonical_json`` and ``hash_payload``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(payload: dict[str, Any]) -> bytes:
    """Return the canonical-JSON byte representation of ``payload``.

    Args:
        payload: Any JSON-serialisable dict.

    Returns:
        UTF-8 encoded canonical JSON bytes.

    Raises:
        TypeError: If ``payload`` contains non-JSON-serialisable values.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def hash_payload(payload: dict[str, Any]) -> str:
    """Return the hex-encoded SHA-256 of ``payload``'s canonical JSON.

    Args:
        payload: Dict to hash.

    Returns:
        Lowercase 64-character hex string.
    """
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def payload_hash_bytes32(payload: dict[str, Any]) -> bytes:
    """Return the 32-byte raw SHA-256 digest, ready for ``bytes32`` contract calls.

    Identical input to ``hash_payload`` — these two helpers are guaranteed
    to agree; if they ever diverge a CI test must catch it.
    """
    return hashlib.sha256(canonical_json(payload)).digest()
