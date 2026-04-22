# 01 — Requirements Document

**Project:** SwarmScout — Decentralized Agent Swarm for Four.Meme Alpha Discovery
**Hackathon:** HACK0015 — Four.Meme AI Sprint
**Document owner:** Senthil
**Architecture session:** AT-0002-01-Architecture-Discussion-22042026
**Status:** Locked — architecture decisions frozen, ready for implementation
**Last updated:** 2026-04-22 06:15 UTC

---

## 0. Document purpose

This document defines **what** SwarmScout must do (functional requirements), **how well** it must do it (non-functional requirements), and **how important** each requirement is (MoSCoW priority). It is the single source of truth against which every subsequent artefact (Architecture, HLD, LLD, Test Plan, Test Cases) is traced and validated.

Every requirement in this document is:
- **Uniquely identified** — `FR-###` for functional, `NFR-###` for non-functional
- **Testable** — written such that pass/fail is unambiguous
- **Traced** — either to a hackathon judging criterion, a user scenario, or an internal engineering rule
- **Prioritised** — MoSCoW: **M**ust / **S**hould / **C**ould / **W**on't (this release)

No requirement is written as "nice to have" or "if time permits." Either it's in scope (M/S/C) or it's explicitly out of scope (W).

---

## 1. Scope

### 1.1 In scope

- A running multi-agent swarm that monitors the Four.meme platform in real time
- Five specialized agents (Hunter, Social, Chain, Risk, Narrator) communicating over a durable message bus
- LLM routing across three providers (Anthropic, OpenAI, Google) via the DGrid AI Gateway with per-agent model specialisation and documented fallback chains
- On-chain findings registry smart contract deployed to BNB Testnet, storing SHA-256 hashes of every agent output
- Three delivery surfaces: Telegram bot, Next.js dashboard, public JSON API
- Full observability: agent activity timeline, cost tracking per provider, on-chain verification links
- 100% test coverage at every layer (unit, integration, end-to-end, frontend, backend, contract), enforced by CI

### 1.2 Out of scope (Won't — this release)

| ID | Item | Rationale |
|---|---|---|
| W-01 | Mainnet contract deployment | Testnet proves the pattern; mainnet is a post-hackathon deployment concern requiring audit. |
| W-02 | Token issuance for SwarmScout itself | Hackathon brief explicitly states "Token issuance is optional and will not influence judging." |
| W-03 | Mobile native apps (iOS/Android) | Telegram bot and responsive web dashboard cover mobile use case. |
| W-04 | User authentication / accounts on dashboard | Public-read dashboard; subscription happens via Telegram bot (`/subscribe`). |
| W-05 | Payment / premium tiers | No monetisation in v1. |
| W-06 | Agents coordinating over peer-to-peer protocols (e.g. Vertex) | Evaluated and deferred — see Architecture doc §X. Migration candidate for v2 edge-deployment scenarios. |
| W-07 | Four.meme listing on mainnet BNB Chain (as opposed to their platform) | Not the same thing; SwarmScout monitors the Four.meme platform, not arbitrary BNB tokens. |
| W-08 | Historical back-testing of agent signals vs actual token outcomes | Requires weeks of data; documented as post-hackathon validation work. |
| W-09 | Multi-language UI (i18n) | English only in v1. |
| W-10 | Running more than one instance of each agent in parallel (horizontal scale) | Single-instance per agent in v1; Redis consumer-group code must **support** horizontal scaling, but v1 runs one worker per agent role. |

---

## 2. Stakeholders & actors

| Actor | Type | Interest |
|---|---|---|
| **Retail trader** | Primary end-user | Wants timely, trustworthy alpha on new Four.meme tokens without watching 24/7. |
| **Power user / algo trader** | Secondary end-user | Wants the raw JSON API to feed their own bots; wants on-chain verification of findings. |
| **Hackathon judge** | Evaluator | Assesses against Innovation (30%), Technical Implementation (30%), Practical Value (20%), Presentation (20%). |
| **DGrid bounty judge** | Evaluator | Assesses depth of DGrid AI Gateway usage; rewards multi-model, multi-provider routing. |
| **Future maintainer (enterprise)** | Post-handoff engineer | Must be able to understand, extend, and operate the system from docs alone. |
| **Four.meme platform** | Upstream data source | Emits new-token events and holds on-chain metadata. **Not controlled by us.** |
| **BNB Testnet** | Blockchain substrate | Hosts the FindingsRegistry contract. **Not controlled by us.** |
| **LLM providers (Anthropic, OpenAI, Google)** | External services | Serve model inference via DGrid. **Not controlled by us; must fail gracefully.** |

