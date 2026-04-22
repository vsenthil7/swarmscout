# Runbook

Operational cheat sheet for SwarmScout. Intended audience: the support/operations team (Women Empowerment Team + Senthil). Read `docs/02_Architecture.md` first for the mental model; this document assumes you already know what the five agents do.

---

## Quick status check

```bash
curl https://<public-api>/health | jq
curl https://<public-api>/ready
curl https://<public-api>/metrics | head -40
```

Expect:

- `/health` returns `"status": "ok"` when every heartbeat is `"online"`. Anything else means one or more agents has not written a heartbeat in the last 30 seconds.
- `/ready` returns `"ready"` whenever the API process is up — does not depend on agents.
- `/metrics` returns Prometheus exposition format. Grep for `swarmscout_events_processed_total`.

If `/health` returns 5xx the API itself is down — check `docker compose ps` on the VPS before anything else.

---

## Daily checks (5 minutes)

1. Dashboard loads at the public URL and shows at least one brief from the last hour.
2. Telegram bot responds to `/status` with every agent `online`.
3. `scripts/smoke_test.sh` passes from a workstation outside the VPS.
4. BscScan shows new `FindingRecorded` events on the `FindingsRegistry` address within the last hour.
5. Agent wallet balance on BNB Testnet is above 0.05 BNB. If lower, run `scripts/seed_testnet_wallet.sh` with `AGENT_WALLET_ADDRESS` set.

---

## Common symptoms and their cause-of-first-resort

### "Dashboard is blank / feed is empty"

1. Check `/health` — if it says degraded, jump to that section.
2. SSH to VPS → `docker compose logs --tail=100 narrator`. The Narrator is the last agent before briefs reach the UI; if it is quiet, look upstream.
3. `docker compose logs --tail=100 risk` — if Risk has no verdicts, look at `join timeout` messages. Social or Chain is probably lagging.
4. `docker compose exec redis redis-cli XLEN stream:candidates` — if this is near zero for many minutes, Hunter has stopped. Go to `docker compose logs hunter`.

### "Telegram bot is silent"

1. `docker compose logs --tail=200 bot` — look for `telegram_rate_limited` or `bot_send_failed`.
2. Does the bot's token still exist? Visit `@BotFather` → `/mybots` → confirm.
3. Verify the subscriber's `threshold`. A brief with `conviction_tier=degen` will not deliver to a `high`-threshold subscriber by design.
4. Check dedup: `docker compose exec redis redis-cli SMEMBERS bot:delivered:<chat_id>` — if the msg_id is already there, delivery is suppressed by design.

### "LLM calls failing"

1. `/metrics` grep `swarmscout_events_failed_total` — which agent is spiking?
2. `docker compose logs --tail=200 <agent>` — look for `router_exhausted` or `dgrid_circuit_open`.
3. `docker compose exec postgres psql -U swarmscout -c "SELECT provider, error_class, COUNT(*) FROM llm_calls WHERE created_at > NOW() - INTERVAL '1 hour' AND NOT success GROUP BY 1, 2"` — tells you which provider is angry and with what kind of error.
4. If DGrid is the problem, the router will have auto-tripped its circuit breaker; direct providers should still serve. If those are also failing, the LLM subsystem is truly exhausted — `requires_human_review` briefs will start appearing, which is by design.

### "Contract anchor failing"

1. `docker compose logs --tail=200 <any agent>` → look for `anchor_failed`.
2. Agent wallet out of BNB? Check balance on BscScan; top up via `seed_testnet_wallet.sh`.
3. RPC endpoint flaky? Try the alternate one in `.env.example` by setting `BNB_TESTNET_RPC_URL` and `docker compose up -d --no-deps <agent>`.
4. Contract address wrong in `.env`? Compare with `docs/DEPLOYMENT.md`.

Remember: anchor failure does not block the pipeline (§base_agent.anchor_and_publish catches exceptions). Briefs still appear in the UI and the Telegram bot, but the `/verify` endpoint will show `on_chain_present=False`. Fix the anchor as soon as possible or users start losing trust in the provenance story.

### "API rate-limited"

Default cap is 60 req/min per IP (configurable via `API_RATE_LIMIT_PER_MINUTE`). If a legitimate caller is tripping it, raise the cap in `.env` and restart the API — or better, persuade them to use the WebSocket endpoint which has no per-message rate limit.

---

## Restart procedures

### Restart one agent

```bash
docker compose restart hunter      # or social / chain / risk / narrator
docker compose logs -f hunter
```

Pending messages in the consumer-group PEL will be redelivered on the restart — no data loss.

### Restart the API

```bash
docker compose restart api
```

WebSocket clients will reconnect automatically thanks to `useBriefStream`'s exponential backoff.

### Full stack restart

```bash
docker compose down
docker compose up -d
```

Briefly degraded state during startup (~30 s). Postgres is persistent; Redis is AOF so the message bus survives.

### Full stack rebuild (after code change)

```bash
bash scripts/deploy.sh
```

This rsyncs, rebuilds images, restarts, and runs smoke tests.

---

## Data operations

### Query recent briefs

```bash
docker compose exec postgres psql -U swarmscout <<'SQL'
SELECT msg_id, payload->>'token_name' AS token, payload->>'conviction_tier' AS tier,
       created_at
  FROM findings
 WHERE agent = 'narrator'
 ORDER BY created_at DESC
 LIMIT 20;
SQL
```

### Re-verify a brief manually

```bash
curl https://<public-api>/briefs/<msg_id>/verify | jq
```

Check that `hash_match` and `on_chain_match` are both `true`. If `hash_match` is false, the payload was mutated after storage — a serious provenance break.

### Audit LLM cost for the day

```bash
docker compose exec postgres psql -U swarmscout <<'SQL'
SELECT provider, model, COUNT(*), ROUND(SUM(cost_usd)::numeric, 4) AS usd
  FROM llm_calls
 WHERE created_at > NOW() - INTERVAL '24 hours'
 GROUP BY 1, 2
 ORDER BY 4 DESC;
SQL
```

---

## Emergency: halt the swarm

If briefs are being emitted with provable incorrect content (e.g. the risk verdict is crediting bad tokens due to an upstream API change), stop the swarm to preserve user trust:

```bash
docker compose stop hunter social chain risk narrator
# API and bot stay up so existing briefs remain verifiable; no new ones produced.
```

Investigate, fix, commit, deploy, then `docker compose start`.

---

## Contact

Maintainer contact path is in `SECURITY.md`. For non-security production issues, open a GitHub issue with the `[ops]` prefix — or, for true emergencies, reach the maintainer directly.
