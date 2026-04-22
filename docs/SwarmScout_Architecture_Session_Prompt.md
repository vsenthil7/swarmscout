# SwarmScout — Architecture Session Handoff Prompt

**Copy-paste this entire file as the FIRST message of the next Claude session (Desktop or web). It carries all context, rules, and deliverables from the previous planning session.**

---

## 0. Who you are in this session

You are Claude. I am Senthil. We are in hour ~2 of a ~12-hour build window for the **Four.Meme AI Sprint hackathon** (deadline: 2026/04/22 16:59 UTC, ~$50k prize pool, submission requires GitHub repo + 3-min demo video). We completed idea selection in the previous session. This session is **Architecture & Specification** — the output of this session feeds directly into a Build session prompt you will generate at the end.

---

## 1. The decision locked in from the previous session

**Idea: SwarmScout** — Decentralized Agent Swarm for Four.Meme Alpha Discovery.

**One-line:** A coordinated swarm of specialized AI agents that monitor Four.meme in real time, each agent playing a narrow role (Hunter, Social, Chain, Risk, Narrator), communicating via a shared message bus, committing findings on-chain to BNB Chain, and delivering conviction-scored alpha briefs to traders via Telegram and web dashboard.

**Why this idea:**
- Empty lane in the competitive field (102 BUIDLs already submitted, none do true multi-agent orchestration with on-chain provenance)
- Hits the **Autonomous Workflows** track directly
- **Multi-model routing** through **DGrid AI Gateway** is a perfect showcase — qualifies for the DGrid bounty ($3,000 in credits)
- Agent-swarm aesthetic is trending in 2026 judging
- AI role is ~60% — high enough to justify an AI hackathon, low enough to leave real engineering substance (message bus, on-chain contract, dashboard, data pipelines)

**Judging criteria being optimized for:**
- Innovation 30% → multi-agent coordination + on-chain findings registry = unique
- Technical Implementation 30% → real message bus, real contract, real pipelines, real tests
- Practical Value 20% → every Four.meme trader is a potential user
- Presentation 20% → demo video shows agents "talking," findings hash being written on-chain, Telegram alert firing

---

## 2. Mandatory working rules — do NOT shrink any of these

These are Senthil's standing rules for all coding work. The previous session confirmed them for this project:

### 2.1 Enterprise-grade mindset
- Every idea, document, and code decision evaluated as if for an enterprise deployment, not a startup prototype or demo
- No corner-cutting disguised as "MVP discipline"
- If a choice is "we'll do the right thing later," that's a deferred defect — flag it explicitly

