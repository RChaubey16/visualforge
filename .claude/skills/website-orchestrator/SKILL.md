---
name: website-orchestrator
description: Master workflow controller for VisualForge. Turns a reference website URL into an original Next.js site by running the VisualForge stage skills (reference-analyzer, ux-design-analyst, design-system-extractor, page-specification, nextjs-architect, frontend-implementer, motion-engineer, visual-qa, release-auditor) in dependency order, with persistent project state, approval gates, resume, retries and a visual QA loop. Use this skill whenever the user wants to build, redesign or "make something like" a website from a reference URL; start, continue, resume or check a VisualForge project; run only the research, design-specification, implementation or visual QA part of the pipeline; or mentions a project under projects/. Use it even when the user only names one stage, because the orchestrator owns state and prerequisites.
compatibility: Claude Code with the Skill, Agent, Bash and AskUserQuestion tools; python3; Playwright MCP for research and QA; Node.js >= 20.9, npm and git for implementation stages.
metadata:
  version: 0.1.0
---

# VisualForge website orchestrator

You run the VisualForge pipeline. You do not do the stage work yourself.
You decide what runs next, invoke the stage skill for real, check what it
produced, and record the result in project state. The architecture in
`docs/architecture/` is the source of truth. This skill puts it into practice.

Two ideas drive everything below:

1. **State lives on disk, not in your memory.** Every transition goes
   through `scripts/vf_state.py`. Sessions get interrupted, and the next
   session (maybe not you) must be able to continue from the files alone.
2. **No mandatory stage is ever silently skipped.** If a stage cannot run
   (missing skill, missing browser, failed twice, gate not approved), it
   is *blocked* and you tell the user why and how to fix it. Never do a
   stage's work yourself, write its outputs by hand, or mark it done
   without its skill's result file. Faked research or QA would poison
   every later stage while looking legitimate.

`S="python3 .claude/skills/website-orchestrator/scripts/vf_state.py"`.
Run it from the repository root. Every command prints JSON. Read it and act on it.

## Stages

| Stage | Skill | Needs | Gate before |
|---|---|---|---|
| S0-init | (this skill) | — | — |
| S1-research | reference-analyzer | browser | A: brief |
| S2a-ux ‖ S2b-design-system | ux-design-analyst ‖ design-system-extractor | S1 | — |
| S3-spec | page-specification | S2a + S2b | — |
| S4-architecture | nextjs-architect | S3 | B: spec |
| S5-implement → S6-motion | frontend-implementer → motion-engineer | S4 | — |
| S7-qa | visual-qa (loops with fixes) | S6, browser | — |
| S8-release | release-auditor | QA passed or accepted | then C: release |

## Modes

Pick the mode from the user's words: `full` (default), `research`,
`design-spec`, `implementation`, `visual-qa`, or `resume`. Details and
prerequisite rules are in `references/execution-modes.md`. Read it
whenever the request is anything other than a plain full build.

## Procedure

### 1. Start or resume

- **New project**: settle the project name (kebab-case), reference URL,
  target page(s), original brand name and positioning, audience and
  constraints. Ask only for what is missing. Then:
  `$S init --repo . --name <name> --url <url> --pages home[,about] --mode <mode> --brand "..." ...`
- **Existing project** (resume, or the project directory already exists):
  `$S lock --project projects/<name>`, then `$S reconcile --project projects/<name>`.
  Report what reconcile found (interrupted, stale, manual edits) before
  continuing. For manual edits, ask the user whether to keep the edit or
  regenerate. See `references/resume-and-recovery.md`.
- If `lock` refuses, another session may be running this project. Stop
  and ask the user. Use `--force` only after they confirm.

### 2. Preflight (new projects, and on resume if tools may have changed)

Check the tools for real; don't assume them:
- **Browser**: tools that load are not the same as a browser that runs.
  The MCP server can be connected while its browser binary is missing.
  1. Load the Playwright MCP tools (`mcp__playwright__browser_navigate`,
     `browser_snapshot`) with ToolSearch if they are deferred.
  2. Probe: `browser_navigate` to `about:blank`, then `browser_snapshot`.
     Never probe with the reference URL. Visiting it is S1's job.
  3. Available only if both calls succeed. Otherwise pass the error.
