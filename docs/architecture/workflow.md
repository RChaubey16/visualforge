# VisualForge — Workflow

Status: **Approved** (2026-11-14)

This document defines runtime behaviour: how the orchestrator invokes
skills, hands artifacts forward, persists state, resumes, parallelises,
and runs the visual QA feedback loop.

## 1. Stage list

| Stage ID | Skill | Blocking predecessors | Gate after |
|---|---|---|---|
| `S0-init` | website-orchestrator | — | **Gate A** |
| `S1-research` | reference-analyzer | S0 | — |
| `S2a-ux` | ux-design-analyst | S1 | — |
| `S2b-design-system` | design-system-extractor | S1 | — |
| `S3-spec` | page-specification | S2a, S2b | **Gate B** |
| `S4-architecture` | nextjs-architect | S3 | — |
| `S5-implement` | frontend-implementer | S4 | — |
| `S6-motion` | motion-engineer | S5 | — |
| `S7-qa` | visual-qa | S6 | loop (§6) |
| `S8-release` | release-auditor | S7 (passed) | **Gate C** |

S2a and S2b are the only stage-level parallel pair.

## 2. Invocation model

- The orchestrator runs **in the main session** as a skill. It is the
  only component that reads and writes `state/project-state.json`.
- Stage skills are invoked with the Skill tool **inline** in the main
  session by default. This keeps tool access (Playwright MCP, Bash,
  file edits) and conversation context, and avoids needless agents.
- Subagents (Agent tool) are used only for the cases in §5.
- Each invocation receives a **stage invocation envelope** (see
  `artifact-schema.md` §4) containing: project root, stage ID, run
  number, input artifact paths, output directory, and any routed defects.
- Skills pass **paths, not content**. Downstream skills read upstream
  artifacts from disk. This makes every hand-off inspectable and
  resumable.
- Each skill finishes by writing a **stage result** (`state/stages/<stage-id>.result.json`):
  status, outputs with content hashes, warnings, open questions. The
  orchestrator validates it (§3.3) before marking the stage complete.

### 2.1 Orchestrator main loop (pseudocode)

```
load or create state/project-state.json
reconcile(state)                          # §4 — verify, invalidate stale stages
loop:
  ready = stages whose predecessors are `completed` and which are not
          `completed`/`running`, and whose gate (if any) is approved
  if ready is empty:
     if all stages completed → stop (report)
     if waiting on a gate   → present gate summary, stop and wait for user
     if blocked             → report blocker, stop
  for stages in ready that are marked parallel-safe → run as parallel group (§5)
  otherwise → run next ready stage inline
  after each stage: validate result → update state → append run log
```

## 3. State management

### 3.1 Files

```
projects/<name>/state/
├── project-state.json         # single source of truth (schema: artifact-schema.md §5)
├── run-log.jsonl              # append-only event log
├── stages/<stage-id>.result.json
├── envelopes/<stage-id>.run<n>.json
└── locks/orchestrator.lock    # PID + timestamp; prevents concurrent orchestrators
```

### 3.2 Stage status machine

```
pending ──► running ──► completed ──► stale ──► running …
               │             ▲
               ├──► failed ──┘ (retry)
               └──► blocked (needs user / missing capability)
```

- `stale`: a completed stage whose inputs changed (fingerprint mismatch)
  or which was invalidated by a routed defect. Stale stages re-run;
  their downstream stages become stale transitively.
- State is written **atomically** (write temp file, rename) after every
  transition, so a crash never leaves a half-written state file.

### 3.3 Completion validation

A stage is `completed` only if:

1. Its result file exists with `status: "completed"`.
2. Every declared output path exists and its sha256 matches the result.
3. JSON outputs validate against `schemas/`.
4. The skill's own quality criteria checklist (in its result file) has no
   `fail` entries.

Otherwise the stage is `failed` with a reason.

## 4. Resume

On every orchestrator start (`reconcile`):

1. Acquire `locks/orchestrator.lock`. If a live lock exists, stop. If the
   lock is older than the configured timeout and its PID is gone, take it
   over and log `lock_recovered`.
2. Any stage found in `running` was interrupted. Mark it `failed`
   (reason `interrupted`) — never assume partial output is valid.
3. For each `completed` stage, recompute the **input fingerprint**: a
   sha256 over (sorted input artifact hashes + skill version +
   relevant config). If it differs from the recorded fingerprint, mark
   it `stale`.
4. Verify recorded output hashes. A missing or hand-edited output marks
   the stage `stale` (hand edits are logged as `manual_edit_detected` and
   the user is asked whether to keep the edit or regenerate).
5. Propagate `stale` downstream through the dependency graph.
6. Resume the main loop. Completed, valid stages are never repeated.

### 4.1 Resume within a stage (checkpoints)

Long stages resume at sub-step granularity using checkpoints recorded in
their result file's `checkpoints` array:

| Stage | Checkpoint unit |
|---|---|
| reference-analyzer | per page × viewport capture, per interaction probe |
| frontend-implementer | per section, then per page |
| motion-engineer | per motion spec entry |
| visual-qa | per page × viewport × check |

