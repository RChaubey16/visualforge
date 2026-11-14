# VisualForge — Skill Contracts

Status: **Approved** (2026-11-14)

Paths below are relative to `projects/<project-name>/` unless they start
with `.claude/`, `schemas/` or `docs/`. Artifact shapes are defined in
`artifact-schema.md`. Shared quality bars are in `quality-standards.md`.

Every skill shares these conventions, which are not repeated per skill:

- **Input** is a stage invocation envelope (`artifact-schema.md` §4).
- **Output** always includes `state/stages/<stage-id>.result.json`.
- **Modes**: `run` (normal) and `fix` (address routed defect IDs only).
  Skills that never receive defects support only `run`.
- **Evidence**: any statement about the reference site carries an
  `epistemic` label and, if `observed`, an evidence reference.
- **No invented capability**: if a needed tool is unavailable, the
  affected work is marked `not_run` / `blocked`, never simulated.

---

## 1. website-orchestrator

**Purpose.** Drive a VisualForge project end to end: initialise it,
invoke stage skills in dependency order, persist state, enforce human
gates, route QA defects, and resume interrupted runs.

**Trigger conditions.** The user asks to build/clone-the-feel-of/redesign
from a reference URL; asks to start, continue, resume or check the status
of a VisualForge project; or names a project in `projects/`.

**Required inputs.** Reference URL (new project) or project name
(existing). For new projects, Gate A collects: project name (kebab-case),
page scope (URLs or "primary nav pages, max N"), original brand name and
one-line positioning, audience, constraints (pages, languages, must-haves,
exclusions). Optional: viewport set override, QA iteration budget.

**Required tools.** Skill (invoke stage skills), Agent (S2 parallel pair
only), Read/Write/Edit, Bash (hashing, schema validation, git),
AskUserQuestion (gates).

**Execution procedure.**
1. Resolve project; create `projects/<name>/` skeleton and `brief.md` if new.
2. Acquire lock; `reconcile` state (`workflow.md` §4).
3. Present Gate A for new projects; record approval.
4. Run the main loop (`workflow.md` §2.1): build envelope → invoke skill →
   validate result (§3.3) → update state → log.
5. Run S2a ‖ S2b as two subagents; wait for both.
6. Present Gate B with a summary of design system, sitemap, page specs.
7. Run S4–S7; manage the QA loop (`workflow.md` §6).
8. Run S8; present Gate C with the release report.
9. Release lock; print status summary.

**Expected outputs.** Project skeleton, `brief.md`,
`state/project-state.json`, `state/run-log.jsonl`, gate records,
`state/status.md` (human-readable progress summary).

**Output file locations.** `brief.md`, `state/`.

**Quality criteria.** Never runs a stage before its predecessors are
`completed` and gates approved; never repeats a valid completed stage;
state always schema-valid; every transition logged; never edits stage
artifacts itself (only state and brief).

**Failure handling.** See `workflow.md` §7. Retries a failed stage once;
then `blocked` with a clear request to the user.

**Dependencies.** All stage skills; `schemas/`.

---

## 2. reference-analyzer

**Purpose.** Inspect the reference site in a real browser and record
raw, evidence-backed observations: structure, computed styles, layout at
each viewport, assets, interactions and motion. It **observes; it does
not interpret or recommend.**

**Trigger conditions.** Orchestrator stage S1; or a re-capture request
(specific page/viewport/interaction) routed by the orchestrator.

**Required inputs.** `brief.md` (URL, page scope, viewport set); optional
re-capture request list.

**Required tools.** Playwright MCP (`browser_navigate`,
`browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`,
`browser_resize`, `browser_hover`, `browser_click`, `browser_press_key`,
`browser_wait_for`, `browser_emulate_media`, `browser_console_messages`,
`browser_network_requests`); Playwright Test for full-page screenshot
sets and scroll videos; Bash; Write. Bundled `scripts/` provide
`browser_evaluate` payloads (computed-style sampler, token-candidate
collector, `document.getAnimations()` dump, font/asset inventory).

