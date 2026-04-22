"""One-shot docstring-filler for SwarmScout.

Reads a dictionary of (filepath, function_name) -> docstring. For each,
finds the function or class definition, inserts the docstring as the first
statement of its body if one is missing, and rewrites the file.

Idempotent: running twice has no effect — if a function already has a
docstring we skip it.
"""

from __future__ import annotations

import ast
from pathlib import Path

# -------------------------------------------------------------------- mapping

DOCS: dict[tuple[str, str], str] = {
    # ====================== agents/chain/bscscan.py ======================
    ("agents/chain/bscscan.py", "__init__"): (
        "Initialise the BscScan client.\n\n"
        "Args:\n"
        "    base_url: Root of the BscScan API (testnet vs mainnet differs).\n"
        "    api_key: Free-tier key from bscscan.com.\n"
        "    rate_per_s: Requests per second cap; enforced via asyncio.Semaphore.\n"
        "    http: Optional injected httpx.AsyncClient for tests."
    ),
    ("agents/chain/bscscan.py", "_get"): (
        "Low-level GET with rate-limit + apikey injection.\n\n"
        "Every caller goes through this method so the per-second semaphore\n"
        "applies uniformly and the api_key is never forgotten."
    ),
    # ====================== agents/chain/main.py ======================
    ("agents/chain/main.py", "__init__"): (
        "Construct a ChainAgent.\n\n"
        "Args:\n"
        "    ctx: Shared process context (bus, db, anchor, router, settings).\n"
        "    bscscan: Pre-configured BscScan client."
    ),
    ("agents/chain/main.py", "_main_loop"): (
        "Consume ``stream:candidates`` under the ``chain:primary`` group.\n\n"
        "Each envelope is processed exactly once per consumer; on success\n"
        "we ack and increment metrics; on failure we log and count failure\n"
        "but never crash the loop."
    ),
    ("agents/chain/main.py", "_process"): (
        "Validate the incoming TokenCandidate and emit the ChainMetrics.\n\n"
        "Called once per consumed envelope."
    ),
    ("agents/chain/main.py", "_gather"): (
        "Fetch holders + contract meta + transfers in parallel.\n\n"
        "Uses ``asyncio.gather(return_exceptions=True)`` so one slow or\n"
        "failing sub-call only flips ``data_quality`` to degraded rather than\n"
        "dropping the whole metrics emission."
    ),
    ("agents/chain/main.py", "_meta_or_default"): (
        "Return the passed-in ContractMeta or a zero-valued placeholder.\n\n"
        "Isolated so the type-narrowing for ``isinstance(_, Exception)`` is\n"
        "done in one place."
    ),
    ("agents/chain/main.py", "_amain"): (
        "Async process entrypoint for the Chain agent.\n\n"
        "Builds the shared Context, instantiates the agent, runs until\n"
        "SIGINT/SIGTERM, then tears down pooled resources."
    ),
    # ====================== agents/common/base_agent.py ======================
    ("agents/common/base_agent.py", "__init__"): (
        "Initialise the metric bundle with fixed labels.\n\n"
        "Each metric is created with ``.labels(agent=agent)`` so the label\n"
        "is stamped in once and does not need to be re-passed at every\n"
        "increment call site."
    ),
    # ====================== agents/common/bus.py ======================
    ("agents/common/bus.py", "__init__"): (
        "Wrap or build a Redis async client.\n\n"
        "Args:\n"
        "    url: Redis URL (used when ``client`` is not provided).\n"
        "    client: Pre-built redis.asyncio.Redis — used in tests with\n"
        "        fakeredis so no real connection pool is opened."
    ),
    # ====================== agents/common/db.py ======================
    ("agents/common/db.py", "__init__"): (
        "Store the backing reference so repository methods can open sessions."
    ),
    ("agents/common/db.py", "_finding_from_row"): (
        "Hydrate a FindingRow from the raw SQLAlchemy mapping.\n\n"
        "Postgres can return ``payload`` either as a pre-parsed dict or as\n"
        "a JSON string depending on driver settings, so we normalise both."
    ),
    # ====================== agents/common/llm_router.py ======================
    ("agents/common/llm_router.py", "__init__"): (
        "Store pricing / circuit / provider references on the router instance."
    ),
    ("agents/common/llm_router.py", "_post"): (
        "POST helper shared by every _HTTPProvider.\n\n"
        "Retries on transient failures with exponential backoff (tenacity)\n"
        "before giving up to the caller. The retry policy is deliberately\n"
        "short: 3 attempts, 0.5-4 s, because the router itself will fall\n"
        "over to another provider if this one fails."
    ),
    ("agents/common/llm_router.py", "_note_dgrid_failure"): (
        "Increment the DGrid consecutive-failure counter.\n\n"
        "When the threshold is hit, stamp the cooldown start so the circuit\n"
        "stays open for ``DGRID_CIRCUIT_COOLDOWN_S`` seconds."
    ),
    ("agents/common/llm_router.py", "_note_dgrid_success"): (
        "Reset the DGrid failure counter to zero.\n\n"
        "Called on every successful DGrid response — returns the circuit\n"
        "to its closed / healthy state."
    ),
    # ====================== agents/common/on_chain.py ======================
    ("agents/common/on_chain.py", "__init__"): (
        "Build a Web3 + contract binding; optionally accept a pre-built AsyncWeb3 for tests."
    ),
    # ====================== agents/common/schemas/payloads.py ======================
    ("agents/common/schemas/payloads.py", "_normalise_address"): (
        "Lowercase the Ethereum address only if it starts with ``0X``.\n\n"
        "Pydantic v2 validators re-enter on re-assignment; keeping the\n"
        "conditional avoids unnecessary allocations on already-normalised\n"
        "input."
    ),
    ("agents/common/schemas/payloads.py", "_review_implies_null_score"): (
        "Single-field validator kept for future cross-field checks.\n\n"
        "The coupling between ``requires_human_review`` and nullity of\n"
        "``score_0_100`` is enforced by the Risk agent at emit time rather\n"
        "than here, since a strict model_validator would complicate\n"
        "partial-construction scenarios in tests."
    ),
    # ====================== agents/hunter/main.py ======================
    ("agents/hunter/main.py", "__init__"): (
        "Initialise HunterAgent with its Context and chosen source adapter."
    ),
    # ====================== agents/hunter/sources/polling.py ======================
    ("agents/hunter/sources/polling.py", "__init__"): (
        "Build a polling source with URL, interval, Redis cursor store, and HTTP client."
    ),
    # ====================== agents/hunter/sources/rpc_log.py ======================
    ("agents/hunter/sources/rpc_log.py", "__init__"): (
        "Configure the RPC-log source.\n\n"
        "Args:\n"
        "    rpc_url: BNB (or BSC mainnet) JSON-RPC endpoint.\n"
        "    factory_address: Four.meme token factory contract.\n"
        "    topic: TokenCreated event topic hash (0x…).\n"
        "    redis: Where to persist the ``last_block`` cursor.\n"
        "    poll_interval_s: How long to wait between log fetches.\n"
        "    w3: Optional pre-built AsyncWeb3 for tests."
    ),
    # ====================== agents/narrator/main.py ======================
    ("agents/narrator/main.py", "__init__"): (
        "Build the narrator; primary_model comes from settings."
    ),
    ("agents/narrator/main.py", "_main_loop"): (
        "Consume ``stream:risk`` under the narrator consumer group.\n\n"
        "One RiskVerdict in, one AlphaBrief or HumanReviewRequest out."
    ),
    ("agents/narrator/main.py", "_process"): (
        "Dispatch a RiskVerdict to either brief narration or human-review emission."
    ),
    ("agents/narrator/main.py", "_amain"): ("Async process entrypoint for the Narrator agent."),
    # ====================== agents/risk/main.py ======================
    ("agents/risk/main.py", "__init__"): (
        "Initialise the Risk agent with an empty pending-pair buffer."
    ),
    ("agents/risk/main.py", "_consume"): (
        "Generic consumer loop shared by the social and chain streams.\n\n"
        "``side`` parameterises the callback so the join logic treats the\n"
        "two streams symmetrically."
    ),
    ("agents/risk/main.py", "_on_message"): (
        "Store one side of the pair in the pending buffer; emit verdict if partner present.\n\n"
        "Guarded by ``self._pending_lock`` because two parallel tasks (one\n"
        "per stream) are both mutating the buffer. Duplicate same-side\n"
        "messages overwrite the earlier envelope (newest wins)."
    ),
    ("agents/risk/main.py", "_emit_verdict"): (
        "Compute heuristics, ask LLM for rationale, publish RiskVerdict on stream:risk."
    ),
    ("agents/risk/main.py", "_emit_partial"): (
        "Emit a degraded RiskVerdict when the join window expired without a partner."
    ),
    ("agents/risk/main.py", "_amain"): ("Async process entrypoint for the Risk agent."),
    # ====================== agents/social/main.py ======================
    ("agents/social/main.py", "__init__"): (
        "Build a SocialAgent.\n\n"
        "Args:\n"
        "    ctx: Shared context (bus, db, anchor, router).\n"
        "    x_scraper: Playwright-driven X search adapter.\n"
        "    telegram_scraper: Playwright-driven Telegram public-preview adapter."
    ),
    ("agents/social/main.py", "_main_loop"): (
        "Consume stream:candidates and emit SocialScore per TokenCandidate."
    ),
    ("agents/social/main.py", "_process"): (
        "Validate the incoming TokenCandidate, scrape + score, publish."
    ),
    ("agents/social/main.py", "_amain"): (
        "Async process entrypoint for the Social agent.\n\n"
        "Starts both Playwright contexts, runs the agent, tears down cleanly."
    ),
    # ====================== agents/social/scrapers/telegram_scraper.py ======================
    ("agents/social/scrapers/telegram_scraper.py", "__init__"): (
        "Build a TelegramScraper with the list of channels to probe."
    ),
    # ====================== agents/social/scrapers/x_scraper.py ======================
    ("agents/social/scrapers/x_scraper.py", "__init__"): (
        "Hold Playwright handles; the real browser opens in ``start()``."
    ),
    # ====================== api/main.py ======================
    ("api/main.py", "__init__"): ("Install the middleware with the per-minute capacity."),
    ("api/main.py", "dispatch"): (
        "Increment the per-IP counter in Redis; reject with 429 on overflow.\n\n"
        "The counter window is one minute (EXPIRE is set on first INCR).\n"
        "Capacity is taken from settings so it can be tuned without a deploy."
    ),
    # ====================== bot/main.py ======================
    ("bot/main.py", "_amain"): (
        "Async process entrypoint for the Telegram bot.\n\n"
        "Runs the aiogram dispatcher and the brief-delivery loop concurrently,\n"
        "tearing both down on SIGINT."
    ),
    # ====================== tests/integration/test_api.py ======================
    ("tests/integration/test_api.py", "class _Row"): (
        "Minimal standalone mirror of ``db.FindingRow`` for tests."
    ),
    ("tests/integration/test_api.py", "class _FakeFindings"): (
        "In-memory stand-in for ``FindingsRepository`` — returns one pre-baked row."
    ),
    ("tests/integration/test_api.py", "class _FakeHeartbeats"): (
        "In-memory stand-in for ``HeartbeatRepository`` — returns one online agent."
    ),
    ("tests/integration/test_api.py", "class _FakeAnchor"): (
        "In-memory stand-in for the on-chain anchor — ``verify()`` always None."
    ),
    ("tests/integration/test_api.py", "client"): (
        "FastAPI TestClient with ``app.state`` populated via a fake lifespan."
    ),
    ("tests/integration/test_api.py", "test_list_briefs"): (
        "``GET /briefs`` returns the one fake row."
    ),
    ("tests/integration/test_api.py", "test_get_brief"): (
        "``GET /briefs/{id}`` finds the fake row by its msg_id."
    ),
    ("tests/integration/test_api.py", "test_get_brief_missing"): (
        "``GET /briefs/{unknown}`` returns 404."
    ),
    ("tests/integration/test_api.py", "test_verify_brief"): (
        "``GET /briefs/{id}/verify`` returns hash_match=True and on_chain_present=False (NullAnchor)."
    ),
    ("tests/integration/test_api.py", "test_verify_missing_is_404"): (
        "``GET /briefs/{unknown}/verify`` returns 404."
    ),
    ("tests/integration/test_api.py", "test_health_ok"): (
        "``GET /health`` surfaces the fake heartbeat."
    ),
    ("tests/integration/test_api.py", "test_ready"): ("``GET /ready`` is unconditionally 200."),
    ("tests/integration/test_api.py", "test_metrics"): (
        "``GET /metrics`` returns Prometheus exposition-format text."
    ),
    ("tests/integration/test_api.py", "test_rate_limit_kicks_in"): (
        "Firing > capacity requests in one minute eventually produces a 429."
    ),
    ("tests/integration/test_api.py", "__init__"): (
        "Bake one Brief row with its hash already computed."
    ),
    ("tests/integration/test_api.py", "list_briefs"): (
        "Return the single baked row regardless of pagination args."
    ),
    ("tests/integration/test_api.py", "get"): (
        "Return the baked row if msg_id matches, else None."
    ),
    ("tests/integration/test_api.py", "all"): ("Return a single online hunter heartbeat."),
    ("tests/integration/test_api.py", "verify"): (
        "Always return None — no records in the fake anchor."
    ),
    ("tests/integration/test_api.py", "fake_lifespan"): (
        "Replacement lifespan that wires fake state instead of real dependencies."
    ),
    # ====================== tests/unit/test_agents.py ======================
    ("tests/unit/test_agents.py", "class _FakeResp"): (
        "Stand-in for ``httpx.Response`` used by the polling-source tests."
    ),
    ("tests/unit/test_agents.py", "class _FakeHTTP"): (
        "Stand-in for an ``httpx.AsyncClient`` that always returns a pre-baked body."
    ),
    ("tests/unit/test_agents.py", "__init__"): ("Hold the body and status; no side effects."),
    ("tests/unit/test_agents.py", "raise_for_status"): (
        "Raise an httpx.HTTPStatusError if the baked status is >=400."
    ),
    ("tests/unit/test_agents.py", "json"): ("Return the baked body verbatim."),
    ("tests/unit/test_agents.py", "get"): ("Ignore URL and return the fake response."),
    ("tests/unit/test_agents.py", "test_polling_map_item_happy"): (
        "A well-formed item maps cleanly to a RawTokenEvent."
    ),
    ("tests/unit/test_agents.py", "test_polling_map_item_rejects_non_dict"): (
        "Non-dict inputs return None rather than raising."
    ),
    ("tests/unit/test_agents.py", "test_polling_map_item_tolerates_missing_fields"): (
        "Missing required keys return None rather than raising."
    ),
    ("tests/unit/test_agents.py", "test_polling_fetch_batch_dedupes"): (
        "Second poll with unchanged cursor yields an empty batch (dedup works)."
    ),
    ("tests/unit/test_agents.py", "test_rpc_log_decode_malformed_returns_none"): (
        "Short topic list decodes to None, never to a garbage event."
    ),
    ("tests/unit/test_agents.py", "test_velocity_empty_returns_zero"): (
        "Empty transfer list -> 0 tx/min (no division by zero)."
    ),
    ("tests/unit/test_agents.py", "test_velocity_basic"): (
        "60 s span with 2 transfers -> 2 tx/min."
    ),
    ("tests/unit/test_agents.py", "test_velocity_bad_timestamps_returns_zero"): (
        "Non-numeric timestamps -> 0 tx/min rather than raising."
    ),
    ("tests/unit/test_agents.py", "test_whale_count_detects_high_transfers"): (
        "A transfer above $1k threshold counts as a whale entry."
    ),
    ("tests/unit/test_agents.py", "test_whale_count_tolerates_bad_data"): (
        "Malformed value / decimal fields do not raise; return 0."
    ),
    ("tests/unit/test_agents.py", "test_derive_conviction_boundaries"): (
        "All four tiers map from representative scores (10/50/70/90)."
    ),
    ("tests/unit/test_agents.py", "test_extract_token_name_found"): (
        "Token name is pulled from the TokenCandidate row in lineage."
    ),
    ("tests/unit/test_agents.py", "test_extract_token_name_missing"): (
        "When no lineage row has a token_name, return None."
    ),
    ("tests/unit/test_agents.py", "test_parse_json_fenced"): (
        "```json fenced content parses after stripping."
    ),
    ("tests/unit/test_agents.py", "test_parse_json_plain"): ("Unfenced JSON parses directly."),
    ("tests/unit/test_agents.py", "test_parse_json_invalid_returns_empty"): (
        "Malformed JSON returns {} rather than raising."
    ),
    ("tests/unit/test_agents.py", "test_parse_json_non_dict_returns_empty"): (
        "A JSON array returns {} — the parser is dict-only by contract."
    ),
    ("tests/unit/test_agents.py", "test_strip_fences_removes_backticks"): (
        "```json wrapped content is unwrapped to its inner JSON."
    ),
    ("tests/unit/test_agents.py", "test_strip_fences_plain_passthrough"): (
        "Text without fences is returned unchanged."
    ),
    # ====================== tests/unit/test_backend_core.py ======================
    ("tests/unit/test_backend_core.py", "_make_payload"): (
        "Small payload dict reused across envelope tests."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_accepts_valid"): (
        "A fully-specified Envelope constructs successfully."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_short_msg_id"): (
        "msg_id shorter than 26 chars raises ValidationError."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_bad_hash"): (
        "Non-hex payload_hash raises ValidationError."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_bad_model_used"): (
        "model_used without a provider/model slash raises ValidationError."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_invalid_ulid_chars"): (
        "Crockford-base32 forbids I and L — msg_id containing them fails."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_bad_upstream_id"): (
        "upstream_ids entries must themselves be 26-char ULIDs."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_rejects_non_iso_timestamp"): (
        "Free-form timestamps are rejected."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_accepts_model_none"): (
        "model_used=None is valid for non-LLM messages (e.g. Hunter emissions)."
    ),
    ("tests/unit/test_backend_core.py", "test_token_candidate_validates_address"): (
        "Non-hex token_address is rejected."
    ),
    ("tests/unit/test_backend_core.py", "test_social_score_bounds"): (
        "organic_score ∉ [0,100] or sentiment ∉ [-1,1] is rejected."
    ),
    ("tests/unit/test_backend_core.py", "test_chain_metrics_happy"): (
        "A valid ChainMetrics constructs with default data_quality=ok."
    ),
    ("tests/unit/test_backend_core.py", "test_risk_verdict_nullable_score"): (
        "score_0_100 may be None when the LLM stack is exhausted (FR-064)."
    ),
    ("tests/unit/test_backend_core.py", "test_risk_verdict_confidence_enum"): (
        "confidence must be one of the RiskConfidence enum values."
    ),
    ("tests/unit/test_backend_core.py", "test_risk_confidence_values"): (
        "RiskConfidence is exactly {low, medium, high}."
    ),
    ("tests/unit/test_backend_core.py", "test_alpha_brief_thesis_length"): (
        "AlphaBrief.thesis below 50 characters is rejected."
    ),
    ("tests/unit/test_backend_core.py", "test_human_review_request_shape"): (
        "HumanReviewRequest constructs with all required fields."
    ),
    ("tests/unit/test_backend_core.py", "test_bus_publish_and_consume"): (
        "XADD then XREADGROUP round-trip recovers the same envelope."
    ),
    ("tests/unit/test_backend_core.py", "test_bus_xlen"): (
        "XLEN reports the stream length after multiple publishes."
    ),
    ("tests/unit/test_backend_core.py", "test_bus_ensure_group_idempotent"): (
        "ensure_group() twice does not raise on BUSYGROUP."
    ),
    ("tests/unit/test_backend_core.py", "test_bus_pel_redelivery"): (
        "Unacked message is redelivered on the next consume (TC-F / reliability)."
    ),
    ("tests/unit/test_backend_core.py", "test_bus_decodes_valid_envelope_field"): (
        "A stream entry missing the ``envelope`` field raises ValueError on consume."
    ),
    ("tests/unit/test_backend_core.py", "test_msg_id_to_bytes32_shape"): (
        "ULID encodes to 32 bytes with right-zero padding; round-trips."
    ),
    ("tests/unit/test_backend_core.py", "test_msg_id_to_bytes32_rejects_too_long"): (
        "A msg_id longer than 32 bytes raises."
    ),
    ("tests/unit/test_backend_core.py", "test_payload_hash_hex_to_bytes32"): (
        "64 hex chars decode to 32 raw bytes."
    ),
    ("tests/unit/test_backend_core.py", "test_payload_hash_hex_rejects_bad_length"): (
        "Fewer than 64 hex chars raises."
    ),
    ("tests/unit/test_backend_core.py", "test_null_anchor_record_and_verify"): (
        "NullAnchor returns a deterministic placeholder; verify() is always None."
    ),
    ("tests/unit/test_backend_core.py", "test_settings_defaults"): (
        "Settings() constructs without environment overrides."
    ),
    ("tests/unit/test_backend_core.py", "test_settings_cached"): (
        "get_settings() is memoised (singleton per process)."
    ),
    ("tests/unit/test_backend_core.py", "test_logging_configures_without_errors"): (
        "configure_logging() + get_logger() + .info() does not raise."
    ),
    ("tests/unit/test_backend_core.py", "test_envelope_round_trips_through_json"): (
        "Envelope -> JSON -> Envelope preserves msg_id, payload_hash, and payload."
    ),
    # ====================== tests/unit/test_bot.py ======================
    ("tests/unit/test_bot.py", "test_passes_threshold_exact_match"): (
        "A brief at the exact user threshold passes."
    ),
    ("tests/unit/test_bot.py", "test_passes_threshold_below_is_false"): (
        "A degen-tier brief does not pass a high-tier subscriber."
    ),
    ("tests/unit/test_bot.py", "test_passes_threshold_above_is_true"): (
        "A high-tier brief passes a moderate-tier subscriber."
    ),
    ("tests/unit/test_bot.py", "test_passes_threshold_unknown_defaults_to_zero"): (
        "Unrecognised tier strings on both sides compare equal (no crash)."
    ),
    ("tests/unit/test_bot.py", "test_format_brief_has_bscscan_link"): (
        "Rendered brief body contains BscScan, conviction tier, and caveats."
    ),
    # ====================== tests/unit/test_hasher.py ======================
    ("tests/unit/test_hasher.py", "test_canonical_json_is_deterministic"): (
        "Same-content dicts in different insertion orders produce identical bytes."
    ),
    ("tests/unit/test_hasher.py", "test_canonical_json_formatting"): (
        "Serialised output has sorted keys, no whitespace, no separator padding."
    ),
    ("tests/unit/test_hasher.py", "test_hash_payload_shape"): (
        "hash_payload returns 64 lowercase hex chars."
    ),
    ("tests/unit/test_hasher.py", "test_hash_payload_stable_under_reordering"): (
        "Key reordering does not change the hash (this is the whole point)."
    ),
    ("tests/unit/test_hasher.py", "test_bytes32_matches_hex"): (
        "payload_hash_bytes32(p).hex() == hash_payload(p)."
    ),
    ("tests/unit/test_hasher.py", "test_canonical_json_unicode_preservation"): (
        "ensure_ascii=False keeps UTF-8 literals (é, etc.) rather than \\u-escaping."
    ),
    ("tests/unit/test_hasher.py", "test_canonical_json_refuses_nan"): (
        "allow_nan=False: NaN/Inf values raise ValueError."
    ),
    ("tests/unit/test_hasher.py", "test_canonical_json_sorts_nested"): (
        "Sorting is recursive into nested objects, not just the top level."
    ),
    ("tests/unit/test_hasher.py", "test_canonical_json_typeerror_on_set"): (
        "Non-JSON-serialisable types (like set) raise TypeError cleanly."
    ),
    ("tests/unit/test_hasher.py", "test_roundtrip_identity"): (
        "dumps -> loads -> hash_payload yields the same hash as hashing the original."
    ),
    # ====================== tests/unit/test_llm_router.py ======================
    ("tests/unit/test_llm_router.py", "__init__"): ("Start with an empty call log."),
    ("tests/unit/test_llm_router.py", "log"): (
        "Capture the call kwargs verbatim so test assertions can inspect them."
    ),
    ("tests/unit/test_llm_router.py", "chat"): (
        "Return a canned success response, or raise ProviderError up to ``raise_times``."
    ),
    ("tests/unit/test_llm_router.py", "audit"): ("Fresh in-memory audit log per test."),
    ("tests/unit/test_llm_router.py", "bucket"): (
        "TokenBucket capacity 10/minute bound to fakeredis."
    ),
    ("tests/unit/test_llm_router.py", "test_router_uses_dgrid_first"): (
        "Happy path: DGrid is primary and its response is returned."
    ),
    ("tests/unit/test_llm_router.py", "test_router_falls_back_on_dgrid_failure"): (
        "DGrid failure falls through to Anthropic on the first call."
    ),
    ("tests/unit/test_llm_router.py", "test_router_circuit_breaker_trips"): (
        "After 3 consecutive DGrid failures, _dgrid_available flips to False."
    ),
    ("tests/unit/test_llm_router.py", "test_rate_limiter_blocks_over_capacity"): (
        "Router surfaces RouterExhaustedError when every provider is rate-limited."
    ),
    ("tests/unit/test_llm_router.py", "test_token_bucket_raises_over_capacity"): (
        "Direct TokenBucket.acquire raises RateLimitedError past capacity."
    ),
    ("tests/unit/test_llm_router.py", "test_router_exhausted"): (
        "TC-F05: every configured provider failing raises RouterExhaustedError."
    ),
    ("tests/unit/test_llm_router.py", "test_prompt_hash_deterministic"): (
        "Same (system, messages) hashes identically; different system differs."
    ),
    ("tests/unit/test_llm_router.py", "test_circuit_resets_on_success"): (
        "After DGrid recovers, consecutive_failures returns to 0."
    ),
    ("tests/unit/test_llm_router.py", "test_router_no_providers"): (
        "Router with no providers at all raises RouterExhaustedError."
    ),
    ("tests/unit/test_llm_router.py", "test_cost_computed"): (
        "cost_usd is computed from the pricing table and surfaced on LLMResponse."
    ),
    # ====================== tests/unit/test_risk_heuristics.py ======================
    ("tests/unit/test_risk_heuristics.py", "_chain"): (
        "Build a ChainMetrics with safe defaults, override via kwargs per test."
    ),
    ("tests/unit/test_risk_heuristics.py", "_social"): (
        "Build a SocialScore with safe defaults, override via kwargs per test."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_unverified_contract_fires"): (
        "Unverified contracts produce the ``unverified-contract`` finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_unverified_contract_silent"): (
        "Verified contracts produce no finding from this rule."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_honeypot_failed"): (
        "Failed honeypot check fires the ``honeypot-suspected`` finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_lp_not_locked"): (
        "Unlocked LP fires the ``lp-not-locked`` finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_high_concentration"): (
        "Top-10 > 70% fires; 50% does not."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_low_holder_count"): (
        "Fewer than 20 holders fires."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_liquidity_too_thin"): (
        "Liquidity below $1k fires."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_suspicious_velocity"): (
        "Velocity > 300 tx/min fires the wash-trading finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_creator_has_history"): (
        "Creator with > 10 prior tokens fires the serial-launcher finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_no_organic_buzz"): (
        "organic_score < 15 fires the no-organic-buzz finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_negative_sentiment"): (
        "Sentiment < -0.4 fires the negative-sentiment finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_bot_shilling"): (
        "Social flag ``copy-paste-shilling`` propagates into the risk findings."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_paid_promotion"): (
        "Social flag ``paid-promotion-disclosure`` propagates."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_whale_sniping"): (
        "> 5 whale entries fires the whale-sniping finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_social_degraded"): (
        "Degraded social data adds a confidence-reduction finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_rule_chain_degraded"): (
        "Degraded chain data adds a confidence-reduction finding."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_all_rules_accept_clean_inputs"): (
        "With perfectly clean inputs, zero findings fire."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_aggregate_score_honeypot_short_circuits"): (
        "Honeypot-suspected forces a hard cap of 5, regardless of other findings."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_aggregate_score_floors_at_zero"): (
        "Many simultaneous rule fires cannot push the score below 0."
    ),
    ("tests/unit/test_risk_heuristics.py", "test_all_rules_exported"): (
        "ALL_RULES tuple contains exactly 15 entries (one per named heuristic)."
    ),
}