On restart after `interrupted`, the skill re-validates each checkpoint's
outputs and continues from the first missing/invalid one.

### 4.2 Git and resume

`site/` changes are committed at the end of S4, S5, S6 and each QA fix
round on the project's feature branch, **only when the user has
authorised commits** for this project (CLAUDE.md Git rules: Conventional
Commits, no Claude co-author). Commit SHAs are stored in state so resume
can detect divergence between state and the working tree.

## 5. Parallelism

| Work | Mode | Rationale |
|---|---|---|
| S2a ux-design-analyst ‖ S2b design-system-extractor | **Parallel**: two subagents, each loading its skill | Both read only S1 artifacts, write disjoint directories, no browser use. Genuine independence. |
| Reference capture (S1) | **Sequential** | Single Playwright MCP browser session; page state, viewport and media emulation are shared. |
| Playwright Test screenshot/video runs (S1 supplement, S7) | Parallel **workers**, not agents | Playwright Test handles concurrency itself. |
| S3 → S4 → S5 → S6 | **Sequential** | Each consumes the previous stage's output. |
| Sections within S5 | Sequential by default | Shared primitives and tokens evolve; parallel edits to `site/` risk conflicts. Optional: independent pages may be built by subagents in separate git worktrees **only** after primitives are complete and if the user opts in. |
| S7 checks (screenshots, a11y, interactions) | Parallel test workers inside one skill run | Read-only against a running dev/prod server. |
| S8 checks (lint, typecheck, unit/e2e, build) | Parallel shell commands where independent | Read-only checks; build last. |

Agent budget per project run: at most **2** concurrent subagents (the S2
pair), plus optional opt-in worktree builders in S5. No other agents.

## 6. Visual QA feedback loop

```
            ┌──────────────── S7 visual-qa (iteration n) ───────────────┐
            │ capture site at viewports → compare against spec,         │
            │ design tokens, reference principles → defects.json         │
            └───────────────┬───────────────────────────────────────────┘
                            │
               no blocking/major defects? ── yes ──► S8 release-auditor
                            │ no
                            ▼
          orchestrator groups defects by `owner_skill`
                            │
   ┌────────────────────────┼─────────────────────────┬─────────────────┐
   ▼                        ▼                         ▼                 ▼
frontend-implementer   motion-engineer   design-system-extractor   page-specification
(layout, a11y,         (motion bugs,     (token value wrong)       (spec gap / ambiguity
 responsive, markup)    reduced-motion)                             → needs Gate B re-approval)
   │                        │                         │                 │
   └──── fix-mode run with only the routed defects ───┴─────────────────┘
                            │
             orchestrator marks dependents stale (minimal set)
                            ▼
               S7 visual-qa (iteration n+1): re-test affected
               pages + full regression screenshot pass
```

Rules:

1. **Severity**: `blocker` (broken/inaccessible/unusable), `major`
   (clear deviation from spec or design system), `minor` (polish),
   `note` (observation). The loop continues while any `blocker` or
   `major` is open.
2. **Fix mode**: owning skills are invoked with `mode: "fix"` and a list
   of defect IDs. They fix only those defects and record which defect
   each change resolves.
3. **Minimal invalidation**: a token fix invalidates S4 token wiring
   checks and every page using the token; a component fix invalidates only
   pages containing it. Upstream analysis (S1–S2) is never invalidated by
   QA defects.
4. **Spec defects** route to page-specification and require Gate B
   re-approval of the changed spec only.
5. **Budget**: max **3** QA iterations by default (configurable). On
   exhaustion the orchestrator stops and presents remaining defects to
   the user: accept as known issues, extend budget, or change spec.
6. **Regression guard**: every iteration re-captures all pages at all
   viewports; a previously-passing check that now fails is a new
   `blocker` (`regression: true`).
7. **No silent passes**: a check that could not run (e.g. tool missing)
   is reported as `not_run`, never as `pass`.
8. `minor` defects are batched into a single optional polish round after
   the loop exits, at the user's discretion.

## 7. Failure handling (orchestrator level)

| Failure | Response |
|---|---|
| Skill reports `failed` | Retry once with the failure reason in the envelope. Second failure → `blocked`, report to user. |
| Reference site unreachable / bot-blocked | S1 `blocked`; ask user for an alternative URL, saved HTML, or screenshots (user-supplied material is labelled `source: user_provided`). |
| Missing capability (e.g. axe not installed) | Proceed; affected checks `not_run`; listed in release report. |
| Schema validation failure | Stage `failed`; validation errors passed to retry. |
| Gate rejected | Route user feedback to the owning stage in fix mode; re-present the gate. |
| Concurrent orchestrator | Refuse to start (lock). |

## 8. Run log

`run-log.jsonl` events: `stage_started`, `stage_completed`,
`stage_failed`, `stage_stale`, `gate_requested`, `gate_approved`,
`gate_rejected`, `defects_routed`, `qa_iteration`, `lock_recovered`,
`manual_edit_detected`, `commit_created`. Each entry has timestamp,
stage ID, run number and a short message. The log is for audit and
debugging; state is reconstructed from `project-state.json`, not the log.
