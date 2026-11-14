# VisualForge progress

Tracks where development stands so work can resume after an interruption
(API limits, a lost session, a new machine). **Update this file as the
last step of every task**, in the same PR.

_Last updated: 2026-11-14_

## Current status

- **Active task:** website-orchestrator skill. PR [#2](https://github.com/RChaubey16/visualforge/pull/2) is open, waiting for review and merge.
- **Branch:** `feature/website-orchestrator-skill`
- **Next task after merge:** to be decided. Either the shared `schemas/` task or `reference-analyzer` (recommended, see "Open decisions").

## How to resume

1. Read this file, then `CLAUDE.md`, then the relevant files in `docs/architecture/`.
2. `git checkout main && git pull`, and check open PRs with `gh pr list`.
3. If a PR is open, wait for the user to merge it. Don't start the next task.
4. If nothing is open, start the next item in the build order on a new feature branch.

## Build order

| # | Task | Status | PR |
|---|---|---|---|
| 0 | Architecture docs (`docs/architecture/`) | ✅ Merged | [#1](https://github.com/RChaubey16/visualforge/pull/1) |
| 1 | Shared artifact schemas (`schemas/`) | ⏸ Started, then rolled back at the user's request. Not done. | — |
| 2 | website-orchestrator (state/resume core) | 🔍 In review | [#2](https://github.com/RChaubey16/visualforge/pull/2) |
| 3 | reference-analyzer | ⬜ Not started | — |
| 4 | design-system-extractor | ⬜ Not started | — |
| 5 | ux-design-analyst | ⬜ Not started | — |
| 6 | page-specification | ⬜ Not started | — |
| 7 | nextjs-architect | ⬜ Not started | — |
| 8 | frontend-implementer | ⬜ Not started | — |
| 9 | motion-engineer | ⬜ Not started | — |
| 10 | visual-qa | ⬜ Not started | — |
| 11 | release-auditor | ⬜ Not started | — |
| 12 | website-orchestrator (full routing, validated against real stage skills) | ⬜ Not started | — |

## Completed work log

### 2026-11-14: Architecture docs (PR #1, merged)
- Six documents in `docs/architecture/` define the 10 skills, the order they run in, state and resume, artifact formats, quality standards and the visual QA loop.
- Approved decisions: `@axe-core/playwright` added to the stack, a shared `schemas/` folder at the repo root, default viewports 375/768/1280/1440, QA loop limit of 3 rounds, LCP ≤ 2.5s, CLS ≤ 0.1, JS per route warn at 200 KB and fail at 300 KB.
- Development workflow and remote added to `CLAUDE.md`.

### 2026-11-14: website-orchestrator skill (PR #2, in review)
- `.claude/skills/website-orchestrator/` holds `SKILL.md`, 5 reference files, `scripts/vf_state.py` (state manager, Python stdlib only), 21 unit tests and `evals/evals.json`.
- Modes: full, research, design-spec, implementation, visual-qa, resume.
- Skill Creator evals, 2 iterations: with the skill 93.8% → 100%; the baseline scored 69.2%.
- Iteration 1 found that preflight treated "Playwright tools loaded" as "browser works". Fixed with a real `about:blank` probe.
- Eval workspace: `website-orchestrator-workspace/` (gitignored, local only), with a review page at `website-orchestrator-workspace/review-iteration-2.html`.

## Open decisions

- **Schemas vs. reference-analyzer next.** The schemas task was rolled back. The recommendation is to build `reference-analyzer` next and define its artifact formats inside the skill. The other option is to redo `schemas/` first.

## Environment notes

- The Playwright MCP browser **can't launch on this machine**: it is set to the `chrome` channel, and `/opt/google/chrome/chrome` is missing. Fix with `npx playwright install chrome`, or point the MCP server at the installed Chromium. Research (S1) and visual QA (S7) need this.
- Node v22.23.3, npm 10.9.9, Python 3.13.13 are available. No Python linter (ruff/pyflakes) is installed.

## Known limitations / follow-ups

- The orchestrator evals could only test orchestration (setup, gates, blocking, resume), because no stage skills exist yet. Re-run them as stage skills land (task 12).
