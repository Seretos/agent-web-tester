# agent-web-tester

Pure skill plugin — no binary, no MCP server. Ships `skills/web-tester/SKILL.md`, which Claude Code loads when the skill's `description` matches the user's intent.

## Contracts an agent won't infer from the tree

- **Release is orphan-branch + marketplace dispatch.** `release.yml` (manual: Actions → release → `version=X.Y.Z`) stamps the version, then force-pushes an orphan `release` branch holding only install-ready files and POSTs a dispatch (`category: skill`) to `Seretos/agent-marketplace`. `main` and `release` share no history. Clients install at the tag `agent-web-tester--vX.Y.Z`.
- **Required secret:** `MARKETPLACE_DISPATCH_TOKEN` — fine-grained PAT, `Contents: RW` + `Pull requests: RW` on `Seretos/agent-marketplace` only.
- **`assets/icon.png` is a release artifact, not just a repo file.** The dispatch payload sends a `raw.githubusercontent.com/${repo}/${TAG}/assets/icon.png` URL to the marketplace, so the file must live on the orphan `release` branch at the tagged commit — `release.yml`'s stage step copies `assets/` into the staging tree for exactly that reason. Ship `assets/icon.png` from day one or the marketplace listing has no image.
- **`description.md` is a release artifact, not just a repo file.** The dispatch payload sends a `raw.githubusercontent.com/${repo}/${TAG}/description.md` URL in the `description_url` field, so the file must live on the orphan `release` branch at the tagged commit — `release.yml` copies it into the staging tree alongside `assets/`. Fill in its Key Features before cutting v0.0.1.
- **Depending on an MCP plugin:** declare it under `dependencies` in `.claude-plugin/plugin.json` (`{ "name": "agent-<mcp>", "version": ">=0.0.1 <1.0.0" }`); Claude Code installs/loads it automatically with this skill.
- **Planned `@playwright/mcp` wrapper.** This plugin will grow an inline `mcpServers` block (Claude + Codex manifests) that launches `@playwright/mcp` via `npx`, following the `agent-serena-wrapper` pattern (external MCP server, no bundled binary). See the plugin's tracked tickets for the build-out.