---

## 3. Functional requirements

### 3.1 Hunter Agent (FR-001 – FR-019)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-001 | The Hunter agent **shall** continuously monitor the Four.meme platform for new token launch events. | **M** | Core product premise |
| FR-002 | The Hunter agent **shall** emit a `TokenCandidate` message to the `stream:candidates` Redis stream within 30 seconds of a new-token event being observable on Four.meme. | **M** | NFR-201 (latency) |
| FR-003 | Each `TokenCandidate` message **shall** contain: token contract address, launch timestamp, creator address, token name, token symbol, initial liquidity pool size, source URL. | **M** | Downstream agents need deterministic schema |
| FR-004 | The Hunter agent **shall** deduplicate events — the same token address **shall not** produce more than one `TokenCandidate` message per 24-hour window. | **M** | Prevents downstream cost explosion |
| FR-005 | The Hunter agent **shall** hash each emitted `TokenCandidate` with SHA-256 and write the hash to the on-chain FindingsRegistry contract before publishing to the downstream stream. | **M** | Core value prop: on-chain provenance |
| FR-006 | The Hunter agent **shall** use `google/gemini-2.5-flash` as its primary LLM for event parsing, with fallback chain `→ anthropic/claude-haiku-4-5 → openai/gpt-4o-mini`. | **M** | Provider resilience (NFR-301) |
| FR-007 | The Hunter agent **shall** retry on transient Four.meme API failures with exponential backoff (1s, 2s, 4s, 8s, 16s; max 5 attempts). | **M** | Robustness |
| FR-008 | The Hunter agent **shall** emit a structured health heartbeat to Redis every 10 seconds, containing: last-event-timestamp, events-processed-last-minute, current-model-in-use, LLM-error-rate-last-5min. | **S** | NFR-401 (observability) |
| FR-009 | The Hunter agent **shall** log every LLM call (provider, model, input hash, output hash, token count, latency, cost) to PostgreSQL. | **M** | Cost accountability + audit |
| FR-010 | The Hunter agent **shall** cache Four.meme responses in Redis with TTL 60 seconds to avoid redundant network calls. | **S** | Cost + rate-limit compliance |

### 3.2 Social Agent (FR-020 – FR-039)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-020 | The Social agent **shall** consume `TokenCandidate` messages from `stream:candidates` via consumer group `group:social`. | **M** | Pipeline topology |
| FR-021 | For each candidate, the Social agent **shall** scrape X (Twitter) and public Telegram channels for mentions of the token address, name, or symbol within the last 24 hours. | **M** | Core signal |
| FR-022 | The Social agent **shall** use the Playwright stealth pattern (reused from HACK0014 `scrape_chats_v2`) for X scraping. | **M** | Reuse proven asset |
| FR-023 | The Social agent **shall** produce a `SocialScore` message containing: organic_score (0–100), mentions_24h (int), sentiment (−1.0 to +1.0), red_flags (list of strings), influencer_mentions (list of handles). | **M** | Schema contract |
| FR-024 | The Social agent **shall** use `openai/gpt-4o` as primary, with fallback chain `→ anthropic/claude-sonnet-4-6 → google/gemini-2.5-pro`. | **M** | Provider resilience |
| FR-025 | The Social agent **shall** detect and flag coordinated inauthentic behaviour (e.g., identical post copy across >10 handles) and include `coordinated_posting: true` in red_flags. | **S** | Rug-pull defence |
| FR-026 | The Social agent **shall** hash each `SocialScore` and write to on-chain registry before publishing to `stream:social`. | **M** | Provenance |
| FR-027 | The Social agent **shall** fail gracefully on scraping errors — emit a partial `SocialScore` with `data_quality: degraded` flag rather than blocking the pipeline. | **M** | Pipeline must not stall on source failures |
| FR-028 | The Social agent **shall** complete analysis within 60 seconds per candidate (P95). | **S** | NFR-201 |
| FR-029 | The Social agent **shall** respect X and Telegram rate limits via Redis-backed token buckets. | **M** | Platform ToS |

