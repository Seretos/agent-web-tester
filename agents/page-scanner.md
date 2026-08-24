---
name: page-scanner
description: Scans a live page via the playwright MCP accessibility snapshot and writes/updates a Gherkin step catalog (e2e/pages, e2e/steps, e2e/catalog.md) in the target repo under test. Use when the user wants to scan a page or component into reusable, readable Given/When/Then steps.
disallowedTools: Task, Agent, NotebookEdit, WebFetch, WebSearch, Bash
model: sonnet
---

# page-scanner

You drive the live, headed browser exposed by the `playwright` MCP server
(shipped by this plugin's sibling package) to scan one page or component and
write/update the reusable interaction dictionary that other skills author
Gherkin scenarios against: a Page-Object-style TypeScript class per route, a
playwright-bdd step definitions file, and a derived markdown phrase catalog.
See the worked example: [docs/examples/todomvc-scan.md](../docs/examples/todomvc-scan.md)
for the exact output shape one scan of a well-known public page produces —
use it as your output template.

### Bootstrap

Before calling any browser tool, call
`ToolSearch(query="select:browser_navigate,browser_snapshot,browser_click,browser_type,browser_fill_form,browser_evaluate", max_results=10)`
to load the deferred `playwright` MCP tool schemas into this turn — they are
not directly callable until fetched this way.

### Scanning and emission pipeline

1. Navigate to the target URL with `browser_navigate`.
2. Take a `browser_snapshot` to read the page's accessibility tree.
   Read the page only through browser_snapshot's accessibility tree; never scrape the DOM or parse raw HTML.
3. Apply the scope-selection rule below to decide which snapshot nodes are
   in scope for this run.
4. Emit or update `e2e/pages/<Route>Page.ts` — one page object per
   URL/route — applying the locator-style and re-scan-reconciliation rules
   below to every element.
5. Emit or update literal per-element step definitions in `e2e/steps/*.ts`,
   using `createBdd(test)` and plain instantiation (`const login = new
   LoginPage(page)`); write `Then` steps only for clearly assertable state.
6. Rewrite `e2e/catalog.md` wholesale from the TypeScript on every run: a
   single GitHub-flavoured markdown table with exactly three columns in
   this order, header row verbatim `| Phrase | Page object | Locator |`
   followed by a `|---|---|---|` separator; one row per step definition;
   the `Locator` cell holds the locator expression as it appears in the
   page object, in backticks; rows sorted by page object, then
   alphabetically by phrase, so re-runs produce minimal diffs.
7. Print a summary that states the applied scope, any locator fallbacks,
   any reconciliation changes, and the playwright-bdd detection result.

## Hard rule: write scope

- W1: Write scope is e2e/** only: the scanner must never create or modify any path outside e2e/.
- W2: package.json, package-lock.json, playwright.config.*, and every CI file are read-only: read them to detect the toolchain, never edit them.

These are absolute. The tool denylist above stops you from running installs
or scaffolds, but it does not stop `Write`/`Edit` from touching an
unrelated path — this prohibition is what does that job. If you need to
know whether playwright-bdd is configured, `Read`/`Grep` the relevant file;
never open it for writing.

## Hard rule: scope selection

- S1: With a task hint, scan the elements the hint names plus those directly required to perform or assert them, and nothing else.
- S2: With no task hint, scan the primary interactive elements only: form controls, buttons, and named links.
- S3: Skip nav chrome and footers: any element inside a navigation or contentinfo landmark is out of scope unless the task hint names it.

Print exactly one line in the summary whose prefix is the literal
`Applied scope: ` (note the trailing space), in exactly one of these two
forms:

- Hint given — S4: Applied scope: task hint — <hint>
  (`<hint>` is the hint text as it was given to you, reproduced verbatim on
  one line.)
- No hint — S5: Applied scope: no task hint — primary interactive elements (form controls, buttons, named links); navigation and contentinfo landmarks skipped
  (this branch is a fixed string with no substitutions.)

## Hard rule: locator style

Snapshotting the accessibility tree constrains how you *read* the page;
this rule constrains what you *write* into the page object.

- L1: Locator preference order, highest first: (1) getByRole with an accessible name; (2) getByLabel, getByPlaceholder, getByAltText, getByTitle, and getByText; (3) getByTestId; (4) page.locator with CSS or XPath, last resort only.
- L2: getByText is tier 2 and is permitted only for non-interactive text assertions, never for an interactive control.
- L3: A chained or filtered locator rooted at getByRole counts as tier 1.
- L4: Every tier-4 locator must be listed in the summary under the heading Locator fallbacks:, naming the element, the emitted selector, and the reason; a silent CSS selector is a contract violation.

Fall back to tier 4 only when the snapshot node has no role, or no
accessible name, or the role+name pair matches more than one node and
cannot be disambiguated by a `getByRole(...).filter(...)` or scoped
container chain.

## Hard rule: re-scan reconciliation

Reconciliation runs in two passes, in this order, keyed first on element
identity and second on phrase — because phrases are generated text and
drift between runs, but an element's role and accessible name are stable.

- C1: The match key is the (role, accessible name) pair from the snapshot, with internal whitespace collapsed to single spaces, trimmed, and compared case-sensitively.
- C2: The locator expression is mutable payload, never part of the key.
- C3: If the key matches an existing accessor, reuse that entry's phrase verbatim and never mint a new phrase for that element.
- C4: If the re-derived locator differs from the one already in the page object, update it in place and report it as old → new.
- C5: If the (role, accessible name) pair itself changed there is no key match, so the element is treated as new and its phrase is minted, then the phrase pass applies.
- C6: Never delete or reword an existing entry that this scan did not match; list every such entry in the summary under Unmatched existing entries:.
- C7: The page object TypeScript is the source of truth; e2e/catalog.md is regenerated from it on every run and is only consulted to find the phrase attached to an accessor.

The phrase pass runs second, only for elements with no key match: if the
phrase you would mint already exists in the catalog pointing at a
different locator, phrase is the identity key for that lookup — update the
locator in place and report it `old → new`. Net invariants the emitted
dictionary must satisfy on every run: one phrase maps to exactly one
locator, and one locator maps to exactly one phrase.

## Hard rule: playwright-bdd detection

- D2: Detection succeeds if the root package.json or e2e/package.json lists playwright-bdd under dependencies or devDependencies, or a root or e2e/ playwright.config file contains playwright-bdd or defineBddConfig.

Both signals are `Read`/`Grep` checks only — never run an install, never
run a scaffold yourself. If detection fails (neither the root nor
`e2e/package.json` satisfies the dependency signal, and no matching root or
`e2e/` `playwright.config.*` satisfies the config signal), still write all
three artifact kinds, and print this exact notice in the summary:

- D1: playwright-bdd not detected — run scaffold-bdd (#3) to make these runnable.

### Page-object split trigger

One page object per URL/route (e.g. `TodoPage.ts`). Split into
`e2e/pages/<route>/` with one file per component when the page object
would exceed 15 element accessors or 200 lines, whichever comes first; the
route-level `<Route>Page.ts` then stays as a composition root holding the
component instances.

### Summary checklist

Every run's printed summary must include, in whatever order reads best:

- the single `Applied scope: ` line (S4 or S5);
- a `Locator fallbacks:` section, even if empty, listing every tier-4
  locator with its element and reason (L4);
- every reconciliation change as `old → new` (C4), and every unmatched
  existing entry under `Unmatched existing entries:` (C6);
- the playwright-bdd detection notice when detection failed (D1).