**Execution procedure.**
1. Build `research/capture-plan.json`: pages × viewports × probes.
   Discover pages from primary navigation if scope says so (cap N).
2. For each page, for each viewport (default 375, 768, 1280, 1440):
   navigate, wait for network idle + fonts, dismiss consent only if needed
   (logged), take viewport + full-page screenshots, accessibility snapshot,
   run style sampler over landmark/heading/text/button/link/card elements.
3. Collect global facts once per page: CSS custom properties on `:root`,
   loaded fonts (`document.fonts`), media query breakpoints found in
   stylesheets (same-origin only; cross-origin noted as unreadable),
   asset inventory with URLs.
4. Interaction probes: hover/focus states on representative controls
   (before/after screenshots + computed-style diffs), menu open/close at
   mobile width, keyboard tab order sample.
5. Motion probes: `document.getAnimations()` and computed
   `transition`/`animation` properties at load and after stepped scroll;
   stepped scroll screenshots; Playwright Test video of a scroll pass;
   `prefers-reduced-motion: reduce` comparison via `browser_emulate_media`.
6. Record each fact as an `Observation` with evidence. Write a factual
   `research-report.md` (no recommendations section).
7. Checkpoint after every page × viewport.

**Expected outputs.** Capture plan, observations, screenshots, snapshots,
style samples, motion captures, asset inventory, research report.

**Output file locations.** `research/` — `capture-plan.json`,
`observations.json`, `pages/<slug>/<viewport>/…`, `motion/…`,
`assets-inventory.json`, `research-report.md`.

**Quality criteria.** 100% of observations have evidence that exists on
disk; every planned capture is `done`, `failed` (with reason) or
`skipped` (with reason); no `recommended` labels anywhere; known
limitations (canvas, cross-origin CSS, JS easing) explicitly listed.

**Failure handling.** Page load failure → retry once, then record
`failed` for that page and continue. Bot wall/CAPTCHA → stop, `blocked`,
ask user for alternatives; never attempt to bypass. Consent banners that
obscure content are dismissed once, and the dismissal is logged.

**Dependencies.** S0 (brief). Upstream of S2a, S2b, and S7 (reference
screenshots for principle comparison).

---

## 3. ux-design-analyst

**Purpose.** Interpret research into transferable UX principles:
information architecture, navigation model, content hierarchy, page and
section patterns, interaction patterns, responsive strategy, and motion
character. Qualitative "why/when", not values.

**Trigger conditions.** Stage S2a.

**Required inputs.** `research/observations.json`, screenshots,
accessibility snapshots, `research-report.md`, `brief.md`.

**Required tools.** Read (incl. images), Write. No browser. Re-captures
are requested via the result file's `recapture_requests`.

**Execution procedure.**
1. Inventory page types and section patterns (hero, feature grid,
   proof, CTA, footer…) with observation IDs.
2. Describe navigation, IA depth, hierarchy and reading flow per viewport.
3. Describe interaction patterns (hover/focus language, disclosure,
   menus) and responsive transformations between viewports.
4. Describe motion character (entrance, scroll, hover, page transition)
   from motion observations — categorical, not numeric.
5. Distil 5–12 **design principles**, each: statement, supporting
   observation IDs, `epistemic` (`inferred`), and a separate
   `recommended` application for the original site.
6. Note accessibility issues observed in the reference so we do not
   inherit them.

**Expected outputs.** UX analysis report and structured findings.

**Output file locations.** `analysis/ux-analysis.md`,
`analysis/ux-findings.json`.

**Quality criteria.** Every finding cites ≥1 observation ID;
observations, inferences and recommendations are in separate fields;
no numeric token values (those belong to S2b); principles are phrased to
transfer to a different brand.

**Failure handling.** Insufficient evidence for a topic → record a gap
and a `recapture_request` rather than guessing. Orchestrator may run a
targeted S1 re-capture, then re-run S2a.

**Dependencies.** S1. Parallel with S2b. Upstream of S3, S7.

---

## 4. design-system-extractor