### 3.3 Chain Agent (FR-040 – FR-059)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-040 | The Chain agent **shall** consume `TokenCandidate` messages from `stream:candidates` via consumer group `group:chain` (parallel to Social). | **M** | Pipeline topology |
| FR-041 | The Chain agent **shall** query BscScan API + BNB RPC to retrieve: holder count, top-10-holder concentration %, liquidity pool size, buy/sell velocity (tx/min), whale entries (>$1k addresses). | **M** | Core signal |
| FR-042 | The Chain agent **shall** produce a `ChainMetrics` message containing all fields in FR-041 plus: contract_verified (bool), honeypot_check_passed (bool), lp_locked (bool), creator_previous_tokens (int). | **M** | Schema contract |
| FR-043 | The Chain agent **shall** use `anthropic/claude-sonnet-4-6` as primary, with fallback chain `→ openai/gpt-4o → google/gemini-2.5-pro`. | **M** | Provider resilience |
| FR-044 | The Chain agent **shall** cache BscScan responses in Redis with TTL 30 seconds. | **M** | API cost + rate limit |
| FR-045 | The Chain agent **shall** hash each `ChainMetrics` output and write to on-chain registry before publishing to `stream:chain`. | **M** | Provenance |
| FR-046 | The Chain agent **shall** flag honeypot contracts detected by running a simulated buy+sell via eth_call and checking for revert. | **M** | Rug-pull defence |
| FR-047 | The Chain agent **shall** complete analysis within 30 seconds per candidate (P95). | **S** | NFR-201 |

### 3.4 Risk Agent (FR-060 – FR-079)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-060 | The Risk agent **shall** consume from both `stream:social` (via `group:risk-social`) and `stream:chain` (via `group:risk-chain`) and join messages by shared `upstream_ids` referring to the same `TokenCandidate`. | **M** | Pipeline topology |
| FR-061 | The Risk agent **shall** wait up to 120 seconds for both Social and Chain outputs for a given candidate before producing a `RiskVerdict` with whatever inputs are available. | **M** | Prevents pipeline stalls on one agent failure |
| FR-062 | The Risk agent **shall** produce a `RiskVerdict` message containing: score_0_100, red_flags (list), rationale (string, 100–500 words), missing_inputs (list of agent names that failed to produce input), confidence (low/medium/high), requires_human_review (bool). | **M** | Schema contract |
| FR-063 | The Risk agent **shall** use `anthropic/claude-opus-4-7` as primary, with fallback chain `→ openai/gpt-4o (reasoning mode) → google/gemini-2.5-pro`. | **M** | Quality ceiling — this is the highest-stakes inference |
| FR-064 | If all three LLM providers fail, the Risk agent **shall** emit a `RiskVerdict` with `confidence: null`, `requires_human_review: true`, and `score_0_100: null` — **not** a default/guess value. | **M** | No silent degradation |
| FR-065 | The Risk agent **shall** hash each `RiskVerdict` and write to on-chain registry before publishing to `stream:risk`. | **M** | Provenance |
| FR-066 | The Risk agent **shall** apply 15 pre-defined rug-pull heuristic rules (e.g., creator has deployed >5 tokens in 7 days, LP <$1k, top-1-holder >50%) and include triggered rules in `red_flags`. | **M** | Deterministic safety net beneath LLM reasoning |
| FR-067 | The Risk agent **shall** complete per-candidate verdict within 90 seconds (P95). | **S** | NFR-201 |

### 3.5 Narrator Agent (FR-080 – FR-099)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-080 | The Narrator agent **shall** consume `RiskVerdict` messages from `stream:risk` via consumer group `group:narrator`. | **M** | Pipeline topology |
| FR-081 | The Narrator agent **shall** fetch all upstream messages (`TokenCandidate`, `SocialScore`, `ChainMetrics`, `RiskVerdict`) from PostgreSQL using the `upstream_ids` lineage. | **M** | Full context required for brief |
| FR-082 | The Narrator agent **shall** produce an `AlphaBrief` containing: token_name, token_address, thesis (50–150 words), conviction_tier (degen/speculative/moderate/high), caveats (list), sources (list of URLs + on-chain verification links), model_attribution (list of models used across the pipeline), brief_generated_at (ISO-8601). | **M** | User-facing output |
| FR-083 | The Narrator agent **shall** use `anthropic/claude-opus-4-7` as primary, with fallback chain `→ openai/gpt-4o → google/gemini-2.5-pro`. | **M** | Quality bar highest for user-facing prose |
| FR-084 | The Narrator agent **shall** hash each `AlphaBrief` and write to on-chain registry before publishing to `stream:briefs`. | **M** | Provenance |
| FR-085 | Each `AlphaBrief` **shall** include a `confidence_tier` that reflects degradation if any upstream agent produced degraded output. | **M** | Honest surfacing of data quality |
| FR-086 | The Narrator agent **shall** NOT produce an `AlphaBrief` if the upstream `RiskVerdict` has `requires_human_review: true` — instead emit a `HumanReviewRequest` to a separate stream. | **M** | Safety escalation |
| FR-087 | The Narrator agent **shall** complete brief generation within 45 seconds (P95). | **S** | NFR-201 |

