# 05 — User Flow Document

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 06:55 UTC

Screen-by-screen and interaction-by-interaction flows for every user-facing path. Each flow traces to use cases in 04_UseCases.md and maps to E2E test cases in 09_TestCases.md (enforcing NFR-324).

---

## UF-01 — First-time Telegram subscription

**Traces to:** UC-01, UC-11 / S-05

```
┌─────────────────────────────────────────────────────────────────────┐
│ User clicks "Start Bot" link on swarmscout.xyz                       │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Telegram opens chat with @SwarmScoutBot                              │
│ Chat is empty; "Start" button at bottom                              │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼  [User taps Start]
┌─────────────────────────────────────────────────────────────────────┐
│ Bot: /start                                                          │
│ Bot replies:                                                         │
│                                                                       │
│   👋 Welcome to SwarmScout.                                           │
│                                                                       │
│   I push cryptographically-verified alpha alerts about new           │
│   Four.meme token launches. Every alert I send is                     │
│   recorded on BNB Testnet — you can verify each one                  │
│   independently.                                                      │
│                                                                       │
│   Commands:                                                           │
│     /subscribe           Start receiving alerts                      │
│     /threshold <tier>    Set minimum conviction                       │
│                          (degen | speculative | moderate | high)     │
│     /status              See your settings                            │
│     /verify <msg_id>     Look up on-chain proof                       │
│     /unsubscribe         Stop alerts                                  │
│     /help                Show this message                            │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼  [User sends /subscribe]
┌─────────────────────────────────────────────────────────────────────┐
│ Bot inserts into subscriptions table:                                │
│   (chat_id, threshold='moderate', subscribed_at=now())               │
│                                                                       │
│ Bot replies:                                                          │
│   ✅ Subscribed.                                                      │
│   Default threshold: moderate                                         │
│   You'll receive alerts for moderate and high conviction             │
│   (~5-15 alerts per day on typical activity).                         │
│                                                                       │
│   Change with /threshold <tier>                                       │
└─────────────────────────────────────────────────────────────────────┘
                             │
           ┌─────────────────┼──────────────────┐
           │                 │                  │
  [optional]        [optional]         [done — wait for alerts]
           │                 │
           ▼                 ▼
/threshold high     /status
           │                 │
           ▼                 ▼
┌──────────────────┐  ┌────────────────────────────────┐
│ Bot validates,   │  │ Bot replies:                    │
│ updates DB,      │  │   chat_id: 1234567890           │
│ replies:         │  │   subscribed: yes               │
│                  │  │   threshold: moderate           │
│   Threshold set  │  │   alerts received (7d): 0       │
│   to high.       │  │   first_alert_expected: ~24h    │
└──────────────────┘  └────────────────────────────────┘
```

**Error paths:**
- `/threshold junk` → Bot: "Invalid tier. Use: degen, speculative, moderate, or high."
- DB unreachable during `/subscribe` → Bot: "Unable to subscribe right now; please retry."

**E2E test:** TC-E01

---

## UF-02 — Receiving an alert in Telegram

**Traces to:** UC-02, UC-05 / S-01

