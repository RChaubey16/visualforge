# VisualForge — Artifact Schema

Status: **Approved** (2026-11-14). Canonical JSON Schemas will live in `schemas/`
(one file per type below) and be created before the first skill.

## 1. Project directory structure

```
projects/<project-name>/
├── brief.md                         S0  project brief (Gate A record)
├── project-report.md                S0  orchestrator report, rewritten on every stop
├── state/                           S0  orchestrator only
│   ├── project-state.json
│   ├── run-log.jsonl
│   ├── status.md
│   ├── stages/<stage-id>.result.json   written by each stage
│   ├── envelopes/<stage-id>.run<n>.json  invocation envelopes (audit trail)
│   └── locks/orchestrator.lock
├── research/                        S1  reference-analyzer
│   ├── capture-plan.json
│   ├── observations.json
│   ├── assets-inventory.json
│   ├── research-report.md
│   ├── pages/<slug>/
│   │   ├── page-meta.json           url, title, visible text, fonts, :root vars
│   │   └── <viewport>/
│   │       ├── viewport.png
│   │       ├── full.png
│   │       ├── a11y-snapshot.md
│   │       ├── styles.json          computed-style samples
│   │       └── interactions/<probe-id>/{before,after}.png, diff.json
│   └── motion/<slug>/
│       ├── animations.json          getAnimations() + computed transitions
│       ├── scroll-steps/<n>.png
│       ├── scroll.webm              Playwright Test video
│       └── reduced-motion/…
├── analysis/                        S2a ux-design-analyst
│   ├── ux-analysis.md
│   └── ux-findings.json
├── design/                          S2b design-system-extractor
│   ├── reference-tokens.json
│   ├── tokens.json
│   └── design-system.md
├── specs/                           S3  page-specification
│   ├── site-spec.md
│   ├── sitemap.json
│   ├── pages/<slug>.json (+ .md)
│   ├── content/<slug>.json
│   ├── motion-spec.json
│   └── asset-briefs.md
├── architecture/                    S4  nextjs-architect
│   ├── nextjs-architecture.md
│   └── component-inventory.json
├── build/                           S5, S6 logs
│   ├── implementation-log.md
│   └── motion-log.md
├── qa/                              S7  visual-qa
│   ├── summary.json
│   └── iteration-<n>/{qa-report.md, defects.json, screenshots/, test-results/}
├── release/                         S8  release-auditor
│   ├── release-report.md
│   ├── checklist.json
│   └── defects.json                 failing checks, routed like QA defects
└── site/                            S4–S6 Next.js app
```

**Write ownership is exclusive**: each directory has exactly one writing
stage (listed above). `site/` is shared by S4/S5/S6 with the file-level
boundaries in `skill-contracts.md`; S7 may write only `site/tests/qa/**`.

## 2. Common conventions

- JSON files: UTF-8, 2-space indent, top-level `schema_version` and
  `generated_by: { skill, skill_version, stage_id, run }`.
- Markdown artifacts begin with YAML front matter carrying the same
  fields plus `sources: [paths]`.
- IDs: `<prefix>-<zero-padded n>` — `obs-0042`, `ux-007`, `tok-…`,
  `sec-<page>-<n>`, `mot-012`, `def-<iter>-<n>`.
- Paths inside artifacts are relative to the project root.
- Viewport keys: `w<width>` (e.g. `w375`, `w1440`).

## 3. Evidence and epistemic labels

Every claim about the reference site uses this structure:

```json
{
  "epistemic": "observed | inferred | recommended",
  "evidence": [
    {
      "type": "screenshot | computed_style | a11y_snapshot | dom_eval | network | video | user_provided",
      "path": "research/pages/home/w1440/styles.json",
      "selector": "main h1",
      "tool": "playwright-mcp:browser_evaluate",
      "captured_at": "2026-11-14T13:02:11Z"
    }
  ],
  "confidence": "high | medium | low"
}
```

Rules:
- `observed` **requires** ≥1 evidence item whose `path` exists.
- `inferred` requires ≥1 supporting observation ID (`based_on`).
- `recommended` describes what *we* will do; it never asserts a
  reference property, and lives in fields named `recommendation*`.

## 4. Stage invocation envelope

```json
{
  "project_root": "projects/acme-studio",
  "stage_id": "S5-implement",
  "run": 2,
  "mode": "run | fix",
  "inputs": { "component_inventory": "architecture/component-inventory.json", "...": "..." },
  "output_dir": "site/",
  "config": { "viewports": [375, 768, 1280, 1440], "qa_budget": 3 },
  "defects": ["def-1-004", "def-1-009"],
  "resume_from_checkpoint": "sec-home-03"
}
```

## 5. `state/project-state.json`

```json
{
  "schema_version": "1.0",
  "project": { "name": "acme-studio", "reference_url": "https://example.com", "created_at": "…" },
  "run_mode": "full | research | design-spec | implementation | visual-qa",
  "config": { "viewports": [375, 768, 1280, 1440], "qa_budget": 3, "commits_authorised": false,
              "target_pages": ["home"] },
  "tools": { "checked_at": "…", "browser_mcp": "available | unavailable",
             "node": { "version": "v22.x", "ok": true }, "npm": {…}, "npx": {…}, "git": {…},
             "problems": [] },
  "gates": {
    "A": { "status": "approved", "at": "…", "notes": "" },
    "B": { "status": "pending" },
    "C": { "status": "pending" }
  },
  "stages": {
    "S1-research": {
      "status": "completed",
      "run": 1,
      "skill_version": "0.1.0",
      "input_fingerprint": "sha256:…",
      "outputs": { "research/observations.json": "sha256:…" },
      "started_at": "…", "finished_at": "…",
      "attempts": 0,
      "checkpoints_done": 8, "checkpoints_total": 8,
      "error": null,
      "blocked_reason": null
    }
  },
  "qa": { "iteration": 1, "open": { "blocker": 0, "major": 3, "minor": 5 },
          "decision": "pass | fix | budget_exhausted | report_only | accepted" },
  "git": { "branch": "feature/acme-studio-site", "last_commit": null }
}
```

