# 07 — Low-Level Design (LLD)

**Project:** SwarmScout
**Status:** Locked
**Last updated:** 2026-04-22 07:20 UTC

Class/module design, data structures, API schemas, DB schemas, contract ABI. This document is the implementation blueprint — the Build Session opens this file and codes directly from it.

---

## 1. Module catalogue (Python)

### 1.1 `agents/common/` — shared library

#### `agents/common/base_agent.py`

```python
class BaseAgent:
    """Abstract base for all five agents.
    Handles: bus subscription, envelope construction, hashing,
    on-chain write, downstream publish, health heartbeat, graceful shutdown.
    Subclasses override `process()` only.
    """

    name: str                               # e.g., "hunter"
    input_stream: str | None                # None for Hunter (external source)
    input_group: str | None
    output_stream: str
    llm_primary: str                        # e.g., "google/gemini-2.5-flash"
    llm_fallbacks: list[str]

    def __init__(
        self,
        bus: MessageBus,
        llm: LLMRouter,
        on_chain: OnChainWriter,
        db: AsyncSession,
        hasher: PayloadHasher,
        health: HealthEmitter,
    ): ...

    async def run(self) -> None:
        """Main loop: read → process → hash → write-on-chain → publish → ack."""

    async def process(self, envelope: Envelope) -> Payload:
        """Agent-specific logic. Subclasses implement."""
        raise NotImplementedError

    async def _handle_message(self, raw_msg: StreamMessage) -> None: ...
    async def _shutdown(self) -> None: ...
```

**Test coverage target:** 100% line + branch. Tests mock bus/llm/on_chain/db/hasher/health; exercise: success path, process-raises-exception, on-chain-write-fails, shutdown signal during in-flight.

#### `agents/common/bus.py`

```python
class MessageBus:
    """Thin wrapper over redis-py Streams API."""

    async def publish(self, stream: str, envelope: Envelope) -> str: ...
    async def consume(
        self, stream: str, group: str, consumer: str, count: int = 1, block_ms: int = 5000
    ) -> list[StreamMessage]: ...
    async def ack(self, stream: str, group: str, msg_id: str) -> int: ...
    async def claim_stale(
        self, stream: str, group: str, consumer: str, min_idle_ms: int = 60_000
    ) -> list[StreamMessage]: ...
    async def pending(self, stream: str, group: str) -> int: ...
    async def xlen(self, stream: str) -> int: ...
    async def xrevrange(self, stream: str, count: int) -> list[StreamMessage]: ...
```

**Test coverage target:** 100%. `fakeredis` for unit, `testcontainers-redis` for integration.

#### `agents/common/llm_router.py`

```python
class LLMRouter:
    """Routes LLM calls through DGrid with per-agent fallback chains.
    Tracks per-(agent, provider) circuit-breaker state.
    """

    def __init__(
        self,
        dgrid_client: AsyncOpenAI,          # points at DGrid
        direct_clients: dict[str, Any],     # {"anthropic": AsyncAnthropic, "openai": AsyncOpenAI, "google": AsyncGenAI}
        agent_config: dict[str, LLMAgentConfig],
        rate_limiter: RedisTokenBucket,
        logger: CallLogger,
    ): ...

    async def complete(
        self,
        agent_name: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        timeout_s: float = 30.0,
    ) -> LLMResponse:
        """Try primary via DGrid → fallbacks → direct APIs. Raise on all failures."""

    def _chain_for(self, agent_name: str) -> list[ProviderModel]: ...
    def _is_circuit_open(self, agent_name: str, provider: str) -> bool: ...
    def _record_success(self, agent_name: str, provider: str) -> None: ...
    def _record_failure(self, agent_name: str, provider: str, err: Exception) -> None: ...


@dataclass(frozen=True)
class LLMAgentConfig:
    primary: str                           # "google/gemini-2.5-flash"
    fallbacks: tuple[str, ...]             # ("anthropic/claude-haiku-4-5", "openai/gpt-4o-mini")


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model_used: str                        # "google/gemini-2.5-flash"
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
```

**Test coverage target:** 100%. Tests: primary succeeds, primary fails → FB1 succeeds, primary+FB1 fail → FB2 succeeds, all three fail → raises, circuit-open skips primary, rate-limit acquires/releases correctly.

#### `agents/common/on_chain.py`

