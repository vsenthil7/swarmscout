---
name: Bug report
about: Report a defect in SwarmScout
title: "[bug] "
labels: bug
assignees: ''
---

## Describe the bug

A clear and concise description of what is wrong.

## To reproduce

Steps to reproduce the behaviour:

1. Environment: (docker compose local / staging VPS / production VPS)
2. Git commit: `git rev-parse HEAD`
3. Commands run: …
4. Observed: …
5. Expected: …

## Affected components

- [ ] Hunter agent
- [ ] Social agent
- [ ] Chain agent
- [ ] Risk agent
- [ ] Narrator agent
- [ ] FindingsRegistry contract
- [ ] Public API (FastAPI)
- [ ] Telegram bot
- [ ] Dashboard (Next.js)
- [ ] CI / infrastructure

## Logs / evidence

Paste relevant log lines (structured JSON) or screenshot. Redact API keys, wallet keys, and user telegram IDs before sharing.

## Environment

- OS:
- Python version:
- Node version:
- Foundry version:
- Browser (if dashboard bug):

## Severity self-assessment

- [ ] Blocker — pipeline down / data corruption / provenance break
- [ ] High — one surface unusable, workarounds exist
- [ ] Medium — degraded experience
- [ ] Low — cosmetic