### 2.2 Git-first development discipline (strict)
- **Initialise the git repo BEFORE writing any code.** First commit is `chore: initial commit with README and .gitignore`
- Every code block you produce: **commit it immediately**, then test
- If the test passes, commit the test result note and move to next item
- If the test fails, fix it, **commit the fix**, re-test, repeat until green
- **Only then move to the next item**
- No batching multiple features into one commit. One logical change = one commit
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`

### 2.3 Block development is fine and encouraged
- Senthil's words: *"block development absolutely fine and you are good at it"*
- You may produce substantial code blocks in one turn — Senthil copies them to the filesystem manually
- Claude produces code → Senthil commits → Senthil tests → Senthil reports → Claude reacts

### 2.4 100% test coverage, no scope shrinking
- Unit tests — every function Claude writes
- Integration tests — every component boundary
- End-to-end automation tests — happy path + at least 2 failure paths
- Frontend tests — component render tests + user-flow tests
- Backend tests — API contract tests + DB integration
- Do not deviate from this even if time is short. If time runs out, scope down the **features**, not the **test coverage of shipped features**

### 2.5 Document artefacts required from architecture session
All of the following must be produced this session, as separate downloadable files:

1. **Requirements Document** — functional + non-functional, prioritised (MoSCoW)
2. **Architecture Document** — component diagram, tech stack per component, data flow, deployment topology
3. **Scenarios Document** — who uses it, when, why
4. **Use Cases Document** — UC-01 through UC-N, actor + precondition + main flow + alternatives
5. **User Flow Document** — screen-by-screen / interaction-by-interaction
6. **High-Level Design (HLD)** — system partitioning, component responsibilities, interfaces
7. **Low-Level Design (LLD)** — class/module design, data structures, API schemas, DB schemas, contract ABI
8. **Test Plan** — strategy, scope, environments, entry/exit criteria, coverage matrix
9. **Test Cases Document** — unit / integration / automation / frontend / backend, each with expected result

Each artefact is a standalone `.md` file with its own downloadable link at the end of this session.

### 2.6 Build session handoff
At the end of this architecture session, generate a **Build Session Prompt** (another handoff `.md` like this one) that:
- Carries forward these rules
- Lists every artefact produced in this session with its file path
- Gives the first-commit instructions
- Specifies the exact order of implementation (which component first, why)

### 2.7 Memory and surface rules
- Claude web chat and Claude Desktop **do not share live conversation history**. Account-level memory summary IS shared, but not turn-by-turn detail.
- Therefore: this prompt is the handoff. Treat its contents as the only context you can rely on.
- If working on Desktop for filesystem access, paste this prompt there. If working in web for thinking/docs, paste it there.

---

## 3. Reusable assets from previous work

### 3.1 HACK0014 — scrape_chats_v2.py
Senthil has a working Playwright-based scraper at `C:\Users\v_sen\Documents\Claude\read_shared_link_code\` with:
- Stealth mode (bypasses Cloudflare on claude.ai share pages)
- Excel / text-file / CLI-args input modes
- Markdown output assembly
- Message-count stability polling (waits for full page load, not just first element)

**Reuse for SwarmScout:**
- The stealth Playwright pattern → directly reused for **Social Agent** scraping X and Telegram public channels
- The polling logic → reused for **Hunter Agent** watching Four.meme new-token pages
- The output assembly pattern → reused for **Narrator Agent** producing final briefs

### 3.2 "Vertex and Fox already installed and working" — PLACEHOLDER
Senthil referenced *"user vertex and Fox already install and working"* in the previous session. This was not verifiable in the HACK0014 scraper context. **Senthil: clarify in your first message of the architecture session what vertex/Fox are** — likely candidates:
- **Google Vertex AI** (as one of the model providers routable via DGrid)
- **Firefox** as an alternative Playwright channel
- **Vertex** and **Fox** could also be names of local agent-framework installs — confirm paths and versions

Do not invent assumptions. Ask Senthil upfront.

### 3.3 Local workspace conventions
- Root: `C:\Users\v_sen\Documents\`
- Pending work: `000_01_PendingWork\pending\`
- Utility tools: `AT-UTIL-WorkOS\`
- Master log: `python AT-UTIL-WorkOS\UT-005-ProjectStatusReport\generate_master_log.py`
- MD→Excel: `python AT-UTIL-WorkOS\UT-002-MD-to-Excel\md_to_excel.py`

Create SwarmScout project at: `C:\Users\v_sen\Documents\Claude\HACK0015-SwarmScout\`

### 3.4 Communication style rules
- Terse, efficient — Senthil prefers timestamped logs and file paths over pasted content
- **Silent, text-only responses** — no audio/voice output
- Show plan first, get explicit approval, then act
- Only execute on "do it," "go ahead," or "yes"
- Never act on questions alone

---

## 4. SwarmScout — starting architecture sketch (to be expanded this session)

Use this as the seed, expand into full HLD/LLD:

### 4.1 The five agents
| Agent | Role | Model (via DGrid) | Input | Output |
|---|---|---|---|---|
| **Hunter** | Detect new Four.meme token launches | Sonnet 4.6 (fast, cheap) | Four.meme event stream | `TokenCandidate{address, launch_ts, creator, metadata}` |
| **Social** | Score social presence | GPT-4o (broad web knowledge) | X, Telegram scrape | `SocialScore{organic_score, mentions_24h, sentiment, red_flags[]}` |
| **Chain** | Analyse on-chain metrics | Sonnet 4.6 + deterministic analytics | BscScan API + RPC | `ChainMetrics{holders, lp_size, velocity, whale_entries[]}` |
| **Risk** | Run rug-pull heuristics | Claude Opus 4.7 (best reasoning) | Chain + Social outputs | `RiskVerdict{score_0_100, red_flags[], rationale}` |
| **Narrator** | Compose final brief | Claude Opus 4.7 | All prior agent outputs | `AlphaBrief{thesis, conviction, caveats, sources[]}` |

### 4.2 Communication backbone
- **Redis Streams** for the agent message bus (each agent subscribes to upstream topics, publishes to its own)
- **Each agent writes a SHA-256 hash of its output to an on-chain registry contract on BNB Testnet** before publishing downstream — creates an immutable findings trail
- **PostgreSQL** stores full agent outputs keyed by hash (hash = pointer, DB = content)

### 4.3 Delivery surfaces
- **Telegram bot** — pushes `AlphaBrief` to subscribed users
- **Next.js dashboard** — live feed of briefs + agent activity timeline + on-chain verification links
- **Public JSON API** — for integrators

### 4.4 Tech stack summary
| Layer | Choice | Justification |
|---|---|---|
| Language | Python 3.11 | Senthil's primary, matches HACK0014 |
| Agent framework | Lightweight custom (async + Redis Streams) | Avoid framework lock-in; ships faster than LangGraph/CrewAI for this size |
| Message bus | Redis Streams | Durable, simple, battle-tested |
| LLM routing | DGrid AI Gateway (`https://api.dgrid.ai/v1`) | Bounty requirement + multi-model showcase |
| DB | PostgreSQL 16 | Reliable, Senthil likely familiar |
| Blockchain | Solidity 0.8.x on BNB Testnet | Gas-free for testing |
| Web3 lib | `web3.py` (Python) + `wagmi` (frontend) | Matches language split |
| Frontend | Next.js 14 + Tailwind + shadcn/ui | Fast demo UI |
| Scraping | Playwright + stealth (from HACK0014) | Already proven working |
| Testing | pytest + pytest-asyncio + playwright-test + hardhat/foundry | Cover every layer |
| CI | GitHub Actions | Free, standard |
| Orchestration | Docker Compose (dev), single VPS for demo | Minimal ops |

