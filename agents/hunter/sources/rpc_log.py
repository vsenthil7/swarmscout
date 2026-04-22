"""On-chain event-log source for Four.meme new-token detection.

Subscribes to an ``eth_getLogs`` filter on a Four.meme factory address.
The ABI of the TokenCreated event is hard-coded here; when Four.meme ships
a newer factory the event topic and decoder tuple are the only things to
update.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from web3 import AsyncHTTPProvider, AsyncWeb3

from agents.common.logging_config import get_logger
from agents.hunter.sources.base import RawTokenEvent

log = get_logger("hunter.sources.rpc_log")

TOKEN_CREATED_TOPIC = "0x" + "00" * 32  # placeholder; overridden via settings once known.
FOURMEME_FACTORY_ADDRESS = "0x0000000000000000000000000000000000000000"

LAST_BLOCK_KEY = "hunter:last_block"


class FourMemeRPCLogSource:
    """Poll the BNB RPC for TokenCreated events."""

    def __init__(
        self,
        *,
        rpc_url: str,
        factory_address: str,
        topic: str,
        redis: aioredis.Redis,
        poll_interval_s: int = 5,
        w3: AsyncWeb3 | None = None,
    ) -> None:
        """Configure the RPC-log source.

        Args:
            rpc_url: BNB (or BSC mainnet) JSON-RPC endpoint.
            factory_address: Four.meme token factory contract.
            topic: TokenCreated event topic hash (0x…).
            redis: Where to persist the ``last_block`` cursor.
            poll_interval_s: How long to wait between log fetches.
            w3: Optional pre-built AsyncWeb3 for tests.
        """
        self._w3 = w3 or AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self._factory = factory_address
        self._topic = topic
        self._redis = redis
        self._interval = poll_interval_s

    async def events(self) -> AsyncIterator[RawTokenEvent]:
        """Yield new events, resuming from the last-processed block."""
        while True:
            last = await self._redis.get(LAST_BLOCK_KEY)
            from_block = int(last) + 1 if last else await self._w3.eth.block_number
            latest = await self._w3.eth.block_number
            if from_block > latest:
                await asyncio.sleep(self._interval)
                continue
            try:
                logs = await self._w3.eth.get_logs(
                    {
                        "fromBlock": from_block,
                        "toBlock": latest,
                        "address": self._factory,
                        "topics": [self._topic],
                    }
                )
            except Exception as err:
                log.warning("rpc_log_get_logs_failed", err=str(err))
                await asyncio.sleep(self._interval)
                continue

            for entry in logs:
                mapped = self._decode(entry)
                if mapped is not None:
                    yield mapped

            await self._redis.set(LAST_BLOCK_KEY, str(latest))
            await asyncio.sleep(self._interval)

    @staticmethod
    def _decode(entry: dict[str, object]) -> RawTokenEvent | None:
        """Decode a log entry; returns ``None`` on malformed entries."""
        try:
            topics = entry.get("topics", [])
            _data = entry.get("data", "")  # reserved for future decoding of non-indexed fields
            if not isinstance(topics, list) or len(topics) < 3:
                return None
            token_addr = "0x" + bytes(topics[1]).hex()[-40:] if isinstance(topics[1], (bytes, bytearray)) else str(topics[1])[-40:]
            creator_addr = "0x" + bytes(topics[2]).hex()[-40:] if isinstance(topics[2], (bytes, bytearray)) else str(topics[2])[-40:]
            return RawTokenEvent(
                token_address=token_addr.lower(),
                creator_address=creator_addr.lower(),
                token_name="(on-chain)",
                token_symbol="?",
                initial_liquidity_usd=0.0,
                launch_timestamp="",
                source_url=f"https://bscscan.com/tx/{entry.get('transactionHash', '')!s}",
            )
        except (ValueError, TypeError, KeyError) as err:
            log.warning("rpc_log_decode_failed", err=str(err))
            return None
