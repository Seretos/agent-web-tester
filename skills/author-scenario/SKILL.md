---
name: author-scenario
description: Turns a plain-language description of a user flow into a runnable Gherkin .feature scenario inside the e2e/ layout scaffold-bdd (#3) established, reusing the phrase catalog page-scanner (#2) produces and delegating back to page-scanner only when the catalog has no semantic match. Use when the user wants to author, write, or add a test scenario, turn a described user flow into a .feature file, or asks for a Given/When/Then scenario from a plain-English description.
---

# author-scenario

You turn a plain-language description of a user flow into a runnable
Gherkin `.feature` scenario inside the `e2e/` layout `scaffold-bdd` (#3)
established, reusing the phrase catalog `page-scanner` (#2) produces and
delegating back to that subagent only when the catalog has no semantic
match. You never invent a locator and you never edit a page object
yourself. See the worked example:
[docs/examples/author-scenario/README.md](../../docs/examples/author-scenario/README.md)
for the exact output shape one run produces — use it as your output
template. The failure path (an element the catalog and a scan both miss)
is worked in
[docs/examples/author-scenario/unresolvable-ui.md](../../docs/examples/author-scenario/unresolvable-ui.md).

## Authoring pipeline

The section order below is fixed and load-bearing: route determination
happens before anything reads the catalog, catalog reuse (and delegation)
happens before file placement, file placement happens before the step
files are written, and the self-check runs last.

1. Determine the route(s) the description visits (route determination).
2. Resolve the scan origin from the target repo's `e2e/playwright.config.ts`
   `baseURL` before any page-scanner delegation (target URL), then read
   `e2e/catalog.md` and reuse or delegate for every element the description
   needs, scanning against that resolved origin (catalog reuse).
3. Decide the target `.feature` path and append or replace the scenario in
   it (file placement).
4. Write the skill-owned step files the scenario needs (skill-owned step
   files).
5. Tag and stub any sentence that resolves to nothing (unresolvable UI).
6. Run the self-check and hand the run command back to the user
   (self-check).

## Hard rule: route determination

- N1: Before reading e2e/catalog.md, derive from the description an ordered list of the route paths the scenario visits — one entry per navigation the sentences imply, in the order they are visited, duplicates collapsed only when consecutive. Every later rule consumes that list; nothing re-derives it.
- N2: When a sentence names a route literally — a token beginning with / or a full URL — that is the route: reproduce it verbatim, normalising a full URL down to its path component only.
- N3: Otherwise recover the route from the target repo, never from imagination: a route already recorded as the parameter of a Given I am on the '<route>' page line under e2e/features/**, or the route a page object under e2e/pages/ was scanned against as recorded in that file, matches when the description names that page. A page object's class name is never itself turned into a route path — TodoPage was scanned from /todomvc, not from /todo.
- N4: When neither N2 nor N3 yields a route, ask the user once for the route path, use the answer for this run only, and never write it into e2e/playwright.config.ts or any other file. Never guess a path from a page name and never extrapolate one from a URL pattern seen elsewhere in the repo.
- N5: The N1 list is what decides F1's branch — exactly one distinct route means e2e/features/<route-slug>.feature, more than one means e2e/features/flows/<flow-slug>.feature — and each route in it is the route a page-scanner delegation under R3 is made against, resolved against the base URL from T1/T2.
- N6: Report the derived list in the summary as exactly one line Routes: <route>[, <route>...] (<source>), where <source> is exactly one of from description, from e2e/, or asked user.

The three N6 source literals are: from description, from e2e/, asked user.

## Hard rule: catalog reuse

- R1: Read e2e/catalog.md before writing anything; every step line you emit is either an existing catalog phrase reproduced verbatim or a phrase minted through R3 — never a phrase you invented on your own.
- R2: A catalog row is a semantic match when it names the same element and the same interaction as the sentence you need; prefer an existing parameterized row (with {string}) over minting a fixed-value twin, and never mint a second phrase for an element the catalog already covers.
- R3: Never invent a locator and never write or edit a page object yourself. When no catalog row matches, delegate that element to the page-scanner subagent with a task hint naming exactly the missing interactions, then re-read e2e/catalog.md and reproduce the phrase the scanner minted, verbatim.
- R4: Gherkin keywords are derived, never chosen: a phrase beginning with "I should " is a Then line, a phrase beginning with "I am " is a Given line, every other phrase is a When line — scaffold-bdd's G2 applied to the catalog phrase you selected. A line whose derived keyword equals the previous line's is written with And.

## Hard rule: file placement

- F1: A scenario that visits exactly one route goes in e2e/features/<route-slug>.feature; a scenario that visits more than one route goes in e2e/features/flows/<flow-slug>.feature. The route slug is the route path lowercased with the leading slash dropped and every remaining run of non-alphanumeric characters replaced by a single hyphen; the empty result (route "/") is written as home.
- F2: Append a new Scenario: block at the end of the target file, preserving every existing byte before it; create the file with a single Feature: line only when it does not already exist.
- F3: A scenario whose name equals an existing Scenario: name in the target file (compared after trimming) replaces that block in place, from its Scenario: line to the line before the next Scenario:, Feature: or end of file, leaving every other block byte-identical — never appended as a duplicate.
- F4: Never write, move or delete anything under e2e/ other than e2e/features/**, e2e/steps/authored.steps.ts, e2e/steps/todo.steps.ts and e2e/steps/todo.authored.steps.ts; e2e/catalog.md, e2e/pages/**, e2e/playwright.config.ts and every scanner-owned step file are read-only to this skill.
- F5: The flow slug is the N1 route list's slugs, each computed by F1's per-route slug function, joined in visit order with a single hyphen between consecutive slugs — the same ordered route list therefore always produces the same flow slug, so re-authoring the same flow replaces the existing e2e/features/flows/<flow-slug>.feature file rather than duplicating it.

## Hard rule: skill-owned step files

- A1: This skill writes step definitions to at most three paths: e2e/steps/authored.steps.ts (the navigation and data steps it mints itself), e2e/steps/todo.steps.ts (placeholder steps for @skip'd scenarios) and e2e/steps/todo.authored.steps.ts (the A5 collision fallback, written only when A5 applies). Every other file under e2e/steps/ is scanner-owned and read-only.
- A2: Every skill-owned file begins with the exact first line // author-scenario: skill-owned. page-scanner never writes here. A file at any of the three paths whose first line is not that marker is scanner-owned: do not edit it.
- A3: e2e/steps/authored.steps.ts contains only steps whose body navigates (page.goto) or calls an accessor that already exists on a page object under e2e/pages/; it never contains a locator expression of its own. The navigation step is Given('I am on the {string} page', ...), taking the route path as its parameter.
- A4: Extend a skill-owned step file by appending new step definitions and, where needed, extending its import list; an existing definition for the same phrase is left byte-identical and never duplicated.
- A5: When e2e/steps/todo.steps.ts already exists and its first line is not the A2 marker, it is scanner-owned: leave every byte of it untouched and write the placeholders to e2e/steps/todo.authored.steps.ts instead, beginning that file with the same A2 marker line, then print exactly Collision: e2e/steps/todo.steps.ts is scanner-owned — placeholders written to e2e/steps/todo.authored.steps.ts

## Hard rule: unresolvable UI

- U1: A sentence whose element is neither in e2e/catalog.md nor found by the page-scanner scan of the route is unresolvable. Never guess a locator, never invent a phrase for it, and never silently drop the sentence.
- U2: Write the scenario anyway, with the tag line @todo @skip directly above its Scenario: line — @skip is playwright-bdd's own tag, so the scenario is skipped and the rest of the suite still runs green.
- U3: Every step line of a @skip'd scenario whose phrase is not in the catalog gets a placeholder definition in e2e/steps/todo.steps.ts — or, when A5 applies, in e2e/steps/todo.authored.steps.ts — whose body is exactly throw new Error('TODO: UI not present'); — an undefined step would fail bddgen for the whole suite, which is what U2 exists to prevent.
- U4: Report each one in the summary as Unresolved: <sentence> — no matching element on <route>; scenario tagged @todo @skip.

## Hard rule: target URL

- T1: Read baseURL from the target repo's e2e/playwright.config.ts before scanning, and use it as the scan origin whenever it is set (uncommented).
- T2: When baseURL is still the commented-out TODO that scaffold-bdd wrote, ask the user once for the base URL, use the answer for this run's scan requests only, and never write it into e2e/playwright.config.ts or any other file.
- T3: When T2 applies, the URL you asked for is used only for this run's scan requests and, per T2, is never persisted; before the exact command V3 prints can resolve routes, the user must set baseURL in e2e/playwright.config.ts themselves — printing that command does not by itself make it runnable in this branch.

## Hard rule: self-check

- V1: After writing, run cd e2e && npx bddgen once and nothing else — never npx playwright test, never a browser, never the user's app.
- V2: Print exactly one of three lines per run — "Self-check: PASS — bddgen resolved every step", "Self-check: FAIL — bddgen exited <code>" followed by the offending phrases under "Undefined or ambiguous steps:", or "Self-check: SKIPPED — no runnable e2e/ project; run scaffold-bdd (#3) first".
- V3: End every summary with the exact line "Run it yourself: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts" — this skill never runs the scenario itself.

## Summary checklist

Every run's printed summary must include, in this order:

- `Routes: <route>[, <route>...] (<source>)` (N6);
- every reused phrase as `Reused (catalog): <phrase>` (R1/R2);
- every minted phrase as `Scanned (new steps): <phrase>` (R3);
- every path written as `Created: <path>` or `Updated: <path>`;
- a replaced scenario as `Replaced scenario: <name>` (F3);
- every unresolvable sentence as `Unresolved: <sentence> — no matching element on <route>; scenario tagged @todo @skip.` (U4);
- an A5 collision, if it occurred, as `Collision: e2e/steps/todo.steps.ts is scanner-owned — placeholders written to e2e/steps/todo.authored.steps.ts`;
- exactly one of `Self-check: PASS — bddgen resolved every step`, `Self-check: FAIL — bddgen exited <code>` (with `Undefined or ambiguous steps:`), or `Self-check: SKIPPED — no runnable e2e/ project; run scaffold-bdd (#3) first` (V2);
- ending with the exact line `Run it yourself: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts` (V3).
