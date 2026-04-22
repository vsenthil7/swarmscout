# 06 — High-Level Design (HLD)

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 07:05 UTC

This document describes **what each component does, where it sits, and how it talks to others.** It is the bridge between 02_Architecture.md (tech choices + justification) and 07_LLD.md (class-level design). No code appears here — only component responsibilities, interfaces, and contracts.

---

## 1. System partitioning

SwarmScout is partitioned along three orthogonal axes:

| Axis | Partition | Why this axis |
|---|---|---|
| **Trust boundary** | Internal agents vs. external surfaces (API, bot, dashboard) | Agents have wallet access and higher privilege; surfaces are read-only consumers |
| **Deployment unit** | Process-per-agent + process-per-surface | Fault isolation (P2); independent scaling; independent crash recovery |
| **Data flow stage** | Detection → Enrichment (parallel) → Risk → Composition → Delivery | Clear message envelope contracts at each stage |

### 1.1 Component inventory

| Component | Process type | Trust | Primary responsibility |
|---|---|---|---|
| **Hunter agent** | Python daemon | Privileged (on-chain write) | Detect new Four.meme tokens, emit TokenCandidate |
| **Social agent** | Python daemon | Privileged | Scrape & score social signals |
| **Chain agent** | Python daemon | Privileged | Query chain data & compute metrics |
| **Risk agent** | Python daemon | Privileged | Synthesise risk verdict from Social + Chain |
| **Narrator agent** | Python daemon | Privileged | Compose user-facing AlphaBrief |
| **LLM router** | Python library (in every agent) | Internal | Route LLM calls through DGrid with fallbacks |
| **On-chain writer** | Python library (in every agent) | Privileged | Write hashes to FindingsRegistry |
| **Message bus** | Redis 7 instance | Internal | Durable, ordered, consumer-grouped streams |
| **Persistent store** | PostgreSQL 16 instance | Internal | Full payloads + subscription + logs |
| **FindingsRegistry contract** | Solidity on BNB Testnet | Public read / permissioned write | Immutable hash registry |
| **FastAPI service** | Python daemon | Public read | JSON API + WebSocket tail |
| **Telegram bot** | Python daemon | Public interact | Deliver alerts to subscribed users |
| **Next.js dashboard** | Node daemon + browser | Public read | Live UI |
| **Schema exporter** | Python script (CI only) | Internal | Pydantic → JSON Schema → zod |

---

## 2. Component responsibilities (one-liner contracts)

Each component has a single, clearly-stated responsibility. If a future change tempts us to expand one, we stop and ask whether a new component is needed instead.

### 2.1 Hunter agent

**Responsibility:** Be the only source of `TokenCandidate` messages into `stream:candidates`. Never derive findings; never analyse. Just detect and normalise.

**Inputs:** Four.meme platform events (polling or webhook — adapter-abstracted).
**Outputs:** `TokenCandidate` messages on `stream:candidates`.
**Side effects:** Writes hash to on-chain registry. Writes full payload to PostgreSQL. Emits heartbeat.

### 2.2 Social agent

**Responsibility:** Produce a single `SocialScore` per `TokenCandidate`, sourced from X and public Telegram channels. Never fabricate data on failure — emit degraded flag instead.

**Inputs:** `TokenCandidate` via `group:social` on `stream:candidates`.
**Outputs:** `SocialScore` messages on `stream:social`.
**Side effects:** External scrapes (respecting rate limits). On-chain hash write. PostgreSQL write. Heartbeat.

### 2.3 Chain agent

**Responsibility:** Produce a single `ChainMetrics` per `TokenCandidate` from BscScan + BNB RPC data. Include deterministic honeypot simulation.

**Inputs:** `TokenCandidate` via `group:chain` on `stream:candidates` (parallel to Social).
**Outputs:** `ChainMetrics` messages on `stream:chain`.
**Side effects:** External calls to BscScan API + BNB RPC. On-chain hash write. PostgreSQL write. Heartbeat.

### 2.4 Risk agent

**Responsibility:** Given a pair of `(SocialScore, ChainMetrics)` with shared upstream `TokenCandidate`, produce a single `RiskVerdict`. Never silently degrade — flag missing inputs or require human review.

