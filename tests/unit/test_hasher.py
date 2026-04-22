"""Hasher unit tests — TC-U40 through TC-U43."""

from __future__ import annotations

import json

import pytest

from agents.common.hasher import canonical_json, hash_payload, payload_hash_bytes32


# TC-U40 — canonical JSON is deterministic
def test_canonical_json_is_deterministic() -> None:
    """Same-content dicts in different insertion orders produce identical bytes."""
    a = {"b": 1, "a": 2, "c": {"y": 1, "x": 2}}
    b = {"a": 2, "c": {"x": 2, "y": 1}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


# TC-U41 — canonical JSON uses no whitespace and sorts keys ascending
def test_canonical_json_formatting() -> None:
    """Serialised output has sorted keys, no whitespace, no separator padding."""
    out = canonical_json({"b": 1, "a": 2}).decode("utf-8")
    assert out == '{"a":2,"b":1}'


# TC-U42 — hash_payload is 64 lowercase hex chars
def test_hash_payload_shape() -> None:
    """hash_payload returns 64 lowercase hex chars."""
    h = hash_payload({"x": 1})
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)


# TC-U42b — hash is stable under key reordering
def test_hash_payload_stable_under_reordering() -> None:
    """Key reordering does not change the hash (this is the whole point)."""
    assert hash_payload({"a": 1, "b": 2}) == hash_payload({"b": 2, "a": 1})


# TC-U43 — payload_hash_bytes32 agrees with hash_payload
def test_bytes32_matches_hex() -> None:
    """payload_hash_bytes32(p).hex() == hash_payload(p)."""
    payload = {"a": [1, 2, 3], "b": "hello"}
    hex_hash = hash_payload(payload)
    raw = payload_hash_bytes32(payload)
    assert raw.hex() == hex_hash


# TC-U43b — ensure_ascii=False preserves unicode bytes
def test_canonical_json_unicode_preservation() -> None:
    r"""ensure_ascii=False keeps UTF-8 literals (é, etc.) rather than \u-escaping."""
    out = canonical_json({"name": "héllo"}).decode("utf-8")
    assert "héllo" in out
    assert "\\u" not in out


# TC-U43c — NaN/Infinity refused (allow_nan=False)
def test_canonical_json_refuses_nan() -> None:
    """allow_nan=False: NaN/Inf values raise ValueError."""
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})


# TC-U43d — nested sorting is recursive
def test_canonical_json_sorts_nested() -> None:
    """Sorting is recursive into nested objects, not just the top level."""
    out = canonical_json({"a": {"z": 1, "b": 2}, "outer": [1, 2]}).decode("utf-8")
    assert out == '{"a":{"b":2,"z":1},"outer":[1,2]}'


# TC-U43e — non-serialisable input raises TypeError
def test_canonical_json_typeerror_on_set() -> None:
    """Non-JSON-serialisable types (like set) raise TypeError cleanly."""
    with pytest.raises(TypeError):
        canonical_json({"x": {1, 2, 3}})  # type: ignore[dict-item]


# TC-U43f — identical hash for logically identical payloads from JSON round-trip
def test_roundtrip_identity() -> None:
    """dumps -> loads -> hash_payload yields the same hash as hashing the original."""
    obj = {"a": 1, "b": [True, False, None], "c": {"d": "e"}}
    dumped = canonical_json(obj)
    restored = json.loads(dumped)
    assert hash_payload(obj) == hash_payload(restored)
