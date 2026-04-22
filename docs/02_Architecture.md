# 02 — Architecture Document

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 06:25 UTC
**Rule reference:** Every choice in this document follows rule 2.8 — what, why, alternatives considered, why rejected, trade-offs accepted. The phrase "for demo purposes" does not appear.

---

## 1. Architecture principles

These principles drive every subsequent decision. They are not aspirational — they are gates.

| # | Principle | Consequence |
|---|---|---|
| P1 | **Enterprise-grade over demo-grade.** Every choice defensible for 5-year production lifetime. | No shortcuts disguised as MVP. Deferred risks flagged, not hidden. |
| P2 | **Fault isolation.** Any single agent or provider failure must not stop the swarm. | Process-per-agent, multi-provider fallback, durable bus. |
| P3 | **Auditability over performance.** Every output hashed on-chain before publish. | Small write-latency cost accepted for cryptographic provenance. |
| P4 | **Schema-first, single source of truth.** Pydantic v2 models generate JSON Schema which generates zod. | Zero drift between Python and TypeScript consumers. |
| P5 | **Testability as a first-class constraint.** If a design is hard to get to 100% coverage, redesign it. | Every component has a clean boundary for mock injection. |
| P6 | **No silent degradation.** Partial success explicitly flagged in payload. | Users see `confidence: low` rather than a confident-looking wrong answer. |
| P7 | **Market standard over novel.** Battle-tested tools that future maintainers already know. | Redis Streams over NATS; FastAPI over exotic async frameworks. |

---

## 2. System context (C4 level 1)

```
                         ┌────────────────────────────────────────────────┐
                         │                                                │
                         │                   SwarmScout                   │
                         │   Decentralized Agent Swarm for Four.Meme      │
                         │                   Alpha Discovery              │
                         │                                                │
                         └────────────────────────────────────────────────┘
                            ▲           ▲           ▲           ▲
                            │           │           │           │
              ┌─────────────┘           │           │           └──────────────┐
              │                         │           │                          │
              ▼                         ▼           ▼                          ▼
     ┌────────────────┐       ┌─────────────────┐  ┌──────────────┐   ┌─────────────────┐
     │  Four.meme     │       │ BscScan / BNB   │  │ LLM Providers│   │ BNB Testnet     │
     │  platform      │       │ RPC             │  │ via DGrid    │   │ (FindingsRegistry│
     │ (token events) │       │ (on-chain data) │  │ A / O / G    │   │  contract)      │
     └────────────────┘       └─────────────────┘  └──────────────┘   └─────────────────┘

         ▼                                                                  ▲
     emits                                                                writes hashes
         │                                                                  │
         └─────────────────────────────────── SwarmScout ───────────────────┘
                                                  │
                                                  ▼
              ┌───────────────────┬────────────────────────┬──────────────────┐
              │                   │                        │                  │
              ▼                   ▼                        ▼                  ▼
        ┌──────────┐      ┌──────────────┐         ┌────────────────┐  ┌────────────┐
        │ Retail   │      │ Power user / │         │ Hackathon      │  │ Future     │
        │ trader   │      │ algo trader  │         │ judge          │  │ maintainer │
        │ (Telegram)│     │ (JSON API)   │         │ (dashboard)    │  │ (docs)     │
        └──────────┘      └──────────────┘         └────────────────┘  └────────────┘
```

---

## 3. Component view (C4 level 2)