`attempts` counts runs since the last success (max 2, then `blocked`).
`blocked_reason` is one of `missing_skill`, `browser_unavailable`,
`retries_exhausted`, `stage_reported`, `other`. The first two are
re-checked on every resume. The website-orchestrator skill's
`scripts/vf_state.py` is the only writer of this file.

## 6. `state/stages/<stage-id>.result.json`

```json
{
  "stage_id": "S2b-design-system",
  "status": "completed | failed | blocked",
  "outputs": [{ "path": "design/tokens.json", "sha256": "…" }],
  "checkpoints": [{ "id": "colour", "status": "done", "outputs": ["…"] }],
  "quality_checklist": [{ "criterion": "AA contrast for all pairings", "result": "pass | fail | not_run", "detail": "" }],
  "warnings": [],
  "open_questions": [],
  "recapture_requests": [],
  "resolved_defects": [],
  "error": null
}
```

## 7. Core record types

**Observation** (`research/observations.json → observations[]`)
```json
{ "id": "obs-0042", "page": "home", "viewport": "w1440",
  "category": "typography | color | spacing | layout | component | interaction | motion | asset | a11y | content",
  "subject": "main h1", "property": "font-size", "value": "72px",
  "epistemic": "observed", "evidence": [ … ], "confidence": "high" }
```

**UX finding** (`analysis/ux-findings.json → findings[]`)
```json
{ "id": "ux-007", "topic": "hierarchy | navigation | flow | interaction | responsive | motion | a11y",
  "statement": "…", "epistemic": "inferred", "based_on": ["obs-0042", "obs-0051"],
  "principle": true, "recommendation": "…", "confidence": "medium" }
```

**Token** (`design/tokens.json` — W3C Design Tokens–style)
```json
{ "color": { "surface": { "$value": "{palette.sand.50}", "$type": "color",
    "$description": "…", "rationale": "…", "relationship_ref": "rel-03" } },
  "motion": { "duration": { "enter": { "$value": "320ms", "$type": "duration" } } } }
```
`reference-tokens.json` uses the same shape plus `observed_in: [obs IDs]`,
`frequency` and `epistemic` per value.

**Page spec** (`specs/pages/<slug>.json`)
```json
{ "slug": "home", "route": "/", "title": "…",
  "sections": [{ "id": "sec-home-01", "type": "hero", "purpose": "…",
    "principles": ["ux-002"], "content_ref": "specs/content/home.json#hero",
    "layout": { "w375": "…", "w1440": "…" }, "tokens": ["color.surface", "type.display"],
    "components": ["Button", "HeroMedia"], "motion_refs": ["mot-003"],
    "a11y": ["…"], "acceptance": [{ "id": "ac-home-01-1", "text": "…", "testable_by": "visual | dom | interaction | a11y" }] }] }
```

**Motion entry** (`specs/motion-spec.json → motions[]`)
```json
{ "id": "mot-003", "section": "sec-home-01", "trigger": "load | in-view | hover | scroll-progress | route",
  "character": "…", "properties": ["opacity", "transform"], "tokens": ["motion.duration.enter", "motion.ease.out"],
  "reduced_motion": "…", "principle": "ux-011" }
```

**Component inventory** (`architecture/component-inventory.json → components[]`)
```json
{ "name": "HeroMedia", "path": "site/src/components/sections/HeroMedia.tsx",
  "kind": "primitive | section | layout", "rendering": "server | client",
  "client_reason": null, "used_in": ["sec-home-01"] }
```

**Defect** (`qa/iteration-<n>/defects.json → defects[]`, also used by S8)
```json
{ "id": "def-1-004", "severity": "blocker | major | minor | note",
  "category": "spec | token | responsive | interaction | motion | a11y | performance | originality | build | console",
  "page": "home", "viewport": "w375", "section": "sec-home-01",
  "acceptance_ref": "ac-home-01-1", "expected": "…", "actual": "…",
  "evidence": [{ "type": "screenshot", "path": "qa/iteration-1/screenshots/home-w375.png" }],
  "owner_skill": "frontend-implementer", "regression": false,
  "status": "open | fixed | verified | accepted" }
```

**Release checklist** (`release/checklist.json → checks[]`)
```json
{ "id": "perf-lcp-home", "category": "build | test | perf | a11y | originality | licence | coverage",
  "result": "pass | fail | not_run", "measured": "1.9s", "threshold": "≤2.5s", "evidence": "…" }
```

## 8. Versioning

`schema_version` uses semver. A major schema bump makes artifacts from
the old version `stale`; the orchestrator offers migration or re-run.
Skill versions (from each `SKILL.md` front matter `metadata.version`) are
part of every stage's input fingerprint, so upgrading a skill re-runs
its stage and the downstream chain.
