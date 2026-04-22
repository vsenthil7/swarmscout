"""Coverage tests for agents/chain/main.py.

Exercises: handle noop, _main_loop ack + error paths, _process validation+publish,
_gather with happy + holders-exception + meta-exception + transfers-exception
(all flipping data_quality to degraded), _holders_or_default + _meta_or_default
branches, _velocity_tx_per_min edge cases, _whale_count edge cases, _amain/run.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from agents.chain.bscscan import ContractMeta, HolderSnapshot
from agents.chain.main import (
    CHAIN_GROUP,
    ChainAgent,
    _velocity_tx_per_min,
    _whale_count,
)
from agents.common.bus import Bus, BusMessage
from agents.common.envelope_builder import build_envelope
from agents.common.on_chain import NullAnchor
from agents.common.schemas.envelope import AgentName, StreamName
from agents.common.schemas.payloads import DataQuality, TokenCandidate


class _StubHeartbeats:
    async def upsert(self, **_: Any) -> None:
        return None


class _NullFindings:
    async def insert_envelope(self, _env: Any) -> None:
        return None

    async def record_onchain(self, *_: Any) -> None:
        return None


class _FakeBscScan:
    """Fake BscScan client with overridable behaviours."""

    def __init__(
        self,
        *,
        holders_result: Any | Exception = None,
        meta_result: Any | Exception = None,
        transfers_result: Any | Exception = None,
    ) -> None:
        self._holders = holders_result or HolderSnapshot(total=100, top10_concentration_pct=40.0)
        self._meta = meta_result or ContractMeta(
            verified=True, creator_address="0x" + "c" * 40, creator_tx_count=120
        )
        self._transfers = transfers_result if transfers_result is not None else []
        self.closed = False

    async def holders(self, _addr: str) -> Any:
        if isinstance(self._holders, Exception):
            raise self._holders
        return self._holders

    async def contract_meta(self, _addr: str) -> Any:
        if isinstance(self._meta, Exception):
            raise self._meta
        return self._meta

    async def recent_transfers(self, _addr: str, _limit: int = 100) -> Any:
        if isinstance(self._transfers, Exception):
            raise self._transfers
        return self._transfers

    async def aclose(self) -> None:
        self.closed = True


def _ctx_stub() -> SimpleNamespace:
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    bus = Bus(url="redis://fake", client=redis)
    return SimpleNamespace(
        settings=SimpleNamespace(
            chain_primary_model="openai/gpt-4o-mini",
            bscscan_base_url="https://api-testnet.bscscan.com/api",
            bscscan_api_key="KEY",
            bscscan_rate_limit_per_sec=4,
        ),
        bus=bus,
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=redis,
    )


def _candidate_env(addr: str = "0x" + "a" * 40) -> Any:
    c = TokenCandidate(
        token_address=addr,
        launch_timestamp="2026-04-22T10:00:00Z",
        creator_address="0x" + "b" * 40,
        token_name="ChainTok",
        token_symbol="CT",
        initial_liquidity_usd=5000.0,
        source_url="https://four.meme/ct",
    )
    return build_envelope(agent=AgentName.HUNTER, payload=c)


# --------------------------------------------------------------------------- #
# _velocity_tx_per_min                                                        #
# --------------------------------------------------------------------------- #


def test_velocity_returns_zero_for_empty_list() -> None:
    assert _velocity_tx_per_min([]) == 0.0


def test_velocity_returns_zero_for_single_transfer() -> None:
    """Need at least two points to compute a rate."""
    assert _velocity_tx_per_min([{"timeStamp": "1713000000"}]) == 0.0


def test_velocity_computes_rate_across_span() -> None:
    """100 transfers across 594 s = ~10.1 tx/min."""
    transfers = [
        {"timeStamp": str(1713000600 - i * 6)} for i in range(100)
    ]  # newest first; span is 99*6 = 594 seconds
    rate = _velocity_tx_per_min(transfers)
    assert 10.0 < rate < 10.5


def test_velocity_returns_zero_for_invalid_timestamp() -> None:
    """Non-numeric timestamps fall through the except branch to zero."""
    bad = [{"timeStamp": "abc"}, {"timeStamp": "xyz"}]
    assert _velocity_tx_per_min(bad) == 0.0


def test_velocity_clamps_zero_span_to_one_second() -> None:
    """When newest == oldest, span is clamped so we don't divide by zero."""
    transfers = [{"timeStamp": "1713000000"} for _ in range(5)]
    rate = _velocity_tx_per_min(transfers)
    assert rate > 0.0  # non-zero, specifically 5/(1/60) = 300


