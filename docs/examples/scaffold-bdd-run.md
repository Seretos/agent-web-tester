# Worked example: scaffolding playwright-bdd

This is a hand-written worked example of exactly what one `scaffold-bdd` run
produces, so `skills/scaffold-bdd/SKILL.md` has a concrete output template.
Like `docs/examples/todomvc-scan.md`, it is not a mirrored source tree —
this plugin repo has no TypeScript/Node toolchain at all, so real files here
would rot silently with nothing to keep them honest. Treat the fenced
blocks below as exactly what the skill would write into the **target repo
under test**, on a fresh repo with no root `package.json` and no root
lockfile (the M3 standalone fallback).

## Generated artifacts

### e2e/package.json

```json
{
  "name": "e2e",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "test": "bddgen && playwright test --config playwright.config.ts"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.0",
    "playwright-bdd": "^7.5.0"
  }
}
```

### e2e/playwright.config.ts

```ts
import { defineConfig } from '@playwright/test';
import { defineBddConfig } from 'playwright-bdd';

const testDir = defineBddConfig({
  features: 'features/**/*.feature',
  steps: 'steps/**/*.ts',
});

export default defineConfig({
  testDir,
  // TODO: point at your app -- uncomment and fill in to run real scenarios.
  // use: {
  //   baseURL: 'http://localhost:3000',
  // },
  // webServer: {
  //   command: 'npm run start',
  //   url: 'http://localhost:3000',
  // },
});
```

### e2e/fixtures/demo.html

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Playwright BDD demo</title>
  </head>
  <body>
    <h1>Playwright BDD demo</h1>
  </body>
</html>
```

### e2e/pages/DemoPage.ts

```ts
import { Page } from '@playwright/test';

export class DemoPage {
  constructor(private readonly page: Page) {}

  heading() {
    return this.page.getByRole('heading', { name: 'Playwright BDD demo' });
  }
}
```

### e2e/steps/demo.steps.ts

```ts
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { createBdd } from 'playwright-bdd';
import { test, expect } from '@playwright/test';
import { DemoPage } from '../pages/DemoPage';

const { Given } = createBdd(test);

Given('I am on the demo page', async ({ page }) => {
  const demo = new DemoPage(page);
  const fixtureUrl = pathToFileURL(path.join(__dirname, '..', 'fixtures', 'demo.html')).href;
  await page.goto(fixtureUrl);
  await expect(demo.heading()).toBeVisible();
});
```

### e2e/features/demo.feature

```gherkin
Feature: Playwright BDD demo canary

  Scenario: The scaffolded toolchain runs against the fixture
    Given I am on the demo page
```

### e2e/catalog.md

```md
| Phrase | Page object | Locator |
|---|---|---|
| I am on the demo page | DemoPage | `this.page.getByRole('heading', { name: 'Playwright BDD demo' })` |
```

### e2e/.gitignore

```
node_modules/
.features-gen/
test-results/
playwright-report/
```

### .github/workflows/e2e.yml

```yaml
name: e2e

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - name: Install dependencies
        run: cd e2e && npm ci
      - name: Install Playwright browsers
        run: cd e2e && npx playwright install --with-deps chromium
      - name: Run BDD tests
        run: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
```

## Scaffold summary

```
Package manager: npm (detected via default)
Created: e2e/package.json
Created: e2e/playwright.config.ts
Created: e2e/features/demo.feature
Created: e2e/steps/demo.steps.ts
Created: e2e/pages/DemoPage.ts
Created: e2e/fixtures/demo.html
Created: e2e/catalog.md
Created: e2e/.gitignore
Workspace: not registered (no root package.json or lockfile) — e2e/ is standalone
Installed: @playwright/test, playwright-bdd (e2e/package-lock.json)
Created: .github/workflows/e2e.yml
Self-check: PASS — 1 scenario passed against e2e/fixtures/demo.html
```

On a **second** run over that same repo, since `e2e/package.json` already
declares both packages and they already resolve from `e2e/`, the dependency
line instead reads:

```
Kept (dependencies already installed)
```

On a repo that already has a root `.github/workflows/` E2E workflow (`I3`),
the CI step instead prints:

```
CI snippet (not written):
cd e2e && npx bddgen && npx playwright test --config playwright.config.ts
```