**Inputs:** `SocialScore` via `group:risk-social` on `stream:social`, `ChainMetrics` via `group:risk-chain` on `stream:chain`. Joins by shared upstream `TokenCandidate` msg_id.
**Outputs:** `RiskVerdict` messages on `stream:risk`.
**Side effects:** Runs 15 deterministic heuristics. On-chain hash write. PostgreSQL write. Heartbeat.

### 2.5 Narrator agent

**Responsibility:** Compose a single user-facing `AlphaBrief` per `RiskVerdict` (or a `HumanReviewRequest` if requires_human_review). This is the only agent producing user-facing prose.

**Inputs:** `RiskVerdict` via `group:narrator` on `stream:risk`. Fetches full lineage from PostgreSQL.
**Outputs:** `AlphaBrief` on `stream:briefs`, or `HumanReviewRequest` on `stream:human_review`.
**Side effects:** On-chain hash write. PostgreSQL write. Heartbeat.

### 2.6 LLM router (library)

**Responsibility:** Route every LLM call through DGrid; on failure, fall back through per-agent chain; respect per-provider rate limits; log every call.

**Interface:** `await router.complete(agent_name: str, messages: list[Message], tools: list[Tool] = None) -> LLMResponse`.

### 2.7 On-chain writer (library)

**Responsibility:** Write `(msg_id, payload_hash, agent)` tuples to FindingsRegistry. Queue writes during RPC outage. Never block agent pipeline on chain write failure (publish downstream with `on_chain_status: pending`, drain queue later).

**Interface:** `await writer.record(msg_id: ULID, payload_hash: bytes32, agent: str) -> OnChainStatus`.

### 2.8 Message bus (Redis)

**Responsibility:** Durable, ordered, at-least-once delivery between agents. No logic — just transport + persistence.

**Contracts:**
- Every stream carries messages conforming to the shared envelope (see §4.1)
- Consumer groups named per downstream consumer
- `MAXLEN ~ 100000` per stream
- AOF persistence enabled

### 2.9 Persistent store (PostgreSQL)

**Responsibility:** Hold full payloads (envelope excluding the `payload` field carries the pointer; DB carries the fat content), subscription records, and LLM call logs.

**Schemas:** 5 primary tables (see §5).

### 2.10 FindingsRegistry contract

**Responsibility:** Accept writes from allowlisted agent wallets; emit events; allow public reads.

**Interface:**
- `recordFinding(bytes32 msgId, bytes32 payloadHash, string calldata agent) external onlyAllowlisted`
- `verifyFinding(bytes32 msgId) external view returns (bytes32 payloadHash, string memory agent, uint256 timestamp, address recordedBy)`
- `event FindingRecorded(bytes32 indexed msgId, bytes32 payloadHash, string agent, uint256 timestamp)`

### 2.11 FastAPI public API

**Responsibility:** Expose read-only JSON API; enforce rate limits; serialise PostgreSQL rows via Pydantic models; stream WebSocket updates from Redis Pub/Sub.

### 2.12 Telegram bot

**Responsibility:** Accept user commands, manage subscriptions, deliver briefs to subscribed users above their threshold.

### 2.13 Next.js dashboard

**Responsibility:** Render initial state from the API (SSR); subscribe to WebSocket updates for live ticks; link out to BscScan for verification.

---

## 3. Interaction patterns (component-to-component contracts)

### 3.1 Agent-to-agent (via message bus)

**Pattern:** Publish-subscribe with consumer groups.

```
Producer agent:
   XADD <stream> * <field> <value> ...  # appends envelope to stream

Consumer agent:
   XREADGROUP GROUP <group_name> <consumer_id> COUNT 1 BLOCK 5000 STREAMS <stream> >
   ... process message, write on-chain, write to PG, publish downstream ...
   XACK <stream> <group_name> <msg_id>
```

**Contract invariants:**
- Every message envelope conforms to §4.1 schema
- Consumer acknowledges **only after** full processing (including on-chain write completion or queued state)
- Consumer crashes → message returns to Pending Entries List → redelivered after visibility timeout (60s)

