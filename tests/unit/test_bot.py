"""Bot helper tests — threshold filtering and brief formatting."""

from __future__ import annotations

from bot.handlers.commands import passes_threshold
from bot.main import _format_brief


def test_passes_threshold_exact_match() -> None:
    """A brief at the exact user threshold passes."""
    assert passes_threshold("moderate", "moderate") is True


def test_passes_threshold_below_is_false() -> None:
    """A degen-tier brief does not pass a high-tier subscriber."""
    assert passes_threshold("degen", "high") is False


def test_passes_threshold_above_is_true() -> None:
    """A high-tier brief passes a moderate-tier subscriber."""
    assert passes_threshold("high", "moderate") is True


def test_passes_threshold_unknown_defaults_to_zero() -> None:
    """Unrecognised tier strings on both sides compare equal (no crash)."""
    assert passes_threshold("???", "???") is True


def test_format_brief_has_bscscan_link() -> None:
    """Rendered brief body contains BscScan, conviction tier, and caveats."""
    body = _format_brief(
        name="Test",
        address="0x1" * 40,
        conviction="moderate",
        thesis="good",
        caveats=["a", "b"],
        msg_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
    )
    assert "BscScan" in body
    assert "moderate" in body
    assert "a\n• b" in body