```
┌─────────────────────────────────────────────────────────────────────┐
│ Push notification appears on user's phone                            │
│   "SwarmScout · 🟢 HIGH CONVICTION — $KORE"                           │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼  [User taps notification]
┌─────────────────────────────────────────────────────────────────────┐
│ Telegram opens the SwarmScout chat at the new message:               │
│                                                                       │
│   🟢 HIGH CONVICTION — $KORE                                          │
│                                                                       │
│   Token: 0xA1B2...c3D4  (BscScan ↗)                                  │
│                                                                       │
│   Thesis: Fresh launch 73 min ago. Unusually                         │
│   healthy early metrics — LP locked 180d, 143                        │
│   holders with moderate concentration, 247                           │
│   organic mentions in 4h across non-coordinated                      │
│   accounts. Creator address has no prior token                       │
│   deploys — unusual for a rug pattern.                               │
│                                                                       │
│   Caveats: Small liquidity ($3.4k). Any entry                        │
│   carries high risk. Do your own research.                           │
│                                                                       │
│   Models: Flash / GPT-4o / Sonnet 4.6 / Opus 4.7                     │
│   Verify on-chain ↗                                                   │
│                                                                       │
│   [ Verify on BscScan ]  [ Token on BscScan ]                         │
└─────────────────────────────────────────────────────────────────────┘
                             │
           ┌─────────────────┼──────────────────┐
           │                 │                  │
           ▼                 ▼                  ▼
  [Tap "Verify on BscScan"]          [Send /verify 01HXXX]
           │                                    │
           ▼                                    ▼
┌──────────────────────┐          ┌──────────────────────────────────┐
│ Browser opens         │          │ Bot replies with:                 │
│ bscscan.com/tx/0x...  │          │   Finding: 01HXXXXXXXXX           │
│ Showing the           │          │   Payload hash: 0x7f3a...bdc2     │
│ recordFinding() tx    │          │   On-chain: block #47219843       │
│ with the msg_id and   │          │   Verify: bscscan.com/tx/0xabc    │
│ hash                  │          │                                   │
└──────────────────────┘          │   Lineage (tap to expand):         │
                                   │   • Hunter (Flash)    → 0x1a...   │
                                   │   • Social (GPT-4o)   → 0x2b...   │
                                   │   • Chain  (Sonnet)   → 0x3c...   │
                                   │   • Risk   (Opus)     → 0x4d...   │
                                   │   • Narrator (Opus)   → 0x5e...   │
                                   └──────────────────────────────────┘
```

**Degraded path (S-10):**

```
   🟡 MODERATE CONVICTION — $XYZ

   ⚠ Social data unavailable — confidence reduced.

   Token: 0x...
   Thesis: ...  (based on chain data only)
   ...
```

**E2E test:** TC-E02 (main), TC-E02a (degraded), TC-E03 (verify)

---

## UF-03 — Auditing a brief after a losing trade

**Traces to:** UC-05, UC-07 / S-03

```
   User opens SwarmScout Telegram chat
                 │
                 ▼
   Scrolls back to the original alert for the token
                 │
                 ▼
   Copies the msg_id from the alert footer
   (or taps "Verify on-chain ↗")
                 │
                 ▼
   Sends /verify 01HXXXXXXXXX
                 │
                 ▼
   Bot returns full lineage + on-chain hashes (as shown in UF-02)
                 │
                 ▼
   User compares:
     - What conviction tier did SwarmScout actually assign?
     - What red flags were flagged at the time?
     - Did the brief say "Do your own research"?
                 │
                 ▼
   User concludes (truthfully) whether the tool was at fault
   or whether they ignored the warnings
```

**Key property:** the data the user sees in the verify response is byte-identical to what was recorded on-chain at the time of the alert. No retroactive editing is possible.

**E2E test:** TC-E04

---

## UF-04 — Algo trader wires API into their bot

**Traces to:** UC-03, UC-04, UC-05, UC-08 / S-02

```
   Developer opens api.swarmscout.xyz/docs
                 │
                 ▼
   Sees auto-generated OpenAPI UI (Swagger)
   with:
     GET /briefs
     GET /briefs/{msg_id}
     GET /briefs/{msg_id}/verify
     GET /health
                 │
                 ▼
   Taps "GET /briefs" → "Try it out" → "Execute"
                 │
                 ▼
   Sees live JSON response with 10 recent briefs.
   Response headers include X-RateLimit-Remaining.
                 │
                 ▼
   Copies the Pydantic-derived schema from /openapi.json
                 │
                 ▼
   Writes their poll loop (see S-02 code sample).
                 │
                 ▼
   Runs bot. Polls every 60s.
                 │
                 ▼
   On each high-conviction brief, bot re-verifies
   via /briefs/{msg_id}/verify before placing trade.
```

