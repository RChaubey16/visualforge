# VisualForge — Quality Standards

Status: **Approved** (2026-11-14). Thresholds are defaults; a project may tighten
them in `brief.md`. Loosening requires explicit user approval recorded
at a gate.

## 1. Evidence integrity (all skills)

1. A reference property is stated only if it was inspected with a real
   tool in this project and the evidence file exists.
2. Every claim is labelled `observed`, `inferred` or `recommended`
   (`artifact-schema.md` §3). Reports keep these in separate sections or
   fields; prose may not blur them ("the site uses…" requires
   `observed`).
3. Unknowns are written as unknowns, with the reason (not captured,
   cross-origin, canvas, blocked).
4. A check that did not run is `not_run`, never `pass`.

## 2. Research completeness (S1)

- Every page × viewport in the capture plan has a terminal status.
- Minimum per captured page: viewport + full-page screenshot, a11y
  snapshot, computed-style samples for headings, body text, links,
  buttons, and the primary layout container.
- Interaction probes: ≥1 hover and focus probe per control type found;
  mobile navigation open/close where present.
- Motion: load and scroll captures; reduced-motion comparison.

## 3. Analysis quality (S2a, S2b)

- Each UX principle cites ≥2 observations, preferably across ≥2 pages.
- Principles are brand-agnostic (transferable).
- Reference token inventory cites observations for every value.
- Original token system: semantic + primitive layers; no distinctive
  reference brand value reused.

## 4. Specification quality (S3)

- Every section: purpose, principle refs, layout per viewport, tokens,
  components, acceptance criteria that are objectively testable.
- All copy original; no placeholder lorem ipsum at Gate B unless
  approved.
- Every motion entry has a reduced-motion behaviour.

## 5. Implementation standards (S4–S6)

- Next.js App Router, TypeScript `strict`, ESLint clean, `tsc --noEmit` clean.
- Server Components by default; every Client Component justified in the
  component inventory.
- Design values only via CSS variables / Tailwind theme mapped to them.
- Semantic HTML and landmarks; one `h1` per page; logical heading order.
- Images via `next/image` with explicit dimensions and meaningful `alt`
  (empty `alt` for decorative); fonts via `next/font`.
- Motion: transform/opacity by default; no CLS from entrances;
  `prefers-reduced-motion` respected.

## 6. Originality and licensing

- No copied text: release audit flags any sentence ≥ 8 words matching
  reference visible text (normalised).
- No reference assets: no reference asset URLs or file hashes in `site/`.
- Fonts: open licence (e.g. OFL) or user-supplied with confirmed licence.
- Logos, names and trademarks of the reference never appear.
- Third-party assets recorded with source and licence in
  `specs/asset-briefs.md` and verified in the release report.

## 7. Visual QA standards (S7)

Default viewport set: **375, 768, 1280, 1440** px wide (configurable).

| Check | Pass condition |
|---|---|
| Spec conformance | Every acceptance criterion verified `pass` |
| Token conformance | Sampled computed colours/fonts/sizes resolve to token values |
| Horizontal overflow | `scrollWidth <= clientWidth` at every viewport |
| Text clipping / overlap | None found in screenshot review |
| Tap targets | ≥ 24×24 CSS px (WCAG 2.2 AA 2.5.8); 44×44 recommended for primary actions |
| Focus | Visible focus indicator on every interactive element; logical tab order |
| Keyboard | All interactive features operable by keyboard; menus closable with Esc |
| Motion | Matches motion spec; reduced-motion variant verified |
| Accessibility scan | 0 serious/critical axe violations (`not_run` if the scanner is unavailable) |
| Console | 0 errors on load and interaction |
| Principle alignment | Reviewer notes per page referencing UX principle IDs; judged on principles, not pixel similarity |
| Regression | No previously-passing check now failing |

**Visual review method**: the reviewing model views screenshots
(Read on PNG), always comparing like-for-like viewport, and records
judgement as a `note`/defect with the screenshot path. Pixel-diff
visual regression (Playwright `toHaveScreenshot`) is used only between
iterations of *our* site, never against the reference.

## 8. Release standards (S8)

| Category | Threshold |
|---|---|
| Build / lint / typecheck / tests | All pass |
| LCP (lab, key pages, w1440 and w375) | ≤ 2.5 s |
| CLS | ≤ 0.1 |
| JS transferred on first load per route | ≤ 200 KB gzip (warn), ≤ 300 KB (fail) |
| Accessibility | 0 serious/critical violations; manual keyboard pass |
| Originality & licensing | All checks pass |
| Spec coverage | 100% acceptance criteria traced to a passing check or an accepted known issue |
| Open defects | 0 `blocker`; 0 `major` unless user-accepted |

Lab measurements are taken with Playwright against `next start` on the
local machine and reported as lab values, not field data.

Verdict rules: any `fail` in build/originality/licence → `not-ready`.
Otherwise any `fail` elsewhere or any user-accepted `major` →
`ready-with-known-issues`. Otherwise `ready`. Any `not_run` is listed
explicitly in the report.

## 9. Skill quality (Skill Creator methodology)

Each skill must have, before its PR is raised:

- `SKILL.md` < 500 lines, imperative, explains *why*; detail in
  `references/` with clear "read when" pointers.
- A trigger-accurate `description` (what + when), later optimised with
  the description loop.
- `evals/evals.json` with ≥ 3 realistic prompts across **≥ 2 different
  reference sites**, and objectively verifiable assertions (e.g. "every
  observation has an existing evidence path", "no `recommended` label in
  research/", "tokens.json validates against schema").
- A with-skill vs. baseline benchmark reviewed in the eval viewer.
- No website-specific values anywhere in the skill directory.
- Lint/tests for bundled scripts pass (CLAUDE.md feature completion).
