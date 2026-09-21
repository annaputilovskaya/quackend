# Contributing

Thanks for your interest.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

## Development loop

1. Create a branch from `develop`: `git checkout develop && git checkout -b feat/<slug>`
2. Write a failing test (`tests/` mirrors `src/`).
3. Implement the minimal change to make it pass.
4. Run the mandatory checks (below).
5. Open a PR.

## Mandatory checks

Run all checks with a single command (see `docs/CONVENTIONS.md` §7):

```bash
.\scripts\dod.ps1      # Windows
./scripts/dod.sh       # Linux/macOS/CI
```

## Commits

Conventional Commits, imperative mood: `feat(store): add seed`, `fix(loader): ...`, `docs: ...`.
Keep the subject under 72 characters; use the body to explain why.

## Conventions

Project-wide conventions live in `docs/CONVENTIONS.md` — read them before touching code.