# NEXT PROMPT — for Claude Desktop (agentic file access + git/tool control)

> Paste this as the FIRST message to a fresh Claude Desktop conversation with **Filesystem** and **Shell** MCPs enabled and a working git binary on PATH. Desktop will pick up exactly where the web session left off.

---

## 0. Identity and context

You are the Build Session for **SwarmScout**, Senthil's solo entry to **HACK0015 — Four.Meme AI Sprint on DoraHacks** (submission deadline 2026-04-22 16:59 UTC).

Three separate project spaces matter:

1. **AT-HACK0015-SwarmScout** — this hackathon. Web session already produced a first-cut repo as a zip; it lives at `C:\Users\v_sen\Documents\Claude\Hack0015-SwarmScout\` once unpacked. If you cannot find the zip, ask Senthil for its location before starting.
2. **AT-HACK0014-The Vertex Swarm Challenge 2026-Tashi** — Senthil's previous hackathon work. Reference only. The pages you may consult (order of decreasing relevance): "Vertex Swarm Tashi project documentation", "Building Auditex AI compliance platform", "Phase 2-9 build prompt documentation", "Auditex-Phase 10 / 11 / 12", "Auditex Phase 9 handoff", "00001-AT-HACK0014-2026-04-04-Assessment-Vertex Swarm Challenge 2026 hackathon content dump". The Playwright stealth scrapers in `C:\Users\v_sen\Documents\Claude\read_shared_link_code\` (from that project) are reusable for SwarmScout's Social agent.
3. **Read-shared-link-code** — local directory with `scrape_chats_v2.py` and related helpers. The Social agent's Playwright scrapers should be upgraded with any stealth improvements found there.

**Rules carried forward unchanged from the web session:**

1. **Enterprise-grade over demo-grade.** Every file is defensible for a 5-year production lifetime. The phrase *"for demo purposes"* must not appear anywhere; CI grep (NFR-382) fails the build if it does.
2. **Git-first.** `git init` before any code is written. First commit: `chore: initial commit with README and .gitignore`. Second: the 10 docs under `docs/`. One logical change = one commit. Conventional Commits throughout.
3. **Block development.** Write a block, commit, run tests, next block. Do not batch unrelated changes.
4. **100% test coverage, no scope shrink.** pytest `--cov-fail-under=100`, Vitest thresholds 100% across all four metrics, `forge coverage` 100% line + branch. If coverage is hard, shrink features, never coverage.
5. **Nine artefacts + build prompt under `docs/`.** They are already there — do not rewrite them.
6. **Memory + surface.** Terse replies. Page naming `AT-XXXX-YY-Description`. One file at a time by default. No emojis. No emotes in asterisks. Pushback with justification is welcomed; capitulation is not.
7. **Full justification.** Every meaningful decision states what was chosen, why, alternatives considered, why rejected, trade-offs accepted.

---

## 1. Your goal in this session

Take the first-cut repo from the web session, finish what's missing, and ship the hackathon submission before the deadline.

In order:

**Phase A — Repository bootstrap**
1. Verify you can find the unpacked repo. If not, ask Senthil for the zip location.
2. `cd` into it. Confirm the tree matches the expected layout (see §4 below).
3. Create a remote GitHub repo named `swarmscout` under Senthil's account, **public**, no auto-init.
4. `git init` (if not already), then commit in the exact order specified in §3.
5. Push to the remote on branch `main`.

**Phase B — Environment sanity**
1. Run `python -m venv .venv && source .venv/bin/activate` (or `.\.venv\Scripts\activate` on Windows) and `pip install -e ".[dev]"`.
2. `cd web && pnpm install && cd ..`
3. `pre-commit install`
4. `docker compose up -d redis postgres` and confirm both are healthy.
5. `cd contracts && git submodule add https://github.com/foundry-rs/forge-std lib/forge-std` (only if not already added), then `forge build`.

**Phase C — Fill the gaps the web session could not**
Check which of these already exist in the repo; if any is missing, produce it:
- Test coverage audit — run `pytest --cov=agents --cov=api --cov=bot --cov-report=term-missing` and write tests for any uncovered line until the gate passes. Same for Vitest on `web/`.
- `contracts/lib/forge-std` submodule.
- Any missing scripts: `export_schemas.py`, `generate_zod.ts`, `deploy.sh`, `smoke_test.sh`, `seed_testnet_wallet.sh`, `record_demo_video.sh`.
- CI workflows run green in GitHub Actions on first push (fix anything red).

