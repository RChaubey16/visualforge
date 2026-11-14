# VisualForge — System Overview

Status: **Approved** (2026-11-14)
Scope: architecture only. No skills and no Next.js application exist yet.

## 1. What VisualForge does

VisualForge takes a reference website URL and produces an **original**
Next.js website inspired by the reference's design philosophy, visual
language, UX, interactions, animations and responsive behaviour.

"Inspired by" means: we learn *principles* (rhythm, hierarchy, contrast
strategy, motion character, layout systems) from evidence we actually
captured, then express them through an original brand, original content
and original assets. We never clone markup, copy, imagery, logos or
proprietary fonts.

## 2. Design goals

| Goal | How the architecture serves it |
|---|---|
| Reusable across any reference site | Skills contain no site-specific values. Everything site-specific lives in `projects/<project-name>/`. |
| Evidence-based | Reference properties are recorded only from browser inspection, each with an evidence pointer (see `artifact-schema.md` §3). |
| Facts vs. recommendations kept apart | Every claim carries an `epistemic` label: `observed`, `inferred` or `recommended`. |
| Resumable | A single state file records stage status, input fingerprints and outputs. Completed, still-valid stages are skipped. |
| Incremental, testable | Implementation is section-by-section; QA runs against real rendered output. |
| Minimal agent sprawl | One orchestrator in the main session. Subagents are used only where work is genuinely independent (see `workflow.md` §5). |

## 3. Components

```
┌──────────────────────────────────────────────────────────────────────┐
│                         website-orchestrator                         │
│   (runs in the main session; owns state, gates, routing, resume)      │
└───────┬──────────────────────────────────────────────────────────────┘
        │ invokes skills in order, passes artifact paths (never blobs)
        ▼
  RESEARCH            ANALYSIS                       SPECIFICATION
  reference-   ──►  ux-design-analyst      ─┐
  analyzer     ──►  design-system-extractor ─┴──►  page-specification
                     (parallel pair)                   │
                                                       ▼  [Gate B: user approval]
  BUILD                                                │
  nextjs-architect ──► frontend-implementer ──► motion-engineer
                                                       │
  VERIFY                                               ▼
                         ┌────────────────────── visual-qa
                         │ defects routed back (bounded loop)
                         ▼                             │ pass
              owning build/spec skill                  ▼
                                                release-auditor
```

### 3.1 The ten skills

| # | Skill | Phase | One-line responsibility |
|---|---|---|---|
| 1 | `website-orchestrator` | Control | Run the pipeline, maintain state, enforce gates, route QA defects, resume. |
| 2 | `reference-analyzer` | Research | Capture raw, evidence-backed observations of the reference site. Observes; does not interpret. |
| 3 | `ux-design-analyst` | Analysis | Interpret observations into UX/IA, interaction and motion *principles*. Qualitative. |
| 4 | `design-system-extractor` | Analysis | Turn observed visual values into a reference token inventory, then propose an **original** token system. Quantitative. |
| 5 | `page-specification` | Spec | Define the original site: sitemap, page/section specs, original copy, motion intent, responsive rules. |
| 6 | `nextjs-architect` | Build | Scaffold `site/`, wire tokens into CSS variables + Tailwind, define routes, component inventory and test harness. |
| 7 | `frontend-implementer` | Build | Build components and pages section-by-section, static and accessible, from spec. |
| 8 | `motion-engineer` | Build | Add Motion for React behaviour per motion spec, with reduced-motion support. |
| 9 | `visual-qa` | Verify | Screenshot, responsive, interaction and accessibility inspection; produce routed defects. |
| 10 | `release-auditor` | Verify | Final gate: build/lint/type/test, performance, accessibility, originality & licensing audit, release report. |

Full contracts: `skill-contracts.md`. Ordering and edges:
`dependency-graph.md`. Runtime behaviour: `workflow.md`.

### 3.2 Ownership boundaries (anti-overlap rules)

These rules were written to remove the responsibility overlaps found in
review (see `dependency-graph.md` §5):

- **Observation vs. interpretation.** Only `reference-analyzer` touches
  the reference site in a browser. Analysts consume its artifacts and may
  request a targeted *re-capture* through the orchestrator; they never
  browse the reference ad hoc. This keeps every observed fact traceable.
- **Qualitative vs. quantitative.** `ux-design-analyst` owns *why/when*
  (hierarchy, flows, interaction patterns, motion character).
  `design-system-extractor` owns *what values* (colour, type scale,
  spacing, radii, shadows, breakpoints, motion durations/easings).