### 3.6 Message bus & persistence (FR-100 – FR-119)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-100 | The system **shall** use Redis Streams as the durable message bus between all agents. | **M** | Architecture decision |
| FR-101 | Every message **shall** conform to a shared envelope: `{msg_id (ULID), agent, upstream_ids[], payload_hash, payload, created_at, model_used}`. | **M** | Auditability |
| FR-102 | Every stream **shall** have `MAXLEN ~ 100000` capped length with AOF persistence enabled on Redis. | **M** | Durability |
| FR-103 | Full payloads **shall** be written to PostgreSQL 16 keyed by `msg_id`, with the stream carrying only the envelope. | **M** | Hot/cold storage split |
| FR-104 | Each agent **shall** use a dedicated consumer group and acknowledge messages only after successful processing AND successful on-chain hash write. | **M** | At-least-once + auditability |
| FR-105 | If a consumer fails mid-processing, the message **shall** be automatically redelivered by Redis after a visibility timeout of 60 seconds. | **M** | Crash recovery |
| FR-106 | The system **shall** expose `XPENDING` and `XLEN` metrics per stream for backpressure monitoring. | **M** | Ops visibility |

### 3.7 On-chain FindingsRegistry contract (FR-120 – FR-139)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-120 | A Solidity 0.8.24 smart contract named `FindingsRegistry` **shall** be deployed to BNB Testnet. | **M** | Core differentiator |
| FR-121 | The contract **shall** expose `recordFinding(bytes32 msgId, bytes32 payloadHash, string agent)` that stores `(msgId, payloadHash, agent, block.timestamp, msg.sender)` in a public mapping. | **M** | Contract API |
| FR-122 | The contract **shall** emit a `FindingRecorded(bytes32 indexed msgId, bytes32 payloadHash, string agent, uint256 timestamp)` event on every write. | **M** | Indexable audit trail |
| FR-123 | The contract **shall** restrict `recordFinding` to an allowlist of agent wallet addresses configured at deploy time. | **M** | Prevent spam/abuse |
| FR-124 | The contract **shall** expose `verifyFinding(bytes32 msgId) returns (bytes32 payloadHash, string agent, uint256 timestamp)` as a read-only method. | **M** | Public verification |
| FR-125 | The contract **shall** have 100% line and branch coverage under `forge coverage`. | **M** | Rule 2.4 |
| FR-126 | The contract **shall** be built with Foundry and deployed via a committed `forge script`. | **M** | Reproducibility |
| FR-127 | The contract **shall** include invariant tests ensuring a recorded finding cannot be mutated or deleted. | **M** | Immutability guarantee |

### 3.8 LLM routing (FR-140 – FR-159)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-140 | All LLM calls **shall** route through the DGrid AI Gateway (`https://api.dgrid.ai/v1`) as the primary provider. | **M** | Bounty requirement ($3k) |
| FR-141 | If DGrid is unreachable or returns 5xx for >3 consecutive calls, the router **shall** fall back to direct provider APIs (Anthropic, OpenAI, Google) using per-provider credentials. | **M** | Production SLO |
| FR-142 | The router **shall** implement per-provider token-bucket rate limiting backed by Redis. | **M** | Cost control + provider ToS |
| FR-143 | The router **shall** log every call with: provider, model, agent_name, prompt_hash, response_hash, input_tokens, output_tokens, cost_usd, latency_ms, success_bool. | **M** | Cost accountability |
| FR-144 | The router **shall** expose a `/metrics` Prometheus endpoint summarising calls-per-hour, errors-per-hour, cost-per-hour per (agent, provider, model) tuple. | **S** | Ops visibility |
| FR-145 | The router's fallback-chain logic **shall** have 100% line and branch coverage in unit tests. | **M** | Rule 2.4 |

