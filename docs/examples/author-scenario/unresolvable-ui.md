# Worked example: unresolvable UI

This is a hand-written worked example of the failure path: a sentence
whose element is on neither the catalog nor the live page. Like
[README.md](README.md), it is never executed (no `npm`, no network, no
live `bddgen`); the only guarantee it gives is *internal consistency*
between the catalog, the feature file and the placeholder step. It reuses
the same tiny, self-contained `/signin` fixture as the happy-path example.

## Description

> On `/signin`, a user fills in their email with `'jane@example.com'` and
> checks the Remember me checkbox.

Following `N2`, the route is a single entry sourced from the description:
`/signin`. A `@todo @skip` scenario is rarely 100% unresolvable, so this
example's sentence deliberately mixes one catalog-covered action (filling
the email) with the one genuinely unresolvable action (the checkbox) — more
faithful to what the fallback path actually produces than an
all-unresolvable scenario would be.

### e2e/catalog.md (excerpt)

The catalog already covers the rest of the sign-in page (see
[README.md](README.md) for the full before/after arithmetic), but no row —
and no accessible element the page-scanner scan of `/signin` finds — names
a "Remember me" checkbox:

```md
| Phrase | Page object | Locator |
|---|---|---|
| I fill in the email textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Email' })` |
| I fill in the password textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Password' })` |
| I click the Sign in button | SignInPage | `this.page.getByRole('button', { name: 'Sign in' })` |
```

Per `U1`, this sentence is unresolvable: never guess a locator, never
invent a phrase, never silently drop the sentence.

## Generated artifacts

### e2e/features/signin.feature

Per `U2`, the scenario is written anyway, tagged `@todo @skip` directly
above its `Scenario:` line, so `@skip` (playwright-bdd's own tag) skips it
and the rest of the suite still runs green. The email-fill step reuses the
already-catalogued `I fill in the email textbox with {string}` row from the
excerpt above, alongside the unresolvable checkbox step — this is also what
makes the catalog-coverage cross-check in `validate_author_scenario.py`
genuinely exercisable: a step whose resolution depends on
`e2e/catalog.md` rather than solely on the `todo.steps.ts` placeholder.

```gherkin
Feature: Sign in

  @todo @skip
  Scenario: A user opts to be remembered
    Given I am on the '/signin' page
    When I fill in the email textbox with 'jane@example.com'
    And I check the Remember me checkbox
```

### e2e/steps/todo.steps.ts

Per `U3`, every step of a `@skip`'d scenario whose phrase is not in the
catalog gets a placeholder definition here, whose body is exactly
`throw new Error('TODO: UI not present');` — so `bddgen` never fails on an
undefined step.

```ts
// author-scenario: skill-owned. page-scanner never writes here.
import { createBdd } from 'playwright-bdd';
import { test } from '@playwright/test';

const { When } = createBdd(test);

When('I check the Remember me checkbox', async () => {
  throw new Error('TODO: UI not present');
});
```

## The A5 collision fallback

This example's `e2e/steps/todo.steps.ts` did not already exist, so it was
created directly, carrying the `A2` marker as its first line. On a repo
where `e2e/steps/todo.steps.ts` already exists with a *different* first
line — meaning `page-scanner` created it (per the precedent in
`docs/examples/todomvc-scan.md`, which shows `page-scanner` emitting its
own `### e2e/steps/todo.steps.ts`) — `A5` applies instead: the skill leaves
every byte of that file untouched and writes the placeholders to
`e2e/steps/todo.authored.steps.ts` instead, beginning that file with the
same `A2` marker line, then prints exactly:

```
Collision: e2e/steps/todo.steps.ts is scanner-owned — placeholders written to e2e/steps/todo.authored.steps.ts
```

No second fixture is needed to demonstrate this — the fallback path and
its exact `Collision: ` line are the same regardless of which scenario
triggers it.

## Summary

Routes: /signin (from description)
Reused (catalog): I fill in the email textbox with {string}
Unresolved: I check the Remember me checkbox — no matching element on /signin; scenario tagged @todo @skip.
Created: e2e/features/signin.feature
Created: e2e/steps/todo.steps.ts
Self-check: PASS — bddgen resolved every step
Run it yourself: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
