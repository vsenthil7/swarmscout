# 09 — Test Cases

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 07:55 UTC

Every test case for SwarmScout, with ID, preconditions, steps, expected result, and trace to FR/NFR/failure mode. Organised by layer, per the identification scheme in 08_TestPlan.md §7.

This document is **not exhaustive per-assertion** — it specifies the **test contract**: what cases must exist, what each must prove. Implementation detail (specific assertion count, exact fixtures) lives in the test code.

---

## Format

```
TC-XNN — Short title
  Trace:       FR / NFR / UC / UF / failure mode
  Layer:       Unit | Integration | Contract | E2E | Failure | Security | Performance
  Preconditions: ...
  Steps:       1. … 2. …
  Expected:    ...
```

---

## 1. Unit test cases (Python)

### 1.1 `BaseAgent`

**TC-U01 — BaseAgent happy path**
- Trace: FR-002, FR-101
- Layer: Unit
- Preconditions: mocked bus, llm, on_chain, db, hasher, health; sample `Envelope` fixture
- Steps: invoke `_handle_message` with a valid message
- Expected: `process` called once; hasher called with returned payload; on_chain.record called; bus.publish called with envelope; bus.ack called last

**TC-U02 — BaseAgent: process raises**
- Trace: §6 error handling (category 3)
- Layer: Unit
- Steps: inject a `process` that raises RuntimeError
- Expected: message NOT acked on input group; error logged; agent loop continues with next message

**TC-U03 — BaseAgent: on-chain write returns pending**
- Trace: FR-005, FR-026, FR-045, FR-065, FR-084
- Layer: Unit
- Steps: on_chain.record returns `OnChainStatus.PENDING`
- Expected: envelope published with `on_chain_status: "pending"`; ack succeeds normally (downstream delivery not blocked)

**TC-U04 — BaseAgent: graceful shutdown mid-process**
- Trace: §7.2 graceful shutdown
- Layer: Unit
- Steps: send SIGTERM while `process` is running
- Expected: in-flight message completes (including on-chain write and ack); no new messages read; loop exits cleanly

### 1.2 `MessageBus`

**TC-U10 — publish + consume round-trip**
- Trace: FR-100, FR-104
- Layer: Unit (fakeredis)
- Steps: publish envelope; consume from group
- Expected: consumed message deserialises to identical envelope

**TC-U11 — consumer group PEL reclaim**
- Trace: FR-105
- Layer: Unit
- Steps: publish; consume but do not ack; wait past visibility timeout; call claim_stale
- Expected: message returned; original consumer can no longer ack it

**TC-U12 — MAXLEN enforcement**
- Trace: FR-102
- Layer: Unit
- Steps: publish 100_005 messages
- Expected: stream length ≤ 100_010 (MAXLEN ~ allows small overshoot)

**TC-U13 — XPENDING exposed via pending()**
- Trace: FR-106
- Layer: Unit
- Steps: publish 3 messages; consume 3; ack 1; call pending()
- Expected: returns 2

### 1.3 `LLMRouter`

**TC-U20 — primary succeeds via DGrid**
- Trace: FR-140
- Layer: Unit (respx)
- Steps: mock DGrid 200 OK; call complete()
- Expected: response from DGrid; model_used = primary; no fallback called

**TC-U21 — primary fails, FB1 succeeds**
- Trace: FR-141, FR-024 (and 006, 043, 063, 083)
- Layer: Unit
- Steps: DGrid 503; direct FB1 200
- Expected: response from FB1; model_used = FB1 model name; circuit for primary opens

**TC-U22 — primary + FB1 fail, FB2 succeeds**
- Trace: FR-141
- Layer: Unit
- Steps: DGrid 503; FB1 503; FB2 200
- Expected: response from FB2; both circuits open

**TC-U23 — all three fail → raises LLMProvidersExhausted**
- Trace: FR-064, FR-086
- Layer: Unit
- Steps: all three 503
- Expected: raises `LLMProvidersExhausted`; every attempt logged to llm_calls table

**TC-U24 — circuit open skips primary on next call**
- Trace: FR-141
- Layer: Unit
- Steps: cause 3 consecutive failures on primary (opens circuit); call complete() again
- Expected: primary skipped; FB1 attempted first

