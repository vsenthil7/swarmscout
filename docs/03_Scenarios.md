# 03 — Scenarios Document

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 06:35 UTC

This document describes the real-world scenarios in which SwarmScout is used. It is the narrative input to 04_UseCases.md (formal actor + flow specifications) and 05_UserFlow.md (screen-by-screen interactions). Every scenario is written as a concrete story with time, place, motivation, and outcome — not as an abstract capability list.

---

## 1. Scenario overview

| # | Scenario | Primary actor | Frequency | Trust signal delivered |
|---|---|---|---|---|
| S-01 | Retail trader gets woken up by high-conviction alert | Retail trader | Daily | Telegram alert + on-chain hash |
| S-02 | Algo trader integrates SwarmScout briefs into bot | Algo / power user | Continuous | JSON API + verifiable hashes |
| S-03 | Trader verifies provenance of a brief after a trade goes wrong | Any user | Event-driven | BscScan record + model attribution |
| S-04 | Hackathon judge opens the dashboard cold | Judge | Once, 3-5 min | Live activity, visible multi-agent coordination, on-chain links |
| S-05 | New user subscribes and configures thresholds | Retail trader | Once per user | Telegram bot command flow |
| S-06 | Four.meme publishes a rug-pull candidate token | System-facing scenario | Unpredictable | Low conviction score + red flags + blocked brief |
| S-07 | LLM provider experiences a regional outage | System-facing scenario | Occasional | Transparent fallback, degraded-flag on output |
| S-08 | Power user audits the full swarm for a specific token | Algo / power user | Rare | Full lineage reconstruction via API |
| S-09 | Maintainer onboards to the codebase post-hackathon | Future engineer | Rare, high-value | Docs + architecture + test suite |
| S-10 | Scraping target updates anti-bot defences | System-facing scenario | Unpredictable | Degraded SocialScore + visible `data_quality` flag |

---

## 2. Scenarios in detail

### S-01 — Retail trader gets a high-conviction alert at 02:47 AM

**Actor:** Dan, a part-time crypto trader in Brisbane. Has ~$5k in crypto wallets. Uses Four.meme casually — 2-3 trades per week on small-cap launches.

**Context:** Dan subscribed to the SwarmScout Telegram bot last week with threshold `moderate`. He's asleep. His phone is on silent but his Apple Watch notifications are on for Telegram.

**Trigger:** A new token `$KORE` launches on Four.meme at 02:46 AM local. The Hunter agent detects it within 18 seconds. Chain agent finds: 143 holders, top-1 holder 22%, LP locked for 180 days, creator has no prior tokens. Social agent finds: 247 organic mentions in 4 hours, 3 respected accounts have posted about it, no coordinated-posting flags. Risk agent synthesises a verdict: score 78, conviction tier = `high`. Narrator composes the brief.

**The alert Dan receives (~04:00 AM):**

```
🟢 HIGH CONVICTION — $KORE

Token: 0xA1B2...c3D4 (BscScan ↗)
Thesis: Fresh launch 73 min ago. Unusually
healthy early metrics — LP locked 180d, 143
holders with moderate concentration, 247
organic mentions in 4h across non-coordinated
accounts. Creator address has no prior token
deploys — unusual for a rug pattern.

Caveats: Small liquidity ($3.4k). Any entry
carries high risk. Do your own research.

Swarm: Hunter/Social/Chain/Risk/Narrator
Models: Flash / GPT-4o / Sonnet 4.6 / Opus 4.7
Verify on-chain ↗
```

**What Dan does:** wakes briefly, taps the BscScan link, sees the hash on the registry contract, scrolls back in the thread to check prior accuracy, makes a small entry on mobile through his wallet. Goes back to sleep.

**What SwarmScout delivers:** not certainty — a well-sourced, cryptographically provenanced, multi-model cross-checked signal that Dan's judgement can act on. No hype language. No false confidence. The `Caveats` block is deliberate.

**Rule trace:** FR-082 (brief format), FR-085 (confidence tier), FR-163 (/verify), FR-164 (formatted output), FR-186 (click-through verify), NFR-260 (full lineage), NFR-261 (hash verifiability).

