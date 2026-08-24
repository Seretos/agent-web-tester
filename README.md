# agent-web-tester

A Claude Code **skill** plugin. Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors/records scenarios that run deterministically via playwright-bdd in the pipeline.

This plugin ships the skill content plus an inline `mcpServers.playwright` block in both `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, launching a pinned `@playwright/mcp` server via `npx` — no bundled binary, no wrapper script.

**Prerequisite:** Node.js with `npx` on `PATH`. Enabling the plugin runs `npx -y @playwright/mcp@<pin>` to fetch/launch the server; nothing extra to install for the plugin itself.

## Install

```
/plugin marketplace add Seretos/agent-marketplace
/plugin install agent-web-tester@agent-marketplace
```

## First scan

Ask Claude to scan a live page — "scan this page", "catalog the login form",
"build the step dictionary for the checkout flow" — and the `web-tester`
skill delegates to the `page-scanner` subagent. It drives the bundled
Playwright MCP browser, reads the page's accessibility tree, and writes or
updates the reusable dictionary in the target repo under test: page objects
under `e2e/pages/*.ts`, step definitions under `e2e/steps/*.ts`, and the
phrase catalog `e2e/catalog.md`. See
[`docs/examples/todomvc-scan.md`](docs/examples/todomvc-scan.md) for a
worked example of the shape it produces.

## First scenario

Once a catalog exists, there are two ways to turn it into a `.feature` file:

- **`author-scenario`** — describe the flow in plain English ("as a user I
  add an item to my cart and check out") and it authors a `.feature` file
  from that description, reusing catalog steps where they already exist and
  minting new ones where they don't.
- **`record-scenario`** — click through the flow for real. It prints a
  companion `npx playwright codegen` command to run in your own terminal,
  then turns the resulting recording into a `.feature` file mapped onto the
  same catalog.

## Running the tests

Once `scaffold-bdd` has scaffolded the `e2e/` subproject, generated
`.feature` files run deterministically, with no LLM involved:

```
cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
```

v0.0.1: worked examples are hand-written and not yet executed end-to-end.