**TC-U25 — circuit closes after probe succeeds**
- Trace: FR-141
- Layer: Unit
- Steps: open circuit; advance time past 60s; inject 200 on primary; call complete()
- Expected: circuit closes; primary used

**TC-U26 — rate-limit token acquire/release**
- Trace: FR-142
- Layer: Unit
- Steps: set rate limit to 1/min; call complete() twice within 1 min
- Expected: second call blocks OR falls back (depending on `wait` config)

**TC-U27 — every call logged**
- Trace: FR-143
- Layer: Unit
- Steps: call complete() with known prompt
- Expected: llm_calls row exists with provider, model, agent, prompt_hash, response_hash, input_tokens, output_tokens, cost_usd, latency_ms, success=true

**TC-U28 — daily cost cap triggers cheaper tier**
- Trace: NFR-302
- Layer: Unit
- Steps: seed llm_calls with cost summing > cap for provider; call complete()
- Expected: router skips that provider, moves to next in chain

### 1.4 `OnChainWriter`

**TC-U30 — record succeeds**
- Trace: FR-120, FR-121
- Layer: Unit (mocked web3)
- Steps: mock successful tx receipt
- Expected: returns CONFIRMED; no queue entry

**TC-U31 — RPC timeout → queued**
- Trace: TC-F08, NFR-222
- Layer: Unit
- Steps: mock web3 timeout
- Expected: returns PENDING; row written to on_chain_queue

**TC-U32 — drain_queue retries and succeeds**
- Trace: TC-F08
- Layer: Unit
- Steps: seed queue with 1 entry; mock successful tx; run drain_queue
- Expected: queue empty; entry's tx hash stored in messages table

**TC-U33 — drain_queue still failing → retry count incremented**
- Trace: TC-F08
- Layer: Unit
- Steps: seed queue; mock continued failure; run drain_queue
- Expected: entry's attempts = 2; last_error populated; entry remains

**TC-U34 — insufficient gas → queued with typed error**
- Trace: TC-F09
- Layer: Unit
- Steps: mock InsufficientFundsError
- Expected: PENDING; last_error = "insufficient_funds"; heartbeat emits warning

### 1.5 `PayloadHasher`

**TC-U40 — same input → same hash**
- Trace: NFR-261
- Layer: Unit
- Steps: hash identical payload twice
- Expected: identical 32-byte digest

**TC-U41 — key order invariance (canonicalisation)**
- Trace: NFR-261
- Layer: Unit
- Steps: hash same payload with different dict key orderings
- Expected: identical digest

**TC-U42 — unicode handling**
- Trace: NFR-261
- Layer: Unit
- Steps: hash payload containing non-ASCII strings (e.g., "émoji 🚀")
- Expected: hash computed without error; deterministic

**TC-U43 — field change → different hash**
- Trace: NFR-261
- Layer: Unit
- Steps: hash, then flip one field, hash again
- Expected: digests differ

### 1.6 `Hunter`

**TC-U50 — Hunter emits TokenCandidate on new event**
- Trace: FR-001, FR-002, FR-003
- Layer: Unit
- Steps: feed a mock `RawTokenEvent`
- Expected: bus.publish called with correctly-shaped envelope; payload fields match FR-003

**TC-U51 — Hunter dedupes same address within 24h**
- Trace: FR-004, TC-F16
- Layer: Unit
- Steps: feed same address twice
- Expected: second call does not publish; logs "duplicate"

**TC-U52 — Hunter retries transient 5xx with backoff**
- Trace: FR-007
- Layer: Unit
- Steps: mock source to 5xx × 3, then 200
- Expected: call succeeds after backoff; retry delays match 1, 2, 4

**TC-U53 — Hunter caches Four.meme responses 60s**
- Trace: FR-010
- Layer: Unit
- Steps: two back-to-back calls within 60s
- Expected: source client called once; second read comes from Redis

### 1.7 `Social`

**TC-U60 — Social produces SocialScore for candidate**
- Trace: FR-020, FR-021, FR-023
- Layer: Unit
- Steps: feed TokenCandidate; mock scrapers return known mentions
- Expected: SocialScore envelope published; fields match FR-023

**TC-U61 — Social handles scraping blocked → degraded**
- Trace: FR-027, UC-15, TC-F14
- Layer: Unit
- Steps: scraper raises ScrapingBlockedError
- Expected: SocialScore emitted with data_quality="degraded", all scores null, red_flags=["social_data_unavailable"]

