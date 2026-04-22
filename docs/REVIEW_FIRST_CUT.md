# First-Cut Review — Honest Audit

**Purpose:** This is the complete, unvarnished accounting of what the web Build Session (Claude Opus 4.7, 2026-04-22 06:36 – 07:25 UTC) actually produced, what was claimed but not delivered, and what is deferred to the Desktop Build Session.

**Read this together with `docs/TRACEABILITY.md`.**

---

## 1. Summary in one paragraph

The repo contains a plausible, architecturally coherent, **first cut** of SwarmScout: 125 files, ~7,400 lines of real code, spanning Python agents, Solidity contract, FastAPI, Telegram bot, Next.js dashboard, and test skeletons in all three languages. **The build session did not execute a single test, did not run `mypy --strict`, did not run `ruff`, did not run `pip install`, did not run `forge build`, did not run `pnpm install`, did not `git init`, did not deploy the contract, and did not record the demo video.** Everything structural is in place; everything runtime is unverified. Desktop's job is to close the gap between "written" and "proven green".

## 2. What was genuinely delivered

### 2.1 Quantitative

| Layer | Files | Lines |
|---|---|---|
| Python (agents + api + bot) | 38 production files | 4,247 |
| Python tests | 7 files | 1,309 |
| Python scripts | 1 file (`export_schemas.py`) | 55 |
| Python infra | 3 files (Dockerfile, SQL, conftest) | — |
| TypeScript / TSX (web) | 10 production files + 2 configs | 596 |
| TypeScript / TSX tests | 5 files (Vitest + Playwright) | 431 |
| TypeScript / TSX script | 1 file (`generate_zod.ts`) | 69 |
| Solidity contract | 1 file | 149 |
| Solidity tests | 3 files (unit, fuzz, invariant) | 275 |
| Solidity script | 1 file (Deploy.s.sol) | 18 |
| Shell scripts | 4 files (deploy, smoke, seed, demo) | 95 |
| Docs | 15 `.md` files | 5,657 lines copied from `/mnt/project/` + 3 new (DEPLOYMENT, POST_SUBMISSION, NEXT_PROMPT_FOR_DESKTOP) + this file + TRACEABILITY |
| CI / infra configs | 11 files (workflows, compose, pyproject, etc.) | — |
| **Total** | **125 files** | **~575 KB** |

### 2.2 Qualitative

What is genuinely present and internally consistent:

1. **Canonical-JSON hasher** with all three required flags (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`) and unit tests that verify determinism, unicode preservation, and NaN rejection.
2. **Envelope schema** with ULID validation, Crockford-base32 alphabet enforcement, ISO-8601 timestamp check, `extra="forbid"`, and the payload_hash formatted so that the bytes32 adapter and the hex adapter agree.
3. **Redis Streams bus** with PEL-first redelivery, consumer groups, approximate MAXLEN trim, XPENDING depth, and a dedicated test for crash-recovery redelivery.
4. **LLM router** with DGrid primary, 3-failure circuit breaker with 60s cooldown, per-provider direct fallback (Anthropic/OpenAI/Google), Redis token-bucket rate limiting, full audit logging, and cost estimation from a pricing table. Tests exercise happy path, single-failure fallback, circuit trip, circuit reset, rate limit, and exhaustion.
5. **On-chain adapter** with `msg_id_to_bytes32` and `payload_hash_hex_to_bytes32` encoders that are symmetric, plus a `NullAnchor` for tests and a real `OnChainAnchor` that builds, signs, sends, and awaits a transaction.
6. **Postgres data layer** with four repositories (findings, llm_calls, subscriptions, heartbeats), proper indices, `JSONB` payload column, and async SQLAlchemy 2.0 patterns.
7. **Base agent** that enforces the hash-then-persist-then-anchor-then-publish ordering in one place — every concrete agent calls `anchor_and_publish()` and cannot accidentally invert it.
8. **Five concrete agents** — each one inherits `BaseAgent`, implements a `_main_loop` that consumes from the correct Redis stream with the correct consumer group, validates the incoming envelope's payload against the correct Pydantic model, and emits the correct downstream envelope with the full `upstream_ids` chain.
9. **All 15 named risk heuristics** as pure callables, each with an individual unit test plus tests for the `honeypot-suspected` short-circuit and the zero-floor of `aggregate_score`.
10. **FastAPI app factory** with `lifespan` context manager, CORS, IP-based rate-limit middleware backed by Redis, three route modules, and a Prometheus `/metrics` endpoint.
11. **Telegram bot** with every one of the 7 commands in FR-161, a separate delivery loop task, Redis-SET dedup with 7-day TTL, Markdown brief formatting, and a `TelegramRetryAfter` handler for 429s.
12. **Next.js 14 dashboard** with server-rendered feed page, four client panels (BriefCard, SwarmHealth, ModelUsage, ActivityTimeline), a `FeedStream` client wrapper, a `useBriefStream` hook with exponential-backoff reconnect + polling fallback after 3 failures, strict TypeScript, and responsive Tailwind grid.
13. **FindingsRegistry contract** with access control, custom errors, events, `append-only` guarantee, plus 15 unit tests covering all error paths, 2 fuzz tests, and 2 invariants proving recorded hashes never change.
14. **CI workflows** for Python (lint + mypy + pytest with coverage gate), Contracts (forge coverage gate ≥100%), E2E (Playwright). Plus pre-commit config with detect-secrets, ruff, and the critical `no-demo-phrase` grep hook.
15. **Docker Compose** with Redis (AOF on, `everysec` fsync), Postgres 16 with init SQL, all five agent services, API, bot, and web dashboard.
16. **Six automation scripts**: schema export (drift gate), zod generator, deploy, smoke test, wallet seed, demo video recorder.

## 3. What was written but NOT proven

### 3.1 Tests exist but were never executed

The single most important disclaimer. The following were **written** but the session did not run them:

- `pytest` — not run. Probable result: several failures on first run due to:
  - Async fixture patterns might need adjustment for `pytest-asyncio ≥ 0.23` loop scope rules.
  - `test_bus_decodes_valid_envelope_field` expects a `ValueError` from direct malformed `xadd`; the wrapping in `_decode` might or might not surface it via `async for`.
  - `_FakeProvider` classes do not formally implement the `ProviderClient` Protocol, which will trip `mypy --strict`.
  - `test_rate_limit_kicks_in` tests for 60 requests with the default cap of 60 but the loop runs 70; it then accepts either 200 or 429 — which is loose but should pass.
- `mypy --strict` — not run. Likely findings:
  - `_FakeProvider` / `_FakeLLMCallRepo` / `_FakeHTTP` in test files not properly typed against Protocols.
  - Some `# type: ignore[arg-type]` markers missing the `[reason: ...]` suffix that pre-commit enforces.
  - `web3` / `eth_account` types may surface as `Any`.
- `ruff check` / `ruff format --check` — not run. Likely findings:
  - A few long lines may exceed 100.
  - S-lint (bandit) may flag the `# noqa: S108` on the `PLAYWRIGHT_USER_DATA_DIR=/tmp/...` default.
- `forge build` — not run. Likely findings:
  - `contracts/lib/forge-std` submodule is declared in `.gitmodules` but not yet pulled; `forge build` will fail until Desktop runs `git submodule update --init --recursive`.
  - `via_ir = true` with optimizer=200 on 0.8.24 sometimes warns on older LLVM; no known blockers.
- `forge test` / `forge coverage` — not run. Contract tests look right by eye but have not been executed. The invariant handler's `try/catch` around `recordFinding` is a pattern that works but some Foundry versions need `failOnRevert=false` already set in the profile (it is).
- `pnpm install` / `tsc --noEmit --strict` / `vitest` / `pnpm exec playwright test` — not run.
  - `useBriefStream` test uses a `MockWebSocket` class with a static `instances` array — works, but the hook's `connect` callback is captured via `useRef` and the test assumes specific call ordering; may be flaky.
  - `panels.test.tsx` mutates `globalThis.fetch` per test without restore — should still pass since later tests overwrite it, but a lint rule may flag it.
  - `@playwright/test` Playwright tests have no dev server running, so they will fail locally unless Desktop starts the app first.

### 3.2 Private-attribute access in tests

`tests/unit/test_llm_router.py` accesses `router._dgrid_available()` and `router._dgrid_health.consecutive_failures` directly. This is a minor code smell — a more hygienic version would expose a public probe. Desktop can decide whether to refactor or leave as-is. Not blocking.

### 3.3 Integration coverage is shallow

- `tests/integration/test_api.py` monkey-patches `app.router.lifespan_context`, which works but is fragile against FastAPI internal changes. A more robust approach is to call `create_app()` and use `TestClient(app)` directly without entering the lifespan; but lifespan setup is how the state dict gets populated, so the patch is the correct workaround.
- There is no integration test that runs Hunter → Social → Chain → Risk → Narrator end-to-end through a real fakeredis. This is **TC-I04** in the plan; it is not present. Desktop should add one to prove the envelope chain is correctly constructed.
- There is no dedicated Telegram integration test. The `aiogram` dispatcher is mocked out and the handlers are trivial, but a TestBot or message-driving harness would be better.

### 3.4 RPC-log source uses a placeholder event topic

`agents/hunter/sources/rpc_log.py` has `TOKEN_CREATED_TOPIC = "0x" + "00" * 32` as a placeholder. If `FOURMEME_SOURCE=rpc_log` is set before Desktop pastes the real event signature hash, the Hunter agent will receive zero events. Desktop must find the real Four.meme factory `TokenCreated` event and replace both `TOKEN_CREATED_TOPIC` and `FOURMEME_FACTORY_ADDRESS`.

### 3.5 Honeypot and LP-locked are surrogates

`ChainAgent._gather` uses `meta.verified` as a proxy for `honeypot_check_passed` and sets `lp_locked=False` unconditionally. This is documented in the code comments as a first-cut placeholder. Desktop should either (a) integrate a honeypot.is API, or (b) accept the surrogate and update `docs/POST_SUBMISSION.md` to list the real check as 30-day roadmap.

### 3.6 Demo video, VPS deploy, contract deploy, Telegram bot registration

All four require external services, live credentials, and human action. The scripts are written but have not been executed. This is Desktop's Phase D work.

## 4. What is genuinely missing and must be added

1. **`contracts/lib/forge-std` submodule content** — `.gitmodules` declares it; `git submodule update --init --recursive` must be run.
2. **Schema-export artefacts** — `web/lib/schemas/generated/*.schema.json` and `*.zod.ts` are not in the repo. Desktop must run `python scripts/export_schemas.py` once, commit the output, so the CI drift gate has a baseline to compare against.
3. **deploy.yml workflow** — `.github/workflows/` currently has `ci.yml`, `contract.yml`, `e2e.yml` but not `deploy.yml` (tag-triggered). The plan in BUILD_SESSION_PROMPT §Phase 12 mentions it; Desktop should add one or accept `scripts/deploy.sh` as the manual path.
4. **Pre-commit hook for `mypy` and `tsc`** — currently only runs detect-secrets, ruff, and the demo-phrase grep. Adding mypy and tsc to pre-commit would catch type errors earlier.
5. **Performance test files (TC-P##)** and **security test files (TC-S##)** — not written. The plan calls for them in `docs/09_TestCases.md` but they are deferred. At minimum Desktop should decide whether to write them or document the deferral.
6. **Additional failure tests (TC-F01-04)** — only TC-F05 (all LLMs down) is written. The plan names 5 failure tests; 4 are missing.
7. **End-to-end integration test (TC-I04)** — described above.
8. **Bot command tests** beyond threshold / format — `on_start`, `on_stop`, `on_status`, `on_latest`, `on_verify`, `on_help` have no dedicated tests.
9. **Real Four.meme factory address + event topic** — see §3.4.
10. **Real honeypot check integration** — see §3.5.
11. **FindingsRegistry bytecode verified on BscScan** — part of Phase D; verifies the deployed address matches source.

## 5. Known bugs / suspected issues

| # | File | Issue | Severity |
|---|---|---|---|
| 1 | `agents/hunter/sources/polling.py::_fetch_batch` | Last-seen dedup logic re-uses `newest` but only from index 0; if the API returns out-of-order newest-last lists, dedup breaks | medium |
| 2 | `agents/hunter/sources/rpc_log.py::_decode` | Topic address slicing `[-40:]` truncates correctly for bytes32-encoded addresses but fails silently for non-hex inputs | low |
| 3 | `agents/social/main.py::_gather` | Scraper exceptions escape `_gather`; `_main_loop` catches via the outer try/except but the `data_quality` path is not exercised | low |
| 4 | `agents/risk/main.py::_on_message` | "Same-side twice" case overwrites the earlier envelope silently — intended but worth a log line | low |
| 5 | `agents/chain/main.py::_gather` | Uses `asyncio.gather(..., return_exceptions=True)` but then pattern-matches via `isinstance(_, Exception)` — fragile if any future sub-call returns an `Exception`-derived success type | low |
| 6 | `api/main.py::metrics` | ~~Creates a fresh `CollectorRegistry(auto_describe=True)` per request, which will not include agent metrics registered in the default registry. Should be `generate_latest()` over the *default* registry.~~ **FIXED 2026-04-22 08:34** — now uses `REGISTRY` from `prometheus_client`. | ~~high~~ resolved |
| 7 | `api/routes/ws.py` | ~~The WebSocket handler subscribes to `pubsub:briefs`, but **no agent actually publishes to that channel** — agents publish to `stream:briefs` (the Redis stream). The WS endpoint will appear to work but never receive anything.~~ **FIXED 2026-04-22 08:34** — `BaseAgent.anchor_and_publish` now fans out to `pubsub:briefs` whenever the target stream is `stream:briefs`. Covered by `tests/unit/test_base_agent_pubsub.py`. | ~~high~~ resolved |
| 8 | `bot/main.py::_delivery_loop` | ~~Same channel-name mismatch possible — verify agents publish to both the stream and the pubsub, or rework the WS to consume the stream with `$`-offset~~ **Not a bug on re-inspection** — the bot correctly consumes `stream:briefs` via the `bot:delivery` consumer group (`bot/main.py:42`). No fix needed. | resolved (false alarm) |
| 9 | `web/lib/hooks/useBriefStream.ts` | `scheduleReconnect` is defined inside `connect` but referenced in `onDisconnect`; TS might warn about implicit use-before-declare. Functionally correct thanks to hoisting of function declarations, but a stricter linter may flag it | low |
| 10 | `contracts/test/FindingsRegistry.invariant.t.sol::Handler.recordFinding` | Uses `try/catch` to silently accept reverts, but the handler then *also* calls `recordFinding` on an already-recorded msgId expecting a revert; logic is correct but fragile against Foundry handler internals | low |

**Bugs #6, #7, #8 are real and material.** They need fixing before the demo video is shot, because the live-update story is a core demo beat.

Recommended fixes (Desktop):

- **#6**: Replace `CollectorRegistry(auto_describe=True)` with the module-level `REGISTRY` from `prometheus_client`.
- **#7 + #8**: Make `BaseAgent.anchor_and_publish` also call `self.bus.client.publish("pubsub:briefs", json_body)` when publishing to `stream:briefs`. One-line change; unit test it.

## 6. Areas of solid confidence

Despite the unverified status, the following are very likely correct on first run:

- Canonical-JSON hasher (tight, well-tested).
- Pydantic schemas (validators are straightforward).
- FindingsRegistry contract (small surface; tests cover every public function and every custom error).
- Envelope → Redis → Envelope round-trip (test already exists).
- Risk heuristic rules (pure functions with single assertions).
- MoSCoW prioritisation baked into traceability.

## 7. Size of the gap for Desktop

Rough calibration, measured in "engineering hours of a competent solo developer":

| Task | Hours |
|---|---|
| Get dependencies installed + pre-commit working | 0.5 |
| First pytest run, fix initial failures | 1.5 |
| First mypy run, fix type errors | 1.0 |
| First ruff run, fix lint | 0.25 |
| First Vitest run | 0.5 |
| First Playwright run (requires running app) | 0.75 |
| First forge test run (after submodule init) | 0.25 |
| Fix the three material bugs (§5 items 6/7/8) | 1.0 |
| Deploy contract, paste address, verify on BscScan | 1.0 |
| Stand up VPS, nginx, certbot | 1.5 |
| Register Telegram bot, wire token | 0.5 |
| Record demo video | 1.0 |
| Fill DoraHacks submission form | 0.25 |
| Buffer | 1.0 |
| **Total** | **~11 h** |

This matches the plan's Phase D + Phase E allocation. Time remaining at the Desktop handoff was ~9 h per BUILD_SESSION_PROMPT; the 11-hour estimate above is solo developer with Desktop AI assistance, which historically compresses to ~8-10 h in practice. **Realistic chance of on-time submission: high, if Desktop starts immediately.**

## 8. Recommended Desktop sequence

Derived from NEXT_PROMPT_FOR_DESKTOP.md but tightened:

1. Unpack zip, `cd`, verify layout matches TRACEABILITY.md.
2. Read this file (`docs/REVIEW_FIRST_CUT.md`) and `docs/TRACEABILITY.md` end-to-end.
3. Fix known material bugs first (§5 items 6/7/8) before running any test — this saves chasing symptoms caused by the WS mismatch.
4. `git submodule add https://github.com/foundry-rs/forge-std contracts/lib/forge-std` if not already present.
5. Run `python scripts/export_schemas.py` once, commit the generated artefacts.
6. Install deps (`pip install -e ".[dev]"`, `cd web && pnpm install`, `forge install`).
7. `pre-commit install`.
8. Run `pytest -x` — fix every failure immediately; do not batch.
9. Run `mypy agents api bot` — fix every error or justify with `# type: ignore[reason: ...]`.
10. Run `ruff check .` and `ruff format --check .`.
11. `cd web && pnpm test` — fix every failure.
12. `cd contracts && forge test` — fix every failure.
13. Now start the remote: `git init`, commit sequence per NEXT_PROMPT §3, push to GitHub.
14. Wait for CI green. Fix anything red.
15. Deploy contract. Paste address. Verify on BscScan.
16. Stand up VPS. Deploy. Smoke-test.
17. Register Telegram bot. Verify `/start` works end-to-end.
18. Record demo video.
19. Fill DoraHacks submission form.
20. Tag `v0.1.0-hackathon` and push.

## 9. What not to do

- Do not rewrite any of the 9 design docs. They are authoritative.
- Do not shrink coverage to "get green". Per rule 1.4: shrink features, never coverage.
- Do not skip pre-commit. Committing with `--no-verify` defeats detect-secrets.
- Do not commit `.env`.
- Do not introduce the phrase "for demo purposes" anywhere.
- Do not commit multiple logical changes together.

---

## 10. Attribution

- **First-cut build:** Claude Opus 4.7 (web Build Session), 06:36–07:25 UTC, 2026-04-22
- **Session tool ceiling:** web UI enforces a per-response tool-call ceiling that made the build run across 8 turns; see the chat history for the turn-by-turn progression
- **Review + traceability author:** same session, final two turns
- **Handoff target:** Claude Desktop with Filesystem + Shell MCPs enabled, live credentials for GitHub / BNB Testnet / Telegram / DGrid / BscScan

---

**End of REVIEW_FIRST_CUT.md**
