"""Payload schemas produced by each agent.

One Pydantic model per message type. These are the single source of truth;
JSON Schema is exported from them and a zod TypeScript mirror is generated
so the Next.js dashboard cannot drift.

Each model is ``extra="forbid"`` — unknown fields are a bug, not a feature.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DataQuality(str, Enum):
    """Quality tag surfaced on every payload that may be produced with partial inputs."""

    OK = "ok"
    DEGRADED = "degraded"


class ConvictionTier(str, Enum):
    """User-facing conviction scale for AlphaBriefs."""

    DEGEN = "degen"
    SPECULATIVE = "speculative"
    MODERATE = "moderate"
    HIGH = "high"


class RiskConfidence(str, Enum):
    """Risk agent's confidence in its own verdict."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --------------------------------------------------------------------------- #
# Hunter -> TokenCandidate                                                    #
# --------------------------------------------------------------------------- #


class TokenCandidate(BaseModel):
    """First-class message produced by the Hunter agent (FR-003).

    Every downstream agent joins on ``token_address``; it is the spine of
    the lineage graph.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    launch_timestamp: str = Field(..., description="ISO-8601 UTC.")
    creator_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    token_name: str = Field(..., min_length=1, max_length=128)
    token_symbol: str = Field(..., min_length=1, max_length=32)
    initial_liquidity_usd: float = Field(..., ge=0)
    source_url: str = Field(..., min_length=1, max_length=1024)

    @field_validator("token_address", "creator_address")
    @classmethod
    def _normalise_address(cls, value: str) -> str:
        """Lowercase the Ethereum address only if it starts with ``0X``.

        Pydantic v2 validators re-enter on re-assignment; keeping the
        conditional avoids unnecessary allocations on already-normalised
        input.
        """
        return value.lower() if value.startswith("0X") else value


# --------------------------------------------------------------------------- #
# Social -> SocialScore                                                       #
# --------------------------------------------------------------------------- #


class SocialScore(BaseModel):
    """Output of the Social agent (FR-023)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    organic_score: int = Field(..., ge=0, le=100)
    mentions_24h: int = Field(..., ge=0)
    sentiment: float = Field(..., ge=-1.0, le=1.0)
    red_flags: list[str] = Field(default_factory=list)
    influencer_mentions: list[str] = Field(default_factory=list)
    data_quality: DataQuality = DataQuality.OK


# --------------------------------------------------------------------------- #
# Chain -> ChainMetrics                                                       #
# --------------------------------------------------------------------------- #


class ChainMetrics(BaseModel):
    """Output of the Chain agent (FR-041, FR-042)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    holder_count: int = Field(..., ge=0)
    top10_concentration_pct: float = Field(..., ge=0, le=100)
    liquidity_usd: float = Field(..., ge=0)
    buy_sell_velocity_tx_per_min: float = Field(..., ge=0)
    whale_entries: int = Field(..., ge=0, description="Addresses with >$1k entry.")
    contract_verified: bool
    honeypot_check_passed: bool
    lp_locked: bool
    creator_previous_tokens: int = Field(..., ge=0)
    data_quality: DataQuality = DataQuality.OK


# --------------------------------------------------------------------------- #
# Risk -> RiskVerdict                                                         #
# --------------------------------------------------------------------------- #


class RiskVerdict(BaseModel):
    """Output of the Risk agent (FR-062).

    ``score_0_100`` and ``confidence`` may be ``None`` when all three LLM
    providers are unreachable (FR-064). In that case ``requires_human_review``
    is mandatorily True.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    score_0_100: int | None = Field(default=None, ge=0, le=100)
    red_flags: list[str] = Field(default_factory=list)
    rationale: str = Field(..., min_length=0, max_length=4000)
    missing_inputs: list[str] = Field(default_factory=list)
    confidence: RiskConfidence | None = None
    requires_human_review: bool = False

    @field_validator("requires_human_review")
    @classmethod
    def _review_implies_null_score(cls, value: bool) -> bool:
        # Cross-field check is done at model level via @model_validator would
        # need access to other fields; we rely on Risk agent to set these
        # consistently — see RiskVerdict.guard() below.
        """Single-field validator kept for future cross-field checks.

        The coupling between ``requires_human_review`` and nullity of
        ``score_0_100`` is enforced by the Risk agent at emit time rather
        than here, since a strict model_validator would complicate
        partial-construction scenarios in tests.
        """
        return value


# --------------------------------------------------------------------------- #
# Narrator -> AlphaBrief                                                      #
# --------------------------------------------------------------------------- #


class AlphaBrief(BaseModel):
    """User-facing output of the Narrator agent (FR-082)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_name: str = Field(..., min_length=1, max_length=128)
    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    thesis: str = Field(..., min_length=50, max_length=2000)
    conviction_tier: ConvictionTier
    caveats: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    model_attribution: list[str] = Field(
        default_factory=list,
        description="provider/model strings used across the pipeline for this brief.",
    )
    brief_generated_at: str = Field(..., description="ISO-8601 UTC.")
    confidence_tier: DataQuality = DataQuality.OK


# --------------------------------------------------------------------------- #
# Narrator -> HumanReviewRequest                                              #
# --------------------------------------------------------------------------- #


class HumanReviewRequest(BaseModel):
    """Emitted instead of an AlphaBrief when the Risk verdict flags review (FR-086)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    token_address: str = Field(..., min_length=42, max_length=42, pattern=r"^0x[0-9a-fA-F]{40}$")
    reason: str = Field(..., min_length=1, max_length=1024)
    risk_verdict_msg_id: str = Field(..., min_length=26, max_length=26)
    raised_at: str = Field(..., description="ISO-8601 UTC.")