**TC-U62 — Social detects coordinated posting**
- Trace: FR-025
- Layer: Unit
- Steps: mock scraper returns 15 posts with >95% identical copy
- Expected: `coordinated_posting` in red_flags

**TC-U63 — Social respects rate limits**
- Trace: FR-029
- Layer: Unit
- Steps: configure limit 1 req/10s; trigger 2 scrapes
- Expected: second scrape delayed appropriately

### 1.8 `Chain`

**TC-U70 — Chain produces ChainMetrics**
- Trace: FR-040, FR-041, FR-042
- Layer: Unit
- Steps: feed TokenCandidate; mock BscScan + RPC responses
- Expected: ChainMetrics envelope published; fields match FR-042

**TC-U71 — Chain detects honeypot**
- Trace: FR-046, TC-F17
- Layer: Unit
- Steps: mock eth_call to revert on sell simulation
- Expected: `honeypot_check_passed: false`

**TC-U72 — Chain caches BscScan responses 30s**
- Trace: FR-044
- Layer: Unit
- Steps: two back-to-back calls within 30s
- Expected: BscScan called once

### 1.9 `Risk`

**TC-U80 — Risk joins Social + Chain by upstream_ids**
- Trace: FR-060
- Layer: Unit
- Steps: publish SocialScore + ChainMetrics with identical upstream
- Expected: Risk consumes both, produces single RiskVerdict

**TC-U81 — Risk times out at 120s if one input missing**
- Trace: FR-061
- Layer: Unit
- Steps: publish only SocialScore; advance time 121s
- Expected: RiskVerdict emitted with missing_inputs=["chain"]

**TC-U82 — Risk all-LLM-fail → requires_human_review**
- Trace: FR-064
- Layer: Unit
- Steps: LLMRouter raises LLMProvidersExhausted
- Expected: RiskVerdict with score_0_100=None, confidence=None, requires_human_review=true

**TC-U83 — 15 heuristics each triggers correctly**
- Trace: FR-066
- Layer: Unit
- Steps: per heuristic, construct minimal failing input
- Expected: 15 separate test functions, one per rule; each asserts rule fires; each asserts rule-name in heuristics_triggered

**TC-U84 — Heuristic does not fire on clean input**
- Trace: FR-066
- Layer: Unit
- Steps: construct input where no rule should fire
- Expected: heuristics_triggered = []

### 1.10 `Narrator`

**TC-U90 — Narrator composes AlphaBrief from RiskVerdict**
- Trace: FR-080, FR-082
- Layer: Unit
- Steps: publish RiskVerdict + prior messages in PG; mock LLM response
- Expected: AlphaBrief envelope with fields per FR-082

**TC-U91 — Narrator degraded upstream → degraded brief**
- Trace: FR-085
- Layer: Unit
- Steps: RiskVerdict with upstream SocialScore.data_quality=degraded
- Expected: AlphaBrief.confidence_tier = "degraded"

**TC-U92 — Narrator requires_human_review → HumanReviewRequest**
- Trace: FR-086
- Layer: Unit
- Steps: RiskVerdict.requires_human_review = true
- Expected: publishes HumanReviewRequest on stream:human_review, NOT AlphaBrief on stream:briefs

---

## 2. Integration test cases (Python)

**TC-I01 — Full pipeline, happy path (mocked LLMs, real Redis+PG)**
- Trace: NFR-200, NFR-260
- Layer: Integration
- Steps: spin up Redis+PG via testcontainers; feed Hunter a TokenCandidate; run all 5 agents; wait for AlphaBrief on stream:briefs
- Expected: AlphaBrief present within 5 min; every intermediate message present in PG; upstream_ids chain intact

**TC-I02 — Full lineage reconstruction**
- Trace: NFR-260
- Layer: Integration
- Steps: after TC-I01, walk upstream_ids from AlphaBrief back
- Expected: 5-hop chain: AlphaBrief → RiskVerdict → ChainMetrics/SocialScore → TokenCandidate

**TC-I03 — Hash integrity across pipeline**
- Trace: NFR-261, NFR-262
- Layer: Integration
- Steps: for every message in the pipeline, re-hash payload; compare to payload_hash and on-chain (Anvil)
- Expected: all hashes match

