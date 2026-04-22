"""Adapter protocol for Four.meme sources.

Why two implementations? A-01 assumption in 01_Requirements.md is that
Four.meme offers *some* new-token feed; which one — REST polling vs on-chain
log subscription — is not yet decided. The ``FourMemeSource`` protocol
decouples the Hunter agent from that decision.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawTokenEvent:
    """Source-agnostic new-token event."""

    token_address: str
    creator_address: str
    token_name: str
    token_symbol: str
    initial_liquidity_usd: float
    launch_timestamp: str
    source_url: str


class FourMemeSource(Protocol):
    """Protocol every source adapter implements."""

    async def events(self) -> AsyncIterator[RawTokenEvent]:
        """Yield events as they arrive."""
        ...  # pragma: no cover - Protocol body, not executed
