"""Shared fixtures for the Python test suite."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio

from agents.common.bus import Bus


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    """Provide a fresh fakeredis instance per test."""
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()


@pytest_asyncio.fixture
async def bus(fake_redis: fakeredis.aioredis.FakeRedis) -> AsyncIterator[Bus]:
    """Bus wired to fakeredis."""
    b = Bus(url="redis://fake", client=fake_redis)
    try:
        yield b
    finally:
        await b.close()


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend for anyio-flavoured tests."""
    return "asyncio"
