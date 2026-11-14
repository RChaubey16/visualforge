# Resume and recovery

## What `reconcile` does

Run it at the start of every session on an existing project, after `lock`.

1. **Interrupted stages**: any stage still `running` becomes `failed`
   (`interrupted`). Its partial output is not trusted. The stage re-runs
   and may resume from its own checkpoints. Pass the last good checkpoint
   with `envelope --checkpoint <id>` if the result file or stage log shows one.
2. **Environment blocks are re-checked**: stages blocked for
   `missing_skill` or `browser_unavailable` go back to `pending`. `next`
   blocks them again if the cause is still there. Run preflight again
   when tools may have changed.
3. **Output integrity**: every completed stage's outputs are re-hashed.
   A missing file, or a changed one (`manual_edits`), makes that stage and
   everything downstream `stale`.
4. **Input fingerprints**: a completed stage whose inputs changed (brief,
   config, upstream outputs, skill version) becomes `stale`, along with
   its downstream stages.
5. Completed, valid stages are listed in `completed_and_valid` and are
   never re-run.

Tell the user what reconcile found before continuing, in one or two lines.

## Manual edits

A user may have edited an artifact on purpose (for example, tweaking
copy in `specs/content/home.json`). Ask: keep the edit or regenerate?
- **Keep**: re-run the stage with `envelope --mode fix --feedback "user
  edited <file>; incorporate it"` so the stage records the new hash
  properly. Downstream stages then re-run as stale.
- **Regenerate**: re-run the stage normally.

## Failures and retries

| Situation | Response |
|---|---|
| `complete` fails, `retry_allowed: true` | Re-run once: `envelope --feedback "<errors>"`, invoke again. |
| Second failure | `next` reports `blocked: retries_exhausted`. Report the errors and stop. |
| Skill returns `status: blocked` | Blocked right away. Relay its `error` and `open_questions`. |
| Stage skill not installed | `blocked: missing_skill`. Name the skill and say it must be built or installed in `.claude/skills/`. |
| Browser unavailable | `blocked: browser_unavailable` for S1/S7. Ask the user to connect Playwright MCP. Don't fall back to WebFetch/curl. |
| Skill invocation errors out (tool error) | `$S fail --stage <id> --reason "<error>"`, then retry per the rules above. |
| User cancels mid-stage | `$S fail --stage <id> --reason "cancelled by user"`, write the report, unlock. |

To unblock after the user fixes something manually (for example, they
supplied saved HTML for a bot-walled site), run reconcile. If the stage
was blocked for another reason, re-run it with
`envelope --feedback "<what changed>"`. The envelope resets it to running.

## Re-capture requests (S2a/S2b → S1)

If an analysis stage's result lists `recapture_requests`, run S1 once in
fix mode with those requests as feedback:
`envelope --stage S1-research --mode fix --feedback '<requests as JSON>'`,
invoke, `complete --fix`. That marks S2a/S2b stale, and they re-run.
Allow one re-capture round per project run, then proceed with the gaps
recorded.
