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

(Skill body — replace this with the actual instructions for Claude.

Typical structure:

1. **What this skill is for** — one paragraph describing the situations where
   Claude should reach for the skill.
2. **Mental model** — the concepts Claude needs to hold in mind: entities,
   their relationships, the lifecycle.
3. **Tool inventory** — if this skill drives an MCP, list the tools and what
   each one is good for. If it's a pure-doc skill, describe the workflow.
4. **Patterns and recipes** — concrete examples of how to combine the tools
   or follow the workflow for common requests.
5. **Pitfalls** — what to avoid, what looks similar but isn't, edge cases.)
