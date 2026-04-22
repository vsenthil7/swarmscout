"""Risk heuristics.

Fifteen named, pure functions, each inspecting the pair ``(social, chain)``
and emitting zero or more ``Finding``\\ s. Keeping them pure keeps them
unit-testable in isolation (TC-U82-84); keeping them separate keeps the
rule catalogue legible.

Each ``Finding`` has:
* ``tag``: a short kebab-case identifier, surfaced in ``red_flags``
* ``weight``: 0-100 penalty contribution to the final score
* ``reason``: human sentence used in the rationale
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agents.common.schemas.payloads import ChainMetrics, SocialScore


@dataclass(frozen=True)
class Finding:
    """One heuristic's verdict."""

    tag: str
    weight: int
    reason: str


Rule = Callable[[SocialScore, ChainMetrics], list[Finding]]


def rule_unverified_contract(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Unverified contracts cannot be audited — high penalty."""
    if not c.contract_verified:
        return [Finding("unverified-contract", 25, "Contract source not verified on BscScan.")]
    return []


def rule_honeypot_failed(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Honeypot check failure — catastrophic, scoring forced low elsewhere."""
    if not c.honeypot_check_passed:
        return [Finding("honeypot-suspected", 40, "Honeypot check did not pass.")]
    return []


def rule_lp_not_locked(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """LP tokens not locked — rugpull risk."""
    if not c.lp_locked:
        return [Finding("lp-not-locked", 20, "Liquidity pool tokens are not locked.")]
    return []


def rule_high_concentration(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Top-10 wallets hold >70% of supply."""
    if c.top10_concentration_pct > 70.0:
        return [
            Finding(
                "high-top10-concentration",
                20,
                f"Top 10 wallets hold {c.top10_concentration_pct:.1f}% of supply.",
            )
        ]
    return []


def rule_low_holder_count(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Fewer than 20 holders."""
    if c.holder_count < 20:
        return [Finding("low-holder-count", 10, f"Only {c.holder_count} holders.")]
    return []


def rule_liquidity_too_thin(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Liquidity below $1k."""
    if c.liquidity_usd < 1_000:
        return [Finding("liquidity-too-thin", 15, f"Liquidity only ${c.liquidity_usd:,.0f}.")]
    return []


def rule_suspicious_velocity(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Tx velocity >300/min suggests wash trading."""
    if c.buy_sell_velocity_tx_per_min > 300:
        return [
            Finding(
                "wash-trading-suspected",
                15,
                f"Velocity {c.buy_sell_velocity_tx_per_min:.0f} tx/min suggests wash trading.",
            )
        ]
    return []


def rule_creator_has_history(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Creator has launched >10 tokens previously — serial-launcher penalty."""
    if c.creator_previous_tokens > 10:
        return [
            Finding(
                "serial-launcher",
                20,
                f"Creator has launched {c.creator_previous_tokens} tokens previously.",
            )
        ]
    return []


def rule_no_organic_buzz(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """organic_score below 15."""
    if s.organic_score < 15:
        return [Finding("no-organic-buzz", 10, f"organic_score is only {s.organic_score}.")]
    return []


def rule_negative_sentiment(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Aggregated sentiment below -0.4."""
    if s.sentiment < -0.4:
        return [Finding("negative-sentiment", 10, f"Sentiment is {s.sentiment:.2f}.")]
    return []


def rule_bot_shilling(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Social agent flagged copy-paste shilling."""
    if "copy-paste-shilling" in s.red_flags:
        return [Finding("copy-paste-shilling", 15, "Social agent flagged copy-paste shilling.")]
    return []


def rule_paid_promotion(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Social agent flagged paid promotion."""
    if "paid-promotion-disclosure" in s.red_flags:
        return [
            Finding("paid-promotion-disclosure", 5, "Social agent flagged paid promotion.")
        ]
    return []


def rule_whale_sniping(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """>5 whale entries in first observation window."""
    if c.whale_entries > 5:
        return [
            Finding(
                "whale-sniping",
                10,
                f"{c.whale_entries} whale entries detected early — possible sniping.",
            )
        ]
    return []


def rule_social_degraded(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Social data came back degraded — confidence penalty."""
    if s.data_quality.value == "degraded":
        return [
            Finding(
                "social-data-degraded",
                5,
                "Social data could not be fully gathered — confidence reduced.",
            )
        ]
    return []


def rule_chain_degraded(s: SocialScore, c: ChainMetrics) -> list[Finding]:  # noqa: ARG001
    """Chain data came back degraded — confidence penalty."""
    if c.data_quality.value == "degraded":
        return [
            Finding(
                "chain-data-degraded",
                5,
                "Chain data could not be fully gathered — confidence reduced.",
            )
        ]
    return []


ALL_RULES: tuple[Rule, ...] = (
    rule_unverified_contract,
    rule_honeypot_failed,
    rule_lp_not_locked,
    rule_high_concentration,
    rule_low_holder_count,
    rule_liquidity_too_thin,
    rule_suspicious_velocity,
    rule_creator_has_history,
    rule_no_organic_buzz,
    rule_negative_sentiment,
    rule_bot_shilling,
    rule_paid_promotion,
    rule_whale_sniping,
    rule_social_degraded,
    rule_chain_degraded,
)


def run_heuristics(s: SocialScore, c: ChainMetrics) -> list[Finding]:
    """Run every rule and return the flat list of triggered findings."""
    findings: list[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(s, c))
    return findings


def aggregate_score(findings: list[Finding]) -> int:
    """Collapse findings into a 0-100 score.

    Formula: start at 100, subtract weights, floor at 0. Honeypot-suspected
    short-circuits to a hard cap of 5.
    """
    if any(f.tag == "honeypot-suspected" for f in findings):
        return 5
    return max(0, 100 - sum(f.weight for f in findings))