### 3.9 Telegram bot (FR-160 – FR-179)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-160 | A Telegram bot **shall** be built with aiogram v3. | **M** | Delivery surface |
| FR-161 | The bot **shall** support commands: `/start`, `/subscribe`, `/unsubscribe`, `/threshold <0–100>`, `/status`, `/help`, `/verify <msg_id>`. | **M** | UX contract |
| FR-162 | `/subscribe` **shall** register the chat_id to receive all new `AlphaBrief` messages above the user's configured conviction threshold (default: moderate). | **M** | Core subscription flow |
| FR-163 | `/verify <msg_id>` **shall** return the BscScan URL of the on-chain record for that finding. | **M** | Provenance UX |
| FR-164 | The bot **shall** format briefs with: token name + address (clickable BscScan link), conviction tier (emoji-coded), thesis, top 3 red flags, on-chain verification link, model attribution footer. | **M** | Readability |
| FR-165 | The bot **shall** dedupe messages per chat using Redis SET with 48-hour TTL to prevent double-sends on retry. | **M** | UX robustness |
| FR-166 | The bot **shall** consume from `stream:briefs` via consumer group `group:telegram`. | **M** | Pipeline topology |

### 3.10 Next.js dashboard (FR-180 – FR-199)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-180 | A Next.js 14 App Router dashboard **shall** be accessible at a public URL. | **M** | Delivery surface |
| FR-181 | The dashboard **shall** display a live feed of `AlphaBrief` messages sorted by recency, paginated. | **M** | Core UX |
| FR-182 | Each brief card **shall** show: token name, conviction tier, thesis summary (expand on click), red flags, model attribution, on-chain verification link (BscScan). | **M** | Readability + provenance |
| FR-183 | The dashboard **shall** include an "Agent Activity Timeline" panel showing the last 100 events across all streams in real-time via WebSocket. | **M** | Judging criterion: Presentation (20%) |
| FR-184 | The dashboard **shall** include a "Model Usage" panel showing calls-per-hour per (agent, provider, model) tuple, refreshing every 10 seconds. | **S** | Bounty showcase (multi-model) |
| FR-185 | The dashboard **shall** include a "Swarm Health" panel showing per-agent status: online/degraded/down, last heartbeat, pending queue depth. | **S** | Ops visibility |
| FR-186 | Every brief shown **shall** have a direct click-through to verify the hash on BscScan (opens new tab). | **M** | Provenance UX |
| FR-187 | The dashboard **shall** be responsive (mobile + desktop). | **M** | User reach |
| FR-188 | The dashboard **shall** achieve 100% component test coverage via Vitest + Testing Library. | **M** | Rule 2.4 |
| FR-189 | The dashboard's happy-path user flows **shall** be covered by Playwright E2E tests. | **M** | Rule 2.4 |

### 3.11 Public JSON API (FR-200 – FR-219)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-200 | A FastAPI-based public JSON API **shall** be available. | **M** | Delivery surface |
| FR-201 | The API **shall** expose: `GET /briefs` (paginated list), `GET /briefs/{msg_id}` (detail), `GET /briefs/{msg_id}/verify` (on-chain lookup), `GET /health` (liveness). | **M** | API surface |
| FR-202 | Every API response **shall** conform to an OpenAPI 3.1 schema auto-generated from Pydantic models. | **M** | Contract discipline |
| FR-203 | The API **shall** rate-limit unauthenticated callers to 60 requests/minute via Redis-backed token buckets. | **S** | Abuse prevention |
| FR-204 | The API **shall** have 100% line and branch coverage via pytest. | **M** | Rule 2.4 |

### 3.12 Shared schema governance (FR-220 – FR-239)

| ID | Requirement | Priority | Trace |
|---|---|---|---|
| FR-220 | All inter-agent message schemas **shall** be defined as Pydantic v2 models in `agents/common/schemas/`. | **M** | Single source of truth |
| FR-221 | Pydantic schemas **shall** be exported to JSON Schema on every CI run. | **M** | Contract discipline |
| FR-222 | JSON Schemas **shall** be converted to TypeScript zod schemas and consumed by the Next.js dashboard and any other TypeScript consumer. | **M** | Zero schema drift |
| FR-223 | CI **shall** fail if the exported JSON Schema differs from the committed copy. | **M** | Drift detection |

---

## 4. Non-functional requirements

### 4.1 Performance (NFR-200 – NFR-219)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-200 | End-to-end latency from Four.meme event → `AlphaBrief` published **shall** be ≤ 5 minutes at P95 under normal load (≤10 candidates/min). | **M** | Timestamped trace through streams |
| NFR-201 | Per-agent latencies defined in FR-002, FR-028, FR-047, FR-067, FR-087 **shall** hold at P95. | **M** | OpenTelemetry traces |
| NFR-202 | System **shall** handle burst loads of 30 candidates/minute without message loss. | **S** | Load test via `locust` hitting mocked Four.meme webhook |