```
┌─────────────────────────────────── SwarmScout system boundary ───────────────────────────────────┐
│                                                                                                    │
│   Data sources              Agent pipeline                        Delivery surfaces                │
│   ─────────────             ───────────────                       ─────────────────                │
│                                                                                                    │
│   ┌──────────┐     ┌─────────┐   ┌─────────┐                                                       │
│   │ Four.meme│───▶ │ Hunter  │──▶│         │    ┌────────┐                                         │
│   └──────────┘     └─────────┘   │         │───▶│ Risk   │───▶┌──────────┐     ┌──────────────┐   │
│                                  │ Redis   │    └────────┘    │ Narrator │────▶│ stream:briefs│──┐│
│   ┌──────────┐     ┌─────────┐   │ Streams │                  └──────────┘     └──────────────┘  ││
│   │ BscScan  │◀───▶│ Chain   │──▶│ bus     │         ▲                                            ││
│   └──────────┘     └─────────┘   │         │─────────┘                                            ││
│                                  │ +       │                                                      ││
│   ┌──────────┐     ┌─────────┐   │ cache   │                                                      ││
│   │ X /      │◀───▶│ Social  │──▶│ + dedup │                                                      ││
│   │ Telegram │     └─────────┘   └─────────┘                                                      ││
│   └──────────┘                         │                                                          ││
│                                        │                                                          ││
│                                        ▼                                                          ││
│                                  ┌───────────┐        ┌──────────────┐                            ││
│                                  │PostgreSQL │        │ BNB Testnet  │                            ││
│                                  │(full      │        │ FindingsRegis│                            ││
│                                  │ payloads) │        │ try contract │                            ││
│                                  └───────────┘        └──────────────┘                            ││
│                                                                                                   ││
│   LLM routing                                                                                     ││
│   ────────────                                                                                    ││
│   Every agent ──▶ llm_router ──▶ DGrid ──▶ Anthropic / OpenAI / Google                            ││
│                       │                                                                           ││
│                       └──fallback──▶ direct Anthropic / OpenAI / Google APIs                      ││
│                                                                                                   ││
│                                                                                                   ││
│   Delivery                                                                                        ││
│   ────────                                                                                        ││
│                                                                                                   ▼│
│   ┌────────────────┐   ┌────────────────┐   ┌────────────────┐                                    │
│   │ Telegram bot   │   │ Next.js        │   │ FastAPI public │◀── all consume stream:briefs ──────┘
│   │ (aiogram v3)   │   │ dashboard      │   │ JSON API       │
│   └────────────────┘   └────────────────┘   └────────────────┘
│                                                                                                    │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Technology decisions — every choice with justification

Rule 2.8 applied to every row. No choice is "because it's what I know." Each has: primary, alternatives considered, rejection reasons, trade-offs accepted.

### 4.1 Agent runtime language — **Python 3.11**

**What:** All five agents (Hunter, Social, Chain, Risk, Narrator), FastAPI public API, Telegram bot.

**Why:** Market standard for LLM pipelines in 2026. The `anthropic`, `openai`, and `google-genai` SDKs expose richer streaming + tool-use semantics in Python than in Node. `web3.py` is more mature than Node's `web3.js` for custom RPC patterns. Playwright has first-class Python bindings (reused from HACK0014). Pydantic v2 gives us runtime-validated models with JSON-Schema export — the foundation of our schema-first discipline (P4).

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **TypeScript/Node (all-TS stack)** | Loses HACK0014 scraper reuse; Node LLM SDKs lag Python in streaming + tool-use ergonomics; `viem` mature but `web3.py` more battle-tested for custom RPC workflows. |
| **Rust** | Excellent performance but slow to write; LLM SDKs are community-maintained; FFI overhead for Playwright; dev velocity not compatible with 10-hour window. |
| **Go** | Good concurrency story but LLM SDKs thinner; no Pydantic-equivalent for runtime validation; Telegram bot libraries weaker than aiogram. |

**Trade-offs accepted:** Python GIL — mitigated because agents are I/O-bound (Redis, HTTP, LLM) not CPU-bound; asyncio handles concurrency within a single agent process.

### 4.2 Agent framework — **Hand-rolled (asyncio + redis-py + Pydantic)**

**What:** No third-party agent framework. A small internal `agents/common/` library provides: `BaseAgent`, `MessageBus`, `LLMRouter`, `OnChainWriter`, `HealthEmitter`.

**Why:** 100% coverage (rule 2.4) is the binding constraint. Third-party agent frameworks carry heavy internal state machines and event loops that resist line+branch testing. Hand-rolled = we control every line = we can test every line. The framework is ~500 lines of Python, not 50,000.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **LangGraph** | Strong for complex graph-of-agent workflows; internal state machine hard to reach 100% branch coverage in our window; adds dependency weight. |
| **CrewAI** | Role-playing paradigm mismatched to our "pipeline of specialists" model; internals opaque; reduces our control over retry/fallback. |
| **AutoGen (Microsoft)** | Research-oriented, API churns; heavy. |
| **OpenAI Swarm** | Educational, now superseded by Agents SDK; stateless-by-design conflicts with our message-bus durability requirement. |
| **Anthropic's agent SDK** | Claude-specific; multi-provider routing (rule requirement) is against its grain. |

**Trade-offs accepted:** We rebuild some wheels (retry, backoff, circuit breakers). Mitigated by using battle-tested primitives underneath (`tenacity`, `stamina`). Net code volume smaller than integrating + configuring any of the above.

### 4.3 Message bus — **Redis Streams + Redis Pub/Sub**

**What:** Single Redis 7 instance with AOF persistence serves as: agent message bus (Streams), WebSocket fanout for dashboard (Pub/Sub), LLM response cache, per-provider rate-limit token buckets, Telegram message deduplication set.

**Why:** Market-standard for event-driven backends below Kafka scale (Uber, Shopify, Twitter pre-X reference architectures). Consumer groups (`XREADGROUP`, `XACK`, PEL) give at-least-once delivery with automatic redelivery on crash. A single binary serves 5 distinct jobs — reduces infra surface area and test matrix.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Apache Kafka / Redpanda** | Correct at 10k+ msg/s; we're 100-1000× below that threshold. KRaft setup + topic management + schema registry eats hours of engineering time. Testcontainers-Kafka slow in CI; hurts 100% coverage timing. Noted as v2 migration candidate if SwarmScout scales past hackathon. |
| **NATS JetStream** | Technically sound, great pull-consumer model; adds a second infra component since Redis still needed for cache and rate-limits. Net: more moving parts, same capability. |
| **RabbitMQ** | Heavier ops, no replay-by-range (XREVRANGE), AMQP mental overhead. Better for complex routing topologies we don't have. |
| **Direct HTTP/gRPC between agents** | Synchronous coupling — if Risk is down, Chain's message is lost. Fails durability (P2). Fails auditability — no shared log to hash onto chain. |
| **PostgreSQL as queue** (`LISTEN/NOTIFY` or polled table) | LISTEN/NOTIFY doesn't persist to disconnected subscribers. Polled queue caps throughput and creates DB contention. Couples bus lifetime to DB — single failure point. |
| **In-process asyncio queues** | Single process = single failure domain. One crash kills the swarm. Dashboard/bot (separate processes) can't subscribe. Fails P2. |
| **Vertex (P2P coordination, from HACK0014)** | Vertex is purpose-built for peer-to-peer coordination of robots/drones/AMRs in degraded-network environments — brilliant in its domain. For a cloud-hosted agent swarm in a single Docker network, P2P provides zero benefit and adds: C/Rust bindings for Python agents requiring unvalidated FFI, unproven test tooling at 100% line+branch, integration risk that fails rule 2.4. Migration candidate for v2 if SwarmScout graduates to edge deployment (on-device trader bots). |

**Trade-offs accepted:** Redis single-instance is a hot SPOF. Mitigated with AOF persistence + bind-mounted volume + documented restore procedure. In production, replace with Redis Sentinel or managed Redis (ElastiCache, Upstash).

### 4.4 LLM routing — **DGrid AI Gateway with multi-provider, per-agent specialisation**

**What:** All LLM calls go through DGrid (`https://api.dgrid.ai/v1`, OpenAI-compatible). Per-agent model assignment with documented fallback chains. Direct-provider keys (Anthropic, OpenAI, Google) serve as fallback if DGrid is unreachable.