```python
class OnChainWriter:
    """Writes (msg_id, payload_hash, agent) to FindingsRegistry.
    Queues to Redis on RPC failure; background task drains queue.
    """

    def __init__(
        self,
        w3: AsyncWeb3,
        registry_address: ChecksumAddress,
        private_key: str,
        redis: Redis,
    ): ...

    async def record(self, msg_id: bytes, payload_hash: bytes, agent: str) -> OnChainStatus:
        """Returns 'confirmed' on success (tx receipt OK), 'pending' on queue."""

    async def drain_queue(self) -> None:
        """Background task; retries queued writes."""


class OnChainStatus(str, Enum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
```

**Test coverage target:** 100%. Tests: write succeeds, RPC timeout → queued, queue drain succeeds, queue drain still fails → stays queued, insufficient gas → queued.

#### `agents/common/hasher.py`

```python
class PayloadHasher:
    """Canonical JSON → SHA-256.
    Uses sort_keys=True, ensure_ascii=False, separators=(',',':') for determinism.
    """

    @staticmethod
    def hash(payload: BaseModel) -> bytes:
        """Returns 32-byte SHA-256 digest."""
```

**Test coverage target:** 100%. Tests: same input → same hash, different key order → same hash (canonicalisation works), unicode handled.

#### `agents/common/health.py`

```python
class HealthEmitter:
    """Periodic heartbeat to Redis + PG health_events table."""

    async def start(self, interval_s: float = 10.0) -> None: ...
    async def stop(self) -> None: ...
    def record_event_processed(self) -> None: ...
    def record_llm_call(self, success: bool) -> None: ...
    def set_current_model(self, model: str) -> None: ...
```

**Test coverage target:** 100%.

#### `agents/common/metrics.py`

Prometheus client wrappers. Exposes `/metrics` HTTP endpoint per agent.

#### `agents/common/db.py`

```python
# SQLAlchemy 2.0 async models
class Message(Base):
    __tablename__ = "messages"
    msg_id: Mapped[str] = mapped_column(primary_key=True)          # ULID as string
    agent: Mapped[str]
    upstream_ids: Mapped[list[str]] = mapped_column(JSONB)
    payload_hash: Mapped[str]                                       # hex
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime]
    model_used: Mapped[str | None]
    confidence_tier: Mapped[str]
    on_chain_status: Mapped[str]
    on_chain_tx_hash: Mapped[str | None]

    __table_args__ = (
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_agent_created", "agent", "created_at"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    chat_id: Mapped[int] = mapped_column(primary_key=True)
    threshold: Mapped[str]
    subscribed_at: Mapped[datetime]
    deleted_at: Mapped[datetime | None]
    last_alert_at: Mapped[datetime | None]


class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    prompt_hash: Mapped[str]
    response_hash: Mapped[str | None]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[float]
    latency_ms: Mapped[int]
    success: Mapped[bool]
    error: Mapped[str | None]
    created_at: Mapped[datetime]


class HealthEvent(Base):
    __tablename__ = "health_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent: Mapped[str]
    timestamp: Mapped[datetime]
    status: Mapped[str]                                             # ok | degraded | down
    current_model: Mapped[str | None]
    error_rate: Mapped[float]
    events_processed_last_minute: Mapped[int]
    pending_queue_depth: Mapped[int | None]


class OnChainQueue(Base):
    __tablename__ = "on_chain_queue"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    msg_id: Mapped[str]
    payload_hash: Mapped[str]
    agent: Mapped[str]
    enqueued_at: Mapped[datetime]
    attempts: Mapped[int]
    last_error: Mapped[str | None]
```

#### `agents/common/schemas/` — Pydantic models

Envelope + all five payload shapes defined as Pydantic v2 models. Every model has:

- `Config.frozen = True` (immutable)
- `Config.extra = "forbid"` (reject unknown fields)
- JSON Schema export via `model_json_schema()`

See §4 for detailed schemas.

### 1.2 `agents/hunter/`

#### `agents/hunter/main.py`

```python
class Hunter(BaseAgent):
    name = "hunter"
    input_stream = None                     # external source
    output_stream = "stream:candidates"
    llm_primary = "google/gemini-2.5-flash"
    llm_fallbacks = ["anthropic/claude-haiku-4-5", "openai/gpt-4o-mini"]

    def __init__(self, source: FourMemeSource, **kw):
        super().__init__(**kw)
        self.source = source

    async def run(self) -> None:
        async for raw_event in self.source.stream():
            if await self._is_duplicate(raw_event):
                continue
            payload = await self._normalise(raw_event)
            envelope = self._build_envelope(payload, upstream_ids=[])
            await self._publish(envelope)
```

