"""Helpers to build envelopes, generate ULIDs, and serialise them to Redis.

Separated from ``schemas/envelope.py`` because the schema is a pure data
contract while this module pulls in time and randomness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from ulid import ULID

from agents.common.hasher import hash_payload
from agents.common.schemas.envelope import AgentName, Envelope


def new_msg_id() -> str:
    """Return a fresh ULID as its 26-char Crockford-base32 string."""
    return str(ULID())


def now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing Z."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_envelope(
    *,
    agent: AgentName,
    payload: BaseModel | dict[str, Any],
    upstream_ids: list[str] | None = None,
    model_used: str | None = None,
    msg_id: str | None = None,
    created_at: str | None = None,
) -> Envelope:
    """Construct a sealed ``Envelope`` wrapping ``payload``.

    The payload is serialised to a dict (Pydantic ``model_dump`` if a model,
    pass-through if already a dict), then hashed canonically. ``payload_hash``
    is computed over the dict form to ensure the on-chain bytes32 always
    agrees with what any re-hashing tool produces from the stored payload.
    """
    if isinstance(payload, BaseModel):
        payload_dict = payload.model_dump(mode="json")
    else:
        payload_dict = payload

    return Envelope(
        msg_id=msg_id or new_msg_id(),
        agent=agent,
        upstream_ids=upstream_ids or [],
        payload_hash=hash_payload(payload_dict),
        payload=payload_dict,
        created_at=created_at or now_iso(),
        model_used=model_used,
    )
