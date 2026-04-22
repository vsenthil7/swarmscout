# 04 — Use Cases Document

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 06:45 UTC

Formal use-case specifications following the actor + preconditions + main flow + alternative flows pattern. Each use case traces back to Functional Requirements (01_Requirements.md) and to Scenarios (03_Scenarios.md). Every alternative flow maps to a test case in 09_TestCases.md.

---

## UC-01 — Subscribe to alpha alerts

**Actor:** Retail trader
**Scope:** Telegram bot
**Trace:** FR-160, FR-161, FR-162 / S-01, S-05
**Priority:** M

**Preconditions:**
- User has a Telegram account
- SwarmScout Telegram bot is running (FR-160)

**Main flow:**
1. User opens the SwarmScout bot in Telegram
2. User sends `/start`
3. Bot replies with welcome message and command list
4. User sends `/subscribe`
5. Bot creates a subscription record in PostgreSQL keyed by `chat_id`, default threshold = `moderate`
6. Bot confirms subscription and states the default threshold

**Postconditions:**
- `subscriptions` table has a row for the `chat_id`
- User will receive all future `AlphaBrief` messages with `conviction_tier` ≥ `moderate`

**Alternative flows:**
- **A1 — User already subscribed:** Bot replies "Already subscribed. Current threshold: {tier}." (no duplicate row)
- **A2 — Database unreachable:** Bot replies "Unable to subscribe right now; please retry." Logs error. User not charged any state.

---

## UC-02 — Receive and read an alpha brief via Telegram

**Actor:** Retail trader
**Scope:** Telegram bot
**Trace:** FR-164, FR-165, FR-186 / S-01, S-06
**Priority:** M

**Preconditions:**
- User is subscribed (UC-01 completed)
- Hunter has detected a new token → Chain + Social have produced outputs → Risk has produced verdict → Narrator has produced brief → brief published on `stream:briefs`

**Main flow:**
1. Bot's consumer (`group:telegram`) reads new `AlphaBrief` message
2. Bot queries `subscriptions` table for users whose threshold ≤ brief's `conviction_tier`
3. For each such user, bot checks Redis dedup SET for `(chat_id, msg_id)`; if present, skip
4. Bot formats the message (FR-164): token + BscScan link, conviction emoji + tier, thesis, red flags, model attribution, verify link
5. Bot sends message via Telegram API
6. Bot writes `(chat_id, msg_id)` to Redis dedup SET with 48h TTL
7. Bot `XACK`s the message on `group:telegram`

**Postconditions:**
- User has received the brief in their Telegram
- Dedup record exists in Redis
- Message acknowledged on the consumer group

**Alternative flows:**
- **A1 — User's threshold higher than brief's tier:** Skip this user
- **A2 — Dedup hit (retry scenario):** Skip send, XACK anyway (no double-send)
- **A3 — Telegram API rate-limit (429):** Back off per Telegram's `retry_after` header; do NOT XACK; message redelivered on next cycle
- **A4 — Brief has `confidence_tier: degraded`:** Include caveat line "⚠ Partial data — confidence reduced" per S-10
- **A5 — Brief has `conviction_tier: degen` AND user threshold < `degen`:** Skip silently (S-06)

---

## UC-03 — Query the public JSON API for recent briefs

**Actor:** Algo trader / power user
**Scope:** FastAPI public API
**Trace:** FR-200, FR-201, FR-202, FR-203 / S-02
**Priority:** M

**Preconditions:**
- API is running at `api.swarmscout.xyz`
- Caller has not exceeded 60 req/min

**Main flow:**
1. Caller issues `GET /briefs?since=30m&limit=50`
2. API validates query params against Pydantic schema
3. API checks rate-limit counter in Redis (`rate:api:{client_ip}`)
4. API queries PostgreSQL for briefs where `created_at > now() - 30m`, ordered DESC, limit 50
5. API serialises result to the `BriefListResponse` Pydantic model
6. API returns 200 with JSON body + `X-RateLimit-Remaining` header

**Postconditions:**
- Caller has the most recent 50 briefs from the last 30 minutes
- Rate-limit counter incremented

**Alternative flows:**
- **A1 — Rate limit exceeded:** 429 with `Retry-After` header
- **A2 — Invalid query parameters:** 422 with Pydantic error detail
- **A3 — Database unavailable:** 503 with generic error (no internal detail leaked)

---

## UC-04 — Retrieve a single brief by msg_id

