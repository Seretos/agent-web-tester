# Worked example: authoring a sign-in scenario

This is a hand-written worked example of exactly what one `author-scenario`
run produces, so `skills/author-scenario/SKILL.md` has a concrete output
template. Like `docs/examples/todomvc-scan.md` and
`docs/examples/scaffold-bdd-run.md`, it is not a mirrored source tree — this
plugin repo has no TypeScript/Node toolchain at all, so real files here
would rot silently with nothing to keep them honest, and it is never
executed (no `npm`, no network, no live `bddgen`). Treat the fenced blocks
below as exactly what the skill would write into (or read from) the
**target repo under test**; the only guarantee this example gives is
*internal consistency* between the catalog, the page object, the fixture
and the feature file — not a green `bddgen` run.

The fixture is a tiny, self-contained sign-in page: its own page object, its
own catalog excerpt, and its own fixture HTML — no TodoMVC/demo reuse.

## Description

> On `/signin`, a user fills in their email with `'jane@example.com'` and
> their password with `'hunter2'`, clicks the Sign in button, and should
> see the Welcome heading.

## Derived route

Following `N2` (the description names `/signin` literally), the route list
is a single entry, sourced from the description itself, reported in the
summary as the exact line `Routes: /signin (from description)`.

## Generated artifacts

### e2e/catalog.md (before)

The catalog already has three rows for this page — reused verbatim per
`R1`/`R2` — but no row for clicking the Sign in button.

```md
| Phrase | Page object | Locator |
|---|---|---|
| I fill in the email textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Email' })` |
| I fill in the password textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Password' })` |
| I should see the Welcome heading | SignInPage | `this.page.getByRole('heading', { name: 'Welcome' })` |
```

No row matches "clicks the Sign in button", so per `R3` the skill delegates
that element to `page-scanner` rather than inventing a locator.

### page-scanner task hint

The exact delegation request sent to `page-scanner`, naming the route and
the missing interaction:

```
Scan /signin for the missing interaction: clicking the button whose
accessible name is "Sign in". No existing catalog row matches a click on
it. Please scan /signin and add an accessor for that button so I can
reproduce the phrase you mint.
```

`page-scanner` scans the page and mints one new accessor and catalog row.
The skill re-reads `e2e/catalog.md` and reproduces the minted phrase
verbatim — never inventing it itself.

### e2e/catalog.md (after)

```md
| Phrase | Page object | Locator |
|---|---|---|
| I click the Sign in button | SignInPage | `this.page.getByRole('button', { name: 'Sign in' })` |
| I fill in the email textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Email' })` |
| I fill in the password textbox with {string} | SignInPage | `this.page.getByRole('textbox', { name: 'Password' })` |
| I should see the Welcome heading | SignInPage | `this.page.getByRole('heading', { name: 'Welcome' })` |
```

### e2e/pages/SignInPage.ts (read-only, scanner-owned)

`page-scanner` owns this file; the skill only reads it, per `R3`/`F4`.

```ts
import { Page } from '@playwright/test';

export class SignInPage {
  constructor(private readonly page: Page) {}

  emailInput() {
    return this.page.getByRole('textbox', { name: 'Email' });
  }

  passwordInput() {
    return this.page.getByRole('textbox', { name: 'Password' });
  }

  signInButton() {
    return this.page.getByRole('button', { name: 'Sign in' });
  }

  welcomeHeading() {
    return this.page.getByRole('heading', { name: 'Welcome' });
  }
}
```

### e2e/fixtures/signin.html (read-only, scanner-owned)

The fixture `page-scanner` scanned to produce the page object above (a
simplified, never-executed illustration — a real sign-in form would use
`type="password"` and a live route rather than a static fixture). The
`Welcome` heading starts hidden via inline `style="display: none"` —
deliberately not the `hidden` attribute, which would remove it from
Playwright's accessibility tree entirely and make the final assertion
unpassable — and a small inline script reveals it only once the form's
`submit` event actually fires (the Sign in button is `type="submit"` inside
the `<form>`, so the page object's `.click()` genuinely triggers it). That
way `Then I should see the Welcome heading` discriminates: it only passes
once the preceding fill and click steps have run, not unconditionally.

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Sign in</title>
  </head>
  <body>
    <h1 id="welcome" style="display: none">Welcome</h1>
    <form>
      <label>Email <input type="text" name="email" /></label>
      <label>Password <input type="text" name="password" /></label>
      <button type="submit">Sign in</button>
    </form>
    <script>
      document.querySelector('form').addEventListener('submit', (event) => {
        event.preventDefault();
        document.getElementById('welcome').style.display = '';
      });
    </script>
  </body>
</html>
```

### e2e/steps/signin.steps.ts (read-only, scanner-owned)

`page-scanner` owns this file too; it carries no `A2` marker, so the skill
never edits it.

```ts
import { createBdd } from 'playwright-bdd';
import { test, expect } from '@playwright/test';
import { SignInPage } from '../pages/SignInPage';

const { When, Then } = createBdd(test);

When('I fill in the email textbox with {string}', async ({ page }, value) => {
  const signIn = new SignInPage(page);
  await signIn.emailInput().fill(value);
});

When('I fill in the password textbox with {string}', async ({ page }, value) => {
  const signIn = new SignInPage(page);
  await signIn.passwordInput().fill(value);
});

When('I click the Sign in button', async ({ page }) => {
  const signIn = new SignInPage(page);
  await signIn.signInButton().click();
});

Then('I should see the Welcome heading', async ({ page }) => {
  const signIn = new SignInPage(page);
  await expect(signIn.welcomeHeading()).toBeVisible();
});
```

### e2e/steps/authored.steps.ts

The skill's own navigation step, minted once per repo and extended (never
duplicated) on later runs, per `A3`/`A4`. It never contains a locator
expression of its own — it only navigates.

```ts
// author-scenario: skill-owned. page-scanner never writes here.
import { createBdd } from 'playwright-bdd';
import { test } from '@playwright/test';

const { Given } = createBdd(test);

Given('I am on the {string} page', async ({ page }, route) => {
  await page.goto(route);
});
```

### e2e/features/signin.feature

`e2e/features/signin.feature` did not exist yet, so it is created with a
single `Feature:` line before the `Scenario:` block is appended, per `F2`.
A scenario that visits more than one route is written to e2e/features/flows/<flow-slug>.feature instead; this example visits only /signin, so it lands in the per-route file.

The route / has an empty slug, so its feature file is written as e2e/features/home.feature.

```gherkin
Feature: Sign in

  Scenario: A user signs in with valid credentials
    Given I am on the '/signin' page
    When I fill in the email textbox with 'jane@example.com'
    And I fill in the password textbox with 'hunter2'
    And I click the Sign in button
    Then I should see the Welcome heading
```

Every step's keyword is derived, never chosen, per `R4`: `I fill in …` and
`I click …` are `When` (neither `"I should "` nor `"I am "`), so the second
and third lines are written with `And`; `I should see …` is `Then`; the
navigation line's phrase, `I am on the {string} page`, is minted by this
skill itself into `authored.steps.ts` under `A3` — it is not, and never
becomes, a catalog row.

## Summary

Routes: /signin (from description)
Reused (catalog): I fill in the email textbox with {string}
Reused (catalog): I fill in the password textbox with {string}
Reused (catalog): I should see the Welcome heading
Scanned (new steps): I click the Sign in button
Created: e2e/features/signin.feature
Created: e2e/steps/authored.steps.ts
Self-check: PASS — bddgen resolved every step
Run it yourself: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
