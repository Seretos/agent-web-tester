# agent-web-tester

Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors scenarios that run deterministically via playwright-bdd in the pipeline.

## Key features

- **Live page scanning** — a `page-scanner` subagent drives a real, headed browser via `@playwright/mcp` and turns a page's accessibility tree into reusable page objects and step definitions.
- **A three-column Gherkin phrase catalog** — every scan builds/updates `e2e/catalog.md` in the target repo under test, so step phrases stay discoverable and reusable across scenarios.
- **description-driven scenario authoring** — describe a flow in plain English and get a `.feature` file assembled from existing catalog phrases, one Given/When/Then line per phrase.
- **Deterministic, zero-LLM execution** — scaffolded `e2e/` projects run on `playwright-bdd`, so CI replays `.feature` files as native Playwright tests with no model involved at test time.
