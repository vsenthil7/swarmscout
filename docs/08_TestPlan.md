# 08 — Test Plan

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 07:35 UTC

This document defines **how** SwarmScout is tested: strategy, scope, layers, environments, tooling, entry and exit criteria, coverage gates, and roles. It is the master contract that 09_TestCases.md populates with specific cases.

No scope shrink on coverage (rule 2.4). The phrase "for demo purposes" does not appear.

---

## 1. Purpose

Describe the testing strategy for SwarmScout such that any competent engineer, reading this document and 09_TestCases.md, can:

1. Know which test runs where
2. Know which tool is used at each layer
3. Know what "done" means at each layer
4. Independently reproduce every CI gate locally

The plan satisfies NFR-320 through NFR-327 (100% coverage across Python, TypeScript, Solidity; CI enforcement; commit discipline).

---

## 2. Scope

### 2.1 In scope

| Layer | Tool | Coverage target |
|---|---|---|
| Python unit tests | pytest + pytest-asyncio + pytest-cov | 100% line + 100% branch |
| Python integration tests | pytest + testcontainers (Redis, Postgres) | Every component boundary exercised against real infrastructure |
| Smart contract unit tests | Foundry `forge test` | 100% line + 100% branch (`forge coverage`) |
| Smart contract property tests | Foundry fuzz + invariant | Every invariant from 07_LLD §3.2 covered |
| TypeScript unit + component tests | Vitest + @vitest/coverage-v8 + Testing Library | 100% lines, branches, functions, statements |
| E2E browser tests | Playwright | Every M-priority user flow from 05_UserFlow.md |
| HTTP mocking (Py) | respx | Deterministic LLM + external-API replay |
| HTTP mocking (TS) | MSW | Deterministic Next.js API replay |
| Schema drift detection | Git diff on generated JSON Schema + zod | 0 drift |
| Lint + type-check | ruff, mypy --strict, biome, tsc --noEmit --strict | 0 warnings |
| Pre-commit | detect-secrets, ruff format, biome format | 0 leaks |

### 2.2 Out of scope (this release)

| Area | Reason |
|---|---|
| Load / soft-real-time performance tests beyond 30 candidates/min burst (NFR-202) | Single-VPS target |
| Chaos-at-scale (multi-agent concurrent kill across many workers) | Single-instance per agent in v1 |
| Penetration testing | Post-hackathon |
| Formal verification of contract | Testnet only; audit before mainnet |
| Visual regression testing | Post-hackathon |
| Cross-browser matrix beyond Chromium + Firefox + WebKit | Playwright defaults cover the three majors |
| i18n testing | W-09 |
| Accessibility beyond WCAG 2.1 AA spot-checks | Post-hackathon |

---

## 3. Test strategy — the layered pyramid

```
                     ┌──────────────────────────┐
                     │    E2E  (Playwright)     │    Every M user flow
                     └──────────────────────────┘
                  ┌────────────────────────────────┐
                  │  Integration (pytest + TC)     │   Every component boundary
                  └────────────────────────────────┘
              ┌──────────────────────────────────────┐
              │  Unit  (pytest / Vitest / Foundry)   │  100% line + branch
              └──────────────────────────────────────┘
         ┌────────────────────────────────────────────────┐
         │  Static  (ruff, mypy, biome, tsc, forge check) │   Baseline gate
         └────────────────────────────────────────────────┘
```

Each layer has distinct purpose, speed, and cost:

| Layer | Purpose | Speed | When it runs |
|---|---|---|---|
| Static | Catch syntax / type / style / secret issues | < 10s | Pre-commit + CI |
| Unit | Prove each function's behaviour in isolation | < 30s (full suite) | Every commit |
| Integration | Prove components interact correctly with real Redis/PG | < 2 min | Every commit |
| E2E | Prove user flows work end-to-end in a browser | < 5 min | Every commit |
| Contract | Prove Solidity correctness, including fuzz and invariants | < 30s | Every commit |

---

## 4. Test environments

### 4.1 Local developer environment

- `docker compose up` starts Redis + Postgres
- `pytest` runs against them (configured via env in `.env.test`)
- `pnpm vitest` runs TS tests
- `forge test` runs contract tests against Foundry's local EVM
- `pnpm playwright test` runs E2E against the local `docker compose` stack

### 4.2 CI environment (GitHub Actions)

