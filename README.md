# agent-web-tester

A Claude Code **skill** plugin. Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors scenarios that run deterministically via playwright-bdd in the pipeline.

This plugin ships the skill content plus an inline `mcpServers.playwright` block in both `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`, launching a pinned `@playwright/mcp` server via `npx` — no bundled binary, no wrapper script.

**Prerequisite:** Node.js with `npx` on `PATH`. Enabling the plugin runs `npx -y @playwright/mcp@<pin>` to fetch/launch the server; nothing extra to install for the plugin itself.

## Install

```
/plugin marketplace add Seretos/agent-marketplace
/plugin install agent-web-tester@agent-marketplace
```

If the skill teaches Claude how to use a specific MCP, declare that MCP as a dependency in `.claude-plugin/plugin.json` (`dependencies` array). Claude Code will install/load it automatically.

## What the skill teaches

See `skills/web-tester/SKILL.md` for the full content.

## First scan

Ask Claude to scan a page — "scan the TodoMVC page at
`https://demo.playwright.dev/todomvc`" — and the `web-tester` skill
delegates to the `page-scanner` subagent. It drives a live, headed browser
via the bundled `@playwright/mcp` server, reads the page's accessibility
tree, and writes a page object, step definitions, and a three-column
Gherkin phrase catalog (`e2e/catalog.md`) into the target repo under test —
never into this plugin repo. See
[docs/examples/todomvc-scan.md](docs/examples/todomvc-scan.md) for a full
worked example of the files one scan produces.

## First scenario

Once the catalog has phrases in it, describe the flow you want to test in
plain English — "on `/signin`, fill in the email and password, click Sign
in, and see the Welcome heading" — and the authoring skill assembles a
`.feature` file from existing catalog phrases, one Given/When/Then line per
phrase, reusing what `page-scanner` already found rather than re-deriving
selectors. See
[docs/examples/author-scenario/README.md](docs/examples/author-scenario/README.md)
for a full worked example, including how it derives the route and what it
writes when a phrase can't be resolved against the catalog.

## Running the tests

Scenarios run deterministically, with zero LLM involvement at test time.
The `scaffold-bdd` skill wires up a self-contained `e2e/` subproject in the
target repo (`playwright-bdd` config, a demo canary, and CI wiring when
safe), so `.feature` files compile and run as:

```
cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
```

`bddgen` compiles the `.feature` files into native Playwright Test specs
first, so the whole suite runs on Playwright's own runner, reporter, and
trace pipeline. See
[docs/examples/scaffold-bdd-run.md](docs/examples/scaffold-bdd-run.md) for
the exact files the scaffolding step produces.

---

v0.0.1: the worked examples under docs/ are hand-written and not yet executed end-to-end.