**Error path:** rate limit exceeded → HTTP 429, retries after the `Retry-After` header value.

**E2E test:** TC-E05 (list + detail + verify)

---

## UF-05 — Judge visits the dashboard

**Traces to:** UC-06, UC-09, UC-10 / S-04

```
   Judge clicks link from submission
                 │
                 ▼
   Browser loads dashboard.swarmscout.xyz
                 │
                 ▼ (SSR completes in <300ms)
┌─────────────────────────────────────────────────────────────────────┐
│ ╭── SwarmScout ──────────────────────────── [Live · 5 agents OK] ─╮ │
│ │                                                                    │ │
│ │  ┌────────────────┐  ┌────────────────────┐ ┌─────────────────┐ │ │
│ │  │ Swarm Health   │  │ Model Usage        │ │ Agent Activity   │ │ │
│ │  │                 │  │ (last 60m)         │ │ Timeline         │ │ │
│ │  │ ● Hunter    28s │  │ 🟢 Gemini Flash 42 │ │ 14:22:11 Hunter  │ │ │
│ │  │ ● Social    19s │  │ 🟢 GPT-4o       15 │ │  emitted TC #12  │ │ │
│ │  │ ● Chain     31s │  │ 🟢 Sonnet 4.6   14 │ │ 14:22:14 Social  │ │ │
│ │  │ ● Risk      44s │  │ 🟢 Opus 4.7      8 │ │  consuming       │ │ │
│ │  │ ● Narrator  52s │  │                    │ │ 14:22:17 Chain   │ │ │
│ │  │                 │  │ Provider split:    │ │  eth_call OK     │ │ │
│ │  │ 0 pending       │  │ Google  48%        │ │ 14:22:22 Risk    │ │ │
│ │  │                 │  │ OpenAI  19%        │ │  joined inputs   │ │ │
│ │  │ Last heartbeat: │  │ Anthropic 33%      │ │ 14:22:38 Narrator│ │ │
│ │  │ all < 60s       │  │                    │ │  publishing brief│ │ │
│ │  └────────────────┘  └────────────────────┘ └─────────────────┘ │ │
│ │                                                                    │ │
│ │  ───  Recent briefs  ──────────────────────────────────────────  │ │
│ │                                                                    │ │
│ │  🟢 HIGH  $KORE  14:22                                             │ │
│ │    Fresh launch. LP locked 180d, 143 holders, 247 mentions.       │ │
│ │    Models: Flash / GPT-4o / Sonnet 4.6 / Opus 4.7                 │ │
│ │    [ Verify on BscScan ↗ ]                                         │ │
│ │                                                                    │ │
│ │  🟡 MODERATE  $PUMP  14:15                                         │ │
│ │    Large holder concentration (top-1 34%). Not flagged honeypot.  │ │
│ │    Models: Flash / GPT-4o / Sonnet 4.6 / Opus 4.7                 │ │
│ │    [ Verify on BscScan ↗ ]                                         │ │
│ │                                                                    │ │
│ │  🔴 DEGEN  $SCMCOIN  14:03  ⚠ Not recommended                      │ │
│ │    No LP lock. Creator deployed 4 tokens this week.                │ │
│ │    [ Verify on BscScan ↗ ]                                         │ │
│ │                                                                    │ │
│ │  … [ Load more ]                                                    │ │
│ ╰──────────────────────────────────────────────────────────────────╯ │
└─────────────────────────────────────────────────────────────────────┘
                 │
                 ▼  [WebSocket tick — new event arrives]
   "Agent Activity Timeline" panel prepends:
     14:22:46 Hunter emitted TC #13
   (animated slide-in)
```

