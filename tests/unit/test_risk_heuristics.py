"""Risk agent tests — TC-U80-84.

Every one of the 15 named rules in ``agents/risk/heuristics.py`` has a
corresponding test here. The aggregator test verifies the honeypot
short-circuit.
"""

from __future__ import annotations

import pytest

from agents.common.schemas.payloads import ChainMetrics, DataQuality, SocialScore
from agents.risk.heuristics import (
    ALL_RULES,
    aggregate_score,
    rule_bot_shilling,
    rule_chain_degraded,
    rule_creator_has_history,
    rule_high_concentration,
    rule_honeypot_failed,
    rule_liquidity_too_thin,
    rule_low_holder_count,
    rule_lp_not_locked,
    rule_negative_sentiment,
    rule_no_organic_buzz,
    rule_paid_promotion,
    rule_social_degraded,
    rule_suspicious_velocity,
    rule_unverified_contract,
    rule_whale_sniping,
    run_heuristics,
)

ADDR = "0x" + "1" * 40


def _chain(**kw: object) -> ChainMetrics:
    """Build a ChainMetrics with safe defaults, override via kwargs per test."""
    return ChainMetrics(
        token_address=ADDR,
        holder_count=int(kw.get("holder_count", 100)),
        top10_concentration_pct=float(kw.get("top10_concentration_pct", 10)),
        liquidity_usd=float(kw.get("liquidity_usd", 10_000)),
        buy_sell_velocity_tx_per_min=float(kw.get("buy_sell_velocity_tx_per_min", 10)),
        whale_entries=int(kw.get("whale_entries", 0)),
        contract_verified=bool(kw.get("contract_verified", True)),
        honeypot_check_passed=bool(kw.get("honeypot_check_passed", True)),
        lp_locked=bool(kw.get("lp_locked", True)),
        creator_previous_tokens=int(kw.get("creator_previous_tokens", 0)),
        data_quality=DataQuality(kw.get("data_quality", "ok")),
    )


def _social(**kw: object) -> SocialScore:
    """Build a SocialScore with safe defaults, override via kwargs per test."""
    return SocialScore(
        token_address=ADDR,
        organic_score=int(kw.get("organic_score", 50)),
        mentions_24h=int(kw.get("mentions_24h", 100)),
        sentiment=float(kw.get("sentiment", 0.2)),
        red_flags=list(kw.get("red_flags", [])),
        influencer_mentions=list(kw.get("influencer_mentions", [])),
        data_quality=DataQuality(kw.get("data_quality", "ok")),
    )


def test_rule_unverified_contract_fires() -> None:
    """Unverified contracts produce the ``unverified-contract`` finding."""
    f = rule_unverified_contract(_social(), _chain(contract_verified=False))
    assert len(f) == 1
    assert f[0].tag == "unverified-contract"


def test_rule_unverified_contract_silent() -> None:
    """Verified contracts produce no finding from this rule."""
    assert rule_unverified_contract(_social(), _chain(contract_verified=True)) == []


def test_rule_honeypot_failed() -> None:
    """Failed honeypot check fires the ``honeypot-suspected`` finding."""
    f = rule_honeypot_failed(_social(), _chain(honeypot_check_passed=False))
    assert f[0].tag == "honeypot-suspected"


def test_rule_lp_not_locked() -> None:
    """Unlocked LP fires the ``lp-not-locked`` finding."""
    f = rule_lp_not_locked(_social(), _chain(lp_locked=False))
    assert f[0].tag == "lp-not-locked"


def test_rule_high_concentration() -> None:
    """Top-10 > 70% fires; 50% does not."""
    f = rule_high_concentration(_social(), _chain(top10_concentration_pct=75))
    assert f[0].tag == "high-top10-concentration"
    assert rule_high_concentration(_social(), _chain(top10_concentration_pct=50)) == []