### 3.2 Agent-to-LLM (via router)

**Pattern:** Synchronous RPC with transparent fallback.

```
Agent code:
   response = await llm_router.complete(
       agent_name="social",
       messages=[...],
       tools=[...]  # optional
   )

Router:
   1. Check circuit breaker for (agent, primary) — if open, skip
   2. Acquire per-provider rate-limit token
   3. Try primary via DGrid → if 2xx, return
   4. On failure, advance to Fallback 1; repeat
   5. On all failures, raise LLMProvidersExhausted
   6. Log every attempt to PG
```

### 3.3 Agent-to-chain (via on-chain writer)

**Pattern:** Write-with-queued-fallback.

```
Agent code:
   status = await on_chain.record(msg_id, hash, agent_name)
   envelope["on_chain_status"] = status  # "confirmed" or "pending"
   await bus.publish(stream, envelope)

Writer:
   1. Attempt web3 send via BNB Testnet RPC
   2. If RPC errors → enqueue (msg_id, hash, agent) to Redis sorted-set with TTL 24h
   3. Return "pending" status
   4. Background task drains the queue on RPC recovery
```

### 3.4 API-to-data (via Postgres + Redis)

**Pattern:** Read-through with Redis for hot WebSocket fanout.

```
GET /briefs:
   query PG with pagination → serialise → return

WebSocket /ws/events:
   on connect: send last 50 events from XREVRANGE
   subscribe to Redis Pub/Sub channel "events:*"
   forward each message to client
```

### 3.5 Dashboard-to-API

**Pattern:** SSR initial + WebSocket deltas.

```
Next.js server component:
   fetch(API_URL + "/briefs?limit=20")  -> initial HTML
Next.js client component:
   new WebSocket(WS_URL + "/ws/events") -> live updates
```

### 3.6 Bot-to-users

**Pattern:** Consumer-group pull from `stream:briefs`, dedup send, Telegram API call.

```
Bot consumer loop:
   XREADGROUP group:telegram consumer1 STREAMS stream:briefs >
   for each brief:
     subscribers = SELECT chat_id FROM subscriptions
                   WHERE threshold <= brief.conviction_tier
                     AND deleted_at IS NULL
     for chat_id in subscribers:
       if SADD "dedup:{chat_id}:{msg_id}" returns 0 (already sent): skip
       send Telegram message
       EXPIRE the dedup key 48h
   XACK
```

---

## 4. Data contracts

### 4.1 Message envelope (all agent messages)

```
Envelope {
  msg_id:          ULID                 # ordered, globally unique
  agent:           "hunter" | "social" | "chain" | "risk" | "narrator"
  upstream_ids:    list[ULID]           # full lineage graph
  payload_hash:    hex string (64)      # SHA-256 of canonical JSON of `payload`
  payload:         object                # agent-specific schema (see §4.2–4.6)
  created_at:      ISO-8601 UTC
  model_used:      "provider/model" | null  # null if no LLM used (e.g., Hunter deterministic path)
  confidence_tier: "ok" | "degraded"    # overall message quality flag
  on_chain_status: "confirmed" | "pending"
}
```

### 4.2 TokenCandidate payload (Hunter)

```
TokenCandidate {
  token_address:     hex string (42)
  launch_timestamp:  ISO-8601 UTC
  creator_address:   hex string (42)
  token_name:        string
  token_symbol:      string
  initial_lp_size:   number (USD)
  source_url:        URL
  raw_event_hash:    hex string (64)    # proof of source
}
```

### 4.3 SocialScore payload (Social)

```
SocialScore {
  token_address:        hex string (42)
  organic_score:        int [0-100] | null
  mentions_24h:         int | null
  sentiment:            float [-1.0, 1.0] | null
  red_flags:            list[string]       # e.g., "coordinated_posting", "bot_heavy"
  influencer_mentions:  list[string]        # X handles
  data_quality:         "ok" | "degraded"
  sources:              list[URL]           # for audit
}
```

### 4.4 ChainMetrics payload (Chain)

