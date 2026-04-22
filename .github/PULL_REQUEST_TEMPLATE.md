# Pull Request

## Summary

Briefly describe what changes this PR introduces and why.

## Type of change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactor (no behavioural change)
- [ ] CI / infra / build tooling

## Traceability

- Requirement(s): `FR-###`, `NFR-###` (cite `docs/TRACEABILITY.md` rows)
- Scenario(s): `SC-##` / `AS-##`
- Test case(s): `TC-U##` / `TC-I##` / `TC-C##` / `TC-E##` / `TC-F##` / `TC-S##` / `TC-P##`

## Checklist before merging

- [ ] One logical change per commit (Conventional Commits: `type(scope): summary`)
- [ ] Tests written and passing locally — `pytest`, `pnpm test`, `forge test` as applicable
- [ ] Coverage still at 100% in each language that changed
- [ ] `ruff check .`, `ruff format --check .`, `mypy agents api bot` all green
- [ ] `biome check .` and `tsc --noEmit` green for `web/`
- [ ] No new `# type: ignore` or `// @ts-ignore` without a `[reason: ...]` marker
- [ ] No "for demo purposes" anywhere (grep check in CI will catch this — NFR-382)
- [ ] `scripts/export_schemas.py` run if any Pydantic model was modified
- [ ] Docstrings added for every new function, method, and class
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] `docs/TRACEABILITY.md` updated if a requirement's row changed

## Screenshots / evidence

If this PR touches the dashboard or bot output, attach a screenshot or a short clip.

## Known deferrals

List anything intentionally not done in this PR that should be tracked as follow-up, with a link to the issue if one exists.