**Actor:** Algo trader / power user / any user via `/verify`
**Scope:** FastAPI public API
**Trace:** FR-201 / S-02, S-03
**Priority:** M

**Preconditions:**
- Brief with given `msg_id` has been produced

**Main flow:**
1. Caller issues `GET /briefs/{msg_id}`
2. API validates `msg_id` format (ULID)
3. API queries PostgreSQL for row with matching `msg_id`
4. API returns 200 with full `AlphaBrief` + envelope metadata

**Alternative flows:**
- **A1 — msg_id not found:** 404
- **A2 — msg_id malformed:** 422

---

## UC-05 — Verify a brief on-chain

**Actor:** Any user
**Scope:** FastAPI public API + Telegram bot + Next.js dashboard
**Trace:** FR-124, FR-163, FR-186, NFR-261 / S-03, S-08
**Priority:** M

**Preconditions:**
- Brief has been published with a hash recorded on-chain

**Main flow:**
1. User requests verification via one of:
   - Telegram: `/verify 01HXXXXXXXXX`
   - API: `GET /briefs/01HXXXXXXXXX/verify`
   - Dashboard: click "Verify on BscScan ↗" button
2. System fetches the brief from PostgreSQL
3. System computes SHA-256 of the brief's canonical payload
4. System calls `FindingsRegistry.verifyFinding(msg_id)` on BNB Testnet via web3.py
5. System compares returned on-chain hash with re-computed hash
6. System returns: `{msg_id, payload_hash, on_chain_hash, matches: bool, bscscan_url, block_number, timestamp}`

**Postconditions:**
- User has cryptographic proof that the brief has not been tampered with since it was recorded

**Alternative flows:**
- **A1 — Hash mismatch:** Return with `matches: false`; log ERROR; the system has been compromised or the brief was modified in the database (this should never happen in normal operation and is itself a security alert)
- **A2 — msg_id not on-chain yet:** If the agent's on-chain write is still pending (queued due to RPC outage per TC-F08), return `{on_chain_status: "pending"}`; user retries later
- **A3 — BNB RPC unreachable:** Return 503; user retries later

---

## UC-06 — View live dashboard

**Actor:** Hackathon judge / curious visitor / retail trader
**Scope:** Next.js dashboard
**Trace:** FR-180, FR-181, FR-182, FR-183, FR-184, FR-185, FR-186, FR-187 / S-04
**Priority:** M

**Preconditions:**
- Dashboard is deployed at `dashboard.swarmscout.xyz`
- Visitor has a browser

**Main flow:**
1. Visitor opens `dashboard.swarmscout.xyz`
2. Next.js SSR renders the initial state (last 20 briefs from PostgreSQL)
3. Client-side JS opens WebSocket to `/api/ws/events`
4. WebSocket handler subscribes to Redis Pub/Sub channels `events:*` and forwards to the client
5. Dashboard displays:
   - **Brief feed** (FR-181, FR-182): paginated, newest-first, with model attribution and verify link
   - **Agent Activity Timeline** (FR-183): rolling log of events from all streams
   - **Model Usage** (FR-184): live chart of calls/hour per (agent, provider)
   - **Swarm Health** (FR-185): per-agent status, last-heartbeat, pending queue depth
6. New events appear without page refresh

**Postconditions:**
- Visitor has a real-time view of the swarm

**Alternative flows:**
- **A1 — WebSocket connection fails:** Fall back to polling `/api/events?since={last_seen_ts}` every 5 seconds; show "live updates paused" indicator
- **A2 — Database unavailable on initial load:** SSR returns a minimal shell; client-side shows "Unable to load feed; retrying…"
- **A3 — Mobile viewport:** Layout reflows; all panels remain functional (FR-187)

---

## UC-07 — Reconstruct full lineage for a brief

**Actor:** Power user / auditor
**Scope:** FastAPI public API
**Trace:** FR-101, NFR-260 / S-03, S-08
**Priority:** S

**Preconditions:**
- Brief with `msg_id` exists
- Full lineage has been persisted in PostgreSQL

**Main flow:**
1. User fetches the brief via UC-04
2. User reads `upstream_ids` from the envelope
3. User fetches each upstream message via repeated UC-04 calls
4. User continues until reaching a message with `upstream_ids: []` (the original `TokenCandidate`)
5. User has the full 5-hop lineage: TokenCandidate → (SocialScore, ChainMetrics) → RiskVerdict → AlphaBrief

**Postconditions:**
- User has reconstructed the complete chain of reasoning
- User can optionally verify each hash on-chain via UC-05