def insert_docstrings(filepath: Path) -> tuple[int, int]:
    """Parse ``filepath``, insert every matching docstring from DOCS, return (added, skipped)."""
    src = filepath.read_text()
    tree = ast.parse(src)
    inserts: list[
        tuple[int, int, str, str]
    ] = []  # (body_start_lineno, body_start_col, docstring, target_name)

    file_key = str(filepath).replace("\\", "/")

    def _wants(name: str, node: ast.AST) -> str | None:
        """Look up the docstring for ``name`` in this file; return None if absent."""
        key = (file_key, name)
        if key in DOCS:
            return DOCS[key]
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(node):
                continue
            name = f"class {node.name}" if isinstance(node, ast.ClassDef) else node.name
            doc = _wants(name, node)
            if doc is None:
                continue
            # Find the line where the body begins
            first_stmt = node.body[0] if node.body else None
            if first_stmt is None:
                continue
            inserts.append((first_stmt.lineno, first_stmt.col_offset, doc, name))

    if not inserts:
        return (0, 0)

    # Apply inserts bottom-up so earlier line numbers stay valid.
    inserts.sort(key=lambda t: t[0], reverse=True)
    lines = src.splitlines(keepends=True)
    for lineno, col, doc, _name in inserts:
        indent = " " * col
        # Build a triple-quoted docstring. Use raw-looking quoting; escape backslashes minimally.
        prefix = "r" if "\\" in doc else ""
        if "\n" in doc:
            body_lines = [f'{indent}{prefix}"""{doc.splitlines()[0]}\n']
            for line in doc.splitlines()[1:]:
                body_lines.append(f"{indent}{line}\n" if line else "\n")
            body_lines.append(f'{indent}"""\n')
            block = "".join(body_lines)
        else:
            block = f'{indent}{prefix}"""{doc}"""\n'
        lines.insert(lineno - 1, block)

    new_src = "".join(lines)
    # Verify we still parse cleanly.
    ast.parse(new_src)
    filepath.write_text(new_src)
    return (len(inserts), 0)


def main() -> None:
    """Run the docstring inserter across every referenced file."""
    root = Path()
    touched_files = sorted({Path(k[0]) for k in DOCS})
    total_added = 0
    for fp in touched_files:
        full = root / fp
        if not full.exists():
            print(f"MISS  {fp}")
            continue
        added, _ = insert_docstrings(full)
        total_added += added
        print(f"{added:3}  {fp}")
    print(f"\nTotal inserted: {total_added}")


if __name__ == "__main__":
    main()
