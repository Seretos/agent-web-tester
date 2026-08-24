# Worked example: recording a TodoMVC scenario

This is a hand-written worked example of what one `record-scenario` run
produces, continuing the same TodoMVC story `docs/examples/todomvc-scan.md`
started: `e2e/catalog.md` already holds the four rows that example scanned
(`I check the Buy milk item checkbox`, `I click the Clear completed
button`, `I fill in the new todo textbox with {string}`, `I should see the
status show 1 item left`), and `e2e/` is already scaffolded by
`scaffold-bdd`. Like the other worked examples, this plugin repo has no
TypeScript toolchain, so treat the fenced blocks below as exactly what the
skill would write into the **target repo under test**, not a mirrored `.ts`
source tree.

- **Recorded URL:** `https://demo.playwright.dev/todomvc`
- **Slug:** `todomvc-add-complete-clear`
- **Flow:** add a todo ("Buy milk"), complete it, clear completed todos,
  then fill in a sync passphrase — recorded deliberately noisily (a hover,
  a scroll, a focus-click immediately before a fill on the same locator,
  and two consecutive fills on that locator with different values), so the
  pruning in `## Hard rule: meaningful actions` has something real to prune.

Because the fill textbox and the Clear-completed button are the *same*
locators `page-scanner` already scanned, this run **reuses** their catalog
phrases byte-identically (`reuse (A1)`) instead of minting new ones — as
does the checkbox check. Only the opening navigation and the sync-passphrase
field are genuinely new, so they mint two rows.

**Note on the reused/minted phrase text:** a non-parametrized phrase below —
reused or minted — appears byte-identical across its catalog row, its step
registration, and its `.feature` line, mirroring the byte-identical phrase
convention `scaffold-bdd`'s own worked example already establishes (catalog
phrase == step phrase == feature phrase, verbatim). A **parametrized**
phrase's catalog row and step registration keep the literal `{string}`
Cucumber-expression placeholder verbatim, but its `.feature` scenario line
substitutes a concrete quoted value for that placeholder instead, per
`scaffold-bdd`'s G3: `{string}` compiles to the regex `"([^"]*)"` and is
matched against a concrete quoted value in the scenario text, so the bare
placeholder text left unsubstituted in a `.feature` line would not bind at
runtime.

## Generated artifacts

### e2e/.recordings/todomvc-add-complete-clear.spec.ts

```ts
import { test, expect } from '@playwright/test';

test('recorded session', async ({ page }) => {
  await page.goto('https://demo.playwright.dev/todomvc');
  await page.getByRole('textbox', { name: 'What needs to be done?' }).click();
  await page.getByRole('textbox', { name: 'What needs to be done?' }).fill('Buy mil');
  await page.getByRole('textbox', { name: 'What needs to be done?' }).fill('Buy milk');
  await page.getByText('Buy milk').hover();
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(1000);
  await page.getByRole('listitem').filter({ hasText: 'Buy milk' }).getByRole('checkbox', { name: 'Toggle Todo' }).check();
  await page.getByRole('button', { name: 'Clear completed' }).click();
  await page.getByLabel('Sync password').fill('hunter2');
});
```

### e2e/features/todomvc-add-complete-clear.feature

```gherkin
Feature: Add a todo, complete it, clear completed todos, and sync a password
  Scenario: Recorded session on TodoMVC
    Given I am on the TodoMVC home page
    When I fill in the new todo textbox with "Buy milk"
    When I check the Buy milk item checkbox
    When I click the Clear completed button
    When I fill in the Sync password field with the secret "E2E_SYNC_PASSWORD"
```

### e2e/steps/recorded.steps.ts

```ts
import { createBdd } from 'playwright-bdd';
import { test } from '@playwright/test';
import { RecordedTodoPage } from '../pages/recorded/TodoPage';

const { Given, When } = createBdd(test);

Given('I am on the TodoMVC home page', async ({ page }) => {
  await page.goto('https://demo.playwright.dev/todomvc');
});

When('I fill in the Sync password field with the secret {string}', async ({ page }, envVarName) => {
  const value = process.env[envVarName];
  if (!value) {
    throw new Error(`Missing environment variable ${envVarName}`);
  }
  const todo = new RecordedTodoPage(page);
  await todo.syncPasswordField().fill(value);
});
```