| Agent | Primary | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Hunter | `google/gemini-2.5-flash` | `anthropic/claude-haiku-4-5` | `openai/gpt-4o-mini` |
| Social | `openai/gpt-4o` | `anthropic/claude-sonnet-4-6` | `google/gemini-2.5-pro` |
| Chain | `anthropic/claude-sonnet-4-6` | `openai/gpt-4o` | `google/gemini-2.5-pro` |
| Risk | `anthropic/claude-opus-4-7` | `openai/gpt-4o` (reasoning) | `google/gemini-2.5-pro` |
| Narrator | `anthropic/claude-opus-4-7` | `openai/gpt-4o` | `google/gemini-2.5-pro` |

**Why:**

1. **Provider resilience (P2).** Single-provider outages happened to OpenAI, Anthropic, and Google multiple times in 2024–2026. Single-provider dependency violates enterprise SLO.
2. **Model-fitness matching.** No frontier model dominates across all tasks. Gemini Flash is fastest + cheapest for structured extraction; GPT-4o has widest social-media training data; Opus 4.7 has best reasoning for risk synthesis and prose composition.
3. **Cost envelope.** Hunter fires ~100× more calls than Risk. Running Hunter on Opus would burn bounty credits in hours. Running Risk on Haiku would compromise the riskiest inference. Model-per-agent is cost-optimal equilibrium.
4. **Bounty optimisation.** DGrid bounty ($3k) rewards genuine gateway usage; multi-provider routing is the strongest submission shape.
5. **Judging alignment.** "Technical Implementation 30%" and "Innovation 30%" reward non-trivial engineering; per-agent model fitness is exactly that.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Single provider (Claude everywhere)** | Fails provider resilience; fails bounty; "because we're on Claude" is not a defensible justification under rule 2.8. |
| **DGrid only, no direct fallback** | DGrid outage = entire system down. Enterprise SLO failure. |
| **OpenRouter instead of DGrid** | Strong alternative but loses the $3k bounty; DGrid is the hackathon-sponsored gateway. |
| **Per-call dynamic routing (pick best model at runtime)** | Dynamic routing adds 100-300ms overhead per call, complicates cost prediction, and is hard to test deterministically. Static per-agent assignment is predictable, testable, and already fits the task shape. |

**Trade-offs accepted:** Static assignment means we don't capitalise on real-time model availability changes. Mitigated by fallback chains — if primary is rate-limited or down, chain kicks in within one retry cycle.

### 4.5 Persistence — **PostgreSQL 16** (full payloads) + **Redis** (hot state) + **BNB Testnet** (hashes)

**What:** Three-tier storage.

