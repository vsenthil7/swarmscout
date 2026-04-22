# SwarmScout

**Decentralised agent swarm for Four.meme alpha discovery.**

Hackathon: HACK0015 — Four.Meme AI Sprint (DoraHacks, 2026-04-22)
Owner: Senthil (solo)

SwarmScout monitors the Four.meme platform in real time with a swarm of five specialised agents (Hunter, Social, Chain, Risk, Narrator). Every agent output is hashed and anchored to the BNB Testnet `FindingsRegistry` contract before being delivered via Telegram, a Next.js dashboard, or a public JSON API. LLM calls are routed through the DGrid AI Gateway across Anthropic, OpenAI, and Google, with documented per-agent fallback chains.

## Why this exists

Memecoin launchpads are adversarial. Retail traders cannot watch every new token, verify every contract, and cross-reference social chatter in real time. Centralised alpha feeds are opaque — the reader has no way to check whether the signal was produced, mutated, or back-dated. SwarmScout's answer is a five-agent pipeline whose every output is hash-anchored on-chain. Anyone can verify the provenance of any brief against BscScan. The model used for every inference is part of the hashed payload.

## Architecture at a glance

```
Four.meme  ->  Hunter  ->  [ Social, Chain ]  ->  Risk  ->  Narrator  ->  [ Telegram, Dashboard, API ]
                   |             |      |           |           |
                   v             v      v           v           v
              FindingsRegistry (BNB Testnet) — one hash per agent output
```

- **Message bus:** Redis Streams with consumer groups (at-least-once), PostgreSQL for full payloads.
- **LLM routing:** DGrid AI Gateway primary; per-agent fallback chains to direct provider APIs.
- **Contract:** Solidity 0.8.24, Foundry-built, 100% coverage including fuzz and invariant tests.

Full detail in `docs/02_Architecture.md` and `docs/06_HLD.md`.

## Quickstart

Prereqs: Docker 25+, Python 3.12, Node 20, pnpm 9, Foundry.

```bash
git clone <repo-url>
cd swarmscout
cp .env.example .env              # fill in keys
docker compose up -d redis postgres
pnpm install
uv sync                            # or pip install -e .[dev]
pre-commit install
pytest -q                          # unit + integration
cd contracts && forge test
cd ../web && pnpm test
```

Live demo URL, Telegram bot handle, and contract address populate `docs/DEPLOYMENT.md` after Phase 3 and Phase 12.

## Documentation

| # | Doc | Content |
|---|---|---|
| 01 | `docs/01_Requirements.md` | 156 FR/NFR, MoSCoW priority, traceability matrix |
| 02 | `docs/02_Architecture.md` | 14 tech decisions, C4 diagrams, failure modes |
| 03 | `docs/03_Scenarios.md` | 10 scenarios + 7 anti-scenarios |
| 04 | `docs/04_UseCases.md` | 16 use cases |
| 05 | `docs/05_UserFlow.md` | 10 user flows |
| 06 | `docs/06_HLD.md` | High-level design |
| 07 | `docs/07_LLD.md` | Low-level design, schemas, contract source |
| 08 | `docs/08_TestPlan.md` | Test strategy, coverage gates |
| 09 | `docs/09_TestCases.md` | Named test cases TC-U##, TC-I##, etc. |
| 10 | `docs/BUILD_SESSION_PROMPT.md` | Implementation handoff |

## License

MIT — see `LICENSE`.
