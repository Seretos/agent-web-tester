---
name: record-scenario
description: Translates a real, recorded browser session into a Gherkin .feature file — a companion npx playwright codegen run captures the user's clicks/types/navigations, this skill prunes the noise, maps each surviving action onto existing e2e/catalog.md steps where one matches, mints new ones where it doesn't, and writes the result after one explicit user confirmation. Use when the user wants to record a scenario, turn a live click-through into a test, or asks how to author a .feature file from actions instead of a description.
---

# record-scenario

You translate a **recorded** browser session — the user's own clicks, types,
and navigations, captured by a companion `npx playwright codegen` run, never
by the `playwright` MCP browser — into a Gherkin `.feature` file, reusing
`e2e/catalog.md` steps where a recorded action matches one and minting new
ones where it doesn't. See the worked example:
[docs/examples/record-scenario-run.md](../../docs/examples/record-scenario-run.md)
for the exact files one recording run produces — use it as your output
template.

## Recording pipeline

1. Detect a runnable `e2e/` (`## Hard rule: recording session`, R1); if
   absent, stop and point the user at `scaffold-bdd`.
2. Pre-create the recording placeholder, print the `codegen` command, and
   wait for the user to say "done" (R2-R4).
3. Read the recording and mechanically prune it to meaningful actions
   (`## Hard rule: meaningful actions`).
4. Map each surviving action onto `e2e/catalog.md` — reuse first, mint only
   when nothing matches (`## Hard rule: catalog matching`).
5. Propose `Then` steps from recorded assertions or an unverified guess
   (`## Hard rule: proposed Then steps`).
6. Detect and redact any secret-looking field (`## Hard rule: secrets`).
7. Show gate (1) — the pruned `When` list, the mapping, the proposed `Then`
   steps, and any dedupe deletions — together, in one message
   (`## Hard rule: confirmation gates`).
8. On confirmation, write the files per `## Hard rule: file ownership`.
9. Run the two-stage verification and print its result
   (`## Hard rule: verification run`).

## Hard rule: recording session

- R1: precondition — a runnable `e2e/` must already exist; detect it with the *same* signal as `page-scanner`'s D2 (`playwright-bdd` in root or `e2e/package.json`, or `playwright-bdd`/`defineBddConfig` in a root or `e2e/` playwright config). If absent, stop and tell the user to run `scaffold-bdd`; record nothing. (Read/Grep only — never install.)
- R2: the skill never records through the `playwright` MCP browser. It pre-creates `e2e/.recordings/<slug>.spec.ts` (a one-line placeholder comment, which also creates the directory so `--output` cannot fail), then prints exactly this command for the user to run in their own terminal: `cd e2e && npx playwright codegen --target playwright-test --browser chromium --output .recordings/<slug>.spec.ts <url>`
- R3: no polling, no timeout — the skill waits for the user to say "done", then reads the file. If it is still the placeholder, print `Recording: EMPTY — nothing captured at e2e/.recordings/<slug>.spec.ts` and stop without writing anything.
- R4: this is a second browser with a second profile — logins/cookies from the MCP browser do not carry over; the skill says so when it prints the command.

## Hard rule: meaningful actions

- N1: the opening `page.goto` becomes the single `Given`, minted only in the `I am ` form so `scaffold-bdd`'s G2 keyword derivation round-trips.
- N2: a `click` on a locator immediately followed by a `fill`/`pressSequentially` on that same locator is dropped as a focus click.
- N3: consecutive `fill`s on one locator collapse to the last value.
- N4: hovers, scrolls, `waitForTimeout` and any non-action line never become steps.
- N5: every survivor becomes a `When` in recorded order (later `goto`s included).

## Hard rule: catalog matching

Priority order, first hit wins.

- A1: locator-string equality against a catalog row's Locator cell after collapsing internal whitespace.
- A2: role + accessible-name equivalence, using `page-scanner`'s C1 key semantics (whitespace-collapsed, trimmed, case-sensitive).
- A3: semantic phrase match — the phrase this action would mint already exists in the catalog.
- A4: otherwise mint, obeying `scaffold-bdd`'s G2 (keyword from phrase) and G3 (`{string}` placeholders → positional params after the fixtures argument).
- A5: the net invariant — one phrase maps to exactly one locator and one locator to exactly one phrase — is preserved across repeat recordings by F7 and across a later scanner run by F8; those two rules are how it survives, and A5 names them.