- **PostgreSQL 16:** full agent-output payloads, LLM call logs (prompt, response, token counts, cost), subscription records (Telegram chat_id + threshold), health-check history.
- **Redis:** active stream messages, cache entries, rate-limit counters, dedup sets, health heartbeats.
- **BNB Testnet FindingsRegistry contract:** `(msg_id, payload_hash, agent, timestamp)` tuples for every agent output — immutable cryptographic pointer into the PostgreSQL payload.

**Why three tiers:** each has a different cost/durability/access profile.

- PostgreSQL is $cheap per GB, durable, queryable for analytics and lineage reconstruction.
- Redis is fast for hot read/write, ephemeral by contract (AOF is backup, not source of truth).
- On-chain is $expensive per write but gives cryptographic provenance that no database can match.

Storing only hashes on-chain (not full payloads) is the standard pattern for on-chain provenance. Full payloads on-chain would cost 1000× more gas for zero security gain.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **All in Redis** | Ephemeral; lineage queries impractical; no SQL for analytics. |
| **All in Postgres (no Redis)** | Streams-as-queue via polled table caps throughput and contends with DB. |
| **Full payloads on-chain** | Gas cost scales with bytes — storing 2KB per finding on every new token would cost $$$ even on testnet; mainnet infeasible. |
| **MongoDB** | No ACID guarantees for our lineage reconstruction; no enterprise necessity here. |
| **ClickHouse** | Excellent for analytics but overkill; adds second DB; 100% coverage on Python analytics layer cheaper than learning ClickHouse SQL dialect. |

**Trade-offs accepted:** Three-tier means three backup/restore procedures. Mitigated by on-chain hashes being the ultimate integrity reference — if both DBs are lost, we can still verify any historical finding whose hash is still reachable on BscScan.

### 4.6 Smart contract language — **Solidity 0.8.24** on **BNB Testnet**

**What:** `FindingsRegistry.sol` on BNB Testnet (chain ID 97).

**Why:**

1. **BNB Chain alignment.** Four.meme runs on BNB Chain; findings about Four.meme tokens belong in BNB's provenance layer. Testnet (not mainnet) because mainnet deployment requires audit — out of scope this release.
2. **Solidity 0.8.24.** Default safe-math, modern features, wide tool support. EVM compatibility keeps post-hackathon migration options open (Ethereum L2s, Polygon, etc.).

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Vyper** | Security advantages but smaller tooling ecosystem; Foundry support thinner; team switching cost not justified. |
| **Deploy on Ethereum Sepolia** | Wrong chain for Four.meme-themed project; BNB alignment is intentional. |
| **Layer 2 (Optimism/Arbitrum testnet)** | No Four.meme context; breaks narrative. |

**Trade-offs accepted:** BNB Testnet has occasional instability. Mitigated by on-chain writes being deferred-but-eventually-durable — if chain is congested, we queue the hash write and retry (finding still flows downstream, verification link arrives within minutes).

### 4.7 Contract tooling — **Foundry**

**What:** `forge build`, `forge test`, `forge coverage`, `forge script` for everything contract-related.

**Why:**

1. Market-standard for new Solidity projects since 2023.
2. `forge coverage` gives line+branch coverage in one command with lcov output — integrates with our CI coverage gate (NFR-322).
3. ~10-50× faster tests than Hardhat — matters when CI runs on every commit (rule 2.2).
4. Native Solidity tests (`.t.sol`) faster to write than Hardhat's JS bridge.
5. Built-in fuzz testing + invariant testing — essential for a registry contract that third parties will verify against.
6. `forge script` deployments are reproducible and committable as text.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Hardhat** | Slower test runs; `solidity-coverage` plugin has known branch-coverage gaps; JS bridge adds mental overhead. |
| **Truffle** | Deprecated; Consensys sunset. |
| **Remix** | IDE-only, not for CI-gated projects. |

**Trade-offs accepted:** Solidity-native test style requires engineers who read Solidity. Mitigated — we have exactly one contract, ~100 lines.

### 4.8 Public API — **FastAPI**

**What:** `GET /briefs`, `GET /briefs/{msg_id}`, `GET /briefs/{msg_id}/verify`, `GET /health`, `GET /metrics`.

**Why:**

1. Same repo and language as agents — Pydantic models shared directly, zero schema duplication.
2. OpenAPI 3.1 auto-generated from Pydantic → JSON Schema for TypeScript consumers.
3. async-native; handles WebSocket upgrades for dashboard tail.
4. Testing via `httpx.AsyncClient` gives full-path coverage including middleware.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Flask** | Sync-first; no native async; weaker OpenAPI story. |
| **Litestar (Starlite)** | Excellent alternative; smaller community, worse tooling integration. |
| **Django REST** | Heavyweight; ORM we don't need (using SQLAlchemy directly). |
| **tRPC in Node** | Requires TypeScript backend; ruled out in §4.1. |