**Interactions:**
- **Click brief card** → expands to show full thesis, red flags, sources, model attribution footer
- **Click "Verify on BscScan ↗"** → opens BscScan in new tab at the `recordFinding` transaction
- **Click an agent dot in Swarm Health** → drawer opens with last 10 heartbeats, current model, pending queue depth
- **Resize to mobile** → panels stack vertically, timeline becomes collapsible

**Error paths:**
- WebSocket disconnects → "Live updates paused" banner appears; falls back to polling every 5s
- Initial SSR fails → minimal shell page with "retrying" state

**E2E test:** TC-E06 (desktop), TC-E06m (mobile), TC-E07 (WebSocket reconnect)

---

## UF-06 — Verifying on BscScan directly (no SwarmScout infrastructure)

**Traces to:** UC-09 / S-03, S-04

```
   User has a msg_id (from Telegram alert or API response)
                 │
                 ▼
   User opens bscscan.com/address/{FindingsRegistry_address}
                 │
                 ▼
   Taps "Contract" tab
                 │
                 ▼
   Taps "Read Contract"
                 │
                 ▼
   Finds `verifyFinding` method
                 │
                 ▼
   Pastes msg_id as bytes32 (0x + 64 hex chars)
                 │
                 ▼
   Clicks "Query"
                 │
                 ▼
   Returns: (payloadHash, agent, timestamp, recordedBy)
                 │
                 ▼
   User compares:
     - agent matches expected (e.g., "narrator")
     - recordedBy is an allowlisted wallet
     - timestamp is sensible
     - payloadHash can be re-computed from SwarmScout API response
   independently
```

**Why this flow exists:** proves SwarmScout's claims hold even if SwarmScout's servers are offline. The cryptographic trail is self-sovereign.

**E2E test:** TC-E08 (automated read-contract check against a known msg_id)

---

## UF-07 — Checking swarm health on the dashboard

**Traces to:** UC-10 / S-04

```
   User (operator or judge) looks at "Swarm Health" panel
                 │
                 ▼
   Sees 5 status dots, each colour-coded:
     🟢 = healthy (heartbeat <30s, error rate <5%)
     🟡 = degraded (heartbeat 30-60s OR fallback model OR error rate 5-20%)
     🔴 = down (no heartbeat in 60s OR error rate >20%)
                 │
                 ▼  [Click any agent dot]
┌─────────────────────────────────────────────────────────────────────┐
│ Drawer slides out from right:                                        │
│                                                                       │
│   Agent: Risk                                                         │
│   Status: 🟡 Degraded                                                 │
│   Reason: Running on fallback — GPT-4o (primary: Opus 4.7 error)    │
│   Current queue depth: 3 pending                                      │
│   Last 10 heartbeats:                                                 │
│     14:22:05  ok  model=openai/gpt-4o        err_rate=8%             │
│     14:21:55  ok  model=openai/gpt-4o        err_rate=9%             │
│     14:21:45  ok  model=openai/gpt-4o        err_rate=11%            │
│     14:21:35  ok  model=anthropic/opus-4-7   err_rate=2%             │
│     …                                                                 │
│                                                                       │
│   Recent errors:                                                      │
│     14:21:40  anthropic/opus-4-7  429 rate limit                     │
│     14:21:42  anthropic/opus-4-7  429 rate limit                     │
│     14:21:44  anthropic/opus-4-7  429 rate limit → fallback triggered│
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

**E2E test:** TC-E09

---

## UF-08 — Unsubscribing from alerts

**Traces to:** UC-11 / S-05

```
   User sends /unsubscribe
                 │
                 ▼
   Bot updates subscriptions table: deleted_at = now()
   (soft delete, preserves history)
                 │
                 ▼
   Bot replies:
     Unsubscribed ✅
     You will not receive further alerts.
     Use /subscribe anytime to re-enable.
