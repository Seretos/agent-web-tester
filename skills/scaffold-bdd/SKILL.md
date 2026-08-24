---
name: scaffold-bdd
description: Scaffolds a self-contained playwright-bdd (vitalets) e2e/ subproject into the target repo under test, so the .feature files and step catalog produced by page-scanner run as cd e2e && npx bddgen && npx playwright test with zero LLM involvement. Use when the user wants to wire up, install, or make runnable a Gherkin/BDD test toolchain, or asks why page-scanner's catalog "doesn't run yet".
---

# scaffold-bdd

You make the `e2e/pages/*.ts`, `e2e/steps/*.ts`, and `e2e/catalog.md` that
`page-scanner` writes/updates *runnable*, by scaffolding a self-contained
`playwright-bdd` project into the **target repo under test** — never into
this plugin repo. This is infrastructure only: you never write or edit a
`.feature` scenario yourself. See the worked example:
[docs/examples/scaffold-bdd-run.md](../../docs/examples/scaffold-bdd-run.md)
for the exact files one run produces — use it as your output template.

## Scaffolding pipeline

1. Detect the package manager (`M1`) and the repo shape (`M2`/`M3`), and
   print the `Package manager: ` summary line.
2. Write every path in `P1` that does not already exist, reusing
   page-scanner's own formats (`P2`) and the `e2e/**` layout other skills
   bind to (`P3`); list each one under `Created:` or `Kept (already
   present):`, per `I1`.
3. Register `e2e` as a workspace member only if `I5` says it already
   qualifies as a workspace shape (`M2`); otherwise print the matching
   `Workspace: ` line and leave the root manifest untouched.
4. Resolve dependencies per `I6`/`M4`/`M5`, printing exactly one of the
   three `I6` outcome lines.
5. Write `.github/workflows/e2e.yml` only if `I3` allows it; otherwise print
   the CI snippet under `CI snippet (not written):`.
6. Create or update `e2e/.gitignore` per `I4`.
7. Run the self-check (`X1`-`X3`) and print exactly one of the three `X2`
   result lines.

## Hard rule: layout

- P1: The scaffold writes exactly these paths: e2e/package.json, e2e/playwright.config.ts, e2e/features/demo.feature, e2e/steps/demo.steps.ts, e2e/pages/DemoPage.ts, e2e/fixtures/demo.html, e2e/catalog.md, e2e/.gitignore.
  This "exactly these paths" list names only the authored/templated files; the lockfile that `M5` puts in the no-root-config branch (a standalone `e2e/package-lock.json`) is not one of the eight and is not authored or templated by this skill, but it is still committed alongside them — required for `npm ci` in the worked example's CI snippet to succeed on a fresh clone.