- **Motion split.** reference-analyzer records motion facts →
  ux-design-analyst describes motion character → design-system-extractor
  emits motion tokens → page-specification assigns motion intent per
  section → motion-engineer implements. No two skills author the same
  artifact.
- **Brand & content.** design-system-extractor owns the original visual
  identity (palette, type pairing, token values). page-specification owns
  original copy, information architecture and asset briefs.
- **Scaffold vs. build.** nextjs-architect creates structure, config,
  tokens wiring, primitives contracts and test harness. frontend-
  implementer fills them in. Architect does not build sections;
  implementer does not change config or the token pipeline.
- **Find vs. fix.** visual-qa and release-auditor never edit `site/`.
  They report defects with an owning skill; the orchestrator routes them.

## 4. Repository layout

```
visualforge/
├── CLAUDE.md
├── README.md
├── docs/architecture/          ← this documentation
├── .claude/skills/<skill>/     ← the 10 reusable skills (Skill Creator layout)
│   ├── SKILL.md
│   ├── references/             ← loaded on demand
│   ├── scripts/                ← deterministic helpers
│   ├── assets/                 ← templates
│   └── evals/evals.json        ← Skill Creator test prompts + assertions
├── schemas/                    ← canonical JSON Schemas for artifacts (shared by skills)
└── projects/<project-name>/    ← one isolated project per reference site
    └── site/                   ← the generated Next.js app
```

Per-project layout is defined in `artifact-schema.md` §1.

`schemas/` is the one shared resource between skills. It holds data
contracts only, no website-specific content, so it does not violate the
project-isolation rule. Skills reference it by repo path instead of
copying schemas into each skill, avoiding drift.

## 5. Tooling (only what actually exists)

| Need | Tool | Notes |
|---|---|---|
| Live reference inspection | Playwright MCP (`browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, `browser_resize`, `browser_hover`, `browser_click`, `browser_press_key`, `browser_wait_for`, `browser_emulate_media`, `browser_console_messages`, `browser_network_requests`) | One browser session. Not parallelised. |
| Repeatable capture & regression | Playwright Test (`@playwright/test`) | Screenshots per viewport, video for motion, trace files. Parallel via workers, not agents. |
| Implementation | Next.js App Router, TypeScript, Tailwind CSS, CSS variables, Motion for React | Permanent stack. |
| Version control | Git | Feature branch + PR per CLAUDE.md. |
| Accessibility scanning | `@axe-core/playwright` | **Approved addition** to the stack (2026-11-14). If it is unavailable in a given environment, a11y checks fall back to the accessibility snapshot + manual checklist and are labelled as such. |

Known capability limits, which skills must state rather than paper over:

- Canvas/WebGL/video content can be screenshotted but not introspected;
  findings about it are `observed` (visual only) or `inferred`.
- Scroll-linked and JS-driven animation is captured through
  `document.getAnimations()`, computed `transition`/`animation` styles,
  stepped screenshots and Playwright Test video. Easing curves of
  JS-driven tweens may not be recoverable and must be marked `inferred`.
- Content behind auth, geo or consent walls is out of scope unless the
  user provides access.
- Font files are identified by name and source; we do not reuse them
  unless the licence allows (see `quality-standards.md` §6).

## 6. Human gates

The orchestrator pauses for user approval at:

- **Gate A — Project brief** (after init): URL, page scope, brand name,
  audience, constraints.
- **Gate B — Specification** (after page-specification): design system +
  page specs + copy. Implementation starts only after approval.
- **Gate C — Release** (after release-auditor): report reviewed; user
  decides on commit/PR per CLAUDE.md Git rules.

The user can also be asked to decide when the QA loop exhausts its
iteration budget (see `workflow.md` §6).

## 7. Skill development methodology

Each skill is built with the Skill Creator plugin, one at a time, on its
own feature branch:

1. Capture intent from `skill-contracts.md` (the contract *is* the intent).
2. Draft `SKILL.md` (< 500 lines; detail moved to `references/`; pushy,
   trigger-accurate `description`).
3. Write 2–3 realistic eval prompts in `evals/evals.json` using
   **at least two structurally different reference sites** (to prove
   reusability; no single reference may be baked in).
4. Run with-skill vs. baseline, grade assertions, review in the eval viewer.
5. Iterate; then optimise the description for triggering.

Recommended build order follows the dependency graph: schemas →
orchestrator (state/resume core only) → reference-analyzer →
design-system-extractor & ux-design-analyst → page-specification →
nextjs-architect → frontend-implementer → motion-engineer → visual-qa →
release-auditor → orchestrator (full routing).