**Alternative flows:**
- **A1 — An upstream message was purged from PostgreSQL (retention policy):** 404 on that fetch; user has partial lineage + on-chain hash proofs for the rest

**Design note:** A dedicated `GET /briefs/{msg_id}/lineage` endpoint would make this a single call. Deferred to post-v1 per S-08.

---

## UC-08 — Integrate with a third-party trading bot

**Actor:** Algo trader
**Scope:** FastAPI public API + on-chain verification
**Trace:** FR-200–FR-204, NFR-261 / S-02
**Priority:** S

**Preconditions:**
- Algo trader has built integration per S-02

**Main flow:**
1. Bot polls `GET /briefs?since={last_poll}&tier=high` every 60s
2. For each returned brief, bot calls `GET /briefs/{msg_id}/verify` (UC-05)
3. Bot applies its own strategy (entry size, venue, etc.)
4. Bot places trade independently of SwarmScout

**Postconditions:**
- Bot has a verified signal
- SwarmScout has zero custody or execution role

**Alternative flows:**
- **A1 — Verify returns `matches: false`:** Bot skips signal; logs security alert
- **A2 — API rate-limited:** Bot reduces poll frequency or authenticates (auth is a post-v1 feature)

---

## UC-09 — Open-chain verification via BscScan directly (no SwarmScout)

**Actor:** Skeptical judge / skeptical user
**Scope:** External (BscScan web UI)
**Trace:** FR-122 (FindingRecorded event), NFR-261 / S-03, S-04
**Priority:** M

**Preconditions:**
- FindingsRegistry contract is deployed and verified on BscScan

**Main flow:**
1. User navigates to `bscscan.com/address/{contract_address}`
2. User clicks "Contract" → "Read Contract"
3. User calls `verifyFinding(msg_id)` with a `msg_id` they have
4. BscScan returns the tuple: `(payloadHash, agent, timestamp)`
5. User independently re-computes SHA-256 of the brief JSON from the SwarmScout API and compares

**Postconditions:**
- User has verified SwarmScout's claim without trusting SwarmScout's code

**Rule trace:** This use case exists explicitly to demonstrate that provenance is **not dependent on SwarmScout's own infrastructure**. If SwarmScout goes offline, BscScan still has every hash.

---

## UC-10 — Check swarm health

**Actor:** Operator / judge / curious visitor
**Scope:** Dashboard + API
**Trace:** FR-185, FR-008 / S-04
**Priority:** S

**Preconditions:**
- Dashboard is accessible

**Main flow:**
1. User views the "Swarm Health" panel on the dashboard
2. Panel shows per-agent: status (green/yellow/red), last heartbeat time, pending queue depth (XPENDING), current primary model
3. User can click any agent for detail view with last 10 heartbeat entries

**Alternative flows:**
- **A1 — Agent shows yellow (degraded):** Indicates agent is alive but running on fallback model (S-07) or has elevated error rate
- **A2 — Agent shows red (down):** No heartbeat in >60s; operator investigates

---

## UC-11 — Change conviction threshold

**Actor:** Retail trader
**Scope:** Telegram bot
**Trace:** FR-161, FR-162 / S-05
**Priority:** M

**Preconditions:**
- User is subscribed (UC-01)

**Main flow:**
1. User sends `/threshold high`
2. Bot validates input against allowed set: `{degen, speculative, moderate, high}`
3. Bot updates `subscriptions` table: `threshold = 'high'` where `chat_id = ...`
4. Bot confirms: "Threshold set to high."

**Alternative flows:**
- **A1 — Invalid tier:** Bot replies with usage message; no change to DB
- **A2 — User not subscribed:** Bot replies "Use /subscribe first."

---

## UC-12 — System rejects a rug-pull candidate (non-alert)

**Actor:** System-facing (no user action)
**Scope:** Full pipeline
**Trace:** FR-066, FR-162, NFR-261 / S-06
**Priority:** M

**Preconditions:**
- A malicious token is launched on Four.meme

**Main flow:**
1. Hunter emits TokenCandidate normally (as for any token)
2. Chain agent's heuristics flag multiple red flags
3. Social agent flags coordinated posting
4. Risk agent synthesises → score <25 → tier `degen`
5. Narrator produces brief with `conviction_tier: degen`
6. Telegram bot does NOT push to any user whose threshold > `degen`
7. Dashboard shows brief in the feed with red-bordered card
8. API returns brief on `GET /briefs`
9. On-chain registry records all hashes (normal provenance)