#### `agents/hunter/sources/`

Adapter pattern for the Four.meme data source. Implements whichever of these is available:

```python
class FourMemeSource(Protocol):
    async def stream(self) -> AsyncIterator[RawTokenEvent]: ...


class FourMemePollingSource:
    """Polls Four.meme REST endpoint every N seconds."""

class FourMemeRPCLogSource:
    """Subscribes to BNB RPC logs for Four.meme factory contract events."""
```

**Design choice deferred to build time:** adapter-pattern means we can switch sources without touching Hunter's business logic. LLD specifies the interface; implementation picks whichever adapter works when we hit the Four.meme platform.

### 1.3 `agents/social/`

```python
class Social(BaseAgent):
    name = "social"
    input_stream = "stream:candidates"
    input_group = "group:social"
    output_stream = "stream:social"
    llm_primary = "openai/gpt-4o"
    llm_fallbacks = ["anthropic/claude-sonnet-4-6", "google/gemini-2.5-pro"]

    async def process(self, envelope: Envelope) -> SocialScore: ...


class XScraper:
    """Playwright stealth; reuses HACK0014 polling + anti-detection patterns."""
    async def scrape_mentions(self, query: str, hours: int = 24) -> list[Mention]: ...


class TelegramPublicScraper:
    async def scrape_mentions(self, query: str, hours: int = 24) -> list[Mention]: ...
```

Both scrapers raise `ScrapingBlockedError` on 403/CAPTCHA; Social catches and emits degraded SocialScore (FR-027, UC-15).

### 1.4 `agents/chain/`

```python
class Chain(BaseAgent):
    name = "chain"
    input_stream = "stream:candidates"
    input_group = "group:chain"
    output_stream = "stream:chain"
    llm_primary = "anthropic/claude-sonnet-4-6"
    llm_fallbacks = ["openai/gpt-4o", "google/gemini-2.5-pro"]


class BscScanClient:
    async def get_holders(self, token: str) -> list[Holder]: ...
    async def get_lp_info(self, token: str) -> LPInfo: ...
    async def get_tx_velocity(self, token: str, window_s: int = 300) -> float: ...


class HoneypotSimulator:
    """Uses eth_call to simulate buy+sell; detects revert on sell."""
    async def check(self, token: str) -> bool: ...
```

### 1.5 `agents/risk/`

```python
class Risk(BaseAgent):
    name = "risk"
    # Special case: joins two streams
    input_streams = ["stream:social", "stream:chain"]
    input_groups = ["group:risk-social", "group:risk-chain"]
    output_stream = "stream:risk"
    llm_primary = "anthropic/claude-opus-4-7"
    llm_fallbacks = ["openai/gpt-4o", "google/gemini-2.5-pro"]
    join_timeout_s = 120


class HeuristicEngine:
    """15 deterministic rug-pull rules.
    Rules are declarative: each is a callable Heuristic(metrics) -> bool.
    """
    RULES: list[Heuristic] = [
        rule_creator_multiple_tokens_7d,           # >5 tokens in 7 days
        rule_lp_below_1k_usd,
        rule_top_holder_above_50pct,
        rule_contract_unverified,
        rule_honeypot_detected,
        rule_lp_not_locked,
        rule_coordinated_posting,
        rule_bot_heavy_mentions,
        rule_zero_organic_mentions,
        rule_creator_eoa_age_below_24h,
        rule_whale_dump_pattern,
        rule_tax_above_10pct,
        rule_ownership_not_renounced,                # for tokens claiming renouncement
        rule_mint_function_present,                   # can inflate supply
        rule_blacklist_function_present,              # can block sellers
    ]

    def evaluate(self, social: SocialScore, chain: ChainMetrics) -> list[str]:
        return [r.__name__ for r in self.RULES if r(social, chain)]
```

### 1.6 `agents/narrator/`

```python
class Narrator(BaseAgent):
    name = "narrator"
    input_stream = "stream:risk"
    input_group = "group:narrator"
    output_stream = "stream:briefs"                   # or "stream:human_review"
    llm_primary = "anthropic/claude-opus-4-7"
    llm_fallbacks = ["openai/gpt-4o", "google/gemini-2.5-pro"]

    async def process(self, envelope: Envelope) -> AlphaBrief | HumanReviewRequest: ...
```