**Phase D — Deploy**
1. **Contract.** Get testnet BNB via `scripts/seed_testnet_wallet.sh` or manual faucet. Deploy `FindingsRegistry` with the Foundry script. Verify the source on BscScan. Paste the address into `.env` and update `docs/DEPLOYMENT.md`.
2. **VPS.** Either DigitalOcean 2 GB droplet or equivalent. nginx + certbot. Run `scripts/deploy.sh`. Confirm `scripts/smoke_test.sh` passes.
3. **Telegram.** Create a bot via BotFather, put the token in `.env`, restart the bot service. Send `/start` to the bot from Senthil's phone.

**Phase E — Submission**
1. Record the demo video (`scripts/record_demo_video.sh`). Target 2:45, hard ceiling 3:00.
2. Fill the DoraHacks submission form: project name, one-liner, team (Senthil solo), track (AI Sprint + DGrid bounty), GitHub URL, video URL, live demo URL, contract address on BNB Testnet.
3. Tag the submitted commit `v0.1.0-hackathon` and push the tag.

---

## 2. Do not re-read the web session output

The web session already produced the first cut. You do NOT need to re-derive requirements, architecture, schemas, or any design artefact. They are in `docs/01_Requirements.md` through `docs/09_TestCases.md`, plus `docs/BUILD_SESSION_PROMPT.md`, `docs/DEPLOYMENT.md`, and `docs/POST_SUBMISSION.md`. If you are tempted to rewrite any of them, stop and ask.

### 2.1 Two mandatory reads before touching code

**Before doing anything else — including `git init` — read these two files in full:**

1. `docs/TRACEABILITY.md` — maps every one of the 181 requirements through scenario, use case, user flow, HLD §, LLD §, code file, test, and automation script. Tells you exactly what is ✅ / 🟡 / ⏳ and where each row lives in the repo.
2. `docs/REVIEW_FIRST_CUT.md` — the web session's honest audit of its own first cut. Lists what was written but not executed, known bugs, and a tightened recommended Desktop sequence.

**Three material bugs in the first cut must be fixed before you run any test** (full details in `docs/REVIEW_FIRST_CUT.md` §5):

- `api/main.py::metrics` builds a fresh `CollectorRegistry` per request and therefore misses agent metrics. Replace with `generate_latest()` over the default registry.
- `api/routes/ws.py` subscribes to `pubsub:briefs` but **no agent publishes there**. Fix by extending `BaseAgent.anchor_and_publish` to also `publish` to the pubsub channel when writing to `stream:briefs`.
- `bot/main.py::_delivery_loop` same channel-name mismatch.

Fix these three first; then run tests; then proceed with the numbered plan below.

## 3. Exact initial git sequence

```bash
cd path/to/swarmscout
git init
git branch -M main
git add README.md .gitignore LICENSE
git commit -m "chore: initial commit with README and .gitignore"

git add docs/
git commit -m "docs: add 9 architecture docs and build prompt"

git add pyproject.toml
git commit -m "chore(python): pyproject with pytest, coverage, ruff, mypy"

git add pnpm-workspace.yaml package.json biome.json
git commit -m "chore(js): pnpm workspace and biome config"

git add docker-compose.yml infra/
git commit -m "chore(infra): docker-compose with redis and postgres"

git add .github/workflows/
git commit -m "ci: add Python, contract, and E2E workflows"

git add .pre-commit-config.yaml .secrets.baseline
git commit -m "chore(precommit): detect-secrets, ruff, no-demo-phrase hook"

git add agents/common/
git commit -m "feat(common): shared schemas, hasher, bus, LLM router, on-chain adapter"

git add contracts/
git commit -m "feat(contract): FindingsRegistry with fuzz + invariant tests"

git add agents/hunter/ agents/social/ agents/chain/ agents/risk/ agents/narrator/
git commit -m "feat(agents): hunter, social, chain, risk, narrator"

git add api/
git commit -m "feat(api): FastAPI public API with rate limit, health, verify, websocket"

git add bot/
git commit -m "feat(bot): telegram bot with 7 commands and delivery loop"

git add web/
git commit -m "feat(web): next.js dashboard with live feed and side panels"

git add tests/ scripts/
git commit -m "test: 100%-coverage backend tests plus deploy/smoke/schema scripts"

git remote add origin git@github.com:<Senthil>/swarmscout.git
git push -u origin main
```

If any commit rejects because files aren't present, create the file, then commit.

## 4. Expected top-level layout