### 4.2 Reliability & availability (NFR-220 – NFR-239)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-220 | No agent failure **shall** cause upstream or parallel agents to fail (fault isolation). | **M** | Chaos test: kill each agent in turn, verify rest of pipeline continues. |
| NFR-221 | The system **shall** achieve ≥99% uptime during the 72-hour judging window post-submission. | **S** | Uptime monitor (Uptime Kuma or equivalent) |
| NFR-222 | No message **shall** be lost between agents (at-least-once delivery). | **M** | Chaos test: force Redis AOF replay, verify all PEL messages re-processed. |
| NFR-223 | If all LLM providers are unreachable, the system **shall** continue to queue events in Redis, resuming processing when providers recover. | **M** | Integration test: disable all providers, verify queue grows without loss; re-enable, verify drain. |

### 4.3 Security (NFR-240 – NFR-259)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-240 | All secrets (API keys, wallet private keys) **shall** be loaded from environment variables, never committed to git. | **M** | `detect-secrets` pre-commit hook |
| NFR-241 | The agent wallet private key used to sign on-chain writes **shall** have limited BNB Testnet funds only (no mainnet funds). | **M** | Wallet configuration review |
| NFR-242 | The FindingsRegistry contract **shall** restrict writes to the allowlisted agent wallet addresses. | **M** | FR-123 |
| NFR-243 | All HTTP traffic **shall** use TLS in any non-local deployment. | **M** | Infrastructure review |
| NFR-244 | The public API **shall** not expose LLM prompts, wallet private keys, or any secret in any response. | **M** | Security test suite |

### 4.4 Auditability & provenance (NFR-260 – NFR-279)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-260 | Every agent output **shall** be traceable from the published brief back through the full `upstream_ids` lineage to the original Four.meme event. | **M** | Integration test: pick any brief, reconstruct full lineage from PostgreSQL. |
| NFR-261 | Every payload hash in the pipeline **shall** match the corresponding record in the on-chain FindingsRegistry. | **M** | CI test: take 10 random briefs, verify every hash on BscScan. |
| NFR-262 | The `model_used` field **shall** be present in every message envelope and included in the hashed payload. | **M** | Schema enforcement + hash verification |

### 4.5 Observability (NFR-280 – NFR-299)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-280 | Every agent **shall** emit structured JSON logs to stdout at minimum INFO level. | **M** | Log schema review |
| NFR-281 | Prometheus-compatible `/metrics` endpoint **shall** be exposed by each agent, API, and the LLM router. | **S** | Endpoint check |
| NFR-282 | The dashboard **shall** render a live health panel for each agent (FR-185). | **S** | UI test |
| NFR-283 | OpenTelemetry trace context **shall** be propagated across every message envelope so a single Four.meme event can be traced end-to-end. | **S** | Trace test in staging |

### 4.6 Cost control (NFR-300 – NFR-319)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-300 | Per-call, per-agent, per-provider cost **shall** be logged to PostgreSQL. | **M** | FR-143 |
| NFR-301 | The dashboard **shall** surface running cost per hour per provider. | **S** | FR-184 |
| NFR-302 | A hard daily cost cap per provider **shall** be configurable via environment variable. When exceeded, the router **shall** fall back to cheaper-tier models within the same fallback chain. | **S** | Circuit breaker test |

### 4.7 Testing & quality (NFR-320 – NFR-339)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-320 | Python code **shall** achieve 100% line and 100% branch coverage via `pytest --cov --cov-branch --cov-fail-under=100`. | **M** | CI gate |
| NFR-321 | TypeScript code **shall** achieve 100% across lines, branches, functions, and statements via `vitest run --coverage` with thresholds enforced. | **M** | CI gate |
| NFR-322 | Solidity code **shall** achieve 100% line and branch coverage via `forge coverage`. | **M** | CI gate |
| NFR-323 | Every component boundary **shall** have at least one integration test exercising real Redis and PostgreSQL (via testcontainers). | **M** | Test plan doc |
| NFR-324 | E2E Playwright tests **shall** cover every dashboard user flow defined in the User Flow document (05_UserFlow.md). | **M** | Rule 2.4 |
| NFR-325 | Each LLM router fallback branch (primary fails → second → third → all fail) **shall** be covered by a named test case. | **M** | FR-145 |
| NFR-326 | Every commit to `main` **shall** pass: linting, type-checking, unit tests, integration tests, contract tests, and coverage gates. | **M** | GitHub Actions CI |
| NFR-327 | A new commit **shall** be created for every logical change (rule 2.2 — one logical change = one commit, Conventional Commits). | **M** | Git history review |