**Purpose.** (a) Consolidate observed visual values into a **reference
token inventory** (colour, typography, spacing, radii, borders, shadows,
breakpoints, layout widths, motion durations/easings), and (b) propose an
**original design system** that preserves the reference's *relationships*
(scale ratios, contrast strategy, density, rhythm) with original values,
palette and typography.

**Trigger conditions.** Stage S2b; fix mode for token defects from S7.

**Required inputs.** `research/observations.json`, style samples,
`:root` custom properties, font inventory, motion captures, `brief.md`
(brand positioning).

**Required tools.** Read, Write, Bash (bundled scripts: value
clustering, scale-ratio fit, WCAG contrast calculator, token JSON →
CSS variables preview).

**Execution procedure.**
1. Cluster observed values; derive scales (e.g. type ratio, spacing
   base) with frequency and observation IDs → `reference-tokens.json`.
   Mark fitted scales `inferred`.
2. Derive design relationships (ratio, contrast strategy, neutral vs.
   accent usage, density).
3. Propose original tokens: new palette meeting contrast targets, open-
   licensed type pairing with the same role structure, spacing/radius/
   shadow/motion scales honouring the relationships. Semantic layer
   (`color.surface`, `color.text.muted`, `motion.duration.enter`…) over
   primitive layer.
4. Validate contrast for every declared text/surface pairing.
5. Document rationale linking each original decision to a relationship.

**Expected outputs.** Reference token inventory, original tokens,
design-system documentation.

**Output file locations.** `design/reference-tokens.json`,
`design/tokens.json`, `design/design-system.md`.

**Quality criteria.** No original token value equals a distinctive
reference brand value (brand colours, proprietary fonts); every declared
text pairing meets WCAG 2.2 AA; tokens are semantic + primitive; every
reference token cites observations; fonts have documented licences.

**Failure handling.** Too few samples for a category → record gap,
propose a sensible original default labelled `recommended` with no
reference claim. Font licence unknown → choose an open-licensed alternative.

**Dependencies.** S1. Parallel with S2a. Upstream of S3, S4, S7, S8.

---

## 5. page-specification

**Purpose.** Define the original website: sitemap, per-page section
specs, original copy, asset briefs, responsive behaviour and motion
intent — the single build contract for S4–S7.

**Trigger conditions.** Stage S3; fix mode for spec defects (requires
Gate B re-approval of the changed parts).

**Required inputs.** `brief.md`, `analysis/ux-findings.json`,
`design/tokens.json`, `design/design-system.md`.

**Required tools.** Read, Write.

**Execution procedure.**
1. Sitemap and routes from brief scope + IA principles.
2. For each page: ordered sections, each with purpose, applied
   principle IDs, content (original copy), layout per viewport, tokens
   used, components needed, states, accessibility notes, acceptance
   criteria (testable).
3. Motion spec: per section, trigger, motion character, token refs,
   reduced-motion behaviour.
4. Asset briefs for original imagery/illustration/icons (generated,
   licensed, or placeholder — never reference assets).
5. Summarise for Gate B.

**Expected outputs.** Site spec, sitemap, page specs, content, motion
spec, asset briefs.

**Output file locations.** `specs/site-spec.md`, `specs/sitemap.json`,
`specs/pages/<slug>.json` (+ `.md` rendering), `specs/content/<slug>.json`,
`specs/motion-spec.json`, `specs/asset-briefs.md`.

**Quality criteria.** Every section has testable acceptance criteria;
every token ref exists in `tokens.json`; copy is original (no sentences
reused from reference); every motion has a reduced-motion variant; every
page defines behaviour at every viewport in the set.

**Failure handling.** Conflicting principles or brief gaps → list as
open questions for Gate B rather than deciding silently.

**Dependencies.** S2a, S2b. Upstream of S4–S8.

---

## 6. nextjs-architect

**Purpose.** Create the Next.js application structure and the contracts
the implementer fills in.

**Trigger conditions.** Stage S4; fix mode for config/token-pipeline/
routing defects.

**Required inputs.** `specs/sitemap.json`, `specs/pages/*.json`,
`design/tokens.json`, `specs/motion-spec.json`.

