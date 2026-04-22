# Post-submission

## Observed bugs

_to be populated during / after judging._

## Judging feedback

_to be populated when received._

## Roadmap — 30 / 60 / 90 days

### 30 days
- Migrate Redis to a managed instance (Upstash or AWS ElastiCache) to remove single-VPS SPOF (02_Architecture.md §4.13).
- Add authenticated write endpoints to the API (signed by agent wallets) so clients can submit priority candidates.
- Formal audit of `FindingsRegistry.sol` before any mainnet deploy.

### 60 days
- Introduce a sixth agent (Liquidity) for DEX-pool depth and slippage modelling.
- Replace heuristic ``_whale_count`` with an on-chain price oracle.
- Add a Grafana dashboard backed by the Prometheus ``/metrics`` endpoint.

### 90 days
- Evaluate moving ``FindingsRegistry`` to an L2 (Linea, Base) to reduce gas per record by ~10×.
- Multi-region deploy — agents in region A, dashboard in B — with a shared Redis via Sentinel.
- Dedicated stealth provider for X scraping; fall back to official API once pricing is tractable.

## Operational TODOs

- Rotate the testnet wallet key when the hackathon window closes.
- Revoke expired DGrid API keys.
- Retire the initial detect-secrets baseline if the repo goes public.