- P2: Page objects, step definitions, and the catalog reuse page-scanner's formats verbatim: constructor(private readonly page: Page) {}, createBdd(test) plus plain instantiation, and the catalog header | Phrase | Page object | Locator | over |---|---|---|, so a later page-scanner run reconciles against them instead of fighting them.
- P3: The scaffolded layout is the contract other skills bind to: features at e2e/features/*.feature, step definitions at e2e/steps/*.ts, page objects at e2e/pages/*.ts, the phrase catalog at e2e/catalog.md, the config at e2e/playwright.config.ts, and the run command cd e2e && npx bddgen && npx playwright test --config playwright.config.ts.

## Hard rule: catalog → step mapping

The catalog's three columns carry no Gherkin keyword column; the keyword is
recovered from the row's own Phrase cell.

- G1: The catalog has exactly three columns and never gains a fourth; a row's Gherkin keyword is derived from its Phrase cell alone, by G2.
- G2: A phrase beginning with "I should " is a Then step; a phrase beginning with "I am " is a Given step; every other phrase is a When step. Mint Given phrases only in the "I am " form, so the derivation round-trips.
- G3: Each {…} placeholder in the phrase, left to right, is one positional parameter of the step function after the fixtures destructuring argument — When('I fill in the new todo textbox with {string}', async ({ page }, text) => …).
- G4: The step body instantiates exactly the class named in the row's Page object cell, imported from ../pages/<PageObject>, by plain instantiation (const demo = new DemoPage(page)), and calls the accessor whose returned expression is the row's Locator cell verbatim; one row never spans two page objects.

## Hard rule: idempotency

- I1: Never overwrite or delete an existing file under e2e/; an existing target path is left byte-identical and listed under Kept (already present):.
- I2: Never edit an existing root playwright.config.*; write e2e/playwright.config.ts and point every script and CI line at it with --config.
- I3: Never write to a path that already exists. Write .github/workflows/e2e.yml only when .github/workflows/ contains no existing E2E workflow — that is, no file whose basename contains "e2e" (case-insensitive) and no file whose contents mention playwright, bddgen, cypress, wdio, webdriverio, nightwatch, testcafe, or selenium. Otherwise write nothing and print the snippet under "CI snippet (not written):".
- I4: e2e/.gitignore is the only file appended in place. If absent, create it with the four managed lines in order and list it under "Created:". If present and every managed line is already there (whole-line match after trimming trailing whitespace), change nothing and list it under "Kept (already present):" like any other existing file. If present but some are missing, append only the missing ones, in the fixed order, at the end of the file after every existing byte — inserting a newline first if the file did not end with one — never rewriting, reordering or deduplicating existing content, and list it under "Updated (appended <n> line(s)): e2e/.gitignore", the only path that may ever appear under that heading.
- I5: e2e counts as already registered if and only if some normalised workspace entry is the literal string "e2e" or the literal string "*". A negated entry "!e2e" (normalised) means deliberately excluded. Every other pattern — "packages/*", "apps/**", "**" — counts as not registered.
- I6: Let DECLARED mean e2e/package.json exists and lists both @playwright/test and playwright-bdd under devDependencies, and let RESOLVES mean both packages resolve from the e2e/ directory (node -e "require.resolve('playwright-bdd')" run with cwd e2e/, likewise @playwright/test). Then exactly: (a) DECLARED and RESOLVES — run no install at all and print "Kept (dependencies already installed)"; (b) DECLARED but not RESOLVES — run the detected package manager's lockfile-respecting install (npm ci / pnpm install --frozen-lockfile / yarn install --immutable / bun install --frozen-lockfile) in the lockfile-owning directory, which by definition never rewrites the lockfile; (c) not DECLARED — run the resolving add (npm install --save-dev / pnpm add -D / yarn add -D / bun add -d) for the missing packages. Only branch (c) may write or change a lockfile. If branch (b) finds no lockfile in the owning directory, treat the run as branch (c).

Normalise each workspace-list entry (root `package.json`'s `workspaces`
array, or `pnpm-workspace.yaml`'s `packages:` list) by stripping one
leading `./` and one trailing `/` before applying `I5`. Registration
outcomes, printed exactly:

- already registered → no edit, print `Kept (already registered): <file>`;
- `!e2e` present → no edit, print `Workspace: not registered (root config excludes e2e) — e2e/ is standalone`;
- otherwise → append exactly one entry (`"e2e"` / `- e2e`), preserving every
  existing entry, their order, and the file's existing indentation, quoting
  and trailing newline; print `Workspace: registered e2e in <file>`.

## Hard rule: package manager

- M1: Package manager detection is a four-step order, first hit wins: (1) a root lockfile (package-lock.json, pnpm-lock.yaml, yarn.lock, bun.lock/bun.lockb); (2) the root package.json's packageManager field; (3) a pnpm-workspace.yaml at the root; (4) default npm.
- M2: Register e2e as a workspace member only when a root workspace config already exists (root package.json workspaces, or pnpm-workspace.yaml); never create one.
- M3: With no root package.json and no root lockfile, fall back to a standalone e2e/ npm project with its own e2e/package-lock.json and no workspace registration.
- M4: Install @playwright/test and playwright-bdd at latest, recorded as caret ranges, lockfile does the pinning — never an exact pin, never latest in the manifest.
- M5: The lockfile-owning directory and file are named per repo shape — workspace registration: the root lockfile only; root package.json with no workspace config: e2e/'s own lockfile in the detected package manager's format; no root package.json and no root lockfile: e2e/package-lock.json.

Print `Package manager: <pm> (detected via <signal>)` on every run, in every branch.

On a repo with a root `package.json` but no workspace config, print `Workspace: not registered (no workspace config at root) — e2e/ is standalone`.

On a repo with neither a root `package.json` nor a root lockfile (M3), print `Workspace: not registered (no root package.json or lockfile) — e2e/ is standalone`.

## Hard rule: self-check

- X1: After the install, run npx playwright install chromium, then npx bddgen once from e2e/, then resolve the canary's generated spec by globbing e2e/.features-gen/**/*demo.feature* — if exactly one file matches, run npx playwright test --config playwright.config.ts <that path>; otherwise run npx playwright test --config playwright.config.ts demo.feature, relying on Playwright's positional argument being a regex matched against the test file path. Run the suite unfiltered never.
- X2: Print exactly one of three lines per run — "Self-check: PASS — 1 scenario passed against e2e/fixtures/demo.html" (the filtered run selected the single demo scenario and it passed), "Self-check: FAIL — <command> exited <code>", or "Self-check: SKIPPED — no demo canary found at e2e/features/demo.feature" (the user removed the canary; nothing is regenerated to replace it — the skill treats an absent demo.feature on a repo that already has e2e/package.json as a deliberate removal).
- X3: The self-check never runs the user's own scenarios and never targets the user's real app. The only test it executes is the demo canary, which navigates only to a file:// URL built with pathToFileURL over e2e/fixtures/demo.html. Because baseURL and webServer stay commented out, no dev server is started and no HTTP request leaves the machine.

On FAIL, print the last 20 lines of the runner's output, then the fixed
sentence: "The scaffold is left in place; nothing is rolled back. Re-run cd
e2e && npx bddgen && npx playwright test after fixing the error above." Do
not retry, do not delete or revert any file already written, and do not
print PASS.

## Summary checklist

Every run's printed summary must include, in whatever order reads best:

- the `Package manager: ` line;
- every written or kept path (`Created:`, `Kept (already present):`,
  `Updated (appended <n> line(s)): e2e/.gitignore`);
- the workspace outcome (`Kept (already registered): `, `Workspace:
  registered e2e in `, or the matching `Workspace: not registered (` line
  for the repo's shape, per the idempotency and package-manager sections
  above);
- the dependency outcome (`Kept (dependencies already installed)` or which
  install branch ran);
- the CI outcome (`.github/workflows/e2e.yml` created, or `CI snippet (not
  written):` with the snippet);
- exactly one `Self-check: PASS — 1 scenario passed against
  e2e/fixtures/demo.html`, `Self-check: FAIL — `, or `Self-check: SKIPPED —
  no demo canary found at e2e/features/demo.feature` line.