- `ubuntu-latest` runner
- Redis 7 + Postgres 16 as GitHub Actions service containers
- Foundry toolchain installed via `foundry-rs/foundry-toolchain@v1`
- Node 20, Python 3.11, pnpm via `pnpm/action-setup`
- Playwright browsers installed via `pnpm playwright install --with-deps`
- Anvil (Foundry's local Ethereum node) for on-chain integration tests

### 4.3 Demo / staging environment (single VPS)

- Full live stack under the production `docker-compose.yml`
- Receives real Four.meme events, writes real hashes to BNB Testnet
- Smoke test script (`scripts/smoke_test.sh`) validates every public surface after deploy

### 4.4 Environment isolation guarantees

- **Unit tests** never touch network, real LLM providers, or real BNB RPC — all mocked
- **Integration tests** may use Redis/PG in containers; never call real LLM providers or BscScan; use `respx` / fixture replay
- **E2E tests** run against a dedicated `docker compose -f docker-compose.test.yml` with mocked external services
- **CI tests never hit real external APIs** — this keeps CI deterministic and free of provider-side rate limits

---

## 5. Test data strategy

### 5.1 Factories

- Python: `factory-boy` generates deterministic `TokenCandidate`, `SocialScore`, `ChainMetrics`, `RiskVerdict`, `AlphaBrief` instances
- TypeScript: `@faker-js/faker` seeded for deterministic runs

### 5.2 Fixtures

- `conftest.py` provides shared fixtures:
  - `redis_client` (testcontainers-redis)
  - `pg_session` (testcontainers-postgres, migrations run, auto-rollback per test)
  - `mock_llm_router` (returns pre-scripted responses)
  - `mock_on_chain` (records calls; never touches chain)
  - `anvil_w3` (Foundry Anvil for on-chain integration tests)
  - `frozen_time` (freezegun for deterministic timestamps)

### 5.3 Replay fixtures

- `tests/fixtures/llm_responses/` — pre-recorded provider responses for deterministic LLM tests via `respx`
- `tests/fixtures/bscscan/` — pre-recorded BscScan responses
- `tests/fixtures/fourmeme/` — pre-recorded Four.meme events
- `tests/fixtures/x_scrape/` — pre-recorded Playwright HTML captures

**Golden-file policy:** updating a replay fixture requires a commit message including `test-data-update:` prefix and a human rationale.

---

## 6. Coverage gates

### 6.1 Python (`pyproject.toml` excerpt)

```toml
[tool.pytest.ini_options]
addopts = "--cov --cov-branch --cov-fail-under=100 --cov-report=term-missing --cov-report=xml -q"
asyncio_mode = "auto"

[tool.coverage.run]
branch = true
source = ["agents", "api", "bot"]
omit = ["*/tests/*", "*/__main__.py"]

[tool.coverage.report]
fail_under = 100
show_missing = true
skip_covered = false
exclude_lines = [
  "pragma: no cover",
  "if __name__ == .__main__.:",
  "raise NotImplementedError",
]
```

**No `exclude_lines` additions** without a committed justification in CONTRIBUTING.md.

### 6.2 TypeScript (`vitest.config.ts` excerpt)

```typescript
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      thresholds: {
        lines: 100,
        branches: 100,
        functions: 100,
        statements: 100,
      },
      exclude: ['**/*.config.*', '**/node_modules/**', '.next/**'],
    },
  },
});
```

### 6.3 Solidity (`forge coverage`)

- CI runs `forge coverage --report summary`
- `scripts/check_forge_coverage_100.sh` parses output and exits 1 on any line or branch < 100%

### 6.4 Schema drift gate

- `python scripts/export_schemas.py` regenerates JSON Schema → zod
- CI runs `git diff --exit-code web/lib/schemas/` — any difference fails the build

---

## 7. Test case identification scheme

Every test case has a unique ID consumed in 09_TestCases.md:

| Prefix | Meaning |
|---|---|
| TC-U### | Unit test case |
| TC-I### | Integration test case |
| TC-C### | Contract test case (Solidity) |
| TC-E### | End-to-end test case (Playwright) |
| TC-F### | Failure-mode test case (from 02_Architecture.md §6 table) |
| TC-P### | Performance / load test case |
| TC-S### | Security test case |

Test case IDs are referenced from: 02_Architecture.md §6 (failure modes) and 05_UserFlow.md (user flow coverage table).

---

## 8. Entry criteria

Before starting any test execution:

1. All source files compile / type-check (ruff, mypy, biome, tsc all pass)
2. `docker compose up -d redis postgres` succeeds locally (or GitHub Actions services are ready)
3. `.env.test` populated with mock credentials
4. Database schema applied (alembic / manual SQL; see Known Gaps)
5. Contract artefacts built: `forge build` succeeds

---

## 9. Exit criteria

A commit is **releasable** when all of the following are true:

| # | Criterion | Enforcement |
|---|---|---|
| 1 | Python coverage = 100% line + 100% branch | pytest --cov-fail-under=100 |
| 2 | TypeScript coverage = 100% lines/branches/functions/statements | vitest thresholds |
| 3 | Solidity coverage = 100% line + branch | check_forge_coverage_100.sh |
| 4 | Every M user flow from 05_UserFlow.md has a passing Playwright test | Playwright output |
| 5 | Every failure mode from 02_Architecture.md §6 has a passing TC-F### | 09_TestCases.md matrix |
| 6 | No `# type: ignore`, `// @ts-ignore`, `pragma: no cover`, or `istanbul ignore` added since last green commit without a committed justification | Grep check in CI |
| 7 | No new `TODO` / `FIXME` / `XXX` comments in `main` branch | Grep check |
| 8 | The phrase "for demo purposes" does not appear in the repo | Grep check (NFR-382) |
| 9 | Schema drift gate: 0 difference between regenerated and committed schemas | `git diff --exit-code` |
| 10 | Lint + type-check: 0 warnings across ruff, mypy --strict, biome, tsc --noEmit --strict | CI stages |
| 11 | Pre-commit `detect-secrets` passes | Pre-commit hook + CI |
| 12 | Smoke test passes against the deployed staging VPS | `scripts/smoke_test.sh` |

Any red → build fails → no merge to `main`.

---

## 10. Roles and responsibilities

| Role | Person | Responsibility |
|---|---|---|
| Test design | Architecture session (this set of docs) | Define strategy, coverage targets, test case catalogue |
| Test implementation | Build session (developer) | Write test code alongside feature code; commit together |
| Test review | Same developer (solo build) | Self-review: every PR must demonstrate new lines are covered by new tests |
| Coverage enforcement | GitHub Actions | Non-negotiable machine gate |
| Fixture maintenance | Build session | Update replay fixtures with `test-data-update:` commits |

---

## 11. Git discipline for tests (rule 2.2 applied)

| Event | Action |
|---|---|
| New feature | Write test + code in the same commit, OR test first in one commit, code in next — both committed before moving on |
| Test fails | Commit the failing test as `test: failing test for X`, fix in next commit as `fix: resolve X`, then commit green as `test: X passing` |
| Coverage drops | Build fails → immediate commit fixing coverage before any other work |
| Fixture needs updating | Commit with `test-data-update:` prefix and rationale |

**Never batch:** one logical change = one commit. A PR may contain 5–20 commits; none of them is a grab-bag.

---

## 12. Failure mode → test case mapping

Every failure mode in 02_Architecture.md §6 has a dedicated test case in 09_TestCases.md:

| Failure mode ID | 02 §6 row | Test case ID |
|---|---|---|
| Four.meme unreachable | 1 | TC-F01 |
| OpenAI down | 2 | TC-F02 |
| Anthropic down | 3 | TC-F03 |
| Gemini down | 4 | TC-F04 |
| All LLM providers down | 5 | TC-F05 |
| Redis crashes | 6 | TC-F06 |
| Postgres crashes | 7 | TC-F07 |
| BNB RPC unreachable | 8 | TC-F08 |
| Agent wallet out of gas | 9 | TC-F09 |
| Consumer group stuck | 10 | TC-F10 |
| Dashboard WebSocket disconnect | 11 | TC-F11 |
| Schema drift | 12 | TC-F12 |
| Telegram rate-limited | 13 | TC-F13 |
| Scraping anti-bot | 14 | TC-F14 |
| DGrid gateway down | 15 | TC-F15 |
| Duplicate new-token event | 16 | TC-F16 |
| Honeypot passes early checks | 17 | TC-F17 |

---

## 13. User flow → E2E test mapping

From 05_UserFlow.md §11:

| Flow | E2E test case |
|---|---|
| UF-01 First-time Telegram subscription | TC-E01 |
| UF-02 Receiving an alert in Telegram | TC-E02, TC-E02a (degraded) |
| UF-02 Verify via bot | TC-E03 |
| UF-03 Audit after losing trade | TC-E04 |
| UF-04 Algo trader API integration | TC-E05 |
| UF-05 Judge dashboard view | TC-E06 (desktop), TC-E06m (mobile) |
| UF-05 WebSocket reconnect | TC-E07 |
| UF-06 Direct BscScan verification | TC-E08 |
| UF-07 Swarm health detail drawer | TC-E09 |
| UF-08 Unsubscribe | TC-E10 |

Every M-priority flow has ≥1 passing test (NFR-324).

---

## 14. Security test strategy

| Concern | Test approach | TC ID |
|---|---|---|
| No secrets in git history | `detect-secrets` pre-commit + CI | TC-S01 |
| API rate-limiting works | Integration test hammers endpoint, verifies 429 | TC-S02 |
| Contract write restricted to allowlist | Foundry unit test attempts write from non-allowlisted wallet, expects revert | TC-S03 |
| TLS in production | Smoke test verifies HTTPS-only redirect | TC-S04 |
| No secrets leaked in API responses | Snapshot tests assert response shape; no field named `*_key`, `*_secret`, `*_token` ever appears | TC-S05 |
| Pydantic input validation rejects malformed input | Unit tests assert 422 on malformed payloads | TC-S06 |

---

## 15. Performance test strategy (NFR-200, NFR-202)

| Target | Test approach | TC ID |
|---|---|---|
| E2E ≤ 5 min P95 at ≤10 candidates/min | `locust` script feeds mocked Four.meme events; measures brief publish latency per msg_id | TC-P01 |
| 30 candidates/min burst without message loss | Same harness at 30/min; asserts 0 messages dropped, all briefs eventually published | TC-P02 |
| Per-agent latency budgets (FR-002, FR-028, FR-047, FR-067, FR-087) | Collected from OpenTelemetry traces in the burst test | TC-P03 |

**Performance tests run on PR and on the VPS after deploy**, not on every commit — they take ~10 minutes and are gated to specific tags or manual triggers.

---

## 16. Regression strategy

- Every bug fix ships with a regression test that would have caught the bug
- Bug regression tests carry a `regression:` tag in pytest and comment in the test code referencing the original issue/commit
- Regression tests are never deleted without explicit justification in commit message

---

## 17. Deployment validation

Post-deploy, `scripts/smoke_test.sh` runs on the VPS and verifies:

1. `GET /health` returns 200 from the API
2. `GET /briefs?limit=1` returns 200 with valid schema
3. The dashboard root page loads with status 200 and contains "SwarmScout"
4. The FindingsRegistry contract at the configured address responds to `verifyFinding(0x00...00)` with zero struct (confirming contract reachability)
5. The Telegram bot responds to `/start` within 5s
6. All 5 agents have emitted a heartbeat within the last 60s

Any failure rolls back the deploy.

---

## 18. Test execution matrix (summary)

| Run | Local (pre-commit) | Local (pre-push) | GitHub Actions | On deploy |
|---|---|---|---|---|
| ruff / mypy / biome / tsc | ✅ | ✅ | ✅ | — |
| detect-secrets | ✅ | ✅ | ✅ | — |
| Python unit + integration | optional | ✅ | ✅ | — |
| TypeScript unit + component | optional | ✅ | ✅ | — |
| Solidity unit + fuzz + invariant | optional | ✅ | ✅ | — |
| Playwright E2E | optional | optional | ✅ | — |
| Schema drift | — | — | ✅ | — |
| Load (TC-P01/P02) | — | — | tag-gated | — |
| Smoke test | — | — | — | ✅ |

---

## 19. Known gaps & deferred work

| Gap | Reason |
|---|---|
| Alembic DB migrations | v1 schemas final for the release; migration framework next iteration |
| Visual regression (Chromatic or Percy) | Post-hackathon |
| Load testing at scale >30/min | Not needed for v1 scope |
| Formal contract verification | Pre-mainnet work |
| Penetration testing | Post-hackathon |
| Accessibility audit | WCAG 2.1 AA spot checks only in v1 |
| Mutation testing (mutmut / Stryker) | Possible upgrade after 100% line+branch is stable |

---

**End of 08_TestPlan.md**