**Trade-offs accepted:** None material.

### 4.9 Telegram bot — **aiogram v3**

**What:** Commands: `/start`, `/subscribe`, `/unsubscribe`, `/threshold`, `/status`, `/help`, `/verify`. Consumes `stream:briefs`, pushes to chat_ids.

**Why:** Market-standard for Python Telegram bots in 2026. Async-native, integrates with asyncio and Redis consumer groups cleanly. Router-based design makes command handlers independently testable to 100% coverage.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **python-telegram-bot (v20+)** | Solid but heavier API; aiogram's filter system cleaner for our command set. |
| **grammy (TypeScript)** | Requires TypeScript backend. |
| **Telethon** | User-account library, not bot-first; overkill. |

**Trade-offs accepted:** aiogram v3 broke API from v2; mitigated by starting fresh on v3.

### 4.10 Dashboard — **Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui**

**What:** Server components for static pages, client components with WebSocket hook for the live Agent Activity Timeline.

**Why:**

1. Market-standard for modern React SSR in 2026.
2. Tailwind + shadcn/ui is the default in hackathon-grade UIs; components are copy-paste-own-the-code (no opaque dependency), which keeps us in 100% coverage control.
3. API routes in the same project let us tail Redis directly via `ioredis` without a separate backend.
4. TypeScript + zod schemas (generated from Pydantic) give compile-time and runtime safety on the wire.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Vite + React (no framework)** | Loses SSR, API routes, and routing conventions — would need to add each manually. |
| **Remix** | Good framework; smaller community; fewer shadcn/ui examples. |
| **SvelteKit** | Excellent; team-switching cost; less hackathon-judge familiarity. |
| **Plain HTML + vanilla JS** | No type safety; no component reuse; 100% coverage harder. |

**Trade-offs accepted:** Next.js App Router complexity. Mitigated by minimal route tree (3-4 routes).

### 4.11 Shared schema discipline — **Pydantic v2 → JSON Schema → zod**

**What:** All cross-process message schemas defined once in Python (`agents/common/schemas/`). Exported to JSON Schema on every CI run. Converted to zod schemas for TypeScript consumption. CI fails if the exported JSON Schema differs from the committed copy.

**Why:** Single source of truth (P4). Eliminates drift between Python publishers and TypeScript consumers. Type-safe on both sides.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Protobuf** | Overkill; requires compilation step in both languages; not human-readable; hackathon-judge-unfriendly in repo. |
| **JSON Schema first, code generated both sides** | More ceremony; Pydantic-first is faster and Pydantic validation is richer than JSON Schema validators. |
| **Hand-written schemas on both sides** | Drift guaranteed over time. |
| **OpenAPI only (no zod)** | Runtime validation on client weaker; zod catches malformed data at the WebSocket boundary. |

**Trade-offs accepted:** Build-time schema export step. Mitigated by committing the exported schemas — CI diff catches drift cheaply.

### 4.12 Testing stack

| Layer | Tool | Coverage target | Why this tool |
|---|---|---|---|
| Python unit + integration | **pytest + pytest-asyncio + pytest-cov** | 100% line + 100% branch | Industry standard; `--cov-branch --cov-fail-under=100` is a hard CI gate. |
| TypeScript unit + component | **Vitest + @vitest/coverage-v8** | 100% lines, branches, functions, statements | Fast (Vite-native); Jest-compatible API; better ES modules support than Jest. |
| E2E (web + bot simulation) | **Playwright** | All user flows from 05_UserFlow.md | Cross-browser; reuses HACK0014 stealth patterns; first-class TypeScript + Python bindings. |
| Solidity | **Foundry** (`forge test`, `forge coverage`, fuzz, invariant) | 100% line + branch | §4.7 reasoning. |
| HTTP mocking (Python) | **respx** | n/a | HTTPX-native; records and replays provider responses for deterministic LLM tests. |
| HTTP mocking (TypeScript) | **MSW (Mock Service Worker)** | n/a | Standard for Next.js tests; intercepts at fetch layer. |
| Test fixtures | **factory-boy (Py), @faker-js/faker (TS)** | n/a | Deterministic test data. |

**CI orchestrator:** GitHub Actions. Matrix: `python-3.11 × os-ubuntu-latest`, `node-20 × os-ubuntu-latest`, `foundry-stable`. Every job must pass; any coverage drop = build fail.

### 4.13 Orchestration — **Docker Compose** (dev) + **single VPS** (demo deploy)

**What:** `docker-compose.yml` at repo root spins up: Redis, PostgreSQL, 5 agent containers, FastAPI, aiogram bot, Next.js dashboard. All with pinned tags.

**Production demo:** single VPS running the same `docker compose up -d`. Nginx reverse proxy with Let's Encrypt TLS in front of dashboard + API. GitHub Actions deploys on tag push via SSH.