### 1.7 `api/` — FastAPI service

```python
# api/main.py
app = FastAPI(title="SwarmScout API", version="0.1.0")
app.include_router(briefs_router)
app.include_router(health_router)
app.include_router(ws_router)
app.add_middleware(RateLimitMiddleware, rate_per_minute=60)


# api/routes/briefs.py
@router.get("/briefs", response_model=BriefListResponse)
async def list_briefs(
    since: timedelta = Query(default=timedelta(minutes=30)),
    limit: int = Query(default=50, le=200),
    tier: ConvictionTier | None = None,
    db: AsyncSession = Depends(get_db),
) -> BriefListResponse: ...


@router.get("/briefs/{msg_id}", response_model=BriefDetailResponse)
async def get_brief(msg_id: str, db: AsyncSession = Depends(get_db)) -> BriefDetailResponse: ...


@router.get("/briefs/{msg_id}/verify", response_model=VerifyResponse)
async def verify_brief(msg_id: str, on_chain: OnChainWriter = Depends(...)) -> VerifyResponse: ...


# api/routes/ws.py
@router.websocket("/ws/events")
async def ws_events(ws: WebSocket, redis: Redis = Depends(...)) -> None:
    await ws.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe("events:*")
    try:
        async for message in pubsub.listen():
            await ws.send_json(message)
    except WebSocketDisconnect:
        await pubsub.unsubscribe()
```

### 1.8 `bot/` — Telegram bot

```python
# bot/main.py
dp = Dispatcher()
dp.include_router(subscribe_router)
dp.include_router(verify_router)
dp.include_router(help_router)


# bot/handlers/subscribe.py
@router.message(Command("subscribe"))
async def cmd_subscribe(msg: Message, db: AsyncSession, ...) -> None: ...


# bot/handlers/verify.py
@router.message(Command("verify"))
async def cmd_verify(msg: Message, api: APIClient, ...) -> None: ...


# bot/consumer.py
class BriefConsumer:
    """Reads stream:briefs, sends to subscribed users."""
    async def run(self) -> None: ...
    async def _send_to_subscribers(self, brief: AlphaBrief) -> None: ...
    async def _is_duplicate(self, chat_id: int, msg_id: str) -> bool: ...
```

---

## 2. Module catalogue (TypeScript / Next.js)

### 2.1 `web/lib/schemas/`

Auto-generated from Pydantic's JSON Schema export via `json-schema-to-zod`. Never edited by hand. CI diff check (FR-223) fails if generated differs from committed.

```typescript
// web/lib/schemas/alpha_brief.ts (auto-generated)
export const AlphaBriefSchema = z.object({
  token_address: z.string().regex(/^0x[a-fA-F0-9]{40}$/),
  token_name: z.string(),
  token_symbol: z.string(),
  thesis: z.string().min(50).max(2000),
  conviction_tier: z.enum(['degen', 'speculative', 'moderate', 'high']),
  confidence_tier: z.enum(['ok', 'degraded']),
  caveats: z.array(z.string()),
  sources: z.array(z.string().url()),
  model_attribution: z.array(z.string()),
  brief_generated_at: z.string().datetime(),
  bscscan_url: z.string().url(),
});

export type AlphaBrief = z.infer<typeof AlphaBriefSchema>;
```

### 2.2 `web/app/page.tsx` (dashboard root)

```typescript
// Server component; SSRs initial state.
export default async function DashboardPage() {
  const briefs = await fetchBriefs({ limit: 20 });
  const health = await fetchHealth();
  const modelUsage = await fetchModelUsage({ window: '60m' });

  return (
    <main className="min-h-screen p-6">
      <TopBar />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <SwarmHealthPanel initial={health} />
        <ModelUsagePanel initial={modelUsage} />
        <ActivityTimelinePanel />
      </div>
      <BriefFeed initial={briefs} />
    </main>
  );
}
```

### 2.3 `web/components/BriefCard.tsx`