# --------------------------------------------------------------------------- #
# _whale_count                                                                #
# --------------------------------------------------------------------------- #


def test_whale_count_identifies_large_transfers() -> None:
    """One transfer over the threshold counts."""
    transfers = [
        {"value": "5000000000000000000000", "tokenDecimal": "18"},  # 5000
        {"value": "100000000000000000000", "tokenDecimal": "18"},   # 100
    ]
    assert _whale_count(transfers, threshold_usd=1000.0) == 1


def test_whale_count_skips_malformed_rows() -> None:
    """Rows with non-numeric value or tokenDecimal are skipped silently."""
    transfers = [
        {"value": "not-a-number", "tokenDecimal": "18"},
        {"value": "1000000000000000000000", "tokenDecimal": "bad"},
        {"value": "5000000000000000000000", "tokenDecimal": "18"},
    ]
    # Only the last one counts (normalised=5000 > 1000).
    assert _whale_count(transfers, threshold_usd=1000.0) == 1


def test_whale_count_handles_missing_fields() -> None:
    """Missing 'value' defaults to 0; missing 'tokenDecimal' defaults to 18."""
    transfers = [{}, {"value": "500000000000000000000"}]  # 500
    assert _whale_count(transfers, threshold_usd=1000.0) == 0


# --------------------------------------------------------------------------- #
# _holders_or_default / _meta_or_default                                      #
# --------------------------------------------------------------------------- #


def test_holders_or_default_returns_input_when_not_exception() -> None:
    snap = HolderSnapshot(total=5, top10_concentration_pct=20.0)
    out = ChainAgent._holders_or_default(snap)
    assert out is snap


def test_holders_or_default_returns_zero_on_exception() -> None:
    out = ChainAgent._holders_or_default(RuntimeError("fail"))
    assert isinstance(out, HolderSnapshot)
    assert out.total == 0
    assert out.top10_concentration_pct == 0.0


def test_meta_or_default_returns_input_when_not_exception() -> None:
    m = ContractMeta(verified=True, creator_address="0x1", creator_tx_count=5)
    out = ChainAgent._meta_or_default(m)
    assert out is m


def test_meta_or_default_returns_placeholder_on_exception() -> None:
    out = ChainAgent._meta_or_default(RuntimeError("fail"))
    assert isinstance(out, ContractMeta)
    assert out.verified is False
    assert out.creator_tx_count == 0


# --------------------------------------------------------------------------- #
# handle() no-op                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_handle_returns_none() -> None:
    ctx = _ctx_stub()
    agent = ChainAgent(ctx=ctx, bscscan=_FakeBscScan())
    assert await agent.handle(None) is None


# --------------------------------------------------------------------------- #
# _gather                                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_gather_happy_path_returns_ok_quality() -> None:
    ctx = _ctx_stub()
    transfers = [
        {"value": "5000000000000000000000", "tokenDecimal": "18", "timeStamp": "1713000600"},
        {"value": "1000000000000000000000", "tokenDecimal": "18", "timeStamp": "1713000000"},
    ]
    bscscan = _FakeBscScan(
        holders_result=HolderSnapshot(total=250, top10_concentration_pct=45.0),
        meta_result=ContractMeta(verified=True, creator_address="0xdef", creator_tx_count=120),
        transfers_result=transfers,
    )
    agent = ChainAgent(ctx=ctx, bscscan=bscscan)
    c = TokenCandidate.model_validate(_candidate_env().payload)
    metrics = await agent._gather(c)
    assert metrics.data_quality == DataQuality.OK
    assert metrics.holder_count == 250
    assert metrics.top10_concentration_pct == 45.0
    assert metrics.contract_verified is True
    assert metrics.honeypot_check_passed is True
    assert metrics.lp_locked is False
    assert metrics.creator_previous_tokens == 2  # 120 // 50 = 2


@pytest.mark.asyncio
async def test_gather_flips_degraded_when_holders_raises() -> None:
    ctx = _ctx_stub()
    bscscan = _FakeBscScan(holders_result=RuntimeError("holders down"))
    agent = ChainAgent(ctx=ctx, bscscan=bscscan)
    c = TokenCandidate.model_validate(_candidate_env().payload)
    metrics = await agent._gather(c)
    assert metrics.data_quality == DataQuality.DEGRADED
    assert metrics.holder_count == 0