**TC-I04 — Agent crash mid-processing → message redelivered**
- Trace: FR-105, NFR-222, TC-F06 (partial)
- Layer: Integration
- Steps: force Risk to crash before ack; wait visibility timeout; restart Risk
- Expected: message re-consumed and processed; exactly one AlphaBrief emitted

**TC-I05 — API returns briefs from PG**
- Trace: FR-200, FR-201
- Layer: Integration
- Steps: seed PG with 3 briefs; GET /briefs
- Expected: 200 OK; list length 3; fields match schema

**TC-I06 — API rate limit 429**
- Trace: FR-203, TC-S02
- Layer: Integration
- Steps: hammer endpoint 61× in 60s
- Expected: 61st returns 429 with Retry-After header

**TC-I07 — Bot delivers brief above threshold**
- Trace: UC-02, FR-162, FR-164
- Layer: Integration
- Steps: seed subscription (chat_id=X, threshold=moderate); publish AlphaBrief with conviction_tier=high
- Expected: Telegram API called exactly once for chat_id=X; dedup SET populated

**TC-I08 — Bot skips brief below threshold**
- Trace: UC-02 A1, UC-12
- Layer: Integration
- Steps: seed subscription (chat_id=X, threshold=high); publish AlphaBrief with conviction_tier=degen
- Expected: Telegram API not called for chat_id=X

**TC-I09 — Bot dedup prevents double-send**
- Trace: FR-165, UC-02 A2
- Layer: Integration
- Steps: publish AlphaBrief; bot sends; bot re-reads (simulated crash before ack); bot consumes again
- Expected: Telegram API called exactly once

**TC-I10 — WebSocket fanout on Redis Pub/Sub**
- Trace: FR-183, UC-06
- Layer: Integration
- Steps: open WebSocket client to /ws/events; publish event on Redis channel
- Expected: client receives event within 1s

**TC-I11 — Schema drift gate catches change**
- Trace: FR-223, TC-F12
- Layer: Integration
- Steps: modify a Pydantic model; run export_schemas.py; run git diff
- Expected: non-zero exit; diff highlights changed schema

**TC-I12 — On-chain queue drains on RPC recovery**
- Trace: TC-F08
- Layer: Integration (Anvil)
- Steps: make Anvil unreachable; trigger agent to emit; verify queue row; restore Anvil; wait drain
- Expected: queue empties; on_chain_tx_hash populated in messages table

---

## 3. Contract test cases (Foundry, Solidity)

**TC-C01 — Owner is deployer**
- Steps: deploy with msg.sender = X
- Expected: `owner() == X`

**TC-C02 — Initial allowlist honoured**
- Steps: deploy with initialAgents = [A, B]
- Expected: allowlist[A] = true, allowlist[B] = true, allowlist[other] = false

**TC-C03 — Non-allowlisted recordFinding reverts**
- Trace: FR-123, TC-S03
- Steps: call recordFinding from non-allowlisted address
- Expected: reverts with NotAllowlisted

**TC-C04 — Allowlisted recordFinding succeeds**
- Trace: FR-121
- Steps: call from allowlisted; query verifyFinding
- Expected: stored values match

**TC-C05 — Duplicate msgId reverts**
- Steps: recordFinding twice with same msgId
- Expected: second reverts with AlreadyRecorded

**TC-C06 — Empty agent string reverts**
- Steps: recordFinding with agent=""
- Expected: reverts with EmptyAgent

**TC-C07 — FindingRecorded event emitted**
- Trace: FR-122
- Steps: recordFinding; inspect logs
- Expected: exactly one FindingRecorded with matching args

**TC-C08 — Non-owner setAllowlist reverts**
- Steps: setAllowlist from non-owner
- Expected: reverts with NotOwner

**TC-C09 — Owner can add and remove from allowlist**
- Steps: setAllowlist(X, true); setAllowlist(X, false)
- Expected: allowlist[X] reflects each state; AllowlistUpdated emitted twice

**TC-C10 — verifyFinding for unknown returns zero struct**
- Steps: verifyFinding(0x...ff) on a non-recorded msgId
- Expected: all-zeros return

### 3.1 Fuzz tests