**Why not Kubernetes:** rule 2.1 — enterprise-grade means right-sized, not maximalist. For 5-10 processes running on a single node, k8s is operational overhead without benefit. Post-hackathon migration to k8s is a documented path.

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Kubernetes (k3s or minikube)** | Operational overhead not justified at this scale. Migration path documented. |
| **Docker Swarm** | Deprecated-adjacent; k8s is the migration target if we scale. |
| **Bare processes with systemd** | No build-reproducibility of environment; slower onboarding. |
| **Serverless (Lambda/Cloud Run)** | Persistent Redis and stateful agents don't fit; cold starts hurt latency. |

**Trade-offs accepted:** Single VPS is SPOF. Mitigated by documenting HA migration (Redis Sentinel, PG replication, multi-node k8s) as post-hackathon work.

### 4.14 Observability — **structlog + Prometheus + OpenTelemetry**

**What:** Every agent uses `structlog` for JSON logs to stdout. Prometheus `/metrics` endpoint per agent + router. OpenTelemetry trace context in every message envelope; OTLP export optional.

**Why:** Market-standard observability triad. Works with any log aggregator (Loki, Datadog, CloudWatch) and any metrics backend (Prometheus, Grafana Cloud, Datadog).

**Alternatives considered:**

| Alternative | Rejection reason |
|---|---|
| **Plain logging module** | No structured output; harder to aggregate. |
| **Datadog-only** | Vendor lock-in; cost ladder; open standards preferred. |
| **Loguru** | Pleasant ergonomics; less enterprise-adopted than structlog. |

**Trade-offs accepted:** None material.

---

## 5. Data flow — the happy path

```
  t=0s     Four.meme emits new-token event for token 0xABC
           │
  t=1s     Hunter polls (or receives webhook), validates event
           │
  t=2s     Hunter → LLM router → Gemini Flash → parses + normalises
           │
  t=3s     Hunter computes SHA-256(payload) = 0xH1
           │
  t=4s     Hunter → BNB Testnet FindingsRegistry.recordFinding(msg_id_1, 0xH1, "hunter")
           │                                     │
  t=6s     │                                     └─▶ tx confirmed in block N
           ▼
  t=6s     Hunter XADD stream:candidates <envelope w/ payload, hash, model_used, upstream_ids=[]>
           │                                       │
  t=6s     Hunter also writes full payload to PostgreSQL(msg_id_1, payload)
           │
  t=6s     Hunter XACK on upstream (if applicable) and logs heartbeat
           │
           ├────────────┬─────────────────────────────────────────────────────┐
           ▼            ▼                                                     ▼
  Social group         Chain group                                    Dashboard group (tail)
  t=6.1s reads         t=6.1s reads                                   t=6.1s displays event
           │            │
  t=35s Social done    t=25s Chain done
  hash=0xH2 on-chain   hash=0xH3 on-chain
  stream:social        stream:chain
           │            │
           └───┬────────┘
               │ Risk group reads both (joins on shared upstream_ids = [msg_id_1])
               ▼
  t=95s  Risk done (Opus 4.7), hash=0xH4 on-chain, stream:risk published
               │
               ▼
  t=140s Narrator (Opus 4.7), fetches full lineage from PG, hash=0xH5 on-chain
         stream:briefs published
               │
               ├───────────────┬────────────────────────┐
               ▼               ▼                        ▼
       Telegram group    Dashboard group         API-cache group
       t=140s pushes     t=140s WebSocket        t=140s warms brief cache
       briefs to subs    tick to UI
```

P95 end-to-end budget: **≤ 300s (5 min)** per NFR-200.

---

## 6. Failure modes and mitigations

Every component failure mode analysed. This is the input to test cases.