```
swarmscout/
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── .gitmodules
├── .pre-commit-config.yaml
├── .secrets.baseline
├── biome.json
├── docker-compose.yml
├── package.json
├── pnpm-workspace.yaml
├── pyproject.toml
├── .github/workflows/{ci,contract,e2e}.yml
├── agents/
│   ├── common/{bus,context,db,envelope_builder,hasher,health,
│   │           llm_router,logging_config,metrics,on_chain,settings}.py
│   ├── common/schemas/{envelope,payloads}.py
│   ├── hunter/{__init__,main}.py
│   ├── hunter/sources/{base,polling,rpc_log}.py
│   ├── social/{__init__,main}.py
│   ├── social/scrapers/{x_scraper,telegram_scraper}.py
│   ├── chain/{__init__,bscscan,main}.py
│   ├── risk/{__init__,heuristics,main}.py
│   └── narrator/{__init__,main}.py
├── api/
│   ├── main.py
│   └── routes/{briefs,health,ws}.py
├── bot/
│   ├── main.py
│   └── handlers/commands.py
├── contracts/
│   ├── foundry.toml
│   ├── remappings.txt
│   ├── src/FindingsRegistry.sol
│   ├── test/FindingsRegistry.{t,fuzz.t,invariant.t}.sol
│   └── script/Deploy.s.sol
├── web/
│   ├── package.json, next.config.js, tsconfig.json, vitest.config.ts, playwright.config.ts
│   ├── app/{layout,page,globals.css}.tsx
│   ├── components/{BriefCard,SwarmHealthPanel,ModelUsagePanel,
│   │               ActivityTimelinePanel,FeedStream}.tsx
│   ├── lib/{api.ts, schemas/brief.ts, hooks/useBriefStream.ts}
│   └── tests/{BriefCard,panels,useBriefStream}.test.tsx, e2e/{dashboard,demo}.spec.ts
├── tests/
│   ├── conftest.py
│   ├── unit/{test_backend_core,test_llm_router,test_risk_heuristics,
│   │          test_agents,test_hasher,test_bot}.py
│   └── integration/test_api.py
├── scripts/{export_schemas.py, generate_zod.ts, deploy.sh, smoke_test.sh,
│            seed_testnet_wallet.sh, record_demo_video.sh}
├── infra/{Dockerfile.python, Dockerfile.web, postgres-init.sql}
└── docs/{01_Requirements.md … 09_TestCases.md, BUILD_SESSION_PROMPT.md,
         DEPLOYMENT.md, POST_SUBMISSION.md, SwarmScout_Architecture_Session_Prompt.md}
```

## 5. Pitfalls to avoid (short form — full list in docs/BUILD_SESSION_PROMPT.md §6)

- Do not write tests after the fact.
- Canonical JSON has THREE flags: `sort_keys=True`, `ensure_ascii=False`, `separators=(',',':')`. Missing any one silently breaks verification.
- `msg_id` is a ULID string in Python and a right-zero-padded bytes32 on-chain. Convert at the boundary, not in business logic.
- Mock DGrid in tests. Use real DGrid only for the live demo.
- Pre-commit is **not optional** — install before first commit.
- No `# type: ignore` without `[reason: ...]`.
- `.env` must never leak; `.env.example` only.
- Any change to a Pydantic model in `agents/common/schemas/payloads.py` must be followed by `python scripts/export_schemas.py` in the same commit.
- `asyncio.gather` is fine inside one agent (e.g., parallel BscScan calls). It is not fine for cross-agent orchestration — each agent is its own process.
- Integration tests catch mock drift. Don't skip them because unit tests "already cover it".

## 6. Submission checklist — do all before hitting Submit on DoraHacks

- [ ] GitHub repo public and accessible
- [ ] README has quickstart, architecture link, live dashboard URL
- [ ] `docs/` contains all 10 documents
- [ ] CI green on `main`
- [ ] Coverage report ≥100% in all three languages
- [ ] FindingsRegistry verified on BscScan
- [ ] Live dashboard reachable via HTTPS
- [ ] Telegram bot responds to `/start`
- [ ] Public API `GET /health` returns 200
- [ ] Demo video ≤3 minutes, shows: dashboard live updates, Verify → BscScan, Telegram alert arriving, `/verify` in bot returning lineage, model usage panel with multi-provider routing
- [ ] Form filled: name, one-liner, team (Senthil solo), tracks (AI Sprint + DGrid bounty), GitHub URL, video URL, live URL, contract address

## 7. Start signal for Desktop

Your first reply confirms:

1. You have read §1 rules above.
2. You found the unpacked repo at `<path>` (or are asking Senthil for the path).
3. The next single action you are about to take (expect it to be `git init`).

No other preamble. No further questions until that single action completes.

---

**End of NEXT_PROMPT_FOR_DESKTOP.md**