**Required tools.** Bash (`npx create-next-app`, npm, git), Write/Edit, Read.

**Execution procedure.**
1. Scaffold `site/` (App Router, TypeScript strict, Tailwind, ESLint).
2. Generate `app/tokens.css` (CSS variables) from `tokens.json` with a
   bundled script; map Tailwind theme to the variables (no raw values in
   components).
3. Create route files for every sitemap entry (placeholder content),
   root layout, metadata, font loading via `next/font`.
4. Define component inventory: primitives, sections, layout; mark each
   Server or Client (Client only for interactivity/motion).
5. Install Motion for React and Playwright Test; create
   `playwright.config.ts` with the project viewport set as projects.
6. Add npm scripts: `dev`, `build`, `lint`, `typecheck`, `test:e2e`, `test:visual`.
7. Verify `build`, `lint`, `typecheck` pass on the skeleton.

**Expected outputs.** Runnable skeleton, architecture document,
component inventory.

**Output file locations.** `site/…`, `architecture/nextjs-architecture.md`,
`architecture/component-inventory.json`.

**Quality criteria.** Clean build/lint/typecheck; tokens only via CSS
variables; every route present; Client Components justified in inventory.

**Failure handling.** Package install failure → retry, then `blocked`
with the error. Version conflicts → pin and record in architecture doc.

**Dependencies.** S3 (and S2b tokens via S3). Upstream of S5–S8.

---

## 7. frontend-implementer

**Purpose.** Implement components and pages from the specs, static and
accessible first, section by section.

**Trigger conditions.** Stage S5; fix mode for layout, responsive,
markup, accessibility and content defects.

**Required inputs.** `architecture/component-inventory.json`, `site/`
skeleton, `specs/pages/*.json`, `specs/content/*.json`, `design/tokens.json`.

**Required tools.** Read/Write/Edit, Bash (dev server, lint, typecheck),
Playwright MCP for a quick self-check screenshot of each finished section
(not a substitute for S7).

**Execution procedure.**
1. Build primitives from the inventory.
2. For each page, for each section: implement → render → self-check at
   smallest and largest viewport → checkpoint.
3. Semantic HTML, landmarks, heading order, focus styles, alt text from
   asset briefs.
4. Run lint + typecheck after each page.

**Expected outputs.** Implemented components and pages; implementation log.

**Output file locations.** `site/src/…`, `build/implementation-log.md`.

**Quality criteria.** Every acceptance criterion addressed (logged per
section); no hard-coded design values; Server Components by default;
lint/typecheck clean.

**Failure handling.** Spec ambiguity → choose the conservative option,
log it as an assumption, surface it in the result's `open_questions`.
Build break → fix before checkpointing.

**Dependencies.** S4. Upstream of S6, S7.

---

## 8. motion-engineer

**Purpose.** Add motion per `specs/motion-spec.json` using Motion for
React, keeping it performant and accessible.

**Trigger conditions.** Stage S6; fix mode for motion defects.

**Required inputs.** `specs/motion-spec.json`, `design/tokens.json`
(motion tokens), implemented `site/`.

**Required tools.** Read/Write/Edit, Bash, Playwright MCP
(`browser_emulate_media` for reduced motion, stepped screenshots),
Playwright Test (video).

**Execution procedure.**
1. Create shared motion utilities reading motion tokens (durations,
   easings as CSS variables / exported constants).
2. Implement each motion entry in the smallest possible Client
   Component wrapper; keep content in Server Components.
3. Animate transform/opacity only unless the spec justifies otherwise.
4. Implement reduced-motion variants (`useReducedMotion` / media query).
5. Verify each entry: normal vs. reduced motion capture; checkpoint.

**Expected outputs.** Motion implementation and log.

**Output file locations.** `site/src/…` (motion components/utilities),
`build/motion-log.md`.

**Quality criteria.** Every spec entry implemented or explicitly
deferred; no layout shift from entrance animations; reduced-motion
verified; no animation of layout-triggering properties without justification.

**Failure handling.** Effect not achievable within performance budget →
implement the simplified variant, log the deviation, flag for Gate C.

