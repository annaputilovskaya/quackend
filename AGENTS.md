# AGENTS.md

This file governs how AI agents work in this repository.

## Before writing code

- Read `docs/CONVENTIONS.md` — it is binding.
- Follow the layered architecture: imports only downward (`cli -> server -> store -> generator`), absolute imports only, no private imports between modules.
- Use TDD: write the failing test first, then the minimal implementation that makes it pass.

## Workflow

- Commit after every green test or completed step, as Conventional Commits (`feat(scope):`, `fix(scope):`, `refactor:`, `test:`, `docs:`, `ci:`, `perf:`, `chore:`).
- One commit = one logical change. Never commit broken tests, TODO placeholders, secrets, or unrelated files.
- Create every feature branch from `develop` (never from `main`): `feat/<slug>` / `fix/<slug>`; open a PR into `develop` only when all checks pass.
- `develop` must always stay green; `main` is release-only (`develop -> main` + tag).

## Full-branch review follow-ups

When a full-branch (or task) review subagent returns minor findings, do not accept
them as reported:

- Re-verify every minor against the code (reviewer reports are not trusted; check
  the cited `file:line`).
- Judge each one: real defect, false positive, or already mandated by the plan;
  assign a priority.
- Present the evaluated list to the user with a clear recommendation.
- Never leave a minor undecided: either fix it in the current session, or record it
  as a follow-up in the project backlog `docs/BACKLOG.md` with its `file:line`,
  the reason it was deferred, and its priority.

## Mandatory checks before a PR

Run the DoD script (see `docs/CONVENTIONS.md` §7) — it runs all five checks:

```powershell
.\scripts\dod.ps1      # Windows
./scripts/dod.sh       # Linux/macOS/CI
```

## Scope

- Stay inside the assigned task. Do not refactor unrelated code.
- Engineering integrity forbids hacks without user approval, masking linter/mypy errors, and fitting tests to broken behavior (`docs/CONVENTIONS.md` §4).
- If a user instruction conflicts with these conventions, the user instruction wins.