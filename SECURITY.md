# Security Policy

## Scope

SwarmScout is a hackathon entry (HACK0015, 2026-04-22) that anchors data to BNB Testnet. The testnet instance is non-custodial and does not hold user funds. No mainnet deployment exists at the time of this document's last update.

If that changes — specifically if SwarmScout ever deploys to BNB mainnet or any chain where funds or real-value assets are at stake — this file will be updated with a mainnet disclosure address and bug-bounty terms.

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.0-hackathon (testnet)     | security reports accepted via the channel below |
| < 0.1.0                       | not supported |

## Reporting a vulnerability

**Do not open a public issue.** Instead:

1. Email the maintainer (address in the GitHub profile of the repo owner), subject line prefixed `[SECURITY]`.
2. Include: reproducible steps, affected version / commit, expected vs observed behaviour, and — where safe — a proof of concept.
3. Give the maintainer a reasonable amount of time to respond and fix before any public disclosure. For a solo hackathon project this means **14 days** unless otherwise negotiated.

For vulnerabilities in the `FindingsRegistry` contract specifically, include the deployed testnet address and any relevant tx hashes.

## What is in scope

- `FindingsRegistry.sol` contract and its deployment pipeline
- LLM router credential handling (leakage, incorrect audit logging, rate-limit bypass)
- Public API — rate-limit bypass, authentication/authorisation (once any auth is added), injection
- Dashboard — XSS, CSRF, content-security issues
- Telegram bot — command injection, impersonation, dedup bypass
- Container / CI secrets exposure
- Hash-collision or canonical-JSON-bypass attacks that could forge a finding

## What is out of scope

- DoS via load (the architecture document explicitly accepts single-VPS single-point-of-failure for v0.1.0)
- Issues requiring Four.meme, BscScan, or DGrid to be compromised
- Browser extension interactions
- Vulnerabilities in upstream dependencies already reported upstream (please link the upstream report)

## Our commitments

- Acknowledge receipt within 72 hours
- Keep you informed of progress
- Credit you in the release notes / CHANGELOG unless you request otherwise
- Not take legal action against good-faith security research that follows this policy
