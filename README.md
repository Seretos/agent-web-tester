# agent-web-tester

A Claude Code **skill** plugin. Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors/records scenarios that run deterministically via playwright-bdd in the pipeline.

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
