# agent-web-tester

Assistant for creating E2E web tests: scans pages into a Gherkin step catalog and authors/records scenarios that run deterministically via playwright-bdd in the pipeline.

## Key features

- **Live browser page scanning** — drives a real, headed browser via the bundled Playwright MCP server to scan a page's accessibility tree and turn it into reusable page objects and step definitions.
- **A reusable Gherkin step catalog** — each scan builds or updates `e2e/catalog.md`, a growing dictionary of phrases scenarios can reuse instead of re-describing the same UI every time.
- **Author scenarios from a description** — describe a flow in plain English and the `author-scenario` skill turns it into a `.feature` file, reusing catalog steps where they exist and minting new ones where they don't.
- **Record scenarios from real clicks** — the `record-scenario` skill turns a live click-through, captured via a companion `npx playwright codegen` session, into a `.feature` file mapped onto the same catalog.
- **Deterministic, zero-LLM CI re-execution** — every generated `.feature` file runs later via `playwright-bdd`, with no LLM involvement at test time, so scenarios stay fast and reproducible in the pipeline.
