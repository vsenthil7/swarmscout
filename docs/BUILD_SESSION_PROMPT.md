# BUILD SESSION PROMPT — SwarmScout

**Purpose:** This document is the handoff from the Architecture Session (AT-0002-01) to the Build Session. The Build Session's job is to turn the 9 architecture documents into a working, tested, deployed system before the hackathon deadline.

**Hackathon:** HACK0015 — Four.Meme AI Sprint on DoraHacks
**Submission deadline:** 2026-04-22 16:59 UTC
**Time remaining at architecture session end:** ~9 hours
**Project root (Windows):** `C:\Users\v_sen\Documents\Claude\Hack0015-SwarmScout\`
**User:** Senthil, solo build

---

## 0. How to use this document

1. Read the rules (§1) — non-negotiable, carry forward from the architecture session
2. Read the artefact inventory (§2) — the 9 docs this prompt hands off from
3. Read the implementation order (§3) — the exact sequence, no improvisation
4. Per-component exit criteria (§4) define "done"
5. Known issues the build session must resolve (§5)
6. Common pitfalls (§6) — things that will waste time if not anticipated

**Start every Build Session reply by confirming you've read §1 rules.**

---

## 1. Rules — carry forward unchanged from the architecture session

These are rules 2.1 through 2.8 as established and reinforced throughout the architecture session. Any Build Session reply that violates them is a defect.

### 1.1 Enterprise-grade over demo-grade

Every file produced must be defensible for a 5-year production lifetime. No shortcuts disguised as MVP. Deferred risks are flagged in a "Known Gaps" section, never hidden. **The phrase "for demo purposes" does not appear anywhere — not in code, not in comments, not in docs, not in commit messages.** A grep check enforces this (NFR-382).

### 1.2 Git-first, commit discipline

- `git init` before any code is written
- First commit: `chore: initial commit with README and .gitignore`
- Second commit: this build prompt and the 9 architecture docs under `docs/`
- After that: **one logical change = one commit**
- Conventional Commits format: `type(scope): summary` — types include `feat`, `fix`, `test`, `docs`, `chore`, `refactor`, `ci`, `build`
- Commit before testing, not after
- On test failure: commit the failing test (if not already committed), commit the fix, commit the green result
- Never batch multiple unrelated changes into one commit
- PRs may contain many commits; none is a grab-bag

### 1.3 Block development

Claude writes code in blocks; Senthil commits and runs tests. This rhythm is preserved in the Build Session. Don't attempt to run tests unilaterally unless Senthil's tooling is proven to be set up — ask first if uncertain.

### 1.4 100% test coverage, no scope shrink

- Python: `pytest --cov --cov-branch --cov-fail-under=100`
- TypeScript: Vitest thresholds at 100% for lines, branches, functions, statements
- Solidity: `forge coverage` at 100% line + branch
- If coverage is hard to reach, **shrink features, not coverage**
- Coverage isn't an aspiration; it's a CI gate

### 1.5 Nine artefacts + build prompt

All 10 files under `docs/` before implementation begins. They exist already — the Build Session does not rewrite them.

### 1.6 Build-session handoff

This document is the handoff. Read it fully before coding.

### 1.7 Memory and surface rules

The assistant retains operational style, rules, and user preferences across turns. User preferences observed in the architecture session:

- Terse communication style
- Page-naming convention: `AT-XXXX-YY-Description`
- Occasional typos — do not over-confirm
- One file at a time by default; exceptions explicitly granted
- Values: enterprise-grade, no scope shrink, 100% test coverage, git discipline
- Silent, text-only responses; no emojis unless already used by user; no emotes or actions in asterisks
- Pushback with justification is welcomed; capitulation is not

### 1.8 Full justification

Every meaningful decision must state: what was chosen, why, what alternatives were considered, why they were rejected, trade-offs accepted. This applies in code review, in commit messages for non-trivial changes, and in any new doc produced during the build session.

---

## 2. Artefact inventory

The following are the authoritative design documents. The Build Session does not modify them except by appending a dated change-log entry.

| # | File | Content |
|---|---|---|
| 01 | `docs/01_Requirements.md` | 156 FR/NFR/W/A/C items; MoSCoW priority; traceability to judging criteria |
| 02 | `docs/02_Architecture.md` | 14 technology decisions with alternatives-rejected tables; C4 diagrams; 17 failure modes |
| 03 | `docs/03_Scenarios.md` | 10 narrative scenarios + 7 anti-scenarios |
| 04 | `docs/04_UseCases.md` | 16 formal use cases (UC-01 – UC-16) |
| 05 | `docs/05_UserFlow.md` | 10 user flows (UF-01 – UF-10) with ASCII screens |
| 06 | `docs/06_HLD.md` | Component responsibilities; interaction patterns; data contracts; DB high-level |
| 07 | `docs/07_LLD.md` | Class / module signatures; Pydantic models; Solidity contract source; OpenAPI; `.env.example`; CI workflows |
| 08 | `docs/08_TestPlan.md` | Layered strategy; environments; coverage gates; entry/exit criteria |
| 09 | `docs/09_TestCases.md` | Named test cases TC-U##, TC-I##, TC-C##, TC-E##, TC-F##, TC-S##, TC-P## with traces to FR/NFR |

When the Build Session needs to know a fact, the order of lookup is:

1. Check the relevant doc first
2. If under-specified, check related docs
3. If still unclear, state the gap and propose a resolution with justification before coding

---

## 3. Implementation order

Twelve numbered phases. Each phase ends with a commit-and-CI-green gate. No phase begins before the prior phase's exit criteria are met.

### Phase 1 — Repo scaffold + CI skeleton

- `git init`
- First commit: README.md (project summary, quickstart placeholder), `.gitignore` (Python, Node, Foundry, OS junk, `.env`)
- Second commit: copy all 10 `docs/` files
- Third commit: `pyproject.toml` with pytest + coverage + ruff + mypy config (matching 07_LLD §6.1)
- Fourth commit: `pnpm-workspace.yaml`, root `package.json`
- Fifth commit: `docker-compose.yml` (Redis + Postgres only so far)
- Sixth commit: `.github/workflows/ci.yml` skeleton (Python job only, no tests yet — but linting and mypy on empty code succeed)
- Seventh commit: `.pre-commit-config.yaml` with detect-secrets, ruff format, ruff lint, biome (once JS exists)

**Exit criteria:** CI green on an otherwise-empty repo; `docker compose up -d redis postgres` works; pre-commit hooks install and run.

### Phase 2 — Shared schemas + hasher + envelope

- `agents/common/schemas/envelope.py` + the 6 payload models per 07_LLD §4
- `agents/common/hasher.py` per 07_LLD §1.1
- `scripts/export_schemas.py` — Pydantic → JSON Schema files under `web/lib/schemas/generated/`
- `scripts/generate_zod.ts` — JSON Schema → zod files under `web/lib/schemas/`
- Unit tests for all models (validation edge cases) and hasher (TC-U40-43)
- CI step added: schema drift gate (TC-I11)

**Exit criteria:** All TC-U40-43 pass; schemas export deterministically; drift gate green.

### Phase 3 — FindingsRegistry contract

- `contracts/foundry.toml`
- `contracts/src/FindingsRegistry.sol` verbatim from 07_LLD §3.1
- `contracts/test/FindingsRegistry.t.sol` covering TC-C01-10
- `contracts/test/FindingsRegistry.fuzz.t.sol` covering TC-C20-21
- `contracts/test/FindingsRegistry.invariant.t.sol` covering TC-C30-31
- `contracts/script/Deploy.s.sol`
- `.github/workflows/contract.yml` with coverage gate
- Deploy to BNB Testnet; capture address to `.env.example` as a placeholder; record deploy tx and address in `docs/DEPLOYMENT.md` (a new small doc)

**Exit criteria:** `forge coverage` reports 100%; deploy tx succeeded; address written to `.env`; `verifyFinding(0x00...00)` returns zero struct from RPC.

### Phase 4 — Message bus + LLM router with mocked providers

- `agents/common/bus.py` per 07_LLD §1.1
- `agents/common/llm_router.py` per 07_LLD §1.1
- `agents/common/on_chain.py` per 07_LLD §1.1
- `agents/common/db.py` per 07_LLD §1.1
- `agents/common/base_agent.py` per 07_LLD §1.1
- `agents/common/health.py` + `metrics.py`
- Unit tests: TC-U01-04, TC-U10-13, TC-U20-28, TC-U30-34
- Integration: TC-I04 (with a trivial dummy agent)

**Exit criteria:** All named TC-U### for common modules pass; 100% coverage on `agents/common/`.

### Phase 5 — Hunter agent

- `agents/hunter/main.py` per 07_LLD §1.2
- `agents/hunter/sources/` — both `FourMemePollingSource` and `FourMemeRPCLogSource` interfaces; pick one at runtime via env var `FOURMEME_SOURCE`
- Unit tests TC-U50-53
- Dockerfile
- Add service to `docker-compose.yml`

**Exit criteria:** Hunter runs under compose; ingests a mock event; publishes envelope to `stream:candidates`; records hash on Anvil.

### Phase 6 — Chain + Social agents in parallel

Both consume `stream:candidates` via their own groups; both can be developed in parallel commits.

- Chain: `agents/chain/` per 07_LLD §1.4; unit tests TC-U70-72
- Social: `agents/social/` per 07_LLD §1.3; unit tests TC-U60-63
- Playwright stealth scrapers: adapt from HACK0014 `scrape_chats_v2.py` (path: `C:\Users\v_sen\Documents\Claude\read_shared_link_code\`)
- Each agent publishes to its own stream with on-chain hash

**Exit criteria:** Given one TokenCandidate, both agents produce envelopes on `stream:social` and `stream:chain`; both hashes recorded on Anvil.

### Phase 7 — Risk agent

- `agents/risk/main.py` per 07_LLD §1.5
- `agents/risk/heuristics.py` — all 15 rules from 07_LLD §1.5; each rule is a named callable
- Two-stream consumer group logic with 120s join timeout (FR-061)
- Unit tests TC-U80-84 (including all 15 heuristic tests)
- Failure test TC-F05 (all LLMs down)

**Exit criteria:** Given paired SocialScore + ChainMetrics, produces RiskVerdict; honours 120s timeout; handles LLM exhaustion with requires_human_review.

### Phase 8 — Narrator agent

- `agents/narrator/main.py` per 07_LLD §1.6
- Lineage-fetch from Postgres
- Unit tests TC-U90-92
- Split-stream publish: `stream:briefs` or `stream:human_review`

**Exit criteria:** Given a RiskVerdict, produces an AlphaBrief with full model attribution; degraded upstream produces degraded brief.

### Phase 9 — FastAPI public API

- `api/main.py` + `api/routes/briefs.py` + `api/routes/ws.py` + `api/routes/health.py` per 07_LLD §1.7
- Rate-limit middleware (FR-203)
- OpenAPI at `/docs` and `/openapi.json`
- WebSocket subscribes to Redis Pub/Sub
- Integration tests TC-I05, TC-I06, TC-I10
- E2E preparation: TC-E05

**Exit criteria:** `/briefs`, `/briefs/{id}`, `/briefs/{id}/verify`, `/health`, `/metrics`, `/ws/events` all responsive; OpenAPI schema matches Pydantic models.

### Phase 10 — Telegram bot

- `bot/main.py` + `bot/handlers/` per 07_LLD §1.8
- All 7 commands per FR-161
- Brief consumer loop (FR-166)
- Dedup Redis SET (FR-165)
- Threshold filtering (FR-162, UC-12)
- Integration tests TC-I07-09
- E2E TC-E01-04, TC-E10

**Exit criteria:** Bot responds to all commands; delivers briefs only to users above threshold; dedupes correctly; handles Telegram 429.

### Phase 11 — Next.js dashboard

- `web/` scaffolding per 07_LLD §2
- Server components for SSR (FR-181, FR-182)
- Client components: BriefCard, SwarmHealthPanel, ModelUsagePanel, ActivityTimelinePanel
- WebSocket hook per 07_LLD §2.4 with reconnect + polling fallback
- Mobile-responsive layout (FR-187)
- Vitest unit tests TC-U100-109
- Playwright E2E TC-E06, TC-E06m, TC-E07, TC-E09

**Exit criteria:** Dashboard at `http://localhost:3000` shows live feed, 4 panels, every brief click-through reaches BscScan; mobile viewport works; WebSocket reconnects.