### 4.8 Maintainability (NFR-340 – NFR-359)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-340 | All code **shall** pass `ruff` (Python) and `biome` (TypeScript) with zero warnings. | **M** | CI gate |
| NFR-341 | All Python code **shall** pass `mypy --strict`. | **M** | CI gate |
| NFR-342 | All TypeScript code **shall** pass `tsc --noEmit --strict`. | **M** | CI gate |
| NFR-343 | Every public function/method **shall** have a docstring explaining purpose, inputs, outputs, and side effects. | **S** | Lint rule |
| NFR-344 | The repository **shall** include a `README.md`, `CONTRIBUTING.md`, and `ARCHITECTURE.md` at root. | **M** | Repo structure |

### 4.9 Deployment (NFR-360 – NFR-379)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-360 | Local development **shall** be runnable via a single `docker compose up` command. | **M** | Developer onboarding |
| NFR-361 | The production demo **shall** be deployable to a single VPS via a committed deployment script. | **M** | Reproducibility |
| NFR-362 | All infrastructure dependencies (Redis, PostgreSQL, app processes) **shall** be pinned to exact versions in `docker-compose.yml`. | **M** | Reproducibility |

### 4.10 Documentation (NFR-380 – NFR-399)

| ID | Requirement | Priority | Measure |
|---|---|---|---|
| NFR-380 | All 9 artefacts specified by handoff prompt §2.5 **shall** be produced before build starts. | **M** | Deliverable gate |
| NFR-381 | Each architecture/design decision **shall** include: what was chosen, why, what alternatives were considered, why they were rejected, trade-offs accepted (rule 2.8). | **M** | Architecture doc review |
| NFR-382 | The phrase "for demo purposes" **shall not** appear in any artefact. | **M** | Grep check |
| NFR-383 | Every artefact **shall** end with a "Known Gaps & Deferred Work" section. | **M** | Document structure |

---

## 5. Traceability matrix (requirements → judging criteria → rules)

| Judging criterion | Weight | Requirements supporting it |
|---|---|---|
| Innovation | 30% | FR-100, FR-101, FR-104, FR-120, FR-121, FR-122, FR-140, FR-141, FR-183, FR-184, NFR-260, NFR-261, NFR-262 |
| Technical Implementation | 30% | FR-005, FR-026, FR-045, FR-065, FR-084, FR-120–FR-127, FR-140–FR-145, FR-220–FR-223, NFR-220, NFR-222, NFR-223, NFR-320–NFR-327 |
| Practical Value | 20% | FR-001–FR-099 (full pipeline), FR-160–FR-166 (bot), FR-180–FR-189 (dashboard), FR-200–FR-204 (API), NFR-260 (provenance is user trust) |
| Presentation | 20% | FR-183 (live timeline), FR-184 (model panel), FR-185 (swarm health), FR-186 (one-click verify), FR-187 (responsive) |
| **DGrid bounty ($3k)** | separate | FR-140, FR-141, FR-144, FR-184, FR-006, FR-024, FR-043, FR-063, FR-083 (multi-model via gateway) |

| Rule | Enforcing requirements |
|---|---|
| 2.1 Enterprise-grade mindset | Entire doc; see W-01…W-10 rationales |
| 2.2 Git-first, one logical change = one commit | NFR-327, NFR-326 |
| 2.3 Block development | Implicit in delivery style; no FR/NFR needed |
| 2.4 100% test coverage, no scope shrink | NFR-320–NFR-327, FR-125, FR-188, FR-204 |
| 2.5 9 required docs | NFR-380 |
| 2.6 Build session handoff | NFR-380 — includes 10th file (BUILD_SESSION_PROMPT.md) |
| 2.7 Memory/surface rules | Handoff prompt structure carries this; no FR/NFR |
| 2.8 Full justification (new rule) | NFR-381, NFR-382 |

---

## 6. Assumptions