**TC-C20 — Fuzz recordFinding over random (msgId, hash, agent)**
- Steps: 1000 random inputs from allowlisted caller
- Expected: every success leads to verifyFinding returning identical values

**TC-C21 — Fuzz: duplicate msgId always reverts**
- Steps: 1000 random msgIds recorded twice
- Expected: second call always reverts

### 3.2 Invariant tests

**TC-C30 — Finding immutability**
- Trace: FR-127
- Steps: write N findings over 1000 random transactions; query each
- Expected: all finding tuples unchanged from their write

**TC-C31 — Allowlist cannot be modified by non-owner**
- Steps: random actors attempt setAllowlist
- Expected: allowlist never changes outside owner actions

---

## 4. TypeScript unit + component test cases

**TC-U100 — BriefCard renders all fields**
- Layer: Vitest + Testing Library
- Steps: render BriefCard with fixture; query for token name, conviction tier, thesis, caveats, verify link
- Expected: all visible

**TC-U101 — BriefCard shows degraded banner**
- Trace: S-10
- Steps: render with confidence_tier=degraded
- Expected: "Partial data" banner visible

**TC-U102 — Conviction tier maps to correct border colour**
- Steps: render each of 4 tiers
- Expected: class names reflect green/yellow/orange/red

**TC-U103 — ModelAttribution lists all models**
- Steps: render with 5 models
- Expected: all 5 visible, separated as per spec

**TC-U104 — SwarmHealthPanel colours match status**
- Steps: render with mix of ok/degraded/down
- Expected: dots coloured green/yellow/red accordingly

**TC-U105 — ModelUsagePanel renders chart**
- Steps: render with sample data
- Expected: recharts element present; data points match input

**TC-U106 — useEventStream connects, handles message**
- Steps: mock WebSocket; simulate onmessage
- Expected: events state updates with parsed event

**TC-U107 — useEventStream reconnects on close**
- Trace: TC-F11
- Steps: mock WebSocket; simulate close
- Expected: reconnect attempted; status transitions connecting → reconnecting

**TC-U108 — useEventStream falls back to polling after 5 reconnect failures**
- Trace: TC-F11
- Steps: simulate 5 consecutive close events
- Expected: status = polling; fetch() called on interval

**TC-U109 — zod schema rejects malformed payload**
- Trace: TC-S06
- Steps: parse known-bad AlphaBrief
- Expected: SafeParseError with specific issue path

---

## 5. E2E test cases (Playwright)

**TC-E01 — First-time Telegram subscription**
- Trace: UF-01, UC-01
- Layer: E2E
- Environment: local `docker compose -f docker-compose.test.yml up` with mock Telegram endpoint
- Steps: simulate `/start`; simulate `/subscribe`; query subscriptions table
- Expected: row exists with threshold=moderate

**TC-E02 — Receiving an alert (happy path)**
- Trace: UF-02, UC-02
- Steps: seed AlphaBrief on stream:briefs; wait for mock Telegram endpoint to receive call
- Expected: exactly one message sent; content matches FR-164 format

**TC-E02a — Receiving a degraded alert**
- Trace: S-10, FR-085
- Steps: seed AlphaBrief with confidence_tier=degraded
- Expected: message contains "⚠ Partial data" caveat line

**TC-E03 — /verify returns on-chain link**
- Trace: UF-02, UC-05, FR-163
- Steps: send `/verify <msg_id>` for a known msg_id in test registry (Anvil)
- Expected: reply contains BscScan-shaped URL, lineage, hash

**TC-E04 — Audit flow: historical brief still verifies**
- Trace: UF-03, S-03
- Steps: verify msg_id from yesterday's fixture
- Expected: returns intact lineage; all hashes re-verify against Anvil registry

**TC-E05 — API list + detail + verify sequence**
- Trace: UF-04, UC-03/04/05
- Steps: GET /briefs → pick first msg_id → GET /briefs/{id} → GET /briefs/{id}/verify
- Expected: all 200; shapes match OpenAPI schema; verify returns matches=true

**TC-E06 — Dashboard desktop view renders**
- Trace: UF-05, UC-06
- Steps: navigate to dashboard; wait for hydration
- Expected: SwarmHealthPanel, ModelUsagePanel, ActivityTimelinePanel, BriefFeed all visible; brief card count matches seeded fixture