```typescript
export function BriefCard({ brief }: { brief: AlphaBrief }) {
  return (
    <article className={cn('rounded-lg border p-4', tierBorder(brief.conviction_tier))}>
      <header>...</header>
      {brief.confidence_tier === 'degraded' && <DegradedBanner />}
      <p>{brief.thesis}</p>
      <ul>{brief.caveats.map(c => <li key={c}>{c}</li>)}</ul>
      <footer>
        <ModelAttribution models={brief.model_attribution} />
        <a href={brief.bscscan_url} target="_blank" rel="noreferrer">Verify on BscScan ↗</a>
      </footer>
    </article>
  );
}
```

### 2.4 `web/lib/ws.ts`

```typescript
export function useEventStream() {
  const [events, setEvents] = useState<Event[]>([]);
  const [status, setStatus] = useState<'connecting' | 'live' | 'reconnecting' | 'polling'>('connecting');

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pollTimer: NodeJS.Timeout | null = null;
    let reconnectAttempts = 0;

    function connect() {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => { setStatus('live'); reconnectAttempts = 0; };
      ws.onmessage = (e) => setEvents(prev => [JSON.parse(e.data), ...prev].slice(0, 100));
      ws.onclose = () => {
        reconnectAttempts++;
        if (reconnectAttempts < 5) {
          setStatus('reconnecting');
          setTimeout(connect, Math.min(1000 * 2 ** reconnectAttempts, 30_000));
        } else {
          setStatus('polling');
          startPolling();
        }
      };
    }

    function startPolling() {
      pollTimer = setInterval(async () => {
        const r = await fetch(`${API_URL}/events?since=${lastTs.current}`);
        const fresh = await r.json();
        if (fresh.length) setEvents(prev => [...fresh, ...prev].slice(0, 100));
      }, 5000);
    }

    connect();
    return () => { ws?.close(); if (pollTimer) clearInterval(pollTimer); };
  }, []);

  return { events, status };
}
```

---

## 3. FindingsRegistry contract (Solidity)

### 3.1 `contracts/src/FindingsRegistry.sol`

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

contract FindingsRegistry {
    struct Finding {
        bytes32 payloadHash;
        string agent;
        uint256 timestamp;
        address recordedBy;
    }

    // msgId => Finding
    mapping(bytes32 => Finding) private findings;

    // wallet => allowed
    mapping(address => bool) public allowlist;

    address public immutable owner;

    event FindingRecorded(bytes32 indexed msgId, bytes32 payloadHash, string agent, uint256 timestamp);
    event AllowlistUpdated(address indexed wallet, bool allowed);

    error NotAllowlisted();
    error AlreadyRecorded();
    error NotOwner();
    error EmptyAgent();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAllowlisted() {
        if (!allowlist[msg.sender]) revert NotAllowlisted();
        _;
    }

    constructor(address[] memory initialAgents) {
        owner = msg.sender;
        for (uint256 i = 0; i < initialAgents.length; i++) {
            allowlist[initialAgents[i]] = true;
            emit AllowlistUpdated(initialAgents[i], true);
        }
    }

    function recordFinding(
        bytes32 msgId,
        bytes32 payloadHash,
        string calldata agent
    ) external onlyAllowlisted {
        if (findings[msgId].timestamp != 0) revert AlreadyRecorded();
        if (bytes(agent).length == 0) revert EmptyAgent();
        findings[msgId] = Finding({
            payloadHash: payloadHash,
            agent: agent,
            timestamp: block.timestamp,
            recordedBy: msg.sender
        });
        emit FindingRecorded(msgId, payloadHash, agent, block.timestamp);
    }

    function verifyFinding(bytes32 msgId)
        external
        view
        returns (bytes32 payloadHash, string memory agent, uint256 timestamp, address recordedBy)
    {
        Finding memory f = findings[msgId];
        return (f.payloadHash, f.agent, f.timestamp, f.recordedBy);
    }

    function setAllowlist(address wallet, bool allowed) external onlyOwner {
        allowlist[wallet] = allowed;
        emit AllowlistUpdated(wallet, allowed);
    }
}
```

### 3.2 Contract invariants (enforced by tests)

| Invariant | Test type |
|---|---|
| A Finding, once recorded, cannot be mutated or deleted | Invariant test + fuzz |
| Only allowlisted wallets can call `recordFinding` | Unit test |
| Only owner can call `setAllowlist` | Unit test |
| `recordFinding` cannot be called twice with the same `msgId` | Unit test |
| `recordFinding` rejects empty agent string | Unit test |
| `verifyFinding` returns zero-struct for unrecorded msgIds | Unit test |
| `FindingRecorded` event is emitted on every successful write | Unit test |
| `AllowlistUpdated` event is emitted on every allowlist change | Unit test |

### 3.3 Gas characteristics

| Call | Gas (approx) |
|---|---|
| `recordFinding` (cold mapping write) | ~70,000 |
| `recordFinding` (warm — follow-up in same tx, unlikely) | ~25,000 |
| `verifyFinding` | view, no gas |
| `setAllowlist` | ~30,000 |

At BNB testnet gas prices (~5 gwei), each `recordFinding` costs approximately 0.00035 BNB. A single faucet request of 0.1 BNB funds ~285 writes; at 10 candidates/min × 5 writes per candidate = 50 writes/min, one faucet top-up lasts ~6 minutes of continuous operation. Documented as operational reality.

---

## 4. Pydantic model definitions (authoritative)

Full Python code for all six payload models + envelope. These are the single source of truth.

```python
# agents/common/schemas/envelope.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Literal, Any

