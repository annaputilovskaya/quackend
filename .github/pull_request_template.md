## What

<!-- One paragraph, or a short bullet list: the change a reviewer reads first. -->

## Why

<!-- The problem this solves, and how you checked it. Link the issue. -->

## Checks

- [ ] `./scripts/dod.sh` (or `.\scripts\dod.ps1`) is green locally — all five
      checks, not just the tests.
- [ ] Every behaviour change has a test in `tests/`, mirroring `src/`, named
      `test_<unit>_<scenario>_<expected>`.
- [ ] `README.md` / `README.ru.md` / `CONTRIBUTING.md` still describe what the
      code does.
- [ ] `CHANGELOG.md` has an entry under `[Unreleased]`, and a public API change
      (a signature or an added `__all__` name) is called out as breaking.
- [ ] Layers are respected: no import upward, no import of a private name from
      another module, no pass-through from `cli` to `generator`.
- [ ] The commit history is linear, Conventional Commits, no `WIP`.

## Breaking changes

<!-- "None", or what a consumer has to do differently. -->
