# Worked example: scanning TodoMVC

This is a hand-written worked example of what one `page-scanner` run
produces, so `agents/page-scanner.md` has a concrete output template and
package #3 (`scaffold-bdd`) has something concrete to map onto. It is not a
mirrored `.ts` source tree — this plugin repo has no TypeScript toolchain at
all, so real `.ts` files here would rot silently with nothing to keep them
honest. Treat the fenced blocks below as exactly what the scanner would
write into the **target repo under test**.

- **Scanned URL:** `https://demo.playwright.dev/todomvc`
- **Task hint:** `adding a todo, completing it, and clearing completed todos`

Because the hint names the clear-completed flow, this scan legitimately
includes the footer `Clear completed` button — the hint overrides the
navigation/contentinfo landmark skip for anything it names. The items-left
counter is included too: it is not itself named by the hint, but it is the
element directly required to assert the effect of "clearing completed
todos" (there is no other observable proof that the clear-completed action
worked), so it is in scope under the hard rule's "plus those directly
required to perform or assert them" clause. The toggle-all checkbox is
*not* included, by contrast: nothing in the hint (which names completing
one specific todo, not all of them) directly requires it.

## Generated artifacts

### e2e/pages/TodoPage.ts

```ts
import { Page } from '@playwright/test';

export class TodoPage {
  constructor(private readonly page: Page) {}

  newTodoInput() {
    return this.page.getByRole('textbox', { name: 'What needs to be done?' });
  }

  buyMilkItemCheckbox() {
    return this.page.getByRole('listitem').filter({ hasText: 'Buy milk' }).getByRole('checkbox', { name: 'Toggle Todo' });
  }

  clearCompletedButton() {
    return this.page.getByRole('button', { name: 'Clear completed' });
  }

  itemsLeftStatus() {
    return this.page.getByTestId('todo-count');
  }
}
```

### e2e/steps/todo.steps.ts

```ts
import { createBdd } from 'playwright-bdd';
import { test, expect } from '@playwright/test';
import { TodoPage } from '../pages/TodoPage';

const { When, Then } = createBdd(test);

When('I fill in the new todo textbox with {string}', async ({ page }, text) => {
  const todo = new TodoPage(page);
  await todo.newTodoInput().fill(text);
  await todo.newTodoInput().press('Enter');
});

When('I check the Buy milk item checkbox', async ({ page }) => {
  const todo = new TodoPage(page);
  await todo.buyMilkItemCheckbox().check();
});

When('I click the Clear completed button', async ({ page }) => {
  const todo = new TodoPage(page);
  await todo.clearCompletedButton().click();
});

Then('I should see the status show 1 item left', async ({ page }) => {
  const todo = new TodoPage(page);
  await expect(todo.itemsLeftStatus()).toBeVisible();
});
```

### e2e/catalog.md

```md
| Phrase | Page object | Locator |
|---|---|---|
| I check the Buy milk item checkbox | TodoPage | `this.page.getByRole('listitem').filter({ hasText: 'Buy milk' }).getByRole('checkbox', { name: 'Toggle Todo' })` |
| I click the Clear completed button | TodoPage | `this.page.getByRole('button', { name: 'Clear completed' })` |
| I fill in the new todo textbox with {string} | TodoPage | `this.page.getByRole('textbox', { name: 'What needs to be done?' })` |
| I should see the status show 1 item left | TodoPage | `this.page.getByTestId('todo-count')` |
```

## Scan summary

```
Applied scope: task hint — adding a todo, completing it, and clearing completed todos

Locator fallbacks: this.page.getByTestId('todo-count') for the items-left counter — the live app renders it as a bare <span data-testid="todo-count"> with no ARIA role, so no getByRole match exists; getByTestId is the tier-3 accessor used instead.

Reconciliation: first run, no existing e2e/ tree — all 4 accessors and phrases are new. Unmatched existing entries: none.

playwright-bdd not detected — run scaffold-bdd (#3) to make these runnable.
```