**TC-E06m — Dashboard mobile view renders**
- Trace: UF-05, FR-187
- Steps: set viewport 375×812; load dashboard
- Expected: panels stack vertically; timeline collapsible; all interactive elements tappable

**TC-E07 — WebSocket reconnect under simulated network drop**
- Trace: UF-05, TC-F11
- Steps: load dashboard; block WebSocket via route interception; restore after 30s
- Expected: "Live updates paused" banner shown during block; reconnects after; events resume

**TC-E08 — BscScan-style direct contract read**
- Trace: UF-06, UC-09
- Steps: call verifyFinding(msg_id) against Anvil registry without going through any SwarmScout code
- Expected: returns stored tuple; payloadHash re-computable from API response

**TC-E09 — Swarm health drawer shows fallback model**
- Trace: UF-07, UC-10 A1
- Steps: simulate Risk agent on fallback; click Risk dot
- Expected: drawer shows current_model = fallback model; reason text visible

**TC-E10 — Unsubscribe persists**
- Trace: UF-08, UC-11
- Steps: `/unsubscribe`; publish AlphaBrief; assert no Telegram send for chat_id
- Expected: subscription soft-deleted; no message delivery

---

## 6. Failure-mode test cases

**TC-F01 — Four.meme unreachable**
- Trace: 02 §6 row 1
- Layer: Failure + Unit
- Steps: mock source to 5xx continuously for 60s; then 200
- Expected: Hunter retries with backoff; logs error; resumes on recovery; no crash

**TC-F02 — OpenAI down, fallback to Anthropic**
- Trace: FR-141, 02 §6 row 2
- Layer: Failure + Unit
- Steps: for Social agent, mock DGrid/OpenAI to 503; FB1 Anthropic to 200
- Expected: SocialScore published; model_used shows Anthropic

**TC-F03 — Anthropic down, fallback to next**
- Trace: FR-141
- Steps: for Chain agent, mock primary Anthropic to 503; FB1 OpenAI to 200
- Expected: ChainMetrics published; model_used shows OpenAI

**TC-F04 — Gemini down, fallback to next**
- Trace: FR-141
- Steps: for Hunter, mock Gemini to 503; FB1 Anthropic Haiku to 200
- Expected: TokenCandidate published; model_used shows Haiku

**TC-F05 — All three LLM providers down for Risk**
- Trace: FR-064, 02 §6 row 5
- Steps: all providers 503 for Risk
- Expected: RiskVerdict with requires_human_review=true, score_0_100=null; downstream Narrator emits HumanReviewRequest

**TC-F06 — Redis restart mid-pipeline**
- Trace: NFR-222, 02 §6 row 6
- Steps: start pipeline; kill Redis; restart with AOF; verify pending message replay
- Expected: all in-flight messages redelivered; no duplicates in downstream output

**TC-F07 — Postgres unavailable during publish**
- Trace: 02 §6 row 7
- Steps: stop PG; publish message; verify retry behaviour; restart PG
- Expected: agent retries PG write; once PG returns, write succeeds; no message loss on bus side

**TC-F08 — BNB RPC unreachable, queue drains on recovery**
- Trace: TC-F08, already enumerated
- Steps: make Anvil unreachable; publish finding; restart Anvil
- Expected: message goes out with on_chain_status=pending; drain background task succeeds; tx hash populated

**TC-F09 — Wallet out of gas**
- Steps: deplete test wallet; attempt recordFinding
- Expected: queued with last_error="insufficient_funds"; heartbeat warning; agent continues

**TC-F10 — Consumer group stuck message → dead letter**
- Steps: inject a poison message that causes consumer to fail repeatedly
- Expected: after N retries (configured), message moves to stream:dead_letter; original XACK'd; loop continues

**TC-F11 — Dashboard WebSocket disconnect**
- Already: TC-U107, TC-U108, TC-E07

**TC-F12 — Schema drift CI gate**
- Already: TC-I11

**TC-F13 — Telegram rate-limited (429)**
- Steps: mock Telegram endpoint to 429 with retry_after=5
- Expected: bot backs off; does not XACK; message redelivered; eventually sent once

**TC-F14 — Scraping blocked**
- Already: TC-U61

