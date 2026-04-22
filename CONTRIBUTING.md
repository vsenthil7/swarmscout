# Contributing to SwarmScout

Thank you for considering a contribution. Read this file end-to-end before opening a PR. The rules are tight because the project anchors real-money on-chain records — a sloppy merge can break provenance for every user.

## 1. Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`. Harassment, discrimination, or personal attacks result in immediate, permanent removal from the project.

## 2. Setting up your environment

Prerequisites: Docker 25+, Python 3.12, Node 20, pnpm 9, Foundry (stable), a POSIX shell.

```bash
git clone https://github.com/<owner>/swarmscout.git
cd swarmscout
git submodule update --init --recursive

python -m venv .venv
source .venv/bin/activate          # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"

cd web && pnpm install && cd ..

pre-commit install
docker compose up -d redis postgres
cp .env.example .env                # fill in keys you need locally
```

Verify green:

```bash
pytest                              # Python unit + integration, coverage gate 100%
cd web && pnpm test && cd ..        # Vitest, coverage gate 100%
cd contracts && forge test && cd .. # Foundry
```

If any of those fail before you've changed anything, file an issue rather than trying to push through.

## 3. Branching and commits

* Branch off `main`: `git checkout -b type/short-summary` — for example `feat/risk-velocity-calibration`.
* **Conventional Commits** are mandatory: `type(scope): subject`. Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `build`, `perf`, `revert`.
* One logical change per commit. No "misc" or "cleanup" grab-bags.
* Commit subject ≤72 characters, imperative mood ("add", not "added"), no trailing period.
* Body (when present) wraps at 100 chars and explains **why**, not what — the diff shows what.
* Sign your commits (`git commit -s`) — adds the `Signed-off-by:` trailer per DCO.

### Example

```
feat(risk): add top-10 concentration rule

Add rule_high_concentration to the heuristics suite. When top-10 holders
own >70% of supply, emit a finding with weight 20. This catches the
most common rug setup that wasn't previously penalised.

Refs FR-062. Closes #142.
```

## 4. Development rhythm

SwarmScout is built in blocks: write code, commit, run tests, next block. Do not batch. Specifically:

1. Write the failing test first (or the code and its test together — never code without test).
2. Run the relevant test suite locally.
3. Commit code + test together.
4. If coverage falls below 100%, the commit is not done — either add more tests or shrink the feature.

## 5. What you cannot do

* Shrink coverage gates. Ever. Shrink the feature instead.
* Use the phrase `for demo purposes` anywhere — CI grep will reject it (NFR-382).
* Add `# type: ignore` or `// @ts-ignore` without a `[reason: ...]` comment.
* Commit `.env` or any other secret file (pre-commit's detect-secrets will block you, but don't rely on it alone).
* Modify `docs/01_Requirements.md` through `docs/09_TestCases.md` except via a dated change-log entry at the bottom. These are authoritative.
* Write code that runs outside the hashed-envelope lineage — if a new agent emits a message, it goes through `base_agent.anchor_and_publish()` and nowhere else.

## 6. Before opening a PR

Run locally:

```bash
ruff check .
ruff format --check .
mypy agents api bot
pytest
cd web && pnpm biome check . && pnpm typecheck && pnpm test && cd ..
cd contracts && forge test && cd ..
python scripts/export_schemas.py    # then commit the refreshed generated/ tree
```

All green? Push.

## 7. PR description

Use the PR template (`.github/PULL_REQUEST_TEMPLATE.md`). Critical fields:

* **What changed.** Plain English, two to four sentences.
* **Why.** Link the requirement (FR-###, NFR-###), issue (#nn), or scenario.
* **How tested.** Specific — "TC-U82 + new TC-U82b covering empty-list edge", not "added tests".
* **Trade-offs accepted.** If you considered alternatives, name them and say why you rejected them (rule 1.8 from the Build Session: full justification).

## 8. Review and merge

* Every PR needs one reviewer approval plus green CI.
* Reviewers: focus on correctness, test coverage, naming, docstrings, and whether the Conventional Commits story tells a clean history.
* Squash-merge by default — the commit message that lands on `main` is the PR title + body.
* If you need to refactor during review, force-push over the branch. Do not tack on "address review" commits.

## 9. Releasing

Maintainers only. See `docs/RUNBOOK.md` §Release.

## 10. Questions

Open a `question` issue, or ping the maintainer listed in `MAINTAINERS.md`. No private channel support — questions asked in public make the project better for everyone.
