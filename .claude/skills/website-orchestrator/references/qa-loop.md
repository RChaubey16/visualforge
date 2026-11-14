# Visual QA feedback loop

```
S7 visual-qa writes qa/iteration-<n>/defects.json
        │
   $S qa → decision
        ├─ pass ─────────────► S8 release-auditor
        ├─ fix ──► for each route (stage → defect IDs), in pipeline order:
        │            $S envelope --stage <owner> --mode fix --defects <ids>
        │            Skill tool → owner skill
        │            $S complete --stage <owner> --fix
        │          then $S next → S7 again (iteration n+1)
        ├─ budget_exhausted ─► ask the user: accept / extend / change spec
        └─ report_only ──────► (visual-qa mode) show defects, ask before fixing
```

Rules:

- **Only blocker and major defects drive the loop.** Minor ones are
  listed and can be batched into one optional polish round at the end, if
  the user wants it.
- **Route in pipeline order** (S2b → S3 → S4 → S5 → S6), because upstream
  fixes can resolve downstream defects.
- **Spec fixes need Gate B again.** A route to S3 (page-specification)
  changes the build contract. After `complete --fix`, set Gate B back
  with `$S gate --gate B --status requested`, present the changed parts,
  and record approval before the build stages re-run.
- **Design-system and spec fixes cascade.** Every downstream stage becomes
  stale and re-runs. Build fixes (S4/S5/S6) are targeted: other completed
  build stages are kept, and only QA (and release) re-run. The script
  handles this when you pass `--fix`.
- **Unroutable defects** (owner missing or not a fixable skill) go to the
  user. Don't guess an owner.
- **Budget**: `config.qa_budget` iterations (default 3). On exhaustion
  never continue silently. Options:
  `$S qa --project <p> --accept "<user's note>"` (proceed to release with
  known issues), `$S qa --project <p> --extend 1`, or change the spec.
- **Release-audit failures** use the same routing. If S8 writes
  `release/defects.json`, run `$S qa --project <p> --defects-file release/defects.json`
  and route the same way. QA and release then re-run.
- `qa` reads defects with `status: "open"`. Stage skills mark a defect
  fixed in their result's `resolved_defects`. visual-qa confirms it in the
  next iteration.
