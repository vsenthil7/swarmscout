# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

See `docs/POST_SUBMISSION.md` for the post-hackathon roadmap. Nothing has been shipped under this heading yet.

## [0.1.0-hackathon] — 2026-04-22

First submission to HACK0015 (Four.Meme AI Sprint, DoraHacks).

### Added

#### Infrastructure

- Docker Compose stack: Redis 7.2 (AOF), Postgres 16, five agent services, API, Telegram bot, Next.js dashboard.
- GitHub Actions workflows: `ci.yml` (Python lint + mypy + pytest with coverage gate), `contract.yml` (Foundry 100% line + branch gate), `e2e.yml` (Playwright).
- Pre-commit: detect-secrets, ruff, ruff-format, trailing-whitespace, no-demo-phrase enforcement.

#### Agents and bus

- Five-agent swarm: Hunter, Social, Chain, Risk, Narrator.
- Hunter supports two source adapters (`FOURMEME_SOURCE=polling | rpc_log`) behind a `FourMemeSource` Protocol.
- Shared `Envelope` schema (ULID msg_id, SHA-256 payload hash, upstream lineage) validated with Pydantic.
- Redis Streams message bus with consumer groups, PEL-first redelivery, approximate MAXLEN trimming.
- Deterministic canonical-JSON hasher with the three required flags (`sort_keys=True`, `ensure_ascii=False`, `separators=(",", ":")`).
- 15 named risk heuristics as pure callables plus honeypot short-circuit in `aggregate_score`.
- Narrator emits AlphaBrief on the happy path, HumanReviewRequest on LLM exhaustion or missing lineage.

#### LLM routing

- `LLMRouter` with DGrid primary (OpenAI-compatible wire format) and direct-provider fallback chains for Anthropic, OpenAI, Google.
- 3-failure circuit breaker with 60-second cooldown; closes on next success.
- Per-provider Redis token-bucket rate limiting; capacity configurable per minute.
- Full audit logging to the `llm_calls` table with cost estimation from the `DEFAULT_PRICING` dictionary.
- Graceful `RouterExhaustedError` when every provider is unreachable.

#### On-chain

- `FindingsRegistry.sol` (Solidity 0.8.24) — append-only, access-controlled, custom errors, events.
- 15 unit tests + 2 fuzz properties (1000 runs) + 2 invariants (256 runs, depth 32).
- Python side: `OnChainAnchor` with signed-tx + receipt-await, `NullAnchor` for tests.

#### API

- FastAPI application with `/briefs`, `/briefs/{id}`, `/briefs/{id}/verify`, `/health`, `/ready`, `/metrics`, `/ws/events`.
- IP-based rate-limit middleware backed by Redis.
- Lifespan-managed shared `Context` with connection pooling.

#### Telegram bot

- All 7 commands: `/start`, `/stop`, `/status`, `/latest`, `/threshold`, `/verify`, `/help`.
- Brief delivery loop consuming `stream:briefs` with conviction-tier threshold filtering per subscriber.
- Redis-SET dedup with 7-day TTL.
- `TelegramRetryAfter` handling for Telegram 429s.

#### Dashboard

- Next.js 14 App Router, SSR feed page.
- Four panels: BriefCard (feed), SwarmHealthPanel, ModelUsagePanel, ActivityTimelinePanel.
- `useBriefStream` hook with exponential-backoff reconnect and polling fallback after 3 failures.
- Mobile-responsive Tailwind grid.

#### Tests

- Python unit suite: 133 tests across hasher, envelope, bus, router, on-chain, 15 risk heuristics, agent helpers, bot helpers.
- Python integration: 10 tests against FastAPI TestClient with faked dependencies.
- Web Vitest: 25 tests across BriefCard, panels, schemas, API client, useBriefStream hook.
- Playwright: dashboard smoke + mobile viewport + demo walkthrough driver.

#### Documentation

- 9 design documents (Requirements, Architecture, Scenarios, Use Cases, User Flow, HLD, LLD, Test Plan, Test Cases).
- `BUILD_SESSION_PROMPT.md` — 12-phase implementation plan.
- `TRACEABILITY.md` — 181 requirements mapped through scenario → UC → UF → HLD → LLD → code → test → script.
- `REVIEW_FIRST_CUT.md` — honest audit of what is proven vs written-not-run.
- `NEXT_PROMPT_FOR_DESKTOP.md` — handoff for the live-deploy session.
- 100% docstring coverage: 58 Python modules, 334 functions, 69 classes, 19 TS exports, all Solidity NatSpec, all shell script headers.

### Known limitations

- Contract not yet deployed to BNB Testnet; `FINDINGS_REGISTRY_ADDRESS` in `.env.example` is a placeholder.
- RPC-log source event topic is a placeholder (`0x00…`); must be replaced with the real Four.meme `TokenCreated` signature before `FOURMEME_SOURCE=rpc_log` is used.
- `honeypot_check_passed` uses the contract-verified flag as a surrogate; a real honeypot service integration is v2.
- `lp_locked` always returns `False`; LP-locker lookup is v2.
- Tests written but not yet executed by the build session. Three known material bugs documented in `docs/REVIEW_FIRST_CUT.md` §5.

### Security

- `.env` is gitignored; `.env.example` contains placeholders only.
- detect-secrets pre-commit baseline at `.secrets.baseline`.
- `FindingsRegistry.recordFinding` guarded by owner-managed agent whitelist.

[Unreleased]: https://github.com/OWNER/swarmscout/compare/v0.1.0-hackathon...HEAD
[0.1.0-hackathon]: https://github.com/OWNER/swarmscout/releases/tag/v0.1.0-hackathon