def test_rule_low_holder_count() -> None:
    """Fewer than 20 holders fires."""
    f = rule_low_holder_count(_social(), _chain(holder_count=5))
    assert f[0].tag == "low-holder-count"


def test_rule_liquidity_too_thin() -> None:
    """Liquidity below $1k fires."""
    f = rule_liquidity_too_thin(_social(), _chain(liquidity_usd=200))
    assert f[0].tag == "liquidity-too-thin"


def test_rule_suspicious_velocity() -> None:
    """Velocity > 300 tx/min fires the wash-trading finding."""
    f = rule_suspicious_velocity(_social(), _chain(buy_sell_velocity_tx_per_min=400))
    assert f[0].tag == "wash-trading-suspected"


def test_rule_creator_has_history() -> None:
    """Creator with > 10 prior tokens fires the serial-launcher finding."""
    f = rule_creator_has_history(_social(), _chain(creator_previous_tokens=20))
    assert f[0].tag == "serial-launcher"


def test_rule_no_organic_buzz() -> None:
    """organic_score < 15 fires the no-organic-buzz finding."""
    f = rule_no_organic_buzz(_social(organic_score=5), _chain())
    assert f[0].tag == "no-organic-buzz"


def test_rule_negative_sentiment() -> None:
    """Sentiment < -0.4 fires the negative-sentiment finding."""
    f = rule_negative_sentiment(_social(sentiment=-0.6), _chain())
    assert f[0].tag == "negative-sentiment"


def test_rule_bot_shilling() -> None:
    """Social flag ``copy-paste-shilling`` propagates into the risk findings."""
    f = rule_bot_shilling(_social(red_flags=["copy-paste-shilling"]), _chain())
    assert f[0].tag == "copy-paste-shilling"


def test_rule_paid_promotion() -> None:
    """Social flag ``paid-promotion-disclosure`` propagates."""
    f = rule_paid_promotion(_social(red_flags=["paid-promotion-disclosure"]), _chain())
    assert f[0].tag == "paid-promotion-disclosure"


def test_rule_whale_sniping() -> None:
    """> 5 whale entries fires the whale-sniping finding."""
    f = rule_whale_sniping(_social(), _chain(whale_entries=10))
    assert f[0].tag == "whale-sniping"


def test_rule_social_degraded() -> None:
    """Degraded social data adds a confidence-reduction finding."""
    f = rule_social_degraded(_social(data_quality="degraded"), _chain())
    assert f[0].tag == "social-data-degraded"


def test_rule_chain_degraded() -> None:
    """Degraded chain data adds a confidence-reduction finding."""
    f = rule_chain_degraded(_social(), _chain(data_quality="degraded"))
    assert f[0].tag == "chain-data-degraded"


def test_all_rules_accept_clean_inputs() -> None:
    """With perfectly clean inputs, zero findings fire."""
    clean_findings = run_heuristics(_social(), _chain())
    assert clean_findings == []


def test_aggregate_score_honeypot_short_circuits() -> None:
    """Honeypot-suspected forces a hard cap of 5, regardless of other findings."""
    findings = run_heuristics(_social(), _chain(honeypot_check_passed=False))
    assert aggregate_score(findings) == 5


def test_aggregate_score_floors_at_zero() -> None:
    # Fire many rules to ensure we don't go negative.
    """Many simultaneous rule fires cannot push the score below 0."""
    findings = run_heuristics(
        _social(organic_score=0, sentiment=-1, red_flags=["copy-paste-shilling"]),
        _chain(
            contract_verified=False,
            lp_locked=False,
            top10_concentration_pct=99,
            holder_count=1,
            liquidity_usd=0,
            buy_sell_velocity_tx_per_min=1000,
            creator_previous_tokens=99,
            whale_entries=20,
            data_quality="degraded",
        ),
    )
    assert 0 <= aggregate_score(findings) <= 100


def test_all_rules_exported() -> None:
    """ALL_RULES tuple contains exactly 15 entries (one per named heuristic)."""
    assert len(ALL_RULES) == 15