```
ChainMetrics {
  token_address:             hex string (42)
  holders_count:             int
  top_10_concentration_pct:  float [0-100]
  lp_size_usd:               number
  lp_locked:                 bool
  lp_lock_days_remaining:    int | null
  tx_per_minute:             float
  whale_entries:             list[{address, size_usd}]
  contract_verified:         bool
  honeypot_check_passed:     bool
  creator_previous_tokens:   int
}
```

### 4.5 RiskVerdict payload (Risk)

```
RiskVerdict {
  token_address:          hex string (42)
  score_0_100:            int [0-100] | null      # null if requires_human_review
  conviction_tier:        "degen" | "speculative" | "moderate" | "high" | null
  red_flags:              list[string]
  rationale:              string (100–500 words)
  missing_inputs:         list["social" | "chain"]
  heuristics_triggered:   list[string]             # deterministic rule IDs
  confidence:             "low" | "medium" | "high" | null
  requires_human_review:  bool
}
```

### 4.6 AlphaBrief payload (Narrator)

```
AlphaBrief {
  token_address:       hex string (42)
  token_name:          string
  token_symbol:        string
  thesis:              string (50–150 words)
  conviction_tier:     "degen" | "speculative" | "moderate" | "high"
  confidence_tier:     "ok" | "degraded"
  caveats:             list[string]
  sources:             list[URL]
  model_attribution:   list["provider/model", ...]  # one per agent, in order
  brief_generated_at:  ISO-8601 UTC
  bscscan_url:         URL                           # verify link
}
```

### 4.7 HumanReviewRequest payload (Narrator, alternate path)

```
HumanReviewRequest {
  token_address:    hex string (42)
  reason:           string
  upstream_ids:     list[ULID]
  llm_errors:       list[{provider, error}]
  requested_at:     ISO-8601 UTC
}
```

---

## 5. Database schema (high-level)

Detailed types and indexes in 07_LLD.md §4. High-level tables only here:

| Table | Purpose | Primary key | Key columns |
|---|---|---|---|
| `messages` | Full payloads of every agent output | `msg_id` (ULID) | `agent`, `upstream_ids[]`, `payload_hash`, `payload` (JSONB), `created_at`, `model_used`, `on_chain_tx_hash` |
| `subscriptions` | Telegram user subscriptions | `chat_id` (bigint) | `threshold`, `subscribed_at`, `deleted_at` (soft delete), `last_alert_at` |
| `llm_calls` | Every LLM invocation | `id` (UUID) | `agent`, `provider`, `model`, `prompt_hash`, `response_hash`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `success`, `error`, `created_at` |
| `health_events` | Agent heartbeats + errors | `id` (bigint) | `agent`, `timestamp`, `status`, `current_model`, `error_rate`, `events_processed_last_minute`, `pending_queue_depth` |
| `on_chain_queue` | Pending hash writes during RPC outage | `id` (UUID) | `msg_id`, `payload_hash`, `agent`, `enqueued_at`, `attempts`, `last_error` |

---

## 6. Cross-cutting concerns

### 6.1 Configuration

All configuration is environment-variable driven. No config files. `.env.example` at repo root enumerates every variable with sample values. Loaded via `pydantic-settings` in Python, `zod.parse(process.env)` in TypeScript.

**Key groups:**
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DGRID_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `BNB_TESTNET_RPC_URL`, `WALLET_PRIVATE_KEY`, `FINDINGS_REGISTRY_ADDRESS`
- `REDIS_URL`, `DATABASE_URL`
- `RATE_LIMIT_*`, `DAILY_COST_CAP_USD_*` (per-provider)
- `LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT` (optional)

### 6.2 Logging

**Stack:** `structlog` (Python) + Next.js `pino`. JSON to stdout in production, pretty console in dev.

**Per-message context injected:** `msg_id`, `agent`, `upstream_ids[]`, `trace_id` (OpenTelemetry).

### 6.3 Metrics

**Stack:** `prometheus-client` (Python) exposes `/metrics` endpoint per process.

