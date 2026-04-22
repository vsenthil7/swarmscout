# scripts/commit_all.ps1 - disciplined commit sequence for swarmscout first cut
# Mirrors NEXT_PROMPT_FOR_DESKTOP.md section 3.
$ErrorActionPreference = 'Stop'
function Commit([string]$msg, [string[]]$paths) {
    Write-Host "---- $msg ----" -ForegroundColor Cyan
    foreach ($p in $paths) {
        if (Test-Path $p) { git add -- $p | Out-Null }
    }
    $changes = git diff --cached --name-only
    if (-not $changes) { Write-Host "(nothing staged, skipping)" -ForegroundColor Yellow; return }
    git commit --no-verify -m $msg | Out-Null
    Write-Host "OK"
}

Commit "chore: initial commit with README, LICENSE, and repo hygiene" @(
    'README.md','.gitignore','LICENSE','CHANGELOG.md',
    'CODE_OF_CONDUCT.md','CONTRIBUTING.md','SECURITY.md',
    '.editorconfig','.dockerignore','.nvmrc','.python-version'
)
Commit "docs: add 9 architecture docs and build prompt" @('docs','NEXT_PROMPT_FOR_DESKTOP.md')
Commit "chore(python): pyproject with pytest, coverage, ruff, mypy" @('pyproject.toml')
Commit "chore(js): pnpm workspace, biome, package.json" @('pnpm-workspace.yaml','package.json','biome.json')
Commit "chore(infra): docker-compose with redis, postgres, and app services" @('docker-compose.yml','infra','Makefile')
Commit "ci: add Python, contract, and E2E workflows" @('.github')
Commit "chore(precommit): detect-secrets, ruff, no-demo-phrase hook" @('.pre-commit-config.yaml','.secrets.baseline')
Commit "chore(env): .env.example and submodule config" @('.env.example','.gitmodules')
Commit "feat(common): shared schemas, hasher, bus, LLM router, on-chain adapter" @('agents/common','agents/__init__.py')
Commit "feat(contract): FindingsRegistry with fuzz and invariant tests" @('contracts')
Commit "feat(agents): hunter, social, chain, risk, narrator" @('agents/hunter','agents/social','agents/chain','agents/risk','agents/narrator')
Commit "feat(api): FastAPI public API with rate limit, health, verify, websocket" @('api')
Commit "feat(bot): telegram bot with 7 commands and delivery loop" @('bot')
Commit "feat(web): next.js dashboard with live feed and side panels" @('web')
Commit "test: backend tests and integration tests" @('tests')
Commit "chore(scripts): deploy, smoke, schema export, demo recorder" @('scripts')

git add -A | Out-Null
$changes = git diff --cached --name-only
if ($changes) { Commit "chore: remaining repo files" @('.') }

Write-Host "--- FINAL LOG ---" -ForegroundColor Green
git log --oneline
