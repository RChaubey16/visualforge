# Invoking stage skills

## Inline invocation (default)

```
$S envelope --project projects/<name> --stage S1-research
→ {"envelope": "projects/<name>/state/envelopes/S1-research.run1.json", "skill": "reference-analyzer", ...}

Skill tool:  skill = "reference-analyzer"
             args  = "envelope=projects/<name>/state/envelopes/S1-research.run1.json"

$S complete --project projects/<name> --stage S1-research
```

The envelope is the whole contract. The stage skill reads its inputs
from the listed paths, writes into `output_dir`, and finishes by writing
`result_path`. Don't paste artifact content into `args`. Paths keep
hand-offs inspectable and resumable.

Envelope fields: `project_root`, `stage_id`, `skill`, `run`, `mode`
(`run`|`fix`), `inputs` (name → project-relative path), `output_dir`,
`result_path`, `config` (viewports, qa_budget, target_pages,
commits_authorised), `defects` (fix mode), `feedback` (gate rejection or
retry errors), `resume_from_checkpoint`, `qa_iteration` (S7 only).

## Result file a stage must write

`state/stages/<stage-id>.result.json`:

```json
{
  "stage_id": "S1-research",
  "status": "completed | failed | blocked",
  "outputs": [{"path": "research/observations.json", "sha256": "sha256:<hex>"}],
  "checkpoints": [{"id": "home-w1440", "status": "done | skipped | failed | pending", "reason": "..."}],
  "quality_checklist": [{"criterion": "...", "result": "pass | fail | not_run", "detail": "..."}],
  "warnings": [], "open_questions": [], "recapture_requests": [], "resolved_defects": [],
  "error": null
}
```

`complete` rejects the stage if the file is missing, the status isn't
`completed`, an output is missing or its hash differs, any criterion is
`fail`, or any checkpoint is `pending`/`failed`. `status: "blocked"`
marks the stage blocked straight away (no retry). Use it for things only
the user can resolve.

## Parallel analysis (S2a ‖ S2b)

Create both envelopes first, then send **one message with two Agent
calls** so they run concurrently:

```
You are running one stage of a VisualForge project.
Repository root: <absolute repo path>
1. Invoke the Skill tool with skill="<ux-design-analyst | design-system-extractor>"
   and args="envelope=<envelope path>".
2. Follow that skill to completion. Read inputs only from the envelope's paths and
   write only inside its output_dir, plus its result_path.
3. Do not touch state/project-state.json. The orchestrator owns it.
4. Reply with the result file path and a 3-line summary (status, outputs, open questions).
```

When both return, run `complete` for each stage separately. If one fails,
the other's completion still stands. Only the failed one is retried.

## Why not more subagents?

Stage skills need the session's tools (Playwright MCP browser, file
edits, dev server) and they run in sequence. Subagents would add
hand-off loss without saving time. S2a/S2b are the exception: they are
independent, read-only on shared inputs, and need no browser.