| ID | Assumption | If wrong, impact |
|---|---|---|
| A-01 | Four.meme exposes either a public WebSocket/polling endpoint or an on-chain event stream for new tokens | High — Hunter architecture changes; may need to switch to pure chain-watching via RPC logs |
| A-02 | BscScan free-tier API rate limits (5 req/s) are sufficient for ≤10 candidates/min | Medium — if not, need paid tier or local BNB node |
| A-03 | BNB Testnet gas is reliably available (faucet-fed) for the agent wallet | Medium — if faucet fails, pause hash writes temporarily; findings still published, provenance delayed |
| A-04 | DGrid AI Gateway is operational and supports all three providers (Anthropic, OpenAI, Google) | Low — direct-provider fallback covers this |
| A-05 | All three LLM provider keys remain valid through the judging window | Low — per-provider fallback chains handle individual outages |
| A-06 | Playwright stealth pattern from HACK0014 still bypasses X and Telegram scraping defences on 2026-04-22 | Medium — if platforms updated defences, Social agent operates in degraded mode per FR-027 |

---

## 7. Constraints

| ID | Constraint |
|---|---|
| C-01 | Submission deadline: 2026-04-22 16:59 UTC — approximately 10h 45m from document completion |
| C-02 | Submission requires: GitHub repo (public) + 3-minute demo video + submission form on DoraHacks |
| C-03 | BNB Testnet only — no mainnet deployment |
| C-04 | Solo build (Senthil) — no team parallelism |
| C-05 | Windows host filesystem at `C:\Users\v_sen\Documents\Claude\Hack0015-SwarmScout\` |
| C-06 | All work must follow rule 2.2 (git-first, commit-before-test, commit-on-fix) |
| C-07 | No "for demo purposes" language anywhere in artefacts or code comments |

---

## 8. Glossary

| Term | Definition |
|---|---|
| **AlphaBrief** | Final user-facing output: a structured brief with thesis, conviction tier, caveats, and sources about one Four.meme token |
| **Alpha** | Crypto-trader term for actionable information that provides an edge |
| **BNB Testnet** | Binance Smart Chain testnet (chain ID 97) — used for gas-free contract deployment |
| **Conviction tier** | 4-level classification: degen / speculative / moderate / high — user-facing risk signal |
| **DGrid** | AI Gateway that routes LLM calls across multiple providers with OpenAI-compatible API; hackathon sponsor offering $3k bounty |
| **Four.meme** | Target platform being monitored — memecoin launch pad |
| **Honeypot** | Malicious token contract that allows buys but blocks sells |
| **LP** | Liquidity Pool — the tokens locked in a DEX pool enabling trading |
| **MoSCoW** | Prioritisation method: Must / Should / Could / Won't (this release) |
| **PEL** | Pending Entries List — Redis Streams' record of unacknowledged messages per consumer group |
| **Rug pull** | Scam where token creator drains liquidity or abandons project |
| **SwarmScout** | This project — codename |
| **ULID** | Universally Unique Lexicographically-sortable Identifier — used as `msg_id` for ordered envelopes |

---

## 9. Known gaps & deferred work

Honest catalogue of things this requirements document has chosen not to specify, and why:

| Gap | Status | Rationale |
|---|---|---|
| **Exact Four.meme event-source API surface** | Deferred to Architecture doc | A-01 assumption to be validated during architecture phase; options are polling REST endpoint, WebSocket, or on-chain log subscription |
| **Precise 15 rug-pull heuristic rules (FR-066)** | Deferred to LLD | Full rule catalogue belongs in low-level design, not requirements |
| **Specific BscScan API endpoints used** | Deferred to LLD | Implementation detail |
| **Playwright stealth configuration specifics** | Deferred to LLD | Reuse from HACK0014 — will inherit that repo's configuration |
| **Exact Prometheus metric names** | Deferred to Architecture doc | Naming convention decision, not requirement |
| **Grafana dashboard definitions** | Out of scope this release (W-11) | Observability above baseline is post-hackathon work |
| **Backup & disaster recovery procedure for the agent wallet** | Deferred to operations runbook (post-hackathon) | Testnet wallet, no real funds; recovery is re-funding from faucet |
| **Rate-limit tuning values** | Deferred to Architecture doc | Will be expressed as env-configurable constants, tuned during staging |
| **"Fox" reference from handoff prompt §3.2** | Unresolved | User has delegated — dropped from requirements unless raised again |
| **Horizontal scaling of agents (multiple workers per role)** | Won't — this release (W-10) | Redis consumer-group code will support it but v1 runs single-instance |
| **Historical back-testing** | Won't — this release (W-08) | Needs weeks of data |

---

## 10. Change log

| Date | Change | Author |
|---|---|---|
| 2026-04-22 06:15 UTC | Initial version — all requirements drafted from architecture session decisions | Claude (architecture session) |

---

**End of 01_Requirements.md**