### Phase 12 — E2E harness + deployment

- Full E2E suite runs against `docker-compose.test.yml` with mocked externals
- `.github/workflows/e2e.yml`
- VPS deploy script (`scripts/deploy.sh`)
- nginx config + Let's Encrypt
- `.github/workflows/deploy.yml` triggered on tag
- Smoke test (`scripts/smoke_test.sh`) runs post-deploy per 08_TestPlan §17
- Demo video recording (3 minutes) — scripted with Playwright (`scripts/record_demo_video.sh`) OR manual OBS capture
- DoraHacks submission: GitHub repo link + video + form

**Exit criteria:** All submission artefacts in place before 16:59 UTC; smoke test green; video under 3 minutes showing: dashboard live updates, brief with verify click-through to BscScan, Telegram alert, /verify round-trip, multi-provider model usage panel.

---

## 4. Per-component exit criteria (summary)

Every phase exits only when:

1. All named test cases for that phase pass
2. Coverage report for that phase's code shows 100% (line + branch for Py/Sol, all 4 metrics for TS)
3. `ruff`, `mypy --strict`, `biome`, `tsc --noEmit --strict` green
4. CI green on the push
5. Commits follow Conventional Commits
6. Grep for "for demo purposes" returns zero

If any criterion fails, the phase is not done. Move to the next phase only when all six are met.

