"""Thin BscScan v1 API client.

Read-only wrapper for the endpoints the Chain agent needs. Keeps a
per-second semaphore so we do not blow the free-tier quota — the caller
needs only call the high-level methods.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from agents.common.logging_config import get_logger

log = get_logger("chain.bscscan")


@dataclass(frozen=True)
class HolderSnapshot:
    """Output of ``holders()``."""

    total: int
    top10_concentration_pct: float


@dataclass(frozen=True)
class ContractMeta:
    """Output of ``contract_meta()``."""

    verified: bool
    creator_address: str
    creator_tx_count: int


class BscScanClient:
    """Client with per-second rate limiting."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        rate_per_s: int = 4,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialise the BscScan client.

        Args:
            base_url: Root of the BscScan API (testnet vs mainnet differs).
            api_key: Free-tier key from bscscan.com.
            rate_per_s: Requests per second cap; enforced via asyncio.Semaphore.
            http: Optional injected httpx.AsyncClient for tests.
        """
        self._base = base_url
        self._key = api_key
        self._rate = max(rate_per_s, 1)
        self._http = http or httpx.AsyncClient(timeout=20.0)
        self._sem = asyncio.Semaphore(self._rate)

    async def aclose(self) -> None:
        """Close the HTTP pool."""
        await self._http.aclose()

    async def _get(self, params: dict[str, str]) -> dict[str, object]:
        """Low-level GET with rate-limit + apikey injection.

        Every caller goes through this method so the per-second semaphore
        applies uniformly and the api_key is never forgotten.
        """
        params = {**params, "apikey": self._key}
        async with self._sem:
            await asyncio.sleep(1 / self._rate)
            resp = await self._http.get(self._base, params=params)
            resp.raise_for_status()
            return resp.json()

    async def holders(self, token_address: str) -> HolderSnapshot:
        """Return holder count and top-10 concentration percent."""
        data = await self._get(
            {
                "module": "token",
                "action": "tokenholderlist",
                "contractaddress": token_address,
                "page": "1",
                "offset": "100",
            }
        )
        result = data.get("result") or []
        if not isinstance(result, list) or not result:
            return HolderSnapshot(total=0, top10_concentration_pct=0.0)
        try:
            total_supply = sum(float(r.get("TokenHolderQuantity", 0) or 0) for r in result)
            top10 = sum(float(r.get("TokenHolderQuantity", 0) or 0) for r in result[:10])
            pct = (top10 / total_supply * 100.0) if total_supply > 0 else 0.0
        except (ValueError, TypeError):
            return HolderSnapshot(total=0, top10_concentration_pct=0.0)
        return HolderSnapshot(total=len(result), top10_concentration_pct=round(pct, 2))

    async def contract_meta(self, token_address: str) -> ContractMeta:
        """Return verified flag, creator address, and creator's tx history length."""
        verify = await self._get(
            {
                "module": "contract",
                "action": "getsourcecode",
                "address": token_address,
            }
        )
        verified = False
        creator = "0x" + "0" * 40
        vresult = verify.get("result") or []
        if isinstance(vresult, list) and vresult:
            src = vresult[0] if isinstance(vresult[0], dict) else {}
            verified = bool(src.get("SourceCode"))
            creator = str(src.get("ContractCreator") or creator).lower()

        tx_list = await self._get(
            {
                "module": "account",
                "action": "txlist",
                "address": creator,
                "startblock": "0",
                "endblock": "99999999",
                "sort": "desc",
                "page": "1",
                "offset": "100",
            }
        )
        txs = tx_list.get("result") or []
        tx_count = len(txs) if isinstance(txs, list) else 0
        return ContractMeta(verified=verified, creator_address=creator, creator_tx_count=tx_count)

    async def recent_transfers(self, token_address: str, limit: int = 100) -> list[dict[str, str]]:
        """Return up to ``limit`` recent transfer events for ``token_address``."""
        data = await self._get(
            {
                "module": "account",
                "action": "tokentx",
                "contractaddress": token_address,
                "page": "1",
                "offset": str(limit),
                "sort": "desc",
            }
        )
        result = data.get("result") or []
        return [r for r in result if isinstance(r, dict)]
