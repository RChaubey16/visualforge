# Project report template

Write to `projects/<name>/project-report.md` every time the orchestrator
stops: on success, at a gate, or when blocked. Fill it from
`state/project-state.json`, `state/status.md`, stage result files and
(when present) `release/release-report.md`. State only what the files
show. If a stage didn't run, say "not run" and why.

```markdown
# <Project name>: VisualForge project report

_Updated <ISO timestamp> · mode: <mode> · overall: <completed | waiting for Gate X | blocked | in progress>_

## Summary
<2–4 sentences: reference URL, target pages, original brand, where the project stands, and the one next step.>

## Stages
| Stage | Skill | Status | Runs | Key outputs / note |
|---|---|---|---|---|
| S0-init | website-orchestrator | completed | 1 | brief.md |
| … | … | … | … | … |

## Gates
| Gate | Status | When | Notes |
|---|---|---|---|

## Environment
<preflight results: browser MCP, node, npm, git, and any problems with the stages they block>

## Visual QA
<iterations run, open blocker/major/minor counts, decision, accepted known issues. Or "not run".>

## Release
<release-auditor verdict and failing or not_run checks. Or "not run".>

## Blockers and open questions
- <blocker>: <cause> → <what the user needs to do>

## Next step
<one concrete action, e.g. "Install the reference-analyzer skill, then say 'resume <name>'".>
```

Keep observed facts and recommendations apart. The report describes
project state. It doesn't summarise reference-site properties unless they
come from completed stage artifacts, and then it cites the file.