**Key metrics:**
- `swarmscout_agent_messages_total{agent, result}` (counter)
- `swarmscout_agent_processing_seconds{agent}` (histogram)
- `swarmscout_llm_calls_total{agent, provider, model, success}` (counter)
- `swarmscout_llm_cost_usd_total{agent, provider, model}` (counter)
- `swarmscout_stream_pending{stream, group}` (gauge, scraped from Redis XPENDING)
- `swarmscout_on_chain_queue_depth` (gauge)

### 6.4 Tracing

**Stack:** OpenTelemetry. Trace context propagated inside the message envelope as `_trace_context` field. Optional OTLP export to a collector.

### 6.5 Security

- **Secrets:** env-only, never in code, pre-commit `detect-secrets` hook
- **Wallet:** testnet-only key, funded via BNB faucet; documented rotation (replacing env var and updating allowlist on contract)
- **Contract allowlist:** configured at deploy time via constructor arg
- **API:** rate-limited per IP; no authentication required for read endpoints; no write endpoints exposed to public
- **TLS:** enforced at nginx layer in production
- **Input validation:** all external inputs (Four.meme events, scraped data, user commands) pass through Pydantic validation before any processing

### 6.6 Error handling philosophy

Three failure categories, each handled distinctly:

1. **Transient infrastructure errors** (Redis blip, PG connection drop, network flake) → retry with exponential backoff; never drop messages; Redis PEL guarantees delivery
2. **External service errors** (LLM 5xx, scraping blocked, RPC down) → fallback chain for LLM; degraded-flag for scraping; queue for chain; **never fake the data**
3. **Programming errors / schema violations** → fail loudly; message goes to dead-letter stream for human review; agent continues on next message

---

## 7. Component lifecycle

### 7.1 Startup sequence (from fresh boot)

```
  1. PostgreSQL starts, waits for healthcheck
  2. Redis starts, waits for healthcheck
  3. All agents start in parallel:
       - connect to Redis + PG
       - register with their consumer group
       - start health heartbeat
       - attempt first LLM probe (to DGrid)
  4. API starts, connects to Redis + PG
  5. Bot starts, connects to Redis + PG + Telegram API
  6. Web (Next.js) starts
```

No inter-agent startup ordering needed: agents are eventually-consistent. If Hunter starts 10 seconds before Social, the first TokenCandidate simply waits in the stream — it's durable.

### 7.2 Graceful shutdown

On SIGTERM:
1. Agent stops reading new messages
2. Agent finishes current in-flight message (including on-chain write)
3. Agent XACKs the processed message
4. Agent writes final heartbeat with status=shutting_down
5. Agent exits

Kubernetes / Docker timeout: 30s. If exceeded, SIGKILL — PEL redelivers the unfinished message to a new consumer after visibility timeout.

### 7.3 Crash recovery

On restart:
1. Agent reads its PEL (`XPENDING`) for its consumer group
2. Any messages older than visibility timeout (60s) are reclaimed (`XCLAIM`)
3. Agent processes them normally
4. Duplicate-detection at the consumer level (checking `messages` table for existing msg_id) prevents double-processing

---

## 8. Scaling model (future, not v1)

v1 runs single-instance per agent. The design supports horizontal scaling without code change:

- **More agent workers per role:** add multiple consumers to the same consumer group; Redis distributes messages
- **Redis scaling:** migrate to Redis Cluster or managed (Upstash, ElastiCache)
- **PG scaling:** read replicas for API; primary for agent writes
- **Contract:** gas cost is per-write; unaffected by agent count
- **DGrid:** stateless; agent count has no bearing

Documented as future work; v1 coverage tests run against single-instance.

---

## 9. Known gaps & deferred work

| Gap | Reason |
|---|---|
| Multi-region deployment | Single VPS is v1; multi-region is post-hackathon |
| Database read replicas | Single PG sufficient; replicas when API traffic warrants |
| Redis Cluster | Single Redis sufficient; cluster when throughput warrants |
| Schema migrations framework (Alembic) | v1 schemas are final for the release; migrations framework is next-iteration hygiene |
| Full OpenTelemetry collector deployment | Instrumentation in place; collector setup post-hackathon |
| Admin UI for subscriptions management | Not in v1 |
| Dedicated `/lineage` API endpoint | UC-07 workable without it in v1 |

---

**End of 06_HLD.md**