### 4.5 Repo structure (to be validated this session)
```
HACK0015-SwarmScout/
├── README.md
├── .gitignore
├── docker-compose.yml
├── docs/                    # all 9 required docs live here
├── contracts/               # Solidity + hardhat/foundry
│   ├── src/FindingsRegistry.sol
│   └── test/
├── agents/                  # Python agent package
│   ├── hunter/
│   ├── social/
│   ├── chain/
│   ├── risk/
│   ├── narrator/
│   ├── common/              # shared: bus, dgrid client, hasher, db models
│   └── tests/
├── api/                     # FastAPI public API
├── bot/                     # Telegram bot
├── web/                     # Next.js dashboard
├── scripts/                 # deployment, seed, demo-video recording
└── .github/workflows/       # CI pipelines
```

---

## 5. What you (Claude) should do IMMEDIATELY in the architecture session

Do these in this exact order. Do NOT skip the confirmation step.

1. **Read this entire prompt back to Senthil in summary form** (5 bullets max) and ask: *"Confirmed? Anything to change before I start producing artefacts?"*
2. **Ask Senthil to clarify the "vertex and Fox" reference** — required to know what's already installed locally
3. **Wait for explicit approval** (`do it`, `go ahead`, or `yes`)
4. **Then produce, in this order, each as a separate downloadable .md file:**
   - `01_Requirements.md`
   - `02_Architecture.md`
   - `03_Scenarios.md`
   - `04_UseCases.md`
   - `05_UserFlow.md`
   - `06_HLD.md`
   - `07_LLD.md`
   - `08_TestPlan.md`
   - `09_TestCases.md`
5. **Pause between each document** — show it, confirm, then proceed. Do NOT produce all 9 in one blast — Senthil wants to validate each.
6. **At the end, produce `BUILD_SESSION_PROMPT.md`** — the next handoff, following the same pattern as this file. Include:
   - All 9 artefact file paths with download links
   - Rules 2.1–2.7 re-stated verbatim
   - First-commit instructions (git init, .gitignore, README, first commit before any code)
   - Exact implementation order (which component first)
   - Exit criteria (what "done" looks like for each component)

---

## 6. Non-negotiable boundaries

- **No shrinking the 9-document list.** If time is tight, you flag it to Senthil — he decides, not you.
- **No inventing features** not discussed here. If the design needs something new, propose it, get approval, then add.
- **No mocking what matters.** The on-chain contract must be real (testnet is fine). The DGrid calls must be real. The message bus must be real. Mock only the external scraped surfaces (Four.meme, X, Telegram) during unit tests — production path uses real scrapes.
- **Every artefact must end with a "Known Gaps & Deferred Work" section** — honesty over polish.

---

## 7. Timestamps carried forward from previous session

- 2026/04/22 04:58 — Senthil uploaded hackathon brief
- 2026/04/22 05:18 — Deadline clarified as 16:59 today, ~11h 40m window at that point
- 2026/04/22 05:26 — Idea locked: SwarmScout
- 2026/04/22 05:30 — Handoff prompt requested (this file)

**Current session start time** (fill in when you paste this): ___________

**Remaining window to deadline** (compute from 16:59 today): ___________

---

## 8. Senthil's signed rules reminder (verbatim from his messages)

> *"always Enterprise grade (not demo or startup prototype) when thinking idea also use that rule.. while developing git first from starting before doing any doing, every code (block development absolutely fine and you are good at it.) then immediately commit then only test if no error then next item but if error fix, git commit then test and repeat till error fixed and move to next item"*

> *"each of it should be 100% test coverage no scope shrinking and no deviation from test coverage discipline matters a lot check how you worked in hack 0014 and you were coding, commit git, run if any error fix, git commit test repeat once no error then next item"*

> *"whatever said follow that don't shrink I know what you are pushing.. forget it start working"*

These rules override any impulse toward brevity, MVP thinking, or demoware shortcuts. Full ceremony. No exceptions.

---

## 9. How the session ends

When all 9 documents are produced AND the Build Session Prompt is generated, you deliver:
- All 9 artefact `.md` files via `present_files`
- The `BUILD_SESSION_PROMPT.md` via `present_files`
- A single summary message listing the 10 files with one-line descriptions
- Then STOP. Do not start building. Building happens in the next session with the new prompt.

---

**End of handoff prompt.**