AgentName = Literal["hunter", "social", "chain", "risk", "narrator"]
ConfidenceTier = Literal["ok", "degraded"]
OnChainStatus = Literal["confirmed", "pending"]


class Envelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    msg_id: str = Field(pattern=r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
    agent: AgentName
    upstream_ids: list[str] = Field(default_factory=list)
    payload_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    payload: dict[str, Any]
    created_at: datetime
    model_used: str | None = None
    confidence_tier: ConfidenceTier = "ok"
    on_chain_status: OnChainStatus
```

Payload models (TokenCandidate, SocialScore, ChainMetrics, RiskVerdict, AlphaBrief, HumanReviewRequest) follow the schemas in 06_HLD.md §4.2–4.7, expressed as Pydantic v2 classes with the same `ConfigDict(frozen=True, extra="forbid")`.

---

## 5. API endpoint schemas (OpenAPI, derived from Pydantic)

```yaml
# Auto-generated at /openapi.json; excerpt:
paths:
  /briefs:
    get:
      parameters:
        - name: since
          schema: { type: string, format: duration, default: "PT30M" }
        - name: limit
          schema: { type: integer, default: 50, maximum: 200 }
        - name: tier
          schema: { type: string, enum: [degen, speculative, moderate, high] }
      responses:
        '200': { content: { application/json: { schema: { $ref: '#/components/schemas/BriefListResponse' } } } }
        '429': { headers: { Retry-After: {...} } }

  /briefs/{msg_id}:
    get:
      parameters: [{ name: msg_id, in: path, schema: { type: string } }]
      responses:
        '200': { content: { application/json: { schema: { $ref: '#/components/schemas/BriefDetailResponse' } } } }
        '404': {}

  /briefs/{msg_id}/verify:
    get:
      responses:
        '200': { content: { application/json: { schema: { $ref: '#/components/schemas/VerifyResponse' } } } }

  /health:
    get:
      responses:
        '200': { content: { application/json: { schema: { $ref: '#/components/schemas/HealthResponse' } } } }

  /metrics:
    get:
      responses:
        '200': { content: { text/plain: {} } }           # Prometheus format
```

---

## 6. Config (environment variables)

```bash
# .env.example

# LLM providers
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
DGRID_API_KEY=...
DGRID_BASE_URL=https://api.dgrid.ai/v1

# Telegram
TELEGRAM_BOT_TOKEN=123:abc...

# BNB Testnet
BNB_TESTNET_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545
WALLET_PRIVATE_KEY=0x...                        # testnet only
FINDINGS_REGISTRY_ADDRESS=0x...                 # populated after deploy

# Infrastructure
REDIS_URL=redis://redis:6379
DATABASE_URL=postgresql+asyncpg://swarm:swarm@postgres:5432/swarmscout

# Rate limits (per minute, per provider)
RATE_LIMIT_ANTHROPIC=60
RATE_LIMIT_OPENAI=60
RATE_LIMIT_GEMINI=60

# Cost caps (USD per day, per provider)
DAILY_COST_CAP_ANTHROPIC=50
DAILY_COST_CAP_OPENAI=50
DAILY_COST_CAP_GEMINI=50

# Observability
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=                     # optional

# Source adapters
FOURMEME_SOURCE=polling                          # polling | rpc_log
FOURMEME_POLL_INTERVAL_S=10
FOURMEME_API_URL=                                # set at integration time
BSCSCAN_API_KEY=
BSCSCAN_API_URL=https://api-testnet.bscscan.com/api

# API
API_RATE_LIMIT_PER_MINUTE=60
```

---

## 7. CI workflows

### 7.1 `.github/workflows/ci.yml`

```yaml
name: CI
on: [push, pull_request]

jobs:
  python:
    runs-on: ubuntu-latest
    services:
      redis: { image: redis:7-alpine, ports: [6379:6379] }
      postgres:
        image: postgres:16-alpine
        ports: [5432:5432]
        env: { POSTGRES_PASSWORD: swarm, POSTGRES_DB: swarmscout }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -e .[dev]
      - run: ruff check .
      - run: mypy --strict .
      - run: pytest --cov --cov-branch --cov-fail-under=100 --cov-report=xml
      - run: python scripts/export_schemas.py
      - run: git diff --exit-code web/lib/schemas/            # fail on drift

  typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: pnpm install --frozen-lockfile
      - run: pnpm biome check .
      - run: pnpm tsc --noEmit
      - run: pnpm vitest run --coverage
      - run: pnpm playwright install --with-deps
      - run: pnpm playwright test

  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: foundry-rs/foundry-toolchain@v1
      - run: forge build
      - run: forge test -vvv
      - run: forge coverage --report summary
      - run: ./scripts/check_forge_coverage_100.sh     # parses summary, fails <100%
```

### 7.2 `scripts/check_forge_coverage_100.sh`

Parses `forge coverage` output, exits 1 if any line or branch < 100%.

---

## 8. Module-level test mapping

Each module has a parallel test file. 100% coverage is a CI gate.

| Module | Test file |
|---|---|
| `agents/common/base_agent.py` | `agents/tests/unit/test_base_agent.py` |
| `agents/common/bus.py` | `agents/tests/unit/test_bus.py` + `integration/test_bus_redis.py` |
| `agents/common/llm_router.py` | `agents/tests/unit/test_llm_router.py` |
| `agents/common/on_chain.py` | `agents/tests/unit/test_on_chain.py` + `integration/test_on_chain_anvil.py` |
| `agents/common/hasher.py` | `agents/tests/unit/test_hasher.py` |
| `agents/common/health.py` | `agents/tests/unit/test_health.py` |
| `agents/hunter/main.py` | `agents/tests/unit/test_hunter.py` |
| `agents/hunter/sources/` | `agents/tests/unit/test_fourmeme_sources.py` |
| `agents/social/main.py` | `agents/tests/unit/test_social.py` |
| `agents/social/scrapers/` | `agents/tests/unit/test_scrapers.py` |
| `agents/chain/main.py` | `agents/tests/unit/test_chain.py` |
| `agents/chain/analytics/` | `agents/tests/unit/test_analytics.py` |
| `agents/risk/main.py` | `agents/tests/unit/test_risk.py` |
| `agents/risk/heuristics.py` | `agents/tests/unit/test_heuristics.py` |
| `agents/narrator/main.py` | `agents/tests/unit/test_narrator.py` |
| `api/routes/briefs.py` | `api/tests/unit/test_routes_briefs.py` + `integration/test_briefs_e2e.py` |
| `api/routes/ws.py` | `api/tests/unit/test_ws.py` |
| `bot/handlers/*.py` | `bot/tests/unit/test_handlers.py` |
| `bot/consumer.py` | `bot/tests/unit/test_consumer.py` |
| `web/components/*.tsx` | `web/tests/*.test.tsx` (Vitest + Testing Library) |
| `web/lib/ws.ts` | `web/tests/ws.test.ts` |
| `contracts/src/FindingsRegistry.sol` | `contracts/test/*.t.sol` |

---

## 9. Known gaps & deferred work

| Gap | Reason |
|---|---|
| Exact Four.meme API endpoint URLs and auth | A-01 — validated at build time |
| BscScan API rate-limit tuning values | A-02 — tuned in staging |
| Precise prompts per agent (system + user template) | Drafted in build session against real data |
| Alembic migration scripts | v1 schemas are final; migration framework next-iteration |
| `/lineage` endpoint implementation | UC-07 workable without it |
| Admin-wallet rotation procedure | Operations runbook, post-hackathon |

---

**End of 07_LLD.md**