---

## 5. Known issues to resolve during build

These are flagged here so the Build Session addresses them deliberately, not accidentally.

| # | Issue | Resolution path |
|---|---|---|
| 1 | DGrid API key not yet obtained | User registers at DGrid during Phase 4; fallback to direct-provider keys works in the meantime |
| 2 | Four.meme event-source API surface (A-01) | During Phase 5, probe the Four.meme platform; pick `FOURMEME_SOURCE=polling` or `rpc_log` based on what's available. Adapter pattern means no business-logic change |
| 3 | BscScan free-tier rate limits | During Phase 6, measure actual call rate; if insufficient, document that a paid tier is required for production (not a release blocker for hackathon) |
| 4 | BNB Testnet gas faucet top-ups | Script `scripts/seed_testnet_wallet.sh` handles this; run before Phase 3 deploy and periodically thereafter |
| 5 | Playwright stealth from HACK0014 may need updates | During Phase 6, test against live X and Telegram; if blocked, fall back to `data_quality: degraded` path rather than over-engineering evasion |
| 6 | Single-VPS SPOF | Documented as v2 work in 02_Architecture.md §4.13 Trade-offs; not a blocker |
| 7 | "Fox" reference from architecture session | User has dropped from scope; no action |
| 8 | Demo video needs to be recorded | Phase 12 step; use Playwright-driven capture for reproducibility, or OBS for a voiced walkthrough. Target 2:45 for safety margin |