**TC-F15 — DGrid gateway down**
- Steps: mock DGrid to 503 while direct providers 200
- Expected: router routes via direct Anthropic/OpenAI/Google APIs

**TC-F16 — Duplicate new-token event**
- Already: TC-U51

**TC-F17 — Honeypot caught by simulation**
- Already: TC-U71

---

## 7. Security test cases

**TC-S01 — No secrets in git history**
- Steps: run `detect-secrets scan --baseline .secrets.baseline`
- Expected: no new secrets detected

**TC-S02 — API rate limit enforced**
- Already: TC-I06

**TC-S03 — Contract write rejects non-allowlisted**
- Already: TC-C03

**TC-S04 — HTTPS redirect in production**
- Steps: curl -I http://dashboard.swarmscout.xyz
- Expected: 301 to https

**TC-S05 — No secret fields in API responses**
- Steps: GET /briefs/{id}; assert JSON contains no keys matching `*_key|*_secret|*_token|private_*`
- Expected: clean

**TC-S06 — Pydantic rejects malformed input**
- Steps: POST-shaped fuzz inputs to every endpoint (even GET validates query params)
- Expected: 422 with clear error detail; no 500

---

## 8. Performance test cases

**TC-P01 — E2E ≤ 5 min P95 at 10 candidates/min**
- Trace: NFR-200
- Steps: locust feeds 10 candidates/min for 10 min; OpenTelemetry traces P95 E2E latency
- Expected: P95 ≤ 300s

**TC-P02 — 30 candidates/min burst, 0 message loss**
- Trace: NFR-202
- Steps: locust feeds 30/min for 3 min
- Expected: every candidate results in exactly one AlphaBrief or HumanReviewRequest; no drops

**TC-P03 — Per-agent P95 latencies**
- Trace: NFR-201
- Steps: collect agent-level timings during TC-P02
- Expected: Hunter ≤ 30s, Social ≤ 60s, Chain ≤ 30s, Risk ≤ 90s, Narrator ≤ 45s

---

## 9. Coverage matrix (summary)

| FR range | Covered by (test ID prefix) |
|---|---|
| FR-001 – FR-019 (Hunter) | TC-U50-53, TC-I01 |
| FR-020 – FR-039 (Social) | TC-U60-63, TC-I01 |
| FR-040 – FR-059 (Chain) | TC-U70-72, TC-I01 |
| FR-060 – FR-079 (Risk) | TC-U80-84, TC-I01, TC-F05 |
| FR-080 – FR-099 (Narrator) | TC-U90-92, TC-I01 |
| FR-100 – FR-119 (Bus) | TC-U10-13, TC-I04 |
| FR-120 – FR-139 (Contract) | TC-C01-31 |
| FR-140 – FR-159 (LLM router) | TC-U20-28, TC-F02-05, TC-F15 |
| FR-160 – FR-179 (Bot) | TC-I07-09, TC-E01-04, TC-E10 |
| FR-180 – FR-199 (Dashboard) | TC-U100-109, TC-E06-09 |
| FR-200 – FR-219 (API) | TC-I05-06, TC-E05 |
| FR-220 – FR-239 (Schemas) | TC-I11, TC-F12, TC-U109 |
| NFR-200 (E2E latency) | TC-P01 |
| NFR-220 (fault isolation) | TC-F02-F10 |
| NFR-222 (no message loss) | TC-I04, TC-F06 |
| NFR-260 (lineage) | TC-I02 |
| NFR-261 (hash verifiability) | TC-I03, TC-U40-43 |
| NFR-320-322 (coverage) | CI gate, not a named test |

Every Must-priority FR has ≥1 test. Every §6 failure mode has a TC-F##. Every M user flow has a TC-E##.

---

## 10. Test ownership

Solo build: Senthil writes and maintains all test code. Test code lives next to production code; every PR with a new feature must include its tests in the same push.

---

## 11. Known gaps & deferred work

| Gap | Reason |
|---|---|
| Mutation testing (mutmut, Stryker) | Future hardening beyond 100% line+branch |
| Full load testing beyond 30/min | v1 scope bounded |
| Cross-browser beyond Chromium/Firefox/WebKit | Playwright covers the three majors |
| Formal verification of contract | Pre-mainnet |
| Accessibility audit beyond AA baseline | Post-hackathon |

---

**End of 09_TestCases.md**