---

### S-02 — Algo trader wires SwarmScout into a custom bot

**Actor:** Priya, a quant-ish hobbyist. Runs a Python bot on a VPS that auto-trades Four.meme tokens based on multiple signals. ~$40k portfolio.

**Context:** Priya's current signals: on-chain liquidity + a basic Telegram-channel sentiment count. She wants a higher-quality signal without hand-rolling a full scraper + risk model.

**Trigger:** Priya reads SwarmScout's README, sees there's a public JSON API at `api.swarmscout.xyz`. She writes a small integration.

**What she does:**

```python
# priya's bot, excerpt
async def poll_swarmscout():
    while True:
        async with httpx.AsyncClient() as client:
            r = await client.get("https://api.swarmscout.xyz/briefs?since=30m")
            briefs = r.json()["items"]
        for brief in briefs:
            if brief["conviction_tier"] == "high" and brief["confidence_tier"] != "degraded":
                # extra verification: re-check on-chain
                ver = await client.get(f"https://api.swarmscout.xyz/briefs/{brief['msg_id']}/verify")
                if ver.status_code == 200 and ver.json()["on_chain_hash_matches"]:
                    await self.place_order(brief["token_address"], size_usd=50)
        await asyncio.sleep(60)
```

**What SwarmScout delivers:** a stable, paginated, schema-documented API. OpenAPI spec at `/openapi.json`. Every brief carries a `msg_id` that Priya can independently re-verify on BscScan at any time. Model attribution in the response lets her back-test which model combinations produced the best outcomes.

**Rule trace:** FR-200, FR-201, FR-202 (OpenAPI), FR-203 (rate limiting), NFR-261 (on-chain verifiability), P4 (schema-first).

---

### S-03 — Trader audits a brief after a losing trade

**Actor:** Marco, bought `$PEPU` based on a SwarmScout brief that gave conviction `moderate`. The token rugged 6 hours later. He lost $200.

**Context:** Marco is angry and wants to know whether SwarmScout was negligent or whether he misread a legitimately uncertain signal.

**Trigger:** Marco opens Telegram, uses `/verify 01HXXXXXXXXX` on the original alert.

**What the bot returns:**

```
Finding: 01HXXXXXXXXX (AlphaBrief, t=2026-04-15T14:23:11Z)
Payload hash: 0x7f3a...bdc2
On-chain: block #47219843, tx 0xabc...
View on BscScan ↗

Lineage:
• Hunter (Gemini Flash)     → 0x1a...
• Social (GPT-4o)           → 0x2b...  [data_quality: ok]
• Chain  (Sonnet 4.6)       → 0x3c...  [LP locked: true, holders: 89]
• Risk   (Opus 4.7)         → 0x4d...  [score: 54, tier: moderate]
• Narrator (Opus 4.7)       → 0x5e...

Red flags flagged at time of brief:
- small_liquidity ($1.8k)
- creator_third_token_this_week
```

**What Marco concludes:** SwarmScout flagged `creator_third_token_this_week` and `small_liquidity`. The brief rated the token only `moderate` conviction. Marco remembers now that the brief explicitly said "high risk of rapid drawdown." He acted on a moderate signal as if it were high. On-chain proof that the warnings were there at the time of the alert is what distinguishes SwarmScout from "trust me bro" alpha channels.

**What SwarmScout delivers:** accountability. The hash on BscScan is immutable. Marco cannot say SwarmScout rewrote history; SwarmScout cannot say it never flagged the risk. Both parties stand on provable ground.

**Rule trace:** FR-163 (/verify), FR-122 (FindingRecorded event), NFR-260, NFR-261, P3 (auditability).

---

### S-04 — Hackathon judge opens the dashboard

**Actor:** Chen, one of the Four.Meme AI Sprint judges. Has 3-5 minutes per submission. Reviewed ~40 BUIDLs today. Tired.

**Context:** Chen has SwarmScout's submission open — GitHub repo, demo video, dashboard link. She clicks the dashboard link first because she can evaluate 3 of the 4 criteria (Innovation, Technical Implementation, Presentation) from a live demo faster than from reading code.

