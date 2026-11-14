# Execution modes

A mode decides which stages this run may execute (its *scope*). Every
stage upstream of the scope must already be `completed`. If one isn't,
`next` returns `missing_prerequisites` and you ask the user. It is never
skipped and never quietly pulled into scope.

| Mode | Scope | Ends with | Pick it when the user says… |
|---|---|---|---|
| `full` | S0 → S8 | Gate C, project report | "build a site inspired by X", "recreate the feel of X", no qualifier |
| `research` | S0, S1 | research artifacts, report | "just analyse/research/inspect X", "don't build anything yet" |
| `design-spec` | S0 → S3 | Gate B, report | "design/spec it out", "give me the design system and page specs" |
| `implementation` | S4 → S6 | report (then suggest visual-qa) | "build it from the approved spec", "implement the site" |
| `visual-qa` | S7 | defect report | "QA the site", "check the build visually / on mobile" |
| `resume` | the mode stored in state | as that mode | "continue", "pick up where we left off", project already exists |

Notes:

- `init --mode` records the mode. `next --mode <m>` switches it later
  (for example, widening `research` to `full` after the user agrees).
- `resume` is not stored. It means: lock → reconcile → continue with
  `run_mode` from state. If the user names a different mode while
  resuming, switch with `next --mode`.
- `implementation` also requires Gate B approved. `next` returns the gate
  if it isn't.
- `visual-qa` runs one QA iteration and reports. `qa` returns
  `report_only` instead of `fix`. Route fixes only if the user asks, and
  then switch to `full` so S8 follows.
- A run with only one target page is normal. Pass it with `--pages`.
  Stage skills read the target pages from `config.target_pages`.
- Ambiguous request? Prefer the narrower mode and say which mode you chose
  in one line. Widening later is cheap; unwanted builds are not.