```

**E2E test:** TC-E10

---

## UF-09 — Handling an alert while offline

**Traces to:** UC-02 (backpressure semantics)

```
   User's phone is offline
                 │
                 ▼
   Bot attempts Telegram send → Telegram accepts with delay
                 │
                 ▼
   Bot XACKs only after Telegram confirms
                 │
                 ▼
   Phone comes online
                 │
                 ▼
   Telegram delivers queued messages in order
                 │
                 ▼
   User sees all missed alerts (bounded by Telegram's retention)
```

**Dedup guarantee:** the Redis dedup SET (FR-165) ensures no double-send even if the bot retries after a transient network error. No E2E test required; unit + integration tests cover FR-165.

---

## UF-10 — Developer runs the system locally for the first time

**Traces to:** UC-14 / S-09

```
   $ git clone https://github.com/<user>/HACK0015-SwarmScout
   $ cd HACK0015-SwarmScout
   $ cp .env.example .env
   $ # (fill in API keys: ANTHROPIC, OPENAI, GEMINI, DGRID, TELEGRAM_BOT_TOKEN,
   $ #  WALLET_PRIVATE_KEY, BNB_TESTNET_RPC)
   $ docker compose up --build
                 │
                 ▼
   Containers start in order:
     postgres (healthcheck: pg_isready)
     redis    (healthcheck: redis-cli ping)
     hunter, social, chain, risk, narrator
     api      (healthcheck: /health)
     bot      (healthcheck: last heartbeat)
     web      (healthcheck: :3000)
                 │
                 ▼
   Developer opens:
     http://localhost:3000 → dashboard
     http://localhost:8000/docs → API OpenAPI UI
     telegram bot via @<configured_bot_username>
                 │
                 ▼
   Developer runs:  make test
                 │
                 ▼
   Output:
     Python:  pytest ... 247 passed ... coverage 100% (line+branch)
     TypeScript: vitest ... 89 passed ... coverage 100% (all metrics)
     Solidity: forge coverage ... 100% (line+branch)
     Playwright E2E: 12 passed
                 │
                 ▼
   All green → confidence to push a change
```

---

## User flow coverage summary

| Flow | Actor | Surface | Main UCs | E2E test |
|---|---|---|---|---|
| UF-01 | Retail trader | Telegram | UC-01, UC-11 | TC-E01 |
| UF-02 | Retail trader | Telegram | UC-02, UC-05 | TC-E02, TC-E02a, TC-E03 |
| UF-03 | Any user | Telegram | UC-05, UC-07 | TC-E04 |
| UF-04 | Algo trader | API | UC-03, UC-04, UC-05, UC-08 | TC-E05 |
| UF-05 | Judge / visitor | Dashboard | UC-06, UC-09, UC-10 | TC-E06, TC-E06m, TC-E07 |
| UF-06 | Skeptic | BscScan | UC-09 | TC-E08 |
| UF-07 | Operator / judge | Dashboard | UC-10 | TC-E09 |
| UF-08 | Retail trader | Telegram | UC-11 | TC-E10 |
| UF-09 | Retail trader | Telegram | UC-02 | (unit + integration only) |
| UF-10 | Developer | Local | UC-14 | smoke script |

Every M-priority user flow has at least one E2E test (NFR-324 compliance).

---

## Accessibility notes

- Dashboard cards use both colour **and** emoji/text for conviction (🟢/🟡/🔴 + word) to meet WCAG 2.1 AA
- Keyboard navigation: all interactive elements focusable with Tab; brief cards expandable with Enter
- Screen reader: status panel uses `role="status"` with `aria-live="polite"` for WebSocket ticks

---

## Known gaps & deferred work

| Gap | Reason |
|---|---|
| Admin UI flows | No admin UI in v1 |
| Payment / upgrade flows | W-05 in Requirements |
| Mobile native app flows | W-03 |
| i18n flows | W-09 |
| Accessibility audit beyond WCAG 2.1 AA baseline | Post-hackathon |

---

**End of 05_UserFlow.md**