## Hard rule: file ownership

- F1: write scope is `e2e/**` only; the only step file this skill ever writes is `e2e/steps/recorded.steps.ts`. It never creates, edits or deletes `e2e/steps/authored.steps.ts` (#4's file), `e2e/steps/demo.steps.ts`, or any other step file.
- F2: if `e2e/pages/<Route>Page.ts` already exists, read it, reuse its matching accessors, and leave it byte-identical — genuinely new elements go into `e2e/pages/recorded/<Route>Page.ts`.
- F3: to keep class names unique and catalog `Page object` cells unambiguous when both files exist for one route, the recorded class is named `Recorded<Route>Page` inside `e2e/pages/recorded/<Route>Page.ts`, imported as `../pages/recorded/<Route>Page`. A deliberate, documented deviation from `scaffold-bdd`'s G4 `../pages/<PageObject>` import shape (the pinned `pages/recorded/` sub-path already deviates); recorded in `AGENTS.md`.
- F4: catalog rows for every minted step are appended to `e2e/catalog.md` in the same three-column shape (`| Phrase | Page object | Locator |` over `|---|---|---|`), never rewriting or reordering existing rows; the scanner's next wholesale rewrite reconciles them.
- F5: `.feature` output goes to `e2e/features/<kebab-slug>.feature`; an existing path is never overwritten — suffix `-2`, `-3`, … and report the final path.
- F6: `.recordings/` is appended to `e2e/.gitignore` using `scaffold-bdd`'s I4 append discipline (whole-line match after trimming trailing whitespace; append only if missing, at EOF, after inserting a newline if the file did not end with one; never rewrite/reorder/dedupe). The recording holds raw typed values including secrets, which is exactly why it must be ignored.
- F7: repeat recording on the same route — merge, never duplicate. `e2e/pages/recorded/<Route>Page.ts` and `e2e/steps/recorded.steps.ts` are re-read and merged in place. An accessor whose locator already exists there is reused, not re-emitted; a `Given(`/`When(`/`Then(` whose phrase is already defined in that file is reused, not re-registered. Never emit a second accessor for one locator and never a second definition for one phrase. A repeat run still produces a new `.feature` under F5's suffix rule — only the page object and step file are merged.
- F8: scanner runs after #5 — the scanner wins, resolved at the next record run. The scanner rewrites `e2e/pages/<Route>Page.ts` and `e2e/catalog.md` wholesale and `record-scenario` never fights it mid-scan. If a later scan puts an accessor into `<Route>Page.ts` whose locator is already in `recorded/<Route>Page.ts`, the next `record-scenario` run on that route resolves the duplicate: F2's read-and-reuse makes the scanner's accessor the winner, the now-duplicate accessor is deleted from `recorded/<Route>Page.ts`, and `recorded.steps.ts` is re-pointed at `<Route>Page`'s accessor (import updated) so one locator keeps exactly one accessor. If that empties `recorded/<Route>Page.ts`, the file is deleted. This is the only case in which this skill deletes anything; each deletion is listed at gate (1) and in the summary under `Removed (deduped): `, so a dedupe is never silent.

## Hard rule: proposed Then steps

- T1: prefer codegen's own recorded `expect(...)` calls, labelled `recorded`.
- T2: otherwise propose 1-3 `Then` steps from the final URL plus the last surviving actions, labelled verbatim `unverified guess`.
- T3: every `Then` phrase begins with `I should ` so G2 round-trips; nothing unconfirmed is ever written.

## Hard rule: secrets

- S1: case-insensitive secret-field detector — locator name / label / placeholder / `type="password"` matching `password|passwd|pwd|secret|token|api key|apikey|otp|cvv|pin|card number`.
- S2: a detected value is never inlined into the feature, steps, catalog, or summary — the minted phrase takes the form `I fill in the <field> with the secret {string}`, the feature line carries the env var name (`E2E_<UPPER_SNAKE>`), and the step body resolves `process.env[name]`, throwing `Missing environment variable <name>` when unset.
- S3: every such name is listed in the summary under `Required environment variables:`, with the warning that the raw recording file still contains the literal.

## Hard rule: confirmation gates

- U1: exactly two gates. Gate (1) is a single combined confirmation moment that shows, together in one message: the pruned `When` list; the action→step mapping giving, per action, `reuse (A1)`, `reuse (A2)`, `reuse (A3)` with the reused phrase, or `mint` with the new phrase; the proposed `Then` steps with their `recorded` / `unverified guess` labels; and any F8 dedupe deletions. Gate (2) is the replay offer defined in the verification-run section.
- U2: gate (1) is the write gate — no file on disk is created or modified before it is confirmed. (The `.recordings/` placeholder and its `.gitignore` line, written in R2/F6 before recording, are the only exception and are named as such.) Gate (2) runs after the files are written; it gates running, not writing.
- U3: any line vetoed at gate (1) is dropped and gate (1) re-printed in full; never write an unconfirmed step.
- U4: declining gate (2) is a first-class, non-error outcome — the written files stay exactly as written and the run ends with the `Verify: SKIPPED — replay declined at the verification gate` line. Never re-ask, never run the replay implicitly.

## Hard rule: verification run

Verification runs in two stages: stage 1 runs npx bddgen unfiltered over the whole e2e/ tree, stage 2 runs npx playwright test scoped to the generated spec after the replay gate. Stage 1 always runs; stage 2 is offered only if stage 1 passed.

- V1: this is how the acceptance criterion is discharged, stated above.
- V2 (stage 1 — full-tree compile, always safe, ungated): from `e2e/`, run `npx bddgen` with no filter, so every feature and every step file in the tree is compiled together. This executes no browser action, starts no server, and touches the user's app not at all — which is why it needs no gate. A non-zero exit, or any reported undefined / ambiguous / duplicate step definition, is a hard failure: print `Verify: COMPILE FAIL — npx bddgen exited <code>: <first reported step error>`, do not offer gate (2), and stop — the written files stay as written. On success print `Verify: COMPILE PASS — npx bddgen generated <n> spec(s) from the full e2e/ tree`. Stage 1 is the check that catches a phrase collision between `recorded.steps.ts` and `authored.steps.ts` or `demo.steps.ts`; a scoped `playwright test` alone would not.
- V3 (stage 2 scope): the replay is scoped to the generated spec only. Reusing stage 1's already-generated output, resolve the spec by globbing `e2e/.features-gen/**/*<slug>.feature*` — if exactly one file matches, run `npx playwright test --config playwright.config.ts <that path>`; otherwise run `npx playwright test --config playwright.config.ts <slug>.feature`, relying on Playwright's positional argument being a regex matched against the test file path. Run the suite unfiltered never. Never target another feature file.
- V4 (the gate-(2) offer): before asking, state (a) the exact target URL the recorded `Given` navigates to, (b) the warning, verbatim: `The recorded actions will be performed again against the real app.` — so any data the recording created or modified will be created or modified again, (c) any `E2E_*` variable from S3 that is currently unset, so the user can export it or decline. Nothing runs until the user confirms.
- V5 (stage-2 result): print exactly one of `Verify: PASS — <n> scenario(s) passed against <url>`, `Verify: FAIL — npx playwright test exited <code>`, or `Verify: SKIPPED — replay declined at the verification gate`. A FAIL never deletes, rewrites, or "fixes" what was already written; it reports the first failing step and stops, leaving the artifacts for the user to edit. A run that fails on `Missing environment variable ` is a FAIL, not a rewrite.

## Summary checklist

Every run's printed summary must include, in whatever order reads best:

- `Recording: ` — the recording file path, or the `EMPTY` notice (R3);
- `Pruned: ` — a count of dropped actions;
- `Reused (catalog): ` — every phrase matched by A1/A2/A3;
- `Minted: ` — every newly minted phrase;
- `Removed (deduped): ` — every F8 dedupe deletion, even if none;
- `Required environment variables:` — every S3 env var name, even if none;
- `Created:`, `Updated (appended `, `Kept (already present):` — every
  written or reused path;
- the `Verify: ` lines in exactly one of two shapes:
  - compile failed: one line only — `Verify: COMPILE FAIL — `
  - compile passed: `Verify: COMPILE PASS — ` followed by exactly one of
    `Verify: PASS — `, `Verify: FAIL — `, `Verify: SKIPPED — `

(Same one-of-N discipline as `scaffold-bdd`'s X2 `Self-check: ` line.
Prefix matching must be longest-first, since `Verify: COMPILE PASS — ` also
starts with `Verify: `.)