**What she sees on first load (dashboard):**

1. A **live feed** of AlphaBriefs, most recent first, with model attribution footer on each card
2. An **Agent Activity Timeline** panel: `[02:14:33 Hunter → emitted TokenCandidate for 0xA1B...] [02:14:35 Social → consuming from stream:candidates] [02:14:38 Chain → consuming...]`. New lines appear every few seconds.
3. A **Model Usage** panel: pie chart of calls/hour by (agent, provider). Shows Gemini Flash dominating Hunter, Opus dominating Risk+Narrator, GPT-4o dominating Social.
4. A **Swarm Health** panel: 5 green dots, each with last-heartbeat time.
5. Every brief card has a `Verify on BscScan ↗` button.

**What Chen scores:**
- **Innovation 30%**: multi-agent swarm + on-chain hashes + multi-provider routing → unique combination among the 102 BUIDLs. **High.**
- **Technical Implementation 30%**: Clicks BscScan link, sees real hashes stored on real blocks. Clicks into the GitHub repo, sees Actions badge green, clicks it, sees 100% coverage across Python + TypeScript + Solidity. **High.**
- **Practical Value 20%**: The Telegram bot screenshot and API doc show this is usable by real traders. **Moderate-high.**
- **Presentation 20%**: Live dashboard with continuous movement, clean UI. **High.**

**What SwarmScout delivers to Chen:** immediate visual proof that every claim in the submission is real, live, and running. No dead buttons. No "this would show a chart in production." On-chain hashes are not only mentioned but clickable.

**Rule trace:** FR-183 (live timeline), FR-184 (model panel), FR-185 (swarm health), FR-186 (verify click-through), FR-187 (responsive), rule 2.1 (enterprise-grade visible).

---

### S-05 — New user subscribes and configures thresholds

**Actor:** Ranjit, found SwarmScout in a Twitter thread. Never used a crypto bot before.

**Trigger:** Ranjit clicks the Telegram link from the SwarmScout site.

**Flow:**

```
Ranjit: /start
Bot:    Welcome to SwarmScout. I push high-signal alerts about
        new Four.meme token launches, verified on-chain.

        Commands:
          /subscribe           — start receiving alerts
          /threshold <tier>    — set your minimum conviction
                                 (degen / speculative / moderate / high)
          /status              — see your settings
          /verify <msg_id>     — look up any alert's on-chain proof
          /unsubscribe         — stop alerts
          /help                — show this

Ranjit: /subscribe
Bot:    Subscribed ✅
        Default threshold: moderate
        You'll receive alerts for moderate and high conviction.
        Change with /threshold

Ranjit: /threshold high
Bot:    Threshold set to high.
        You'll only receive high-conviction alerts
        (~1-3 per day on typical Four.meme activity).

Ranjit: /status
Bot:    Chat_id: 1234567890
        Subscribed: yes
        Threshold: high
        Alerts received (7d): 0
        Your first alert will arrive when Swarm verdict ≥ high.
```

**What SwarmScout delivers:** friction-free onboarding. No wallet connection required for read/subscribe. Clear explanations. Clear expectations about alert frequency. Every command discoverable.

**Rule trace:** FR-160, FR-161, FR-162, FR-164.

---

### S-06 — Four.meme publishes a rug-pull candidate

**Actor:** System-facing — no user; the swarm itself is the actor.

**Context:** A malicious creator deploys `$SCMCOIN` with: LP $800 (not locked), top-1 holder 92%, contract not verified, creator has deployed 4 tokens in 5 days, honeypot check fails.

**What happens:**

- **Hunter** (Gemini Flash): emits TokenCandidate normally.
- **Chain** (Sonnet 4.6): flags `lp_locked: false`, `top_holder_pct: 92`, `contract_verified: false`, `honeypot_check_passed: false`, `creator_previous_tokens: 4`.
- **Social** (GPT-4o): finds 3 mentions, all from newly-created accounts. Flags `coordinated_posting: true`, `organic_score: 4`.
- **Risk** (Opus 4.7): synthesises — score 6/100, tier `degen`, rationale cites all 5 red flags. Publishes RiskVerdict normally.
- **Narrator** (Opus 4.7): produces a brief with `conviction_tier: degen`.

