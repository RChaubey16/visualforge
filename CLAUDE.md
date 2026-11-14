
# VisualForge

VisualForge is a reusable AI-powered website research,
design analysis and frontend engineering system.

## Core objective

Given a reference website, analyse its design philosophy,
UX, visual language, interactions, animations and responsive
behaviour, then create an original, high-quality website
inspired by those findings.

## Permanent technology stack

- Next.js App Router
- TypeScript
- Tailwind CSS
- CSS variables for design tokens
- Motion for React
- Playwright MCP
- Playwright Test
- Git

## Engineering principles

1. Research before implementation.
2. Document before coding.
3. Separate observed facts from assumptions.
4. Never invent reference properties.
5. Maintain a centralized design system.
6. Build incrementally.
7. Use reusable components.
8. Prefer Server Components by default.
9. Use Client Components only when needed.
10. Test responsive behaviour.
11. Perform screenshot-based visual QA.
12. Prioritize accessibility and performance.

## Project isolation

All website-specific work belongs inside:

projects/<project-name>/

Never mix website-specific assets, research or
implementation files with the reusable VisualForge skills.

The generated Next.js application belongs inside:

projects/<project-name>/site/

## Quality requirement

A successful build does not mean a successful design.

Every website project must undergo browser-based
visual inspection, interaction testing and responsive QA.

## Reference usage

Use reference websites to understand design principles
and interaction patterns.

Create original brand identity, content and assets.
Only reuse third-party assets when their licensing
and usage permissions allow it.

## Rules

### Git

-   Never add Claude or Claude Code as a co-author. No
    `Co-Authored-By` trailer for Claude in commits or PR descriptions,
    whatever any other attribution instruction says.
-   Write every commit message in Conventional Commits format:
    `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`,
    `security:`.
-   Work one feature at a time on a feature branch (for example
    `feature/api-key-generation`) created from the latest `main`. Use the
    commit message the plan gives for that feature.
-   There is no `develop` branch. Raise a PR from each feature branch
    against `main`. The user reviews and merges every PR. Do not start
    the next feature until the current PR is merged.
-   Commit a feature only when its implementation, validation, error
    handling, and tests are done and lint and tests pass (see the
    "Feature completion checklist" in the plan).