- Then run `$S preflight --project <p> --browser available|unavailable [--browser-error "<message>"]`.
  It checks node, npm, npx, git and python3, and lists stage skills that
  are not installed.

Tell the user about every problem preflight reports, which stages it
blocks, and the stage skills in this mode's scope that aren't installed
(`missing_skills_in_scope`). Do this up front, at Gate A, not stage by
stage. Don't substitute WebFetch, curl or memory for the browser:
research and QA must come from a real rendered page.

### 3. Main loop

Repeat `$S next --project <p>` and act on `action`:

| action | What to do |
|---|---|
| `preflight` | Do step 2. |
| `gate` | Present the gate (below) with AskUserQuestion, record it with `$S gate`, stop if not approved. |
| `run` | Invoke the listed stage(s) (step 4). If `parallel` is true, run them concurrently. |
| `qa_loop` | Run the QA loop (`references/qa-loop.md`). |
| `missing_prerequisites` | Tell the user which earlier stages are required. Offer to run them (switch to a wider mode) or stop. |
| `blocked` | Report each blocker with its remedy (install the skill, connect the browser, fix the error). Stop. Don't work around it. |
| `done` | Write the project report (step 6). |

**Gates.** A: show the brief (`brief.md`), viewports and target pages.
B: summarise the design system, sitemap, page specs and open questions.
C: summarise the release report and verdict. Record decisions with
`$S gate --project <p> --gate A|B|C --status approved|rejected --notes "..."`.
A rejection carries the user's feedback. Re-run the owning stage with
`envelope --mode fix --feedback "..."` and present the gate again.

### 4. Invoking a stage

1. `$S envelope --project <p> --stage <id>` writes the invocation
   envelope (input paths, output dir, config, defects) and marks the
   stage running.
2. Invoke the skill **with the Skill tool**: `skill: <skill-name>`,
   `args: "envelope=<envelope path>"`. Naming a skill in prose does not
   run it. Only a Skill tool call does.
3. The stage skill writes `state/stages/<id>.result.json`. Then:
   `$S complete --project <p> --stage <id>` (add `--fix` for fix-mode
   runs). This checks that declared outputs exist, that hashes match,
   that no quality criterion failed and that no checkpoint is pending.
4. If complete fails: if `retry_allowed`, re-run once, passing the errors
   in the envelope (`--feedback`). Otherwise `next` will report the
   stage blocked. Surface `open_questions` and `warnings` to the user.
   `recapture_requests` from S2a/S2b mean one targeted S1 re-run
   (`references/resume-and-recovery.md`).

**Parallel S2a ‖ S2b.** These two only read S1 output and write
separate directories. Create both envelopes, then launch two Agent
subagents in a single message. Each one is told to invoke its skill with
the Skill tool and the envelope path, and to report the result file
path. After both return, run `complete` for each. This is the only place
you spawn subagents. Everything else runs inline so stage skills keep the
session's browser and file access. Prompt template:
`references/invocation.md`.

### 5. Visual QA loop

After S7 completes, run `$S qa --project <p>`. Follow `decision`:
`pass` → continue to S8. `fix` → route each defect group to its owning
skill in fix mode, then QA runs again. `budget_exhausted` → stop and ask
the user to accept the remaining defects (`qa --accept "..."`), extend the
budget (`qa --extend 1`), or change the spec. `report_only` (visual-qa
mode) → show defects and ask before fixing. Full rules:
`references/qa-loop.md`.

### 6. Finish

When `next` says `done`, or you must stop (blocked, waiting for a gate):
1. `$S status --project <p>` (writes `state/status.md`).
2. Write or update `projects/<name>/project-report.md` using
   `references/report-template.md`. Write it on every stop, not only on
   success, so the user always has a current picture.
3. `$S unlock --project <p>`.
4. Tell the user, briefly: what ran, what was produced, what is blocked
   or waiting, and the exact next step.

## Rules that are easy to get wrong

- Report observed facts only from evidence. If a stage didn't run, the
  report says so. Never present plans as results.
- Never edit stage artifacts. You write only `brief.md`, `state/` (via
  the script) and `project-report.md`.
- Git: commit only if the user has authorised commits for this project.
  Use Conventional Commits, no Claude co-author, and follow the CLAUDE.md
  branch/PR rules.
- Keep the user informed at gates and blockers. Between stages, give one
  short line of progress.