**Filtering decisions:**
- Telegram bot **does not push** to users whose threshold is `speculative`, `moderate`, or `high` — only `degen`-threshold users receive it.
- Dashboard **shows** the brief in a dedicated "Avoid" feed (if implemented) or with a red-bordered card.
- API **returns** the brief on `GET /briefs` — API consumers filter themselves.

**What SwarmScout delivers:** a deliberate non-alert. The system does not suppress the finding (provenance requires it be recorded), but does not push it to users who asked for cleaner signal. The brief exists on-chain for verification, but your phone stays quiet.

**Rule trace:** FR-066 (heuristics), FR-162 (threshold filter), FR-186 (verify), NFR-261 (even rejected tokens are recorded).

---

### S-07 — OpenAI has a regional outage

**Actor:** System-facing.

**Context:** OpenAI's API starts returning 503 in the EU region. Social agent (primary: GPT-4o) calls start failing.

**What happens:**

- LLMRouter detects 3 consecutive 5xx from OpenAI for the Social agent.
- Circuit breaker opens for OpenAI / Social for 60 seconds.
- Next call falls through to Fallback 1: `anthropic/claude-sonnet-4-6`.
- Social agent continues producing SocialScore messages. Each message's `model_used` field reads `anthropic/claude-sonnet-4-6` (not GPT-4o). The hash on-chain reflects this.
- Every 60 seconds, a probe request tests OpenAI; if it succeeds, circuit closes.
- During the outage, dashboard's Model Usage panel visibly shifts GPT-4o bar to zero and Sonnet 4.6 bar to higher.
- No user-visible degradation in alerts.

**What SwarmScout delivers:** silent resilience. The system takes the outage; the users don't. The auditable fact that a different model produced this particular SocialScore is preserved in the envelope and on-chain hash — no retroactive rewriting of "which model was used."

**Rule trace:** FR-024 (Social fallback), FR-141 (DGrid fallback), FR-143 (call logging), NFR-262 (model_used in envelope), P6 (no silent degradation — but degradation is handled and attributed).

---

### S-08 — Power user audits a specific token's full lineage

**Actor:** Priya (from S-02), doing retrospective analysis after a winning trade.

**Trigger:** `GET /briefs/01HXXXXXXXXX/lineage` (bonus endpoint, not in MVP FRs — documented as post-v1).

**Alternative for MVP:** Priya reconstructs lineage manually:

```python
brief = await get_brief(msg_id)
lineage = []
current = brief
while current:
    lineage.append(current)
    if current.upstream_ids:
        current = await get_message(current.upstream_ids[0])
    else:
        current = None
# lineage now contains: [AlphaBrief, RiskVerdict, ChainMetrics/SocialScore, TokenCandidate]
for msg in lineage:
    assert await verify_on_chain(msg.msg_id, msg.payload_hash)
```

**What she gets:** full 5-step lineage, each step with its `model_used`, `payload_hash`, `created_at`, and a BscScan URL. She can write a blog post claiming "SwarmScout was 3-for-4 on high-conviction calls this week" and **prove it** by pointing to the immutable hashes.

**What SwarmScout delivers:** the primitives for third-party auditing. Not a polished audit UI in v1, but every ingredient to build one.

**Rule trace:** NFR-260, NFR-261, FR-201 (detail endpoint).

---

### S-09 — A new engineer onboards post-hackathon

**Actor:** Mei, a backend engineer hired at a hypothetical company that wants to productionise SwarmScout.

**Day 1 expectation:** read docs, run locally, push a trivial PR.

**What Mei finds:**
1. `README.md` points to `docs/01_Requirements.md` through `09_TestCases.md` and `ARCHITECTURE.md`.
2. `docker compose up` works on her Mac in 4 minutes after a `cp .env.example .env` + filling in API keys.
3. `make test` runs the full suite. She sees 100% coverage reports in stdout.
4. `CONTRIBUTING.md` tells her: git first, one logical change = one commit, Conventional Commits, test before commit, fix → commit fix → re-test → commit green, never batch.
5. Architecture doc explains every technology choice with alternatives rejected — she doesn't have to guess why Redis Streams and not Kafka.
6. First PR: adds a new rug-pull heuristic. She reads `agents/risk/heuristics.py`, adds a test case in `agents/tests/unit/test_heuristics.py`, adds the rule, commits. CI passes. Merged in 30 minutes.