**Dependencies.** S5. Upstream of S7.

---

## 9. visual-qa

**Purpose.** Inspect the built site in a browser and produce routed,
evidence-backed defects. It **finds; it does not fix.**

**Trigger conditions.** Stage S7 (each loop iteration).

**Required inputs.** Running `site/` (the skill starts it), `specs/`,
`design/tokens.json`, `analysis/ux-findings.json`, reference screenshots
from `research/`, previous iteration's results.

**Required tools.** Bash (start server, run Playwright Test), Playwright
Test (screenshots per viewport, interaction tests, visual regression
baselines), Playwright MCP (exploratory inspection, hover/focus, keyboard
navigation, `browser_evaluate` for computed-style token checks),
`@axe-core/playwright` (else `not_run`), Read (images).

**Execution procedure.**
1. Start production build (`build` + `start`); fall back to dev only if
   build fails (that itself is a `blocker`).
2. Capture every page × viewport.
3. Checks: (a) spec conformance per acceptance criterion; (b) token
   conformance via computed styles; (c) responsive — no horizontal
   overflow, no clipped text, tap targets; (d) interaction — hover,
   focus-visible, keyboard nav, menus; (e) motion — normal and reduced;
   (f) accessibility scan; (g) console errors; (h) principle alignment —
   side-by-side review with reference screenshots for *design principles*
   (hierarchy, rhythm, density), explicitly **not** pixel likeness;
   (i) originality smell test (no reference copy/assets visible).
4. Regression comparison against previous iteration baselines.
5. Write defects with severity, evidence and `owner_skill`.

**Expected outputs.** QA report, defects, screenshots, test results.

**Output file locations.** `qa/iteration-<n>/` — `qa-report.md`,
`defects.json`, `screenshots/…`, `test-results/…`; `qa/summary.json`
(latest status across iterations).

**Quality criteria.** Every page × viewport × check has a status
(`pass`/`fail`/`not_run`); every defect has evidence and an owner;
no edits to `site/` source (test files under `site/tests/` excepted).

**Failure handling.** Server won't start → single `blocker` defect owned
by nextjs-architect or frontend-implementer based on the error. Flaky
check → rerun up to 2×, report as `flaky` if inconsistent.

**Dependencies.** S6 (and S1, S2a, S2b, S3 as references). Upstream of S8;
feeds fix-mode runs of S2b, S3, S4, S5, S6.

---

## 10. release-auditor

**Purpose.** Final, independent release gate across quality,
performance, accessibility, originality and licensing.

**Trigger conditions.** Stage S8 after visual-qa has no open
`blocker`/`major` defects (or the user accepted them).

**Required inputs.** `site/`, `qa/summary.json`, all specs, design system,
`research/assets-inventory.json`, `brief.md`.

**Required tools.** Bash (`lint`, `typecheck`, `build`, `test:e2e`,
dependency licence listing), Playwright Test (performance metrics: LCP,
CLS via `PerformanceObserver`; transfer sizes), Read.

**Execution procedure.**
1. Run lint, typecheck, tests, production build; record outputs.
2. Measure performance on key pages against budgets.
3. Re-run accessibility scan on all pages.
4. Originality audit: compare site text against reference text
   (exact/near-duplicate sentence check), verify no reference asset URLs
   or hashes appear in `site/`, verify font and image licences.
5. Spec coverage: every acceptance criterion traced to a passing check.
6. Check `site/` README, env, and `next build` output for warnings.
7. Write release report with verdict `ready` / `ready-with-known-issues` /
   `not-ready`.

**Expected outputs.** Release report and machine-readable checklist.

**Output file locations.** `release/release-report.md`,
`release/checklist.json`.

**Quality criteria.** Every check has a measured result (no claimed
results); verdict follows mechanically from checklist rules
(`quality-standards.md` §8); known issues listed with owner.

**Failure handling.** Failing checks become defects routed by the
orchestrator (same mechanism as QA), then S8 re-runs. Never edits code.

**Dependencies.** S7 (pass). Terminal stage before Gate C.