### e2e/pages/recorded/TodoPage.ts

```ts
import { Page } from '@playwright/test';

export class RecordedTodoPage {
  constructor(private readonly page: Page) {}

  homePage() {
    return this.page;
  }

  syncPasswordField() {
    return this.page.getByLabel('Sync password');
  }
}
```

### e2e/catalog.md

```md
| Phrase | Page object | Locator |
|---|---|---|
| I am on the TodoMVC home page | RecordedTodoPage | `this.page` |
| I fill in the Sync password field with the secret {string} | RecordedTodoPage | `this.page.getByLabel('Sync password')` |
```

### e2e/.gitignore

```
node_modules/
.features-gen/
test-results/
playwright-report/
.recordings/
```

## Gate (1) confirmation

Pruned `When` list (4 surviving actions, in recorded order — the focus
click, the intermediate `'Buy mil'` fill, the hover, the scroll, and the
wait are all gone):

1. Fill the "What needs to be done?" textbox
2. Check the "Buy milk" item's checkbox
3. Click the "Clear completed" button
4. Fill the "Sync password" field with the recorded secret

Action → step mapping:

1. reuse (A1) — locator-string match → `I fill in the new todo textbox with {string}`
2. reuse (A1) — locator-string match → `I check the Buy milk item checkbox`
3. reuse (A1) — locator-string match → `I click the Clear completed button`
4. mint — no existing catalog row matches `page.getByLabel('Sync password')` → `I fill in the Sync password field with the secret {string}`

Proposed `Then` steps:

- unverified guess — Then I should see the new todo textbox empty

Removed (deduped): none

```
> Confirm gate (1) and write the files? [y/N] y
> Also veto the proposed "I should see the new todo textbox empty" guess — do not write it.
```

Gate (1) re-printed without the vetoed guess and confirmed (U3). Writing
`e2e/features/todomvc-add-complete-clear.feature`,
`e2e/steps/recorded.steps.ts`, `e2e/pages/recorded/TodoPage.ts`, and
appending the two minted rows to `e2e/catalog.md` now — no `Then` line is
written, since the only proposed one was vetoed.

## Gate (2) confirmation

Stage 1 always runs, unfiltered, and needs no confirmation:

```
$ cd e2e && npx bddgen
```

Verify: COMPILE PASS — npx bddgen generated 6 spec(s) from the full e2e/ tree

Stage 1 passed, so the replay offer (V4) is shown before asking:

- Target URL: `https://demo.playwright.dev/todomvc`
- The recorded actions will be performed again against the real app.
- `E2E_SYNC_PASSWORD` is currently unset in this shell — export it or decline.

```
> Run the scoped replay against the real app now? [y/N] y
$ export E2E_SYNC_PASSWORD=hunter2
$ npx playwright test --config playwright.config.ts e2e/.features-gen/features/todomvc-add-complete-clear.feature.spec.js
```

## Record summary

```
Recording: e2e/.recordings/todomvc-add-complete-clear.spec.ts
Pruned: 5
Reused (catalog): I fill in the new todo textbox with {string}, I check the Buy milk item checkbox, I click the Clear completed button
Minted: I am on the TodoMVC home page, I fill in the Sync password field with the secret {string}
Removed (deduped): none
Required environment variables: E2E_SYNC_PASSWORD (the raw recording at e2e/.recordings/todomvc-add-complete-clear.spec.ts still contains the literal value typed during recording)
Created: e2e/features/todomvc-add-complete-clear.feature, e2e/steps/recorded.steps.ts, e2e/pages/recorded/TodoPage.ts
Updated (appended 2 row(s)): e2e/catalog.md
Updated (appended 1 line(s)): e2e/.gitignore
Kept (already present): e2e/pages/TodoPage.ts, e2e/steps/todo.steps.ts
Verify: COMPILE PASS — npx bddgen generated 6 spec(s) from the full e2e/ tree
Verify: PASS — 1 scenario(s) passed against https://demo.playwright.dev/todomvc
```