**Postconditions:**
- Token is recorded, analysed, and publicly visible
- Subscribed users are not spammed with low-conviction noise
- Provable audit trail exists on-chain

---

## UC-13 — LLM provider outage (graceful degradation)

**Actor:** System-facing
**Scope:** LLM router
**Trace:** FR-141, FR-024, FR-043, FR-063, FR-083 / S-07
**Priority:** M

**Preconditions:**
- At least one primary LLM provider becomes unavailable

**Main flow:**
1. LLMRouter detects 3 consecutive 5xx / timeout from primary
2. Circuit breaker opens for that (agent, provider) tuple for 60s
3. Next call uses Fallback 1
4. If Fallback 1 also fails, use Fallback 2
5. Every 60s, a health probe tests the original primary
6. On success, circuit closes, primary resumes

**Alternative flows:**
- **A1 — All 3 providers down for Risk agent:** RiskVerdict emitted with `confidence: null`, `requires_human_review: true`, `score_0_100: null` (FR-064)
- **A2 — All 3 providers down for Narrator:** `HumanReviewRequest` emitted instead of brief (FR-086)
- **A3 — DGrid gateway down but direct providers OK:** Router uses direct provider APIs with per-provider keys (FR-141)

---

## UC-14 — Developer onboards post-hackathon

**Actor:** New engineer
**Scope:** Entire repository
**Trace:** NFR-344, NFR-381 / S-09
**Priority:** S

**Main flow:**
1. Clone repo
2. Read `README.md` → points to `docs/`
3. Run `cp .env.example .env`, fill in API keys
4. Run `docker compose up --build`
5. Run `make test` → 100% coverage reported
6. Read `CONTRIBUTING.md` → understand git-first rule and commit style
7. Make a small change, commit, PR, CI passes, merged

**Postconditions:**
- Engineer is productive on Day 1

---

## UC-15 — Scraping source goes behind anti-bot defences

**Actor:** System-facing
**Scope:** Social agent
**Trace:** FR-027, FR-085 / S-10
**Priority:** M

**Main flow:**
1. Social agent's Playwright scraper raises `ScrapingBlockedError`
2. Agent emits SocialScore with `data_quality: degraded` and all score fields null
3. Hash of degraded output still recorded on-chain
4. Risk agent incorporates missing data into confidence calculation
5. Narrator brief includes "⚠ Social data unavailable" caveat
6. Dashboard brief card shows orange "Partial data" banner
7. Telegram alert includes degraded caveat line

---

## UC-16 — Operator rotates wallet key

**Actor:** Operator (post-hackathon)
**Scope:** Out-of-band (runbook)
**Priority:** C

**Not detailed in v1.** See Known Gaps in 03_Scenarios.md §5.

---

## Use case summary matrix

| ID | Title | Priority | Actor | Scope |
|---|---|---|---|---|
| UC-01 | Subscribe to alerts | M | Retail trader | Telegram |
| UC-02 | Receive + read brief | M | Retail trader | Telegram |
| UC-03 | Query briefs list | M | Algo trader | API |
| UC-04 | Get single brief | M | Any user | API |
| UC-05 | Verify on-chain | M | Any user | API / Telegram / Dashboard |
| UC-06 | View live dashboard | M | Judge / visitor | Dashboard |
| UC-07 | Reconstruct lineage | S | Power user | API |
| UC-08 | Third-party bot integration | S | Algo trader | API |
| UC-09 | Direct BscScan verification | M | Skeptic | External |
| UC-10 | Check swarm health | S | Operator / judge | Dashboard |
| UC-11 | Change threshold | M | Retail trader | Telegram |
| UC-12 | Reject rug-pull (non-alert) | M | System | Pipeline |
| UC-13 | LLM outage degradation | M | System | Router |
| UC-14 | Developer onboarding | S | New engineer | Repo |
| UC-15 | Scraping blocked | M | System | Social agent |
| UC-16 | Operator: wallet rotation | C | Operator | Runbook |

---

## Known gaps & deferred work

| Gap | Reason |
|---|---|
| Authenticated API use cases | Post-v1; v1 is rate-limited anonymous |
| Paid tier use cases | W-05 in Requirements |
| Admin UI use cases | No admin UI in v1 |
| Dedicated `/lineage` endpoint | UC-07 workable with repeated UC-04 calls; dedicated endpoint deferred |

---

**End of 04_UseCases.md**
