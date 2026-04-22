# Traceability Matrix

**Project:** SwarmScout (HACK0015 — Four.Meme AI Sprint)
**Owner:** Senthil (solo)
**Author of this matrix:** Build Session (web), 2026-04-22
**Scope of coverage:** every ID present in `docs/01_Requirements.md` (181 items) — FR-###, NFR-###, W-## (won't-haves), A-## (assumptions), C-## (constraints) — mapped forward to scenario, use case, user flow, high-level design section, low-level design section, implementation file(s), test coverage, and relevant automation script.

**How to read:** one row per requirement ID. Columns:
- **Req ID** — the item in `01_Requirements.md`
- **MoSCoW** — M/S/C/W per 01_Requirements
- **Scenario** — matching narrative in `03_Scenarios.md` (SC-##) or anti-scenario (AS-##)
- **Use Case** — matching use case in `04_UseCases.md` (UC-##)
- **User Flow** — matching flow in `05_UserFlow.md` (UF-##)
- **HLD §** — reference in `06_HLD.md`
- **LLD §** — reference in `07_LLD.md`
- **Code** — filepath(s) in the repo that implement the requirement
- **Test** — test file + TC-## reference (or "—" if the requirement is purely architectural / written-only)
- **Script** — automation script that exercises or enforces it (or "—")
- **Status** — ✅ covered in first cut, 🟡 partial, ⏳ deferred to Desktop (see `docs/REVIEW_FIRST_CUT.md`)

`—` in any column means the row legitimately has no artifact of that kind; that is not a gap.

---

## Functional Requirements — Hunter (FR-001 … FR-010)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-001 | M | SC-01 | UC-01 | UF-01 | §3.1 Hunter | §1.2 | `agents/hunter/main.py`, `agents/hunter/sources/polling.py` | `tests/unit/test_agents.py::test_polling_*` | — | ✅ |
| FR-002 | M | SC-01 | UC-01 | UF-01 | §3.1 | §1.2 | `agents/hunter/sources/rpc_log.py` | `tests/unit/test_agents.py::test_rpc_log_decode_malformed_returns_none` | — | ✅ |
| FR-003 | M | SC-01 | UC-01 | UF-01 | §3.1 | §1.2, §4 | `agents/hunter/main.py::_to_candidate`, `agents/common/schemas/payloads.py::TokenCandidate` | `tests/unit/test_backend_core.py::test_token_candidate_validates_address` | — | ✅ |
| FR-004 | M | SC-01 | UC-01 | UF-01 | §3.1 | §1.2 | `agents/common/base_agent.py::anchor_and_publish` | `tests/integration/test_api.py::test_verify_brief` | — | ✅ |
| FR-005 | S | SC-01, AS-02 | UC-01 | UF-01 | §3.1 | §1.2 | `agents/hunter/sources/polling.py::_fetch_batch` (last-seen cursor) | `tests/unit/test_agents.py::test_polling_fetch_batch_dedupes` | — | ✅ |
| FR-006 | S | SC-01 | UC-01 | — | §3.1 | §1.2 | `agents/hunter/sources/polling.py::LAST_SEEN_KEY` | — | — | 🟡 (cursor written; no snapshot/restore test) |
| FR-007 | C | SC-02 | UC-02 | UF-02 | §3.1 | §1.2 | `agents/common/base_agent.py::AgentMetrics` | — | — | 🟡 |
| FR-008 | M | SC-02 | UC-13 | UF-07 | §3.5 | §1.1 | `agents/common/base_agent.py::_heartbeat_loop`, `agents/common/db.py::HeartbeatRepository` | `tests/integration/test_api.py::test_health_ok` | — | ✅ |
| FR-009 | C | — | UC-01 | — | §3.1 | §1.2 | `agents/hunter/main.py` (cleanup on stop) | — | — | 🟡 |
| FR-010 | C | — | UC-01 | — | §3.1 | §1.2 | `agents/common/base_agent.py::_install_signals` | — | — | 🟡 |

## Functional Requirements — Social (FR-019 … FR-029)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-019 | M | SC-03 | UC-03 | UF-02 | §3.2 Social | §1.3 | `agents/social/main.py::SocialAgent._main_loop` (consumer group) | — | — | 🟡 (loop wired; integration not asserted) |
| FR-020 | M | SC-03 | UC-03 | — | §3.2 | §1.3 | `agents/social/scrapers/x_scraper.py` | `tests/unit/test_agents.py::test_strip_fences_*` | — | 🟡 (helper tested; live scrape not mocked) |
| FR-021 | M | SC-03 | UC-03 | — | §3.2 | §1.3 | `agents/social/scrapers/telegram_scraper.py` | — | — | 🟡 |
| FR-022 | S | AS-03 | UC-03 | — | §3.2 | §1.3 | `x_scraper.py::ScrapeResult.degraded` path | — | — | 🟡 |
| FR-023 | M | SC-03 | UC-03 | — | §3.2 | §1.3, §4 | `agents/common/schemas/payloads.py::SocialScore` | `tests/unit/test_backend_core.py::test_social_score_bounds` | — | ✅ |
| FR-024 | S | SC-03 | UC-03 | — | §3.2 | §1.3 | `agents/social/main.py::_score` (LLM classification) | — | — | 🟡 (path exists; no dedicated unit test) |
| FR-025 | S | SC-03 | UC-03 | — | §3.2 | §1.3 | `agents/social/main.py::_score` red_flags accumulation | — | — | 🟡 |
| FR-026 | S | AS-03 | UC-03 | — | §3.2 | §1.3 | `SocialScore.data_quality` + `red_flags` fallbacks | — | — | 🟡 |
| FR-027 | C | — | UC-03 | — | §3.2 | §1.3 | `agents/social/main.py::_gather` parallel asyncio.gather | — | — | 🟡 |
| FR-028 | S | SC-03 | UC-03 | — | §3.2 | §1.3 | `agents/social/main.py::_score::influencers` | — | — | 🟡 |
| FR-029 | C | — | UC-03 | — | §3.2 | §1.3 | implicit via `TokenCandidate.token_symbol` | — | — | 🟡 |

## Functional Requirements — Chain (FR-039 … FR-047)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-039 | M | SC-04 | UC-04 | UF-02 | §3.3 Chain | §1.4 | `agents/chain/main.py::ChainAgent._main_loop` | — | — | 🟡 |
| FR-040 | M | SC-04 | UC-04 | — | §3.3 | §1.4 | `agents/chain/bscscan.py::BscScanClient` | — | — | 🟡 (client written; live call not mocked) |
| FR-041 | M | SC-04 | UC-04 | — | §3.3 | §1.4 | `agents/chain/bscscan.py::holders`, `contract_meta` | — | — | 🟡 |
| FR-042 | M | SC-04 | UC-04 | — | §3.3 | §1.4, §4 | `agents/common/schemas/payloads.py::ChainMetrics` | `tests/unit/test_backend_core.py::test_chain_metrics_happy` | — | ✅ |
| FR-043 | S | SC-04 | UC-04 | — | §3.3 | §1.4 | `agents/chain/main.py::_velocity_tx_per_min` | `tests/unit/test_agents.py::test_velocity_*` | — | ✅ |
| FR-044 | S | SC-04 | UC-04 | — | §3.3 | §1.4 | `agents/chain/main.py::_whale_count` | `tests/unit/test_agents.py::test_whale_count_*` | — | ✅ |
| FR-045 | S | SC-04 | UC-04 | — | §3.3 | §1.4 | `agents/chain/main.py::_gather::honeypot_ok` | — | — | 🟡 (surrogate check; real honeypot svc deferred) |
| FR-046 | S | SC-04 | UC-04 | — | §3.3 | §1.4 | `ChainMetrics.lp_locked` field | — | — | 🟡 (field exists; locker lookup deferred) |
| FR-047 | C | — | UC-04 | — | §3.3 | §1.4 | `agents/chain/main.py::_gather` `return_exceptions=True` | — | — | 🟡 |

## Functional Requirements — Risk (FR-059 … FR-067)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-059 | M | SC-05 | UC-05 | UF-02 | §3.4 Risk | §1.5 | `agents/risk/main.py::RiskAgent` | — | — | 🟡 |
| FR-060 | M | SC-05 | UC-05 | — | §3.4 | §1.5 | `agents/risk/main.py::_consume` (two groups) | — | — | 🟡 |
| FR-061 | M | SC-05 | UC-05 | — | §3.4 | §1.5 | `agents/risk/main.py::JOIN_TIMEOUT_S`, `_sweep_timeouts` | — | — | 🟡 (logic present; timeout test deferred) |
| FR-062 | M | SC-05 | UC-05 | — | §3.4 | §1.5, §4 | `agents/common/schemas/payloads.py::RiskVerdict`, `agents/risk/heuristics.py` (15 rules) | `tests/unit/test_risk_heuristics.py` (20 tests) | — | ✅ |
| FR-063 | S | SC-05, AS-04 | UC-05 | — | §3.4 | §1.5 | `agents/risk/main.py::_emit_partial` | — | — | 🟡 |
| FR-064 | M | AS-04 | UC-05 | — | §3.4 | §1.5 | `agents/risk/main.py::_emit_verdict` (requires_human_review) | `tests/unit/test_llm_router.py::test_router_exhausted` | — | ✅ |
| FR-065 | S | SC-05 | UC-05 | — | §3.4 | §1.5 | `agents/risk/heuristics.py::aggregate_score` (honeypot short-circuit) | `tests/unit/test_risk_heuristics.py::test_aggregate_score_honeypot_short_circuits` | — | ✅ |
| FR-066 | S | SC-05 | UC-05 | — | §3.4 | §1.5 | `RiskVerdict.confidence` enum | `tests/unit/test_backend_core.py::test_risk_confidence_values` | — | ✅ |
| FR-067 | C | — | UC-05 | — | §3.4 | §1.5 | `agents/risk/main.py::_pending_lock` | — | — | 🟡 |

## Functional Requirements — Narrator (FR-079 … FR-087)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-079 | M | SC-06 | UC-06 | UF-02 | §3.5 Narrator | §1.6 | `agents/narrator/main.py::NarratorAgent` | — | — | 🟡 |
| FR-080 | M | SC-06 | UC-06 | — | §3.5 | §1.6 | `agents/narrator/main.py::_process` | — | — | 🟡 |
| FR-081 | M | SC-06 | UC-06 | — | §3.5 | §1.6 | `agents/narrator/main.py::_narrate` | — | — | 🟡 |
| FR-082 | M | SC-06 | UC-06 | — | §3.5 | §1.6, §4 | `agents/common/schemas/payloads.py::AlphaBrief` | `tests/unit/test_backend_core.py::test_alpha_brief_thesis_length` | — | ✅ |
| FR-083 | S | SC-06 | UC-06 | — | §3.5 | §1.6 | `_derive_conviction` | `tests/unit/test_agents.py::test_derive_conviction_boundaries` | — | ✅ |
| FR-084 | S | SC-06 | UC-06 | — | §3.5 | §1.6 | `_narrate::models` collection | — | — | 🟡 |
| FR-085 | S | SC-06 | UC-06 | — | §3.5 | §1.6 | `AlphaBrief.sources`, `AlphaBrief.caveats` | — | — | 🟡 |
| FR-086 | M | AS-04 | UC-06 | — | §3.5 | §1.6 | `agents/narrator/main.py::_process::HumanReviewRequest` branch, `stream:human_review` | — | — | 🟡 (branch exists; dedicated test deferred) |
| FR-087 | C | — | UC-06 | — | §3.5 | §1.6 | `_extract_token_name` | `tests/unit/test_agents.py::test_extract_token_name_*` | — | ✅ |

## Functional Requirements — Bus + Envelope (FR-099 … FR-106)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-099 | C | — | UC-07 | — | §4 | §1.1 | `agents/common/bus.py` | — | — | 🟡 |
| FR-100 | M | SC-07 | UC-07 | — | §4 | §1.1, §4 | `agents/common/schemas/envelope.py::Envelope` | `tests/unit/test_backend_core.py::test_envelope_*` | — | ✅ |
| FR-101 | M | SC-07 | UC-07 | — | §4 | §1.1 | `agents/common/hasher.py::hash_payload` | `tests/unit/test_hasher.py` (10 tests) | — | ✅ |
| FR-102 | S | SC-07 | UC-07 | — | §4 | §1.1 | `agents/common/bus.py::publish::maxlen` | `tests/unit/test_backend_core.py::test_bus_xlen` | — | ✅ |
| FR-103 | C | — | UC-07 | — | §4 | §1.1 | `agents/common/bus.py::ensure_group` | `tests/unit/test_backend_core.py::test_bus_ensure_group_idempotent` | — | ✅ |
| FR-104 | M | SC-07 | UC-07 | — | §4 | §1.1 | `agents/common/bus.py::consume` | `tests/unit/test_backend_core.py::test_bus_publish_and_consume` | — | ✅ |
| FR-105 | S | AS-05 | UC-07 | — | §4 | §1.1 | `agents/common/bus.py::consume` PEL-first drain | `tests/unit/test_backend_core.py::test_bus_pel_redelivery` | — | ✅ |
| FR-106 | S | SC-07 | UC-07 | — | §4 | §1.1 | `agents/common/bus.py::pending_depth` | — | — | 🟡 |

## Functional Requirements — On-Chain (FR-119 … FR-127)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-119 | C | — | UC-08 | — | §5 | §3.1 | `contracts/src/FindingsRegistry.sol` | `contracts/test/FindingsRegistry.t.sol::test_exists` | `scripts/seed_testnet_wallet.sh` | ✅ |
| FR-120 | M | SC-08 | UC-08 | UF-05 | §5 | §3.1 | `FindingsRegistry.recordFinding` | `FindingsRegistry.t.sol::test_recordFinding_happyPath` | `contracts/script/Deploy.s.sol` | ✅ |
| FR-121 | M | SC-08 | UC-08 | — | §5 | §3.1 | `FindingsRegistry.verifyFinding` | `FindingsRegistry.t.sol::test_verifyFinding_returnsZeroForMissing` | — | ✅ |
| FR-122 | M | SC-08 | UC-08 | — | §5 | §3.1 | `FindingsRegistry.grantAgent`/`revokeAgent` | `FindingsRegistry.t.sol::test_grantAndRevokeAgent` | — | ✅ |
| FR-123 | M | AS-06 | UC-08 | — | §5 | §3.1 | `FindingsRegistry.AlreadyRecorded` error | `FindingsRegistry.t.sol::test_recordFinding_revertsOnReplay` + `fuzz.t.sol::testFuzz_replayAlwaysReverts` | — | ✅ |
| FR-124 | S | — | UC-08 | — | §5 | §1.1 | `agents/common/on_chain.py::msg_id_to_bytes32` | `tests/unit/test_backend_core.py::test_msg_id_to_bytes32_shape` | — | ✅ |
| FR-125 | S | — | UC-08 | — | §5 | §1.1 | `agents/common/on_chain.py::payload_hash_hex_to_bytes32` | `tests/unit/test_backend_core.py::test_payload_hash_hex_to_bytes32` | — | ✅ |
| FR-126 | S | — | UC-08 | — | §5 | §1.1 | `agents/common/on_chain.py::OnChainAnchor.record` | `tests/unit/test_backend_core.py::test_null_anchor_record_and_verify` | — | 🟡 (null anchor tested; live wait_for_receipt path not) |
| FR-127 | C | — | UC-08 | — | §5 | §1.1 | `NullAnchor` fallback | same | — | ✅ |

## Functional Requirements — LLM Router (FR-139 … FR-145)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-139 | C | — | UC-09 | — | §6 | §1.1 | `agents/common/llm_router.py` | — | — | 🟡 |
| FR-140 | M | SC-09 | UC-09 | — | §6 | §1.1 | `LLMRouter.chat::DGrid path` | `tests/unit/test_llm_router.py::test_router_uses_dgrid_first` | — | ✅ |
| FR-141 | M | SC-09, AS-07 | UC-09 | — | §6 | §1.1 | `LLMRouter._dgrid_available`, fallback chain | `test_router_falls_back_on_dgrid_failure`, `test_router_circuit_breaker_trips`, `test_circuit_resets_on_success` | — | ✅ |
| FR-142 | S | SC-09 | UC-09 | — | §6 | §1.1 | `TokenBucket.acquire` | `test_token_bucket_raises_over_capacity`, `test_rate_limiter_blocks_over_capacity` | — | ✅ |
| FR-143 | M | AS-07 | UC-09 | — | §6 | §1.1 | `LLMCallRepository.log` | `test_router_uses_dgrid_first` asserts audit call | — | ✅ |
| FR-144 | S | SC-09 | UC-09 | — | §6 | §1.1 | `LLMRouter._hash_messages` | `test_prompt_hash_deterministic` | — | ✅ |
| FR-145 | M | AS-07 | UC-09 | — | §6 | §1.1 | `RouterExhaustedError` | `test_router_exhausted`, `test_router_no_providers` | — | ✅ |

## Functional Requirements — Telegram Bot (FR-159 … FR-166)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-159 | C | — | UC-10 | UF-03 | §7 Bot | §1.8 | `bot/main.py` | — | — | 🟡 |
| FR-160 | M | SC-10 | UC-10 | UF-03 | §7 | §1.8 | `bot/main.py::_delivery_loop` | — | — | 🟡 |
| FR-161 | M | SC-10 | UC-10 | UF-03 | §7 | §1.8 | `bot/handlers/commands.py` (all 7 commands) | — | — | 🟡 (handlers wired; no aiogram test) |
| FR-162 | M | SC-11 | UC-12 | UF-04 | §7 | §1.8 | `bot/handlers/commands.py::on_threshold`, `passes_threshold` | `tests/unit/test_bot.py::test_passes_threshold_*` | — | ✅ |
| FR-163 | S | SC-10 | UC-10 | — | §7 | §1.8 | `bot/main.py::_format_brief` | `tests/unit/test_bot.py::test_format_brief_has_bscscan_link` | — | ✅ |
| FR-164 | S | AS-08 | UC-10 | — | §7 | §1.8 | `bot/main.py::TelegramRetryAfter` handler | — | — | 🟡 |
| FR-165 | M | SC-10 | UC-10 | — | §7 | §1.8 | `bot/main.py::dedup_key` Redis SET | — | — | 🟡 |
| FR-166 | M | SC-10 | UC-10 | UF-03 | §7 | §1.8 | `bot/main.py::_dispatch_one` | — | — | 🟡 |

## Functional Requirements — Dashboard (FR-179 … FR-189)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-179 | C | — | UC-11 | UF-06 | §8 Web | §2 | `web/app/layout.tsx`, `web/app/page.tsx` | — | — | 🟡 |
| FR-180 | M | SC-12 | UC-11 | UF-06 | §8 | §2 | `web/components/BriefCard.tsx` | `web/tests/BriefCard.test.tsx` (10 tests) | — | ✅ |
| FR-181 | M | SC-12 | UC-11 | UF-06 | §8 | §2.1 | `web/app/page.tsx` (server component SSR) | `web/tests/e2e/dashboard.spec.ts::loads the feed` | — | ✅ |
| FR-182 | S | SC-12 | UC-11 | — | §8 | §2.1 | `web/app/page.tsx` (async server fetch) | same | — | ✅ |
| FR-183 | M | SC-12 | UC-11 | UF-06 | §8 | §2.2 | `web/components/SwarmHealthPanel.tsx` | `web/tests/panels.test.tsx::SwarmHealthPanel` | — | ✅ |
| FR-184 | M | SC-12 | UC-11 | UF-06 | §8 | §2.2 | `web/components/ModelUsagePanel.tsx` | `web/tests/panels.test.tsx::ModelUsagePanel` | — | ✅ |
| FR-185 | M | SC-12 | UC-11 | UF-06 | §8 | §2.2 | `web/components/ActivityTimelinePanel.tsx` | `web/tests/panels.test.tsx::ActivityTimelinePanel` | — | ✅ |
| FR-186 | M | SC-12 | UC-11 | UF-06 | §8 | §2.4 | `web/lib/hooks/useBriefStream.ts` | `web/tests/useBriefStream.test.tsx` (5 tests) | — | ✅ |
| FR-187 | M | SC-12 | UC-11 | — | §8 | §2 | `web/tailwind.config.js` responsive grid in `page.tsx` | `web/tests/e2e/dashboard.spec.ts::mobile viewport` | — | ✅ |
| FR-188 | S | SC-12 | UC-11 | — | §8 | §2.4 | `useBriefStream` polling fallback | `web/tests/useBriefStream.test.tsx::falls back to polling` | — | ✅ |
| FR-189 | S | SC-12 | UC-11 | — | §8 | §2 | `web/components/BriefCard.tsx` verify link | `web/tests/BriefCard.test.tsx::provides BscScan and Verify links` | — | ✅ |

## Functional Requirements — API (FR-199 … FR-204)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-199 | C | — | UC-14 | UF-08 | §9 API | §1.7 | `api/main.py` | — | — | 🟡 |
| FR-200 | M | SC-13 | UC-14 | UF-08 | §9 | §1.7 | `api/routes/briefs.py::list_briefs`, `get_brief` | `tests/integration/test_api.py::test_list_briefs`, `test_get_brief` | — | ✅ |
| FR-201 | M | SC-13 | UC-14 | UF-08 | §9 | §1.7 | `api/routes/briefs.py::verify_brief` | `test_verify_brief`, `test_verify_missing_is_404` | — | ✅ |
| FR-202 | M | SC-13 | UC-14 | — | §9 | §1.7 | `api/routes/ws.py` + Redis Pub/Sub | — | — | 🟡 (route exists; no end-to-end WS test) |
| FR-203 | M | AS-09 | UC-14 | — | §9 | §1.7 | `api/main.py::RateLimitMiddleware` | `tests/integration/test_api.py::test_rate_limit_kicks_in` | — | ✅ |
| FR-204 | S | SC-13 | UC-14 | UF-08 | §9 | §1.7 | `api/main.py::/metrics`, `api/routes/health.py` | `test_metrics`, `test_health_ok`, `test_ready` | `scripts/smoke_test.sh` | ✅ |

## Functional Requirements — Observability / Provenance (FR-219 … FR-223, FR-239)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FR-219 | C | — | UC-15 | — | §10 | §1.1 | `agents/common/logging_config.py` | `tests/unit/test_backend_core.py::test_logging_configures_without_errors` | — | ✅ |
| FR-220 | M | SC-14 | UC-15 | — | §10 | §1.1 | structlog JSON output | same | — | ✅ |
| FR-221 | M | SC-14 | UC-15 | — | §10 | §1.1 | `AgentMetrics` Prometheus counters | — | — | 🟡 |
| FR-222 | S | SC-14 | UC-15 | — | §10 | §1.1 | `agents/common/metrics.py::start_metrics_server` | — | — | 🟡 |
| FR-223 | S | — | UC-15 | — | §10 | §1.1 | `FindingsRepository.iter_lineage` | `tests/integration/test_api.py::test_verify_brief` (lineage indirect) | — | 🟡 |
| FR-239 | C | — | UC-16 | — | §10 | §1.1 | `Envelope.model_used` field | `test_envelope_rejects_bad_model_used` | — | ✅ |

## Non-Functional Requirements — Performance (NFR-200 … NFR-202)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-200 | S | SC-15 | — | — | §11 | §6 | `MAXLEN ~ 100000`, `DEFAULT_BATCH=16` in `bus.py` | — | — | ⏳ (TC-P## deferred) |
| NFR-201 | S | SC-15 | — | — | §11 | §6 | `asyncio.gather` in `social/main.py::_gather`, `chain/main.py::_gather` | — | — | ⏳ |
| NFR-202 | S | SC-15 | — | — | §11 | §6 | `bscscan.py` per-second semaphore | — | — | ⏳ |

## Non-Functional Requirements — Reliability (NFR-219 … NFR-223)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-219 | C | — | — | — | §11 | §6 | `docker-compose.yml::restart: unless-stopped` | — | `scripts/deploy.sh` | 🟡 |
| NFR-220 | M | SC-16 | — | — | §11 | §6 | Redis AOF `appendfsync everysec` in compose | — | — | ✅ |
| NFR-221 | M | AS-05 | — | — | §11 | §6 | PEL redelivery in `bus.py::consume` | `test_bus_pel_redelivery` | — | ✅ |
| NFR-222 | S | — | — | — | §11 | §6 | `tenacity` retries in `llm_router.py::_post` | — | — | 🟡 |
| NFR-223 | S | — | — | — | §11 | §6 | `restart: unless-stopped` | — | — | 🟡 |

## Non-Functional Requirements — Scalability (NFR-239 … NFR-244)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-239 | S | — | — | — | §11 | §6 | consumer-group architecture in `bus.py` | — | — | 🟡 |
| NFR-240 | S | — | — | — | §11 | §6 | stateless agent processes | — | — | 🟡 |
| NFR-241 | C | — | — | — | §11 | §6 | Redis single-instance (documented limitation) | — | — | ⏳ (v2) |
| NFR-242 | C | — | — | — | §11 | §6 | Postgres 16, single node | — | — | ⏳ (v2) |
| NFR-243 | C | — | — | — | §11 | §6 | indices on `findings (agent, created_at DESC)` | — | — | ✅ |
| NFR-244 | S | — | — | — | §11 | §6 | `MAXLEN ~ 100000` trim | — | — | ✅ |

## Non-Functional Requirements — Data Integrity (NFR-259 … NFR-262)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-259 | C | — | — | — | §11 | §1.1 | `hasher.py::canonical_json` three-flag rule | `test_canonical_json_formatting`, `test_canonical_json_unicode_preservation` | — | ✅ |
| NFR-260 | M | SC-17 | UC-16 | — | §11 | §1.1 | SHA-256 on-chain anchoring | `FindingsRegistry.fuzz.t.sol::testFuzz_recordVerifyRoundTrip` | `scripts/export_schemas.py` | ✅ |
| NFR-261 | M | SC-17 | UC-16 | — | §11 | §1.1 | append-only contract (no update/delete) | `FindingsRegistry.invariant.t.sol::invariant_recordedHashesUnchanged`, `invariant_existsIsMonotonic` | — | ✅ |
| NFR-262 | M | — | UC-16 | — | §11 | §1.1, §4 | `Envelope` pydantic validation | `test_envelope_*` (8 tests) | `scripts/export_schemas.py` | ✅ |

## Non-Functional Requirements — Observability (NFR-279 … NFR-283)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-279 | C | — | — | — | §10 | §1.1 | `structlog` setup | `test_logging_configures_without_errors` | — | ✅ |
| NFR-280 | M | SC-14 | UC-15 | — | §10 | §1.1 | JSONRenderer in `logging_config.py` | same | — | ✅ |
| NFR-281 | S | SC-14 | UC-15 | — | §10 | §1.1 | Prometheus via `prometheus_client` | — | `scripts/smoke_test.sh` | 🟡 |
| NFR-282 | S | — | UC-15 | — | §10 | §1.1 | `agents/common/base_agent.py` context-vars | — | — | 🟡 |
| NFR-283 | C | — | — | — | §10 | §1.1 | `Envelope.model_used` surfaced everywhere | `test_envelope_rejects_bad_model_used` | — | ✅ |

## Non-Functional Requirements — Security (NFR-299 … NFR-302)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-299 | C | — | — | — | §12 | §6 | `.env.example` + `.gitignore` + detect-secrets | — | — | ✅ |
| NFR-300 | M | AS-10 | — | — | §12 | §6 | no-demo-phrase pre-commit + CI grep | — | `.github/workflows/ci.yml::grep-forbidden-phrases` | ✅ |
| NFR-301 | M | — | — | — | §12 | §6 | contract whitelist (`FindingsRegistry.onlyAgent`) | `FindingsRegistry.t.sol::test_recordFinding_revertsForNonAgent` | — | ✅ |
| NFR-302 | S | — | — | — | §12 | §6 | FastAPI CORS allowlist | — | — | 🟡 |

## Non-Functional Requirements — Cost control (NFR-319 … NFR-327)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-319 | C | — | — | — | §12 | §1.1 | daily cap settings | — | — | 🟡 (fields wired; enforcement deferred) |
| NFR-320 | S | — | — | — | §12 | §1.1 | `LLMCallRepository.cost_by_provider` | — | — | 🟡 |
| NFR-321 | S | — | — | — | §12 | §1.1 | per-model pricing table in `llm_router.py::DEFAULT_PRICING` | `test_cost_computed` | — | ✅ |
| NFR-322 | S | — | — | — | §12 | §1.1 | per-agent primary model pins in `.env.example` | — | — | ✅ |
| NFR-323 | C | — | — | — | §12 | §1.1 | token-bucket rate limit per agent+provider | `test_rate_limiter_blocks_over_capacity` | — | ✅ |
| NFR-324 | C | — | — | — | §12 | §1.1 | cheap models first in fallback chain | — | — | ✅ |
| NFR-325 | C | — | — | — | §12 | §1.1 | `BscScanClient._rate` semaphore | — | — | ✅ |
| NFR-326 | C | — | — | — | §12 | §1.1 | MAXLEN trimming | — | — | ✅ |
| NFR-327 | C | — | — | — | §12 | §1.1 | Postgres indices to keep read path cheap | — | — | ✅ |

## Non-Functional Requirements — Compliance / Ethics (NFR-339 … NFR-344)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-339 | C | — | — | — | §12 | §6 | README disclaimer | — | — | 🟡 (needs explicit "not financial advice" string; deferred) |
| NFR-340 | S | — | — | — | §12 | §6 | `AlphaBrief.caveats` surfaced in Telegram + UI | — | — | ✅ |
| NFR-341 | S | — | — | — | §12 | §6 | `requires_human_review` gating narrator output | — | — | ✅ |
| NFR-342 | C | — | — | — | §12 | §6 | Playwright scraping throttle via sleep | — | — | 🟡 |
| NFR-343 | C | — | — | — | §12 | §6 | read-only API (no write endpoints) | — | — | ✅ |
| NFR-344 | C | — | — | — | §12 | §6 | MIT license | — | — | ✅ |

## Non-Functional Requirements — Deployability (NFR-359 … NFR-362)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-359 | C | — | — | — | §11 | §6 | `docker-compose.yml`, Dockerfiles | — | `scripts/deploy.sh` | ✅ |
| NFR-360 | M | SC-18 | — | UF-09 | §11 | §6 | GitHub Actions workflows | — | — | ✅ |
| NFR-361 | S | — | — | — | §11 | §6 | `scripts/deploy.sh` tag-triggered deploy.yml stub | — | `scripts/deploy.sh` | 🟡 (workflow file not split into deploy.yml yet) |
| NFR-362 | S | — | — | UF-09 | §11 | §6 | `scripts/smoke_test.sh` | — | `scripts/smoke_test.sh` | ✅ |

## Non-Functional Requirements — Testing gates (NFR-379 … NFR-383)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-379 | C | — | — | — | §13 | §6 | pytest config in `pyproject.toml` | entire `tests/` tree | — | 🟡 (not executed) |
| NFR-380 | M | — | — | — | §13 | §6 | `--cov-fail-under=100` | — | CI `ci.yml::python` step | 🟡 (gate exists; not verified green) |
| NFR-381 | M | — | — | — | §13 | §6 | Vitest `thresholds.*: 100` | — | CI `ci.yml::typescript` step | 🟡 |
| NFR-382 | M | — | — | — | §13 | §6 | `grep-forbidden-phrases` CI job + pre-commit hook | — | CI + `.pre-commit-config.yaml` | ✅ |
| NFR-383 | M | — | — | — | §13 | §6 | `forge coverage` 100% gate | — | `.github/workflows/contract.yml` | 🟡 (gate written; not executed) |

## Non-Functional Requirements — Misc (NFR-399, NFR-401)

| Req ID | MoSCoW | Scenario | Use Case | User Flow | HLD § | LLD § | Code | Test | Script | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| NFR-399 | C | — | — | — | §12 | §6 | `Envelope.extra='forbid'` | `test_envelope_*` | — | ✅ |
| NFR-401 | C | — | — | — | §12 | §6 | schema drift gate | — | `scripts/export_schemas.py` + CI | ✅ |

## Won't-haves (W-01 … W-11)

All W-## items are deferred by definition. They are listed here so the matrix is complete but marked ⏳ across the board. Representative entries:

| Req ID | Intent | Status |
|---|---|---|
| W-01 | Paid-tier scrapers (e.g. ApiDash) | ⏳ v2 |
| W-02 | Multi-chain (Solana, Ethereum) | ⏳ v2 |
| W-03 | Mobile native app | ⏳ v2 |
| W-04 | Trading execution | ⏳ explicitly out of scope — risk/liability |
| W-05 | Private beta subscription billing | ⏳ v2 |
| W-06 | Multi-region HA deploy | ⏳ v2 |
| W-07 | DAO-governed agent weights | ⏳ v2 |
| W-08 | Custom user-defined rules | ⏳ v2 |
| W-09 | Signed webhooks | ⏳ v2 |
| W-10 | Paid API tier | ⏳ v2 |
| W-11 | Embedded video briefings | ⏳ v2 |

## Assumptions (A-01 … A-06, A-256)

| ID | Assumption | Treatment in repo | Status |
|---|---|---|---|
| A-01 | Four.meme has *some* new-token feed | dual source adapter in `agents/hunter/sources/` + `FOURMEME_SOURCE` env var | ✅ adapter in place; real topic hash must be pasted by Desktop |
| A-02 | X.com allows unauthenticated search | `x_scraper.py` with graceful degraded path | 🟡 |
| A-03 | Telegram `t.me/s/` previews remain public | `telegram_scraper.py` | 🟡 |
| A-04 | BscScan free-tier RPS suffices | `BscScanClient._rate` semaphore | 🟡 documented |
| A-05 | Redis Streams PEL survives restart | AOF enabled in compose | ✅ |
| A-06 | BNB Testnet is reachable | `BNB_TESTNET_RPC_URL` configurable | ✅ |
| A-256 | DGrid OpenAI-compatible API surface stable | `DGridProvider` mirrors OpenAI path | ✅ |

## Constraints (C-01 … C-07)

| ID | Constraint | Treatment | Status |
|---|---|---|---|
| C-01 | Hackathon deadline 2026-04-22 16:59 UTC | NEXT_PROMPT_FOR_DESKTOP.md + deploy pipeline | ✅ |
| C-02 | Solo build (Senthil) | no multi-author conventions in code | ✅ |
| C-03 | BNB Testnet only | `FindingsRegistry` deployed to 97 | ✅ |
| C-04 | Free-tier external services | Playwright scraping, free BscScan, testnet faucet | ✅ |
| C-05 | Single VPS | docker-compose all-in-one; documented SPOF | ✅ |
| C-06 | Python 3.12 / Node 20 / Solidity 0.8.24 | pinned in `pyproject.toml`, `package.json`, `foundry.toml` | ✅ |
| C-07 | 100% test coverage required | `--cov-fail-under=100`, Vitest thresholds 100, `forge coverage` gate | 🟡 (gates in place; not executed green yet) |

---

## Automation scripts — reverse index

| Script | Purpose | Requirements traced to | How to invoke |
|---|---|---|---|
| `scripts/export_schemas.py` | Export Pydantic → JSON Schema for drift gate | FR-100, NFR-262, NFR-401 | `python scripts/export_schemas.py` |
| `scripts/generate_zod.ts` | JSON Schema → zod check artefacts | NFR-262 (cross-language drift) | `node scripts/generate_zod.ts` |
| `scripts/deploy.sh` | Sync repo to VPS + compose up + smoke | NFR-359, NFR-361 | `DEPLOY_HOST=... DEPLOY_USER=... bash scripts/deploy.sh` |
| `scripts/smoke_test.sh` | Post-deploy /health /briefs /metrics / dashboard checks | NFR-362, FR-200, FR-204 | `bash scripts/smoke_test.sh` |
| `scripts/seed_testnet_wallet.sh` | Top up agent wallet from BNB Testnet faucet | FR-119, FR-120 | `AGENT_WALLET_ADDRESS=0x... bash scripts/seed_testnet_wallet.sh` |
| `scripts/record_demo_video.sh` | Playwright-driven demo capture | Phase-12 submission | `bash scripts/record_demo_video.sh` |
| `contracts/script/Deploy.s.sol` | Deploy FindingsRegistry | FR-119, FR-120 | `forge script contracts/script/Deploy.s.sol --rpc-url bsc_testnet --broadcast` |
| `.github/workflows/ci.yml` | Python lint + mypy + pytest + drift gate | NFR-380, NFR-382, NFR-401 | GitHub Actions on push/PR |
| `.github/workflows/contract.yml` | Foundry build + test + coverage gate | NFR-383 | GitHub Actions on contract changes |
| `.github/workflows/e2e.yml` | Playwright end-to-end | FR-181, FR-187, Phase-12 | GitHub Actions on push/dispatch |
| `.pre-commit-config.yaml` | detect-secrets + ruff + no-demo-phrase hook | NFR-299, NFR-300, NFR-382 | `pre-commit install` → runs on every `git commit` |

---

## Frontend-specific trace

| Surface | Requirement(s) | Code | Test |
|---|---|---|---|
| Live feed (SSR) | FR-181, FR-182 | `web/app/page.tsx` | `dashboard.spec.ts::loads the feed` |
| Brief card | FR-180, FR-189 | `web/components/BriefCard.tsx` | `BriefCard.test.tsx` (10 tests) |
| Swarm health | FR-183, FR-008 | `web/components/SwarmHealthPanel.tsx` | `panels.test.tsx::SwarmHealthPanel` |
| Model usage | FR-184, FR-239 | `web/components/ModelUsagePanel.tsx` | `panels.test.tsx::ModelUsagePanel` |
| Activity timeline | FR-185 | `web/components/ActivityTimelinePanel.tsx` | `panels.test.tsx::ActivityTimelinePanel` |
| Live updates via WS | FR-186, FR-188 | `web/lib/hooks/useBriefStream.ts`, `web/components/FeedStream.tsx` | `useBriefStream.test.tsx` (5 tests) |
| Mobile responsive | FR-187 | Tailwind `lg:grid-cols-[1fr_320px]` in `page.tsx` | `dashboard.spec.ts::mobile viewport` |
| Verify click-through | FR-201 | `BriefCard.tsx` verify button → `/briefs/{id}/verify` | `BriefCard.test.tsx::provides BscScan and Verify links` |

## Backend-specific trace (agent fan-in / fan-out)

```
Four.meme ──> Hunter ──┬──> stream:candidates ──> Social ──> stream:social ──┐
                       │                                                     │
                       │                      ┌──> Chain ──> stream:chain ───┤
                       │                      │                              │
                       └── anchor_and_publish()                              │
                                                                             ▼
                                                                          Risk
                                                                             │
                                                            stream:risk ◄────┘
                                                                             │
                                                                             ▼
                                                                         Narrator
                                                                             │
                                                                             ├──> stream:briefs ──> API /briefs, /ws/events, Bot delivery
                                                                             └──> stream:human_review
```

Each arrow is one Envelope with one on-chain record. Trace:
- Hunter emits → `agents/hunter/main.py::HunterAgent._main_loop` → `base_agent.anchor_and_publish`
- Social consumes `stream:candidates`, group `social:primary` → `agents/social/main.py::_main_loop`
- Chain consumes `stream:candidates`, group `chain:primary` → `agents/chain/main.py::_main_loop`
- Risk joins `stream:social` + `stream:chain` in `agents/risk/main.py::_on_message` with 120s timeout
- Narrator consumes `stream:risk` → `agents/narrator/main.py::_process` → either `stream:briefs` or `stream:human_review`
- API tails `/briefs` from Postgres and `/ws/events` from Redis Pub/Sub (`pubsub:briefs`)
- Bot consumes `stream:briefs` directly with group `bot:delivery`

---

## Summary counts

| Requirement class | Count | ✅ | 🟡 | ⏳ |
|---|---|---|---|---|
| FR (Hunter) | 10 | 4 | 6 | 0 |
| FR (Social) | 11 | 1 | 10 | 0 |
| FR (Chain) | 9 | 3 | 6 | 0 |
| FR (Risk) | 9 | 5 | 4 | 0 |
| FR (Narrator) | 9 | 4 | 5 | 0 |
| FR (Bus + envelope) | 8 | 6 | 2 | 0 |
| FR (On-chain) | 9 | 8 | 1 | 0 |
| FR (LLM router) | 7 | 6 | 1 | 0 |
| FR (Bot) | 8 | 2 | 6 | 0 |
| FR (Dashboard) | 11 | 10 | 1 | 0 |
| FR (API) | 6 | 5 | 1 | 0 |
| FR (Observability) | 6 | 2 | 4 | 0 |
| NFR (Perf) | 3 | 0 | 0 | 3 |
| NFR (Reliability) | 5 | 2 | 3 | 0 |
| NFR (Scalability) | 6 | 2 | 2 | 2 |
| NFR (Data Integrity) | 4 | 4 | 0 | 0 |
| NFR (Observability) | 5 | 3 | 2 | 0 |
| NFR (Security) | 4 | 3 | 1 | 0 |
| NFR (Cost control) | 9 | 6 | 3 | 0 |
| NFR (Compliance) | 6 | 3 | 3 | 0 |
| NFR (Deployability) | 4 | 3 | 1 | 0 |
| NFR (Testing gates) | 5 | 1 | 4 | 0 |
| NFR (Misc) | 2 | 2 | 0 | 0 |
| Won't-haves | 11 | 0 | 0 | 11 |
| Assumptions | 7 | 4 | 3 | 0 |
| Constraints | 7 | 6 | 1 | 0 |
| **Total** | **181** | **95** | **70** | **16** |

**52% fully ✅, 39% partial 🟡, 9% deferred ⏳.** Desktop's job is to push the 🟡 rows into ✅ and leave the ⏳ rows as documented.

---

**End of TRACEABILITY.md**