**What SwarmScout delivers:** a repository that respects its future readers. No institutional knowledge locked in the original author's head.

**Rule trace:** NFR-344, NFR-381, rule 2.1.

---

### S-10 — Scraping target updates anti-bot defences

**Actor:** System-facing.

**Context:** X ships a new Cloudflare bot-detection layer. Playwright stealth bypass from HACK0014 starts failing — scrapes return 403 or CAPTCHA pages.

**What happens:**

- Social agent's scraper raises a recognisable exception (`ScrapingBlockedError`).
- Social agent emits SocialScore with:
  - `organic_score: null`
  - `mentions_24h: null`
  - `sentiment: null`
  - `red_flags: ["social_data_unavailable"]`
  - `data_quality: degraded`
- Hash is still computed and recorded on-chain (FR-026).
- Risk agent receives the degraded SocialScore, produces a verdict that relies more heavily on Chain metrics, and the resulting AlphaBrief carries `confidence_tier: degraded`.
- Dashboard brief card shows an orange "Partial data" banner.
- Telegram bot includes a caveat line in the brief: `⚠ Social data unavailable — confidence reduced.`

**What SwarmScout delivers:** transparency. Users are told when a signal is missing. The system does not fabricate a score to look complete. The on-chain record shows exactly what data was and wasn't available.

**Rule trace:** FR-027, FR-085, P6 (no silent degradation), rule 2.1 (enterprise-grade honesty).

---

## 3. Scenario coverage matrix

| Scenario | Primary UCs (see 04_UseCases.md) | Primary user flows (see 05_UserFlow.md) |
|---|---|---|
| S-01 | UC-01, UC-02, UC-07 | UF-01, UF-03 |
| S-02 | UC-03, UC-04, UC-08 | UF-04 |
| S-03 | UC-05, UC-07 | UF-03, UF-06 |
| S-04 | UC-06, UC-09, UC-10 | UF-05 |
| S-05 | UC-01, UC-11 | UF-02 |
| S-06 | UC-02, UC-12 | UF-01 (blocked path) |
| S-07 | UC-13 | n/a (system scenario) |
| S-08 | UC-04, UC-05, UC-07 | UF-04, UF-06 |
| S-09 | UC-14 | n/a (developer scenario) |
| S-10 | UC-13, UC-15 | UF-05 (degraded display) |

---

## 4. Anti-scenarios — what SwarmScout is NOT designed to do

Stating these explicitly prevents scope creep later.

| # | Anti-scenario | Why we don't do this |
|---|---|---|
| AS-01 | Execute trades on behalf of the user | Custody + regulatory risk; out of scope |
| AS-02 | Promise returns or quote "expected" profit | Not a licensed financial advisor; caveat language is in every brief |
| AS-03 | Filter or censor legitimate tokens for political/subjective reasons | Signals are data-driven; thresholds are user-configurable |
| AS-04 | Replace users' own due diligence | Briefs explicitly say "Do your own research" |
| AS-05 | Guarantee that a "high conviction" token will appreciate | No such thing; risk language preserved |
| AS-06 | Operate without internet access | Cloud-hosted agents; edge/Vertex variant is post-hackathon |
| AS-07 | Monitor tokens outside Four.meme | Scope-bounded; other platforms are post-hackathon |

---

## 5. Known gaps & deferred work

| Gap | Status |
|---|---|
| Scenarios for admin/maintenance (e.g., operator rotating wallet keys) | Deferred to operations runbook post-hackathon |
| Scenarios for abusive users (e.g., scraping the bot itself) | FR-203 rate limit is the v1 mitigation; full abuse model post-hackathon |
| Back-testing scenario (historical replay of swarm on old Four.meme data) | W-08 in Requirements |
| Mobile native UX scenarios | W-03 in Requirements |

---

**End of 03_Scenarios.md**
