# agent-web-tester

A Claude Code **skill** plugin. Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors/records scenarios that run deterministically via playwright-bdd in the pipeline.

This plugin ships **only the skill content** — no binaries, no MCP server.

## Install

```
/plugin marketplace add Seretos/agent-marketplace
/plugin install agent-web-tester@agent-marketplace
```

If the skill teaches Claude how to use a specific MCP, declare that MCP as a dependency in `.claude-plugin/plugin.json` (`dependencies` array). Claude Code will install/load it automatically.

## What the skill teaches

See `skills/web-tester/SKILL.md` for the full content.