@pytest.mark.asyncio
async def test_gather_flips_degraded_when_meta_raises() -> None:
    ctx = _ctx_stub()
    bscscan = _FakeBscScan(meta_result=RuntimeError("meta down"))
    agent = ChainAgent(ctx=ctx, bscscan=bscscan)
    c = TokenCandidate.model_validate(_candidate_env().payload)
    metrics = await agent._gather(c)
    assert metrics.data_quality == DataQuality.DEGRADED
    assert metrics.contract_verified is False


@pytest.mark.asyncio
async def test_gather_flips_degraded_when_transfers_raises() -> None:
    ctx = _ctx_stub()
    bscscan = _FakeBscScan(transfers_result=RuntimeError("tx down"))
    agent = ChainAgent(ctx=ctx, bscscan=bscscan)
    c = TokenCandidate.model_validate(_candidate_env().payload)
    metrics = await agent._gather(c)
    assert metrics.data_quality == DataQuality.DEGRADED
    # Velocity computed over empty list falls to 0.
    assert metrics.buy_sell_velocity_tx_per_min == 0.0


# --------------------------------------------------------------------------- #
# _process                                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_process_validates_and_publishes() -> None:
    ctx = _ctx_stub()
    agent = ChainAgent(ctx=ctx, bscscan=_FakeBscScan())
    env = _candidate_env()
    with patch.object(agent, "anchor_and_publish", new=AsyncMock()) as emit:
        await agent._process(env)
    emit.assert_awaited_once()


# --------------------------------------------------------------------------- #
# _main_loop                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_main_loop_acks_on_success() -> None:
    ctx = _ctx_stub()
    agent = ChainAgent(ctx=ctx, bscscan=_FakeBscScan())
    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock()):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    ctx.bus.ack.assert_awaited_once()
    assert agent._events_in_window == 1


@pytest.mark.asyncio
async def test_main_loop_swallows_process_exception() -> None:
    ctx = _ctx_stub()
    agent = ChainAgent(ctx=ctx, bscscan=_FakeBscScan())
    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    ctx.bus.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_main_loop_exits_when_stop_event_set() -> None:
    ctx = _ctx_stub()
    agent = ChainAgent(ctx=ctx, bscscan=_FakeBscScan())
    agent._stop_event.set()

    env = _candidate_env()
    msg = BusMessage(stream=StreamName.CANDIDATES.value, entry_id="1-0", envelope=env)

    async def fake_consume(**_: Any):  # type: ignore[no-untyped-def]
        yield msg

    ctx.bus.consume = fake_consume  # type: ignore[assignment]
    ctx.bus.ack = AsyncMock()

    with patch.object(agent, "_process", new=AsyncMock()) as proc:
        await asyncio.wait_for(agent._main_loop(), timeout=3)

    proc.assert_not_awaited()


# --------------------------------------------------------------------------- #
# _amain + run                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_amain_builds_client_runs_agent_and_closes() -> None:
    from agents.chain import main as chain_main

    fake_bscscan = _FakeBscScan()
    fake_ctx = SimpleNamespace(
        settings=SimpleNamespace(
            chain_primary_model="m",
            bscscan_base_url="https://x",
            bscscan_api_key="k",
            bscscan_rate_limit_per_sec=4,
        ),
        bus=Bus(url="redis://fake", client=fakeredis.aioredis.FakeRedis(decode_responses=True)),
        findings=_NullFindings(),
        heartbeats=_StubHeartbeats(),
        anchor=NullAnchor(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        aclose=AsyncMock(),
    )

    async def fake_build_context() -> SimpleNamespace:
        return fake_ctx

    with patch.object(chain_main, "build_context", new=fake_build_context), \
         patch.object(chain_main, "BscScanClient", return_value=fake_bscscan), \
         patch.object(ChainAgent, "run", new=AsyncMock()):
        await chain_main._amain()

    assert fake_bscscan.closed is True
    fake_ctx.aclose.assert_awaited_once()


def test_run_entrypoint_invokes_amain_via_asyncio_run() -> None:
    from agents.chain import main as chain_main

    with patch.object(chain_main.asyncio, "run") as mock_run:
        chain_main.run()
    mock_run.assert_called_once()