---

## 6. Common pitfalls to anticipate

1. **Do not write tests after the fact.** Tests and code commit together; 100% coverage emerges naturally if tests are written alongside.
2. **Do not skip the canonical JSON step in the hasher.** sort_keys=True, ensure_ascii=False, separators=(',',':') — all three. Without these, hashes won't reproduce across Python / BscScan / BscScan UI / third-party tools.
3. **Do not conflate `msg_id` formats.** ULID in application code; bytes32 for contract calls (left-padded / encoded). Envelope stores ULID string; on-chain adapter converts at the boundary.
4. **Do not assume DGrid is up during development.** Mock it by default; use direct providers when real calls are needed.
5. **Do not let the pre-commit hook be optional.** Install it in Phase 1; commits without it bypass detect-secrets.
6. **Do not use `# type: ignore` or `// @ts-ignore` without a comment explaining why.** Grep check in CI forbids new ones without a justification marker `# type: ignore[reason: ...]`.
7. **Do not commit secrets to `.env.example`.** Examples only; real values live in gitignored `.env`.
8. **Do not forget the schema drift gate.** Every change to a Pydantic model that affects wire format must re-export schemas in the same commit.
9. **Do not use asyncio.gather on agent main-loops.** Each agent is its own process; gather is for intra-agent parallelism (e.g., parallel BscScan calls).
10. **Do not skip integration tests because "unit tests cover it."** Unit tests mock; integration tests catch mock-divergence from reality. Both are required.

---

## 7. Submission checklist (Phase 12 final)

Before hitting Submit on DoraHacks, all of the following must be true:

- [ ] GitHub repo public and accessible
- [ ] README at repo root has clear quickstart, architecture link, live dashboard URL
- [ ] `docs/` contains all 10 documents
- [ ] CI green on `main`
- [ ] Coverage badge or report visible (or linked)
- [ ] FindingsRegistry contract verified on BscScan (source code + ABI visible)
- [ ] Live dashboard URL reachable (HTTPS)
- [ ] Telegram bot responsive to `/start`
- [ ] Public API `GET /health` returns 200
- [ ] Demo video ≤ 3 minutes, shows: (1) dashboard live updates, (2) clicking Verify → BscScan, (3) Telegram alert arriving, (4) `/verify` in bot returning lineage, (5) model usage panel showing multi-provider routing
- [ ] Submission form filled with: project name, one-liner, team (Senthil solo), track (AI Sprint + DGrid bounty), GitHub URL, video URL, live demo URL, contract address on BNB Testnet

---

## 8. After submission

Regardless of outcome:

- Tag the submitted commit as `v0.1.0-hackathon`
- Create `docs/POST_SUBMISSION.md` with observed bugs, judging feedback (when received), and post-hackathon roadmap items (migrate Redis to managed, audit contract for mainnet, add authenticated API, etc.)
- Do not keep operating the testnet wallet indefinitely — rotate the key when the hackathon submission window closes

---

## 9. Start signal for the Build Session

The Build Session replies to its first prompt with:

1. Confirmation that §1 rules are understood
2. The first git-init + README commit (Phase 1 step 1)
3. Stop for Senthil to run `git log` and confirm

No other preamble, no other questions.

---

**End of BUILD_SESSION_PROMPT.md**
