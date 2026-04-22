"""Message envelope shared across all agents and streams.

Every message on Redis Streams conforms to this envelope. The full payload
lives in PostgreSQL keyed by ``msg_id``; the stream itself carries only the
envelope so entries stay small and cheap to iterate.

FR-100 / FR-101 / FR-104 / NFR-262 all touch this file — the envelope is the
contract every downstream consumer relies on.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentName(str, Enum):
    """Fixed set of agent identifiers.

    Using an Enum rather than free-form strings means schema validators can
    reject typos like ``"hunter "`` or ``"Hunter"`` at ingest time, not when
    a consumer group fails to match.
    """

    HUNTER = "hunter"
    SOCIAL = "social"
    CHAIN = "chain"
    RISK = "risk"
    NARRATOR = "narrator"


class StreamName(str, Enum):
    """Canonical Redis stream names.

    Encoded here (rather than as loose strings at call sites) so a rename is
    a single-file change and misspellings are caught by mypy.
    """

    CANDIDATES = "stream:candidates"
    SOCIAL = "stream:social"
    CHAIN = "stream:chain"
    RISK = "stream:risk"
    BRIEFS = "stream:briefs"
    HUMAN_REVIEW = "stream:human_review"


class Envelope(BaseModel):
    """Envelope wrapping every inter-agent message.

    Fields:
        msg_id: ULID string (26 chars). Monotonically sortable, unique.
        agent: Which agent produced this message.
        upstream_ids: Parent msg_ids in the lineage graph. Empty for root
            events (Hunter); 1+ for every downstream message.
        payload_hash: Hex-encoded SHA-256 of the canonical JSON of payload,
            computed *after* all fields (including ``model_used``) are set.
            Matches the bytes32 stored in FindingsRegistry on-chain.
        payload: Payload object, serialised as dict for transport.
        created_at: ISO-8601 UTC timestamp.
        model_used: ``provider/model`` string identifying the LLM behind this
            output, or ``None`` for non-LLM messages (e.g. health heartbeats).
    """

    model_config = ConfigDict(extra="forbid", frozen=False, str_strip_whitespace=True)

    msg_id: str = Field(
        ...,
        min_length=26,
        max_length=26,
        description="ULID (Crockford base32, 26 chars).",
    )
    agent: AgentName
    upstream_ids: list[str] = Field(default_factory=list)
    payload_hash: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="Hex-encoded SHA-256 of the canonical JSON of payload.",
    )
    payload: dict[str, Any]
    created_at: str = Field(
        ...,
        description="ISO-8601 UTC timestamp, e.g. 2026-04-22T06:45:00Z.",
    )
    model_used: str | None = Field(
        default=None,
        description="provider/model string, e.g. anthropic/claude-opus-4-7.",
    )

    @field_validator("msg_id")
    @classmethod
    def _validate_ulid_alphabet(cls, value: str) -> str:
        """Reject non-Crockford-base32 characters in msg_id."""
        allowed = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        upper = value.upper()
        if not set(upper).issubset(allowed):
            raise ValueError(f"msg_id contains non-Crockford-base32 characters: {value!r}")
        return upper

    @field_validator("upstream_ids")
    @classmethod
    def _validate_upstream_ids(cls, value: list[str]) -> list[str]:
        """Each upstream id must itself be a 26-char Crockford-base32 string."""
        allowed = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        result: list[str] = []
        for raw in value:
            if len(raw) != 26:
                raise ValueError(f"upstream_id {raw!r} must be 26 chars")
            upper = raw.upper()
            if not set(upper).issubset(allowed):
                raise ValueError(f"upstream_id {raw!r} contains invalid characters")
            result.append(upper)
        return result

    @field_validator("created_at")
    @classmethod
    def _validate_iso8601(cls, value: str) -> str:
        """Shallow ISO-8601 check — tight parsing happens at producer side."""
        if "T" not in value or not (value.endswith("Z") or "+" in value or "-" in value[10:]):
            raise ValueError(f"created_at must be ISO-8601 UTC; got {value!r}")
        return value

    @field_validator("model_used")
    @classmethod
    def _validate_model_used(cls, value: str | None) -> str | None:
        """When present, model_used must be provider/model form."""
        if value is None:
            return None
        if "/" not in value or value.startswith("/") or value.endswith("/"):
            raise ValueError(f"model_used must be 'provider/model'; got {value!r}")
        return value
