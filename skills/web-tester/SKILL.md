---
name: web-tester
description: Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors/records scenarios that run deterministically via playwright-bdd in the pipeline.
---

# web-tester

## Scanning a page: delegate to the page-scanner subagent

When the user wants to turn a live page or component into reusable,
readable steps — "scan this page", "catalog the login form", "build the
step dictionary for the checkout flow" — delegate to the `page-scanner`
subagent (`agents/page-scanner.md`) rather than driving the `playwright`
MCP tools directly from this skill. It scans the page's accessibility tree
and writes/updates the dictionary this skill (and later authoring skills)
consume: `e2e/pages/*.ts` page objects, `e2e/steps/*.ts` playwright-bdd
step definitions, and `e2e/catalog.md` — all in the target repo under
test, not in this plugin. See `docs/examples/todomvc-scan.md` for a worked
example of the shape it produces.

This delegation is Claude-Code-specific: subagents (`agents/*.md`) are a
Claude-Code-only, convention-discovered feature, so on a host that doesn't
load them (e.g. Codex), follow the same contract inline instead —
`agents/page-scanner.md` is the source of the rules and
`docs/examples/todomvc-scan.md` is the output template.

## Making the catalog runnable: delegate to scaffold-bdd

Once `e2e/catalog.md` exists, the scenarios that will read it need
somewhere to run deterministically, with zero LLM involvement. Delegate
that to the `scaffold-bdd` skill (`skills/scaffold-bdd/SKILL.md`): it
scaffolds a self-contained `e2e/` subproject — `playwright-bdd` config, a
demo canary, and (when safe) CI wiring — into the target repo under test,
so `.feature` files run as `cd e2e && npx bddgen && npx playwright test
--config playwright.config.ts`. See `docs/examples/scaffold-bdd-run.md` for
the exact files it produces.

## Overview

- **Scan first** — `page-scanner` builds/updates the reusable dictionary:
  `e2e/pages/*.ts` page objects, `e2e/steps/*.ts` step definitions, and the
  phrase catalog `e2e/catalog.md`.
- **Scaffold once** — `scaffold-bdd` makes that catalog runnable in CI,
  without touching the catalog's contents.
- **Author scenarios** (a future package) will read `e2e/catalog.md` and
  write `e2e/features/*.feature`, one Given/When/Then line per phrase.

This skill's own job today is routing: point the user at `page-scanner` for
scanning a page into the catalog, and at `scaffold-bdd` for wiring up the
runner. Authoring `.feature` files from the catalog is a separate,
not-yet-built package.