| Failure | Detection | Mitigation | Test case |
|---|---|---|---|
| Four.meme unreachable | HTTP timeout / 5xx | Hunter exponential backoff (1s→16s, 5 attempts), then sleep 60s, retry | TC-F01 |
| Single LLM provider down | `respx` replay or live 5xx | `llm_router` falls back to next in chain | TC-F02–TC-F04 |
| All LLM providers down | All 3 fail | Risk agent emits `requires_human_review: true`; Narrator emits `HumanReviewRequest` instead of brief | TC-F05 |
| Redis crashes | Client connection error | AOF replay on restart; consumer-group state preserved; in-flight messages redelivered after visibility timeout | TC-F06 |
| PostgreSQL crashes | Client connection error | Agents queue writes in Redis with TTL; on PG return, drain queue; brief generation pauses (can't fetch lineage) | TC-F07 |
| BNB RPC unreachable | web3.py timeout | Queue hash-write in Redis; agents continue publishing downstream with `on_chain_status: pending`; retry loop drains queue when RPC returns | TC-F08 |
| Agent wallet out of gas | Insufficient funds error | Alert via log + health endpoint; auto-refund from faucet via scheduled script; pause hash-writes (not pipeline) | TC-F09 |
| Consumer group stuck (one message blocking pending list) | `XPENDING` > threshold | Move message to `stream:dead_letter`, XACK original, alert | TC-F10 |
| Dashboard WebSocket disconnect | Client-side detect | Reconnect with exponential backoff; replay last 100 events from `XREVRANGE` on reconnect | TC-F11 |
| Schema drift (Pydantic changed, zod not regenerated) | CI diff check | Build fails — can't merge | TC-F12 |
| Telegram bot rate-limited by Telegram | 429 response | aiogram built-in rate-limiter + Redis dedup ensures no double-send on retry | TC-F13 |
| Scraping target (X, Telegram) updates anti-bot | Playwright timeout or 403 | Social emits degraded `SocialScore` with `data_quality: degraded` (FR-027) | TC-F14 |
| DGrid gateway down | 5xx or timeout | Direct-provider API fallback (FR-141) | TC-F15 |
| Duplicate new-token event from Four.meme | Hash-based dedup in Hunter (FR-004) | Message dropped silently, logged | TC-F16 |
| Honeypot token passes all checks | Static heuristic catches it | FR-046 eth_call simulation flags it; added to `red_flags` before Risk | TC-F17 |

---

## 7. Deployment topology

### 7.1 Development (local)

```
Developer laptop
├─ docker-compose.yml
│  ├─ redis:7-alpine              (port 6379)
│  ├─ postgres:16-alpine          (port 5432)
│  ├─ hunter                      (python:3.11, agents/hunter/Dockerfile)
│  ├─ social                      (python:3.11, agents/social/Dockerfile)
│  ├─ chain                       (python:3.11, agents/chain/Dockerfile)
│  ├─ risk                        (python:3.11, agents/risk/Dockerfile)
│  ├─ narrator                    (python:3.11, agents/narrator/Dockerfile)
│  ├─ api                         (python:3.11, api/Dockerfile)         → :8000
│  ├─ bot                         (python:3.11, bot/Dockerfile)
│  └─ web                         (node:20-alpine, web/Dockerfile)      → :3000
└─ .env                           (gitignored; secrets)
```

Single command: `docker compose up --build`.

### 7.2 Production demo (single VPS)

```
VPS (e.g. Hetzner CX21, 2vCPU / 4GB RAM, €4/mo)
├─ nginx (reverse proxy, Let's Encrypt TLS)
│  ├─ dashboard.swarmscout.xyz → web:3000
│  └─ api.swarmscout.xyz       → api:8000
├─ docker compose (same file as dev, different .env)
└─ systemd unit ensures docker compose up on reboot
```

GitHub Actions deploys on `git push --tags` via SSH:

```yaml
- uses: appleboy/ssh-action@master
  with:
    host: ${{ secrets.VPS_HOST }}
    username: deploy
    key: ${{ secrets.VPS_SSH_KEY }}
    script: |
      cd /opt/swarmscout
      git fetch --tags && git checkout ${{ github.ref_name }}
      docker compose pull && docker compose up -d
```

### 7.3 Secrets management

- Local: `.env` file, gitignored, example at `.env.example`
- Production: VPS-level `.env` file, mode 600, owned by deploy user
- Pre-commit hook runs `detect-secrets` to block accidental commits
- Wallet private key is a funded-testnet-only key; documented rotation procedure

---

## 8. Repository structure

```
HACK0015-SwarmScout/
├── README.md                          # project overview, quickstart
├── ARCHITECTURE.md                    # points to docs/02_Architecture.md
├── CONTRIBUTING.md                    # git rules, commit style, test coverage
├── .gitignore
├── .env.example
├── docker-compose.yml
├── docker-compose.override.yml        # dev-only overrides (exposed ports, etc.)
├── Makefile                           # common commands: test, cov, lint, deploy
├── pyproject.toml                     # Python project + pytest + coverage + ruff + mypy config
├── pnpm-workspace.yaml                # TS monorepo config
├── package.json                       # root scripts
│
├── docs/                              # all 9 artefacts live here
│   ├── 01_Requirements.md
│   ├── 02_Architecture.md
│   ├── 03_Scenarios.md
│   ├── 04_UseCases.md
│   ├── 05_UserFlow.md
│   ├── 06_HLD.md
│   ├── 07_LLD.md
│   ├── 08_TestPlan.md
│   ├── 09_TestCases.md
│   └── BUILD_SESSION_PROMPT.md
│
├── contracts/
│   ├── foundry.toml
│   ├── src/
│   │   └── FindingsRegistry.sol
│   ├── test/
│   │   ├── FindingsRegistry.t.sol     # unit + branch
│   │   ├── FindingsRegistry.fuzz.t.sol
│   │   └── FindingsRegistry.invariant.t.sol
│   └── script/
│       └── Deploy.s.sol
│
├── agents/
│   ├── __init__.py
│   ├── common/
│   │   ├── base_agent.py
│   │   ├── bus.py                     # Redis Streams wrapper
│   │   ├── llm_router.py              # DGrid + fallback chains
│   │   ├── on_chain.py                # web3.py writer
│   │   ├── hasher.py                  # SHA-256 envelope hasher
│   │   ├── health.py                  # heartbeat emitter
│   │   ├── metrics.py                 # Prometheus
│   │   ├── db.py                      # SQLAlchemy async session
│   │   └── schemas/
│   │       ├── envelope.py
│   │       ├── token_candidate.py
│   │       ├── social_score.py
│   │       ├── chain_metrics.py
│   │       ├── risk_verdict.py
│   │       └── alpha_brief.py
│   ├── hunter/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── sources/                   # Four.meme client(s)
│   │   └── Dockerfile
│   ├── social/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── scrapers/                  # X, Telegram (reuse HACK0014 stealth)
│   │   └── Dockerfile
│   ├── chain/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── analytics/                 # holders, LP, velocity, honeypot sim
│   │   └── Dockerfile
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── heuristics.py              # 15 deterministic rules
│   │   └── Dockerfile
│   ├── narrator/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── Dockerfile
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── conftest.py                # pytest fixtures (Redis/PG testcontainers)
│
├── api/
│   ├── main.py                        # FastAPI app
│   ├── routes/
│   ├── Dockerfile
│   └── tests/
│
├── bot/
│   ├── main.py                        # aiogram v3 app
│   ├── handlers/
│   ├── Dockerfile
│   └── tests/
│
├── web/
│   ├── package.json
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   ├── app/                           # Next.js 14 App Router
│   ├── components/
│   ├── lib/
│   │   ├── schemas/                   # zod, generated from Pydantic JSON Schema
│   │   └── ws.ts                      # WebSocket client
│   ├── tests/                         # Vitest unit + component
│   ├── e2e/                           # Playwright
│   └── Dockerfile
│
├── scripts/
│   ├── export_schemas.py              # Pydantic → JSON Schema export
│   ├── generate_zod.ts                # JSON Schema → zod
│   ├── deploy_contract.sh
│   ├── seed_testnet_wallet.sh         # BNB faucet request
│   ├── record_demo_video.sh           # Playwright-based demo recorder
│   └── smoke_test.sh
│
└── .github/
    └── workflows/
        ├── ci.yml                     # lint + type + test + coverage gate
        ├── contract.yml               # forge test + coverage
        ├── e2e.yml                    # Playwright full pipeline run
        └── deploy.yml                 # tag-push → VPS deploy
```

---

## 9. Non-functional architecture summary

| NFR | Architectural enabler |
|---|---|
| NFR-200 (E2E ≤ 5min) | Per-agent latency budgets; parallel Social+Chain; async I/O throughout |
| NFR-220 (fault isolation) | Separate process per agent; durable bus; per-provider fallback |
| NFR-222 (no message loss) | Redis Streams consumer groups + PEL + AOF persistence |
| NFR-223 (LLM all-down recoverability) | Router queues retries; RiskVerdict.requires_human_review path |
| NFR-240 (secrets in env) | `.env` pattern + detect-secrets hook |
| NFR-260 (full lineage) | upstream_ids in envelope + PostgreSQL lookup by msg_id |
| NFR-261 (hash verifiability) | On-chain registry + BscScan event index |
| NFR-320–322 (100% coverage) | Testing stack §4.12 + CI gate §7.3 |
| NFR-326 (CI on every commit) | GitHub Actions workflow §7.2 |

---

## 10. Known gaps & deferred work

| Gap | Why deferred | Planned resolution |
|---|---|---|
| Redis HA (Sentinel or managed) | Single-instance is adequate for 5-10 concurrent producers/consumers; HA adds deployment complexity | Post-hackathon: managed Redis (Upstash or ElastiCache) |
| PostgreSQL replication | Same reasoning | Post-hackathon: managed PG (Neon, Supabase, or RDS) |
| Grafana dashboard | Observability above baseline | Post-hackathon: Prometheus + Grafana Cloud |
| Contract audit | Mainnet requires audit; testnet does not | Before any mainnet deployment |
| Rate-limit tuning | Values are educated guesses; will be tuned in staging | Load test in next phase |
| Four.meme event-source concrete adapter | A-01 assumption; will be validated in LLD phase by hitting the actual endpoint | `07_LLD.md` §Hunter adapter |
| "Fox" from handoff prompt | User delegated; no clear mapping to architecture | Noted and dropped unless re-raised |
| Horizontal scale (multiple workers per agent role) | W-10; consumer groups support it but v1 runs single worker | Smoke-tested in v1 with 2 workers on one agent, not productionised |

---

**End of 02_Architecture.md**
