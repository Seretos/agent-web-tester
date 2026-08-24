#!/usr/bin/env python3
"""Validate the `scaffold-bdd` skill package (WP #3): that
``skills/scaffold-bdd/SKILL.md`` exists with sibling-convention frontmatter
and carries its five pinned ``## Hard rule:`` sections (layout, catalog ->
step mapping, idempotency, package manager, self-check); that the
placeholder body in ``skills/web-tester/SKILL.md`` is gone and routes to
both packages; that the worked example at
``docs/examples/scaffold-bdd-run.md`` is internally consistent (its nine
fenced blocks round-trip against each other and the one-row demo arithmetic
holds); that ``agents/page-scanner.md``'s amended D2 bullet is byte-identical
to the D2 literal pinned in ``validate_agents.py``; that ``release.yml``
still stages ``skills/`` wholesale, ``AGENTS.md`` carries the five new
contract bullets, and this repo carries no committed ``e2e/`` tree; that
``lint.yml`` wires in this validator; and that the catalog-row ->
Given/When/Then derivation (``derive_keyword``) is total and agrees with
every keyword actually committed in both the new demo example and the
already-merged ``docs/examples/todomvc-scan.md``.

Usage:
    python .github/scripts/validate_scaffold.py     (local, Windows or *nix)
    python3 .github/scripts/validate_scaffold.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_agents.py`` and ``validate_manifests.py``.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_FILE = REPO_ROOT / "skills" / "scaffold-bdd" / "SKILL.md"
WEB_TESTER_FILE = REPO_ROOT / "skills" / "web-tester" / "SKILL.md"
EXAMPLE_FILE = REPO_ROOT / "docs" / "examples" / "scaffold-bdd-run.md"
TODOMVC_FILE = REPO_ROOT / "docs" / "examples" / "todomvc-scan.md"
AGENT_FILE = REPO_ROOT / "agents" / "page-scanner.md"
VALIDATE_AGENTS_SCRIPT = REPO_ROOT / ".github" / "scripts" / "validate_agents.py"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
E2E_DIR = REPO_ROOT / "e2e"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

HARD_RULE_HEADINGS = [
    "## Hard rule: layout",
    "## Hard rule: catalog → step mapping",
    "## Hard rule: idempotency",
    "## Hard rule: package manager",
    "## Hard rule: self-check",
]

# Pinned literals per plan revision 3, Approach SS1-SS9. Where the plan gives
# an exact quoted sentence (P3, G1-G4, I3-I6, X1-X3) the text below is copied
# verbatim, punctuation included. Where the plan only describes a rule's
# substance without a single quoted sentence (P1, P2, I1, I2, M1-M5), the
# text below is this developer's own pinned phrasing of that substance --
# flagged in the change report as an interpretive necessity, not a
# weakening: the implement phase must reproduce these sentences verbatim in
# skills/scaffold-bdd/SKILL.md for this validator (written first, per the
# plan's own sequencing) to go green.
PINNED_LITERALS = {
    "## Hard rule: layout": [
        ("P1", "P1: The scaffold writes exactly these paths: e2e/package.json, "
               "e2e/playwright.config.ts, e2e/features/demo.feature, "
               "e2e/steps/demo.steps.ts, e2e/pages/DemoPage.ts, "
               "e2e/fixtures/demo.html, e2e/catalog.md, e2e/.gitignore."),
        ("P2", "P2: Page objects, step definitions, and the catalog reuse "
               "page-scanner's formats verbatim: constructor(private readonly "
               "page: Page) {}, createBdd(test) plus plain instantiation, and "
               "the catalog header | Phrase | Page object | Locator | over "
               "|---|---|---|, so a later page-scanner run reconciles against "
               "them instead of fighting them."),
        ("P3", "P3: The scaffolded layout is the contract other skills bind to: "
               "features at e2e/features/*.feature, step definitions at "
               "e2e/steps/*.ts, page objects at e2e/pages/*.ts, the phrase "
               "catalog at e2e/catalog.md, the config at e2e/playwright.config.ts, "
               "and the run command cd e2e && npx bddgen && npx playwright test "
               "--config playwright.config.ts."),
    ],
    "## Hard rule: catalog → step mapping": [
        ("G1", "G1: The catalog has exactly three columns and never gains a "
               "fourth; a row's Gherkin keyword is derived from its Phrase cell "
               "alone, by G2."),
        ("G2", 'G2: A phrase beginning with "I should " is a Then step; a '
               'phrase beginning with "I am " is a Given step; every other '
               'phrase is a When step. Mint Given phrases only in the "I am " '
               "form, so the derivation round-trips."),
        ("G3", "G3: Each {…} placeholder in the phrase, left to right, is "
               "one positional parameter of the step function after the "
               "fixtures destructuring argument — When('I fill in the new "
               "todo textbox with {string}', async ({ page }, text) => …)."),
        ("G4", "G4: The step body instantiates exactly the class named in the "
               "row's Page object cell, imported from ../pages/<PageObject>, by "
               "plain instantiation (const demo = new DemoPage(page)), and "
               "calls the accessor whose returned expression is the row's "
               "Locator cell verbatim; one row never spans two page objects."),
    ],
    "## Hard rule: idempotency": [
        ("I1", "I1: Never overwrite or delete an existing file under e2e/; an "
               "existing target path is left byte-identical and listed under "
               "Kept (already present):."),
        ("I2", "I2: Never edit an existing root playwright.config.*; write "
               "e2e/playwright.config.ts and point every script and CI line at "
               "it with --config."),
        ("I3", "I3: Never write to a path that already exists. Write "
               ".github/workflows/e2e.yml only when .github/workflows/ contains "
               'no existing E2E workflow — that is, no file whose basename '
               'contains "e2e" (case-insensitive) and no file whose contents '
               "mention playwright, bddgen, cypress, wdio, webdriverio, "
               "nightwatch, testcafe, or selenium. Otherwise write nothing and "
               'print the snippet under "CI snippet (not written):".'),
        ("I4", "I4: e2e/.gitignore is the only file appended in place. If "
               "absent, create it with the four managed lines in order and list "
               'it under "Created:". If present and every managed line is '
               "already there (whole-line match after trimming trailing "
               'whitespace), change nothing and list it under "Kept (already '
               'present):" like any other existing file. If present but some '
               "are missing, append only the missing ones, in the fixed order, "
               "at the end of the file after every existing byte — inserting "
               "a newline first if the file did not end with one — never "
               "rewriting, reordering or deduplicating existing content, and "
               'list it under "Updated (appended <n> line(s)): e2e/.gitignore", '
               "the only path that may ever appear under that heading."),
        ("I5", "I5: e2e counts as already registered if and only if some "
               'normalised workspace entry is the literal string "e2e" or the '
               'literal string "*". A negated entry "!e2e" (normalised) means '
               'deliberately excluded. Every other pattern — "packages/*", '
               '"apps/**", "**" — counts as not registered.'),
        ("I6", "I6: Let DECLARED mean e2e/package.json exists and lists both "
               "@playwright/test and playwright-bdd under devDependencies, and "
               "let RESOLVES mean both packages resolve from the e2e/ directory "
               '(node -e "require.resolve(\'playwright-bdd\')" run with cwd '
               "e2e/, likewise @playwright/test). Then exactly: (a) DECLARED "
               'and RESOLVES — run no install at all and print "Kept '
               '(dependencies already installed)"; (b) DECLARED but not '
               "RESOLVES — run the detected package manager's "
               "lockfile-respecting install (npm ci / pnpm install "
               "--frozen-lockfile / yarn install --immutable / bun install "
               "--frozen-lockfile) in the lockfile-owning directory, which by "
               "definition never rewrites the lockfile; (c) not DECLARED — "
               "run the resolving add (npm install --save-dev / pnpm add -D / "
               "yarn add -D / bun add -d) for the missing packages. Only branch "
               "(c) may write or change a lockfile. If branch (b) finds no "
               "lockfile in the owning directory, treat the run as branch (c)."),
    ],
    "## Hard rule: package manager": [
        ("M1", "M1: Package manager detection is a four-step order, first hit "
               "wins: (1) a root lockfile (package-lock.json, pnpm-lock.yaml, "
               "yarn.lock, bun.lock/bun.lockb); (2) the root package.json's "
               "packageManager field; (3) a pnpm-workspace.yaml at the root; "
               "(4) default npm."),
        ("M2", "M2: Register e2e as a workspace member only when a root "
               "workspace config already exists (root package.json workspaces, "
               "or pnpm-workspace.yaml); never create one."),
        ("M3", "M3: With no root package.json and no root lockfile, fall back "
               "to a standalone e2e/ npm project with its own "
               "e2e/package-lock.json and no workspace registration."),
        ("M4", "M4: Install @playwright/test and playwright-bdd at latest, "
               "recorded as caret ranges, lockfile does the pinning — never "
               "an exact pin, never latest in the manifest."),
        ("M5", "M5: The lockfile-owning directory and file are named per repo "
               "shape — workspace registration: the root lockfile only; root "
               "package.json with no workspace config: e2e/'s own lockfile in "
               "the detected package manager's format; no root package.json "
               "and no root lockfile: e2e/package-lock.json."),
    ],
    "## Hard rule: self-check": [
        ("X1", "X1: After the install, run npx playwright install chromium, "
               "then npx bddgen once from e2e/, then resolve the canary's "
               "generated spec by globbing e2e/.features-gen/**/*demo.feature* "
               "— if exactly one file matches, run npx playwright test "
               "--config playwright.config.ts <that path>; otherwise run npx "
               "playwright test --config playwright.config.ts demo.feature, "
               "relying on Playwright's positional argument being a regex "
               "matched against the test file path. Run the suite unfiltered "
               "never."),
        ("X2", "X2: Print exactly one of three lines per run — "
               '"Self-check: PASS — 1 scenario passed against '
               'e2e/fixtures/demo.html" (the filtered run selected the single '
               'demo scenario and it passed), "Self-check: FAIL — <command> '
               'exited <code>", or "Self-check: SKIPPED — no demo canary '
               'found at e2e/features/demo.feature" (the user removed the '
               "canary; nothing is regenerated to replace it — the skill "
               "treats an absent demo.feature on a repo that already has "
               "e2e/package.json as a deliberate removal)."),
        ("X3", "X3: The self-check never runs the user's own scenarios and "
               "never targets the user's real app. The only test it executes "
               "is the demo canary, which navigates only to a file:// URL "
               "built with pathToFileURL over e2e/fixtures/demo.html. Because "
               "baseURL and webServer stay commented out, no dev server is "
               "started and no HTTP request leaves the machine."),
    ],
}

D2_AMENDED_MUST_MENTION = "e2e/package.json"
# F3 hardening: the byte-identity check between agents/page-scanner.md and
# validate_agents.py's pin only forces the two files to agree with *each
# other* -- it says nothing about whether the amendment actually added the
# e2e/ playwright.config clause the plan requires. Require that clause too.
D2_AMENDED_MUST_MENTION_CONFIG = "e2e/ playwright.config"

# F2 hardening: check_web_tester_body used to assert only the bare word
# 'page-scanner', which survives even if #2's actual delegation section were
# gutted and replaced by unrelated prose that happens to mention the word.
# Pin the section's own heading instead -- a stable, structural literal from
# the file #2 actually wrote that a wholesale rewrite would not leave intact.
PAGE_SCANNER_SECTION_HEADING = "## Scanning a page: delegate to the page-scanner subagent"

# The three X2 result lines and the full summary vocabulary R1 pins.
SUMMARY_VOCABULARY = [
    "Created:",
    "Kept (already present):",
    "Updated (appended ",
    "Kept (already registered): ",
    "Kept (dependencies already installed)",
    "Workspace: registered e2e in ",
    "Workspace: not registered (",
    ") — e2e/ is standalone",
    "Package manager: ",
    "CI snippet (not written):",
    "Self-check: PASS — 1 scenario passed against e2e/fixtures/demo.html",
    "Self-check: FAIL — ",
    "Self-check: SKIPPED — no demo canary found at e2e/features/demo.feature",
]

WORKSPACE_NOT_REGISTERED_REASONS = [
    "no workspace config at root",
    "root config excludes e2e",
    "no root package.json or lockfile",
]

# I4's four managed .gitignore lines, in the fixed pinned order.
GITIGNORE_MANAGED_LINES = ["node_modules/", ".features-gen/", "test-results/", "playwright-report/"]

REQUIRED_EXAMPLE_HEADINGS = [
    "e2e/package.json",
    "e2e/playwright.config.ts",
    "e2e/fixtures/demo.html",
    "e2e/pages/DemoPage.ts",
    "e2e/steps/demo.steps.ts",
    "e2e/features/demo.feature",
    "e2e/catalog.md",
    "e2e/.gitignore",
    ".github/workflows/e2e.yml",
]

# The adversarial totality table from plan Approach SS2b, entry by entry.
ADVERSARIAL_TABLE = [
    ("", "When"),
    ("I should ", "Then"),
    ("I should see X", "Then"),
    ("I am ", "Given"),
    ("I am on the demo page", "Given"),
    ("I ambush the form", "When"),
    ("I shouldnt see X", "When"),
    ("I click the Save button", "When"),
    ("I fill in {string}", "When"),
]


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def derive_keyword(phrase):
    """R7's pure, total catalog-row -> Gherkin-keyword function (plan G2).

    A phrase beginning with "I should " is Then; a phrase beginning with
    "I am " is Given; every other phrase (including the empty string) is
    When. The trailing spaces are load-bearing: they are what stop
    "I ambush the form" from being misread as a Given.
    """
    if phrase.startswith("I should "):
        return "Then"
    if phrase.startswith("I am "):
        return "Given"
    return "When"


def get_section_spans(body_text, headings):
    """Section spans: from a hard-rule heading (verbatim, start of line) to
    the next line starting with '## ', or EOF. Mirrors validate_agents.py's
    get_section_spans."""
    spans = {}
    generic_heading_re = re.compile(r"^## ", re.MULTILINE)
    for heading in headings:
        pattern = re.compile(r"^" + re.escape(heading) + r"\s*$", re.MULTILINE)
        match = pattern.search(body_text)
        if not match:
            continue
        line_end = body_text.find("\n", match.end())
        search_from = line_end + 1 if line_end != -1 else len(body_text)
        next_match = generic_heading_re.search(body_text, search_from)
        end = next_match.start() if next_match else len(body_text)
        spans[heading] = body_text[match.start():end]
    return spans


def parse_headed_code_blocks(text):
    """Map '### <heading>' -> the content of the first fenced code block
    that follows it (before the next '### ' heading or EOF). Mirrors
    validate_agents.py's parse_headed_code_blocks."""
    lines = text.split("\n")
    blocks = {}
    current_heading = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("### "):
            current_heading = line[4:].strip()
            i += 1
            continue
        if line.startswith("```") and current_heading is not None and current_heading not in blocks:
            j = i + 1
            content_lines = []
            while j < n and not lines[j].startswith("```"):
                content_lines.append(lines[j])
                j += 1
            blocks[current_heading] = "\n".join(content_lines)
            i = j + 1
            continue
        i += 1
    return blocks


def parse_catalog_table(block_text, source_file, failures):
    lines = [l for l in block_text.split("\n") if l.strip() != ""]
    if not lines:
        failures.append(f"{rel(source_file)}: e2e/catalog.md block is empty")
        return []

    header = lines[0].strip()
    if header != "| Phrase | Page object | Locator |":
        failures.append(
            f"{rel(source_file)}: e2e/catalog.md header line is {header!r}, "
            "expected '| Phrase | Page object | Locator |'"
        )

    if len(lines) < 2:
        failures.append(f"{rel(source_file)}: e2e/catalog.md missing separator row")
        return []

    sep = lines[1].strip()
    if sep != "|---|---|---|":
        failures.append(f"{rel(source_file)}: e2e/catalog.md separator row is {sep!r}, expected '|---|---|---|'")

    rows = []
    for row_line in lines[2:]:
        cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
        if len(cells) != 3:
            failures.append(f"{rel(source_file)}: e2e/catalog.md row does not have exactly 3 cells: {row_line!r}")
            continue
        rows.append(tuple(cells))
    return rows


def _find_live_cp_match(regex, stage_text):
    """Search ``stage_text`` line-by-line for ``regex`` and return the
    absolute character offset of the first match found on a live
    (not commented-out) line, or None. Mirrors validate_agents.py's
    _find_live_cp_match."""
    offset = 0
    for line in stage_text.split("\n"):
        if not line.strip().startswith("#"):
            m = regex.search(line)
            if m:
                return offset + m.start()
        offset += len(line) + 1
    return None


# ---------------------------------------------------------------------------
# R1 -- skills/scaffold-bdd/SKILL.md exists and carries its pinned contract
# ---------------------------------------------------------------------------

def check_skill_frontmatter(failures):
    """R1. Returns the normalised (LF-only) full file text on success, or
    None if the file could not be read at all."""
    if not SKILL_FILE.is_file():
        failures.append(f"{rel(SKILL_FILE)}: file not found")
        return None

    raw = SKILL_FILE.read_bytes()
    if b"\r\n" in raw:
        failures.append(f"{rel(SKILL_FILE)}: file contains CRLF line endings (\\r\\n); must be LF-only")

    text = raw.decode("utf-8").replace("\r\n", "\n")

    m = FRONTMATTER_RE.match(text)
    if not m:
        failures.append(f"{rel(SKILL_FILE)}: missing YAML frontmatter matching '^---\\n(.*?)\\n---\\n'")
        return text

    fm = m.group(1)
    if not fm.strip():
        failures.append(f"{rel(SKILL_FILE)}: frontmatter is empty")

    for key in ("name:", "description:"):
        if key not in fm:
            failures.append(f"{rel(SKILL_FILE)}: frontmatter missing '{key}' key")

    name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.MULTILINE)
    if name_match:
        name_value = name_match.group(1).strip().strip("\"'")
        if name_value != "scaffold-bdd":
            failures.append(f"{rel(SKILL_FILE)}: frontmatter 'name' is {name_value!r}, expected 'scaffold-bdd'")
    elif "name:" in fm:
        failures.append(f"{rel(SKILL_FILE)}: could not parse 'name:' value from frontmatter")

    desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if desc_match:
        if not desc_match.group(1).strip():
            failures.append(f"{rel(SKILL_FILE)}: frontmatter 'description' is empty")
    elif "description:" in fm:
        failures.append(f"{rel(SKILL_FILE)}: could not parse 'description:' value from frontmatter")

    return text


def check_skill_hard_rules(failures, skill_text):
    """R1's heading-order and pinned-literal assertions. No-op if the file
    could not be read at all -- check_skill_frontmatter already reported
    that."""
    if skill_text is None:
        return

    m = FRONTMATTER_RE.match(skill_text)
    body = skill_text[m.end():] if m else skill_text

    heading_offsets = []
    for heading in HARD_RULE_HEADINGS:
        pattern = re.compile(r"^" + re.escape(heading) + r"\s*$", re.MULTILINE)
        match = pattern.search(body)
        if match is None:
            failures.append(f'{rel(SKILL_FILE)}: missing hard-rule heading "{heading}"')
            heading_offsets.append(None)
        else:
            heading_offsets.append(match.start())

    present_offsets = [o for o in heading_offsets if o is not None]
    if present_offsets != sorted(present_offsets):
        failures.append(
            f"{rel(SKILL_FILE)}: hard-rule headings are present but not in the required order "
            f"({HARD_RULE_HEADINGS})"
        )

    spans = get_section_spans(body, HARD_RULE_HEADINGS)
    for heading, literals in PINNED_LITERALS.items():
        span = spans.get(heading)
        for _label, literal in literals:
            if span is None or literal not in span:
                snippet = literal[:60]
                failures.append(
                    f'{rel(SKILL_FILE)}: section "{heading}" is missing the pinned literal: "{snippet}..."'
                )

    # Additional edge-case coverage (R1): the full summary vocabulary and the
    # three "Workspace: not registered" reason tokens, each appearing exactly
    # once in the whole document (not scoped to a single section, since the
    # summary checklist prose may sit outside any one Hard rule span).
    for token in SUMMARY_VOCABULARY:
        if token not in body:
            failures.append(f"{rel(SKILL_FILE)}: missing summary vocabulary literal: {token!r}")

    for reason in WORKSPACE_NOT_REGISTERED_REASONS:
        count = body.count(reason)
        if count != 1:
            failures.append(
                f"{rel(SKILL_FILE)}: 'Workspace: not registered' reason token {reason!r} "
                f"appears {count} time(s), expected exactly 1"
            )


# ---------------------------------------------------------------------------
# R2 -- web-tester placeholder body is gone and routes to both packages
# ---------------------------------------------------------------------------

PLACEHOLDER_MARKER = "(Skill body — replace this"
PLACEHOLDER_SURVIVOR_LINES = ["Typical structure:", "**Mental model**"]


def check_web_tester_body(failures):
    if not WEB_TESTER_FILE.is_file():
        failures.append(f"{rel(WEB_TESTER_FILE)}: file not found")
        return

    text = WEB_TESTER_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")

    if PLACEHOLDER_MARKER in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: still contains the placeholder body marker '{PLACEHOLDER_MARKER}'"
        )

    for required in ("scaffold-bdd", "page-scanner", "e2e/catalog.md"):
        if required not in text:
            failures.append(f"{rel(WEB_TESTER_FILE)}: does not mention {required!r}")

    # F2: a bare 'page-scanner' substring match above would still pass if
    # #2's actual delegation section were gutted and replaced with unrelated
    # prose that merely name-drops the word. Require the section's own
    # heading -- a structural literal a wholesale rewrite would not leave
    # standing -- to actually survive.
    if PAGE_SCANNER_SECTION_HEADING not in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: missing the surviving page-scanner delegation section "
            f"heading {PAGE_SCANNER_SECTION_HEADING!r} (a bare 'page-scanner' substring match "
            "would still pass even if #2's actual section were gutted)"
        )

    for survivor in PLACEHOLDER_SURVIVOR_LINES:
        if survivor in text:
            failures.append(
                f"{rel(WEB_TESTER_FILE)}: still contains placeholder scaffolding text {survivor!r} "
                "(a half-deletion of the placeholder body)"
            )


# ---------------------------------------------------------------------------
# R3 -- the worked example is internally consistent
# ---------------------------------------------------------------------------

def _demo_step_phrases(steps_block):
    """(keyword, phrase) pairs for every Given/When/Then(...) call in a
    steps block."""
    return re.findall(r"(Given|When|Then)\(\s*['\"](.*?)['\"]", steps_block)


def _feature_step_lines(feature_block):
    """Lines of a .feature block (stripped) that open with an explicit
    Given/When/Then/And/But keyword."""
    out = []
    for line in feature_block.split("\n"):
        stripped = line.strip()
        for kw in ("Given ", "When ", "Then ", "And ", "But "):
            if stripped.startswith(kw):
                out.append(stripped)
                break
    return out


def check_worked_example(failures):
    """R3. Returns the parsed heading->block dict (possibly empty/partial)."""
    if not EXAMPLE_FILE.is_file():
        failures.append(f"{rel(EXAMPLE_FILE)}: file not found")
        return {}

    try:
        text = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError as exc:
        failures.append(f"{rel(EXAMPLE_FILE)}: could not read file ({exc})")
        return {}

    blocks = parse_headed_code_blocks(text)

    for heading in REQUIRED_EXAMPLE_HEADINGS:
        if heading not in blocks:
            failures.append(f"{rel(EXAMPLE_FILE)}: missing fenced block for heading '{heading}'")

    pkg_block = blocks.get("e2e/package.json")
    config_block = blocks.get("e2e/playwright.config.ts")
    pages_block = blocks.get("e2e/pages/DemoPage.ts")
    steps_block = blocks.get("e2e/steps/demo.steps.ts")
    feature_block = blocks.get("e2e/features/demo.feature")
    catalog_block = blocks.get("e2e/catalog.md")
    gitignore_block = blocks.get("e2e/.gitignore")
    ci_block = blocks.get(".github/workflows/e2e.yml")
    fixture_block = blocks.get("e2e/fixtures/demo.html")

    catalog_rows = parse_catalog_table(catalog_block, EXAMPLE_FILE, failures) if catalog_block is not None else []
    step_pairs = _demo_step_phrases(steps_block) if steps_block is not None else []
    feature_step_lines = _feature_step_lines(feature_block) if feature_block is not None else []

    # The one-row arithmetic, asserted rather than assumed (plan SS2b /
    # R3's "one-row arithmetic" bullet).
    if catalog_block is not None and len(catalog_rows) != 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/catalog.md has {len(catalog_rows)} data row(s), expected exactly 1"
        )
    if steps_block is not None and len(step_pairs) != 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/steps/demo.steps.ts defines {len(step_pairs)} step "
            "definition(s), expected exactly 1"
        )
    scenario_count = feature_block.count("Scenario:") if feature_block is not None else 0
    if feature_block is not None and scenario_count != 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature has {scenario_count} 'Scenario:' "
            "line(s), expected exactly 1"
        )
    if feature_block is not None and len(feature_step_lines) != 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature has {len(feature_step_lines)} step "
            "line(s), expected exactly 1"
        )

    # demo.feature uses only explicit keywords: no And/But, no Scenario
    # Outline/Examples, no doc-strings or data tables -- required for the
    # exact-equality "matches" relation (R3) to be safe.
    if feature_block is not None:
        if "Scenario Outline" in feature_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature must not use 'Scenario Outline'")
        if "Examples:" in feature_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature must not use 'Examples:'")
        if '"""' in feature_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature must not use a doc-string")
        for line in feature_block.split("\n"):
            if line.strip().startswith("And ") or line.strip().startswith("But "):
                failures.append(f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature must not use 'And'/'But'")
                break
        for line in feature_block.split("\n"):
            if line.strip().startswith("|"):
                failures.append(f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature must not use a data table")
                break

    # The exact-equality "matches" relation: normalise(s) = strip only.
    if catalog_rows and step_pairs and feature_step_lines:
        catalog_phrase = catalog_rows[0][0].strip()
        step_keyword, step_phrase = step_pairs[0]
        step_phrase = step_phrase.strip()
        feature_line = feature_step_lines[0]
        feature_keyword, _, feature_phrase = feature_line.partition(" ")
        feature_phrase = feature_phrase.strip()

        if not (catalog_phrase == step_phrase == feature_phrase):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: the three demo phrases do not match verbatim -- "
                f"catalog={catalog_phrase!r} step={step_phrase!r} feature={feature_phrase!r}"
            )
        for label, phrase in (("catalog", catalog_phrase), ("step", step_phrase), ("feature", feature_phrase)):
            if "{" in phrase:
                failures.append(f"{rel(EXAMPLE_FILE)}: the demo {label} phrase must be parameter-free (no '{{')")

    # Locator / class / config / CI / package.json / .gitignore consistency.
    if catalog_rows and pages_block is not None:
        _phrase, page_obj, locator = catalog_rows[0]
        if locator.strip("`") not in pages_block:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: catalog locator {locator!r} does not appear verbatim "
                "in e2e/pages/DemoPage.ts"
            )
        if page_obj.strip("`") != "DemoPage":
            failures.append(
                f"{rel(EXAMPLE_FILE)}: catalog row page object {page_obj!r} does not match 'DemoPage'"
            )

    if pages_block is not None and "constructor(private readonly page: Page) {}" not in pages_block:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/pages/DemoPage.ts block missing "
            "'constructor(private readonly page: Page) {}'"
        )

    if steps_block is not None:
        for needle in ("createBdd(test)", "new DemoPage(page)", "pathToFileURL"):
            if needle not in steps_block:
                failures.append(f"{rel(EXAMPLE_FILE)}: e2e/steps/demo.steps.ts missing {needle!r}")
        if "http://" in steps_block or "https://" in steps_block:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/steps/demo.steps.ts must not contain an http(s):// literal"
            )
        # F6: the canary's "fails loudly" property is unconstrained unless
        # the step body actually asserts something -- a step that only
        # navigates and never checks the page would pass every other check
        # here yet never fail even if the fixture were blank.
        if "expect(" not in steps_block or "toBeVisible()" not in steps_block:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/steps/demo.steps.ts has no real assertion "
                "(expect(...).toBeVisible()) -- the canary would not fail loudly on a broken "
                "toolchain, only silently navigate"
            )

    if fixture_block is not None and pages_block is not None:
        # F6: also require the fixture to actually contain the heading text
        # the locator selects (read from the page object's own getByRole
        # call, not assumed) -- otherwise the fixture could be blank and the
        # locator-name literal check above would never notice.
        name_match = re.search(r"name:\s*'([^']*)'", pages_block)
        if name_match:
            heading_text = name_match.group(1)
            if heading_text not in fixture_block:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: e2e/fixtures/demo.html does not contain the heading "
                    f"text {heading_text!r} that e2e/pages/DemoPage.ts's locator selects -- the "
                    "canary could pass on a blank page"
                )
        else:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/pages/DemoPage.ts has no getByRole(..., name: '...') "
                "call to read the canary's expected heading text from"
            )

    if config_block is not None:
        if "defineBddConfig" not in config_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/playwright.config.ts missing 'defineBddConfig'")

        # F5: the plan requires the commented-out webServer/baseURL TODO
        # block to actually exist (not just requiring that no *uncommented*
        # key exists -- a config with neither line at all used to pass the
        # old negative-only check). Also, an inline uncommented occurrence
        # (e.g. `use: { baseURL: 'http://...' }`) escaped the old
        # line-prefix-only test; check for the token appearing before any
        # '//' on its line, not just at the start of the (stripped) line.
        config_lines = config_block.split("\n")

        def _is_commented(l):
            return l.strip().startswith("//")

        def _uncommented_occurrence(l, token):
            token_idx = l.find(token)
            if token_idx == -1:
                return False
            comment_idx = l.find("//")
            return comment_idx == -1 or token_idx < comment_idx

        if "TODO" not in config_block:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/playwright.config.ts is missing the commented-out "
                "webServer/baseURL TODO block"
            )
        if not any(_is_commented(l) and "baseURL" in l for l in config_lines):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/playwright.config.ts is missing a commented-out "
                "'baseURL' line in the TODO block"
            )
        if not any(_is_commented(l) and "webServer" in l for l in config_lines):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/playwright.config.ts is missing a commented-out "
                "'webServer' line in the TODO block"
            )
        for line in config_lines:
            for token in ("baseURL", "webServer"):
                if _uncommented_occurrence(line, token):
                    failures.append(
                        f"{rel(EXAMPLE_FILE)}: e2e/playwright.config.ts has an uncommented "
                        f"{token} occurrence: {line.strip()!r}"
                    )

    if pkg_block is not None:
        test_match = re.search(r'"test"\s*:\s*"([^"]*)"', pkg_block)
        if not test_match:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/package.json has no \"test\" script")
        elif "--config playwright.config.ts" not in test_match.group(1):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/package.json 'test' script "
                f"{test_match.group(1)!r} is missing '--config playwright.config.ts'"
            )
        for dep in ("@playwright/test", "playwright-bdd"):
            dep_match = re.search(r'"' + re.escape(dep) + r'"\s*:\s*"([^"]*)"', pkg_block)
            if not dep_match:
                failures.append(f"{rel(EXAMPLE_FILE)}: e2e/package.json does not declare a dependency on {dep!r}")
            else:
                version = dep_match.group(1)
                # Merged into one condition (minor hardening): "latest"
                # already fails the caret check too, so a separate
                # elif-less second assertion for it was unreachable as its
                # own distinct RED path -- no version can start with '^'
                # and equal 'latest' at once.
                if version.strip() == "latest" or not version.startswith("^"):
                    failures.append(
                        f"{rel(EXAMPLE_FILE)}: e2e/package.json {dep!r} version {version!r} "
                        "must be a caret range, never an exact pin or 'latest'"
                    )

    if ci_block is not None:
        if "cd e2e" not in ci_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: .github/workflows/e2e.yml missing 'cd e2e'")
        if "npx bddgen" not in ci_block:
            failures.append(f"{rel(EXAMPLE_FILE)}: .github/workflows/e2e.yml missing 'npx bddgen'")
        test_lines = [l for l in ci_block.split("\n") if "npx playwright test" in l]
        if not test_lines:
            failures.append(f"{rel(EXAMPLE_FILE)}: .github/workflows/e2e.yml has no 'npx playwright test' line")
        elif not any("--config playwright.config.ts" in l for l in test_lines):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: .github/workflows/e2e.yml's 'npx playwright test' line "
                "is missing '--config playwright.config.ts'"
            )

    if gitignore_block is not None:
        gi_lines = [l.rstrip() for l in gitignore_block.split("\n") if l.strip() != ""]
        if gi_lines != GITIGNORE_MANAGED_LINES:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/.gitignore block is {gi_lines!r}, "
                f"expected exactly {GITIGNORE_MANAGED_LINES!r} in that order"
            )

    return blocks


# ---------------------------------------------------------------------------
# R4 -- D2 detects an e2e/-only scaffold and cannot drift from its pin
# ---------------------------------------------------------------------------

def check_d2_amendment(failures):
    if not AGENT_FILE.is_file():
        failures.append(f"{rel(AGENT_FILE)}: file not found")
        return
    if not VALIDATE_AGENTS_SCRIPT.is_file():
        failures.append(f"{rel(VALIDATE_AGENTS_SCRIPT)}: file not found")
        return

    agent_text = AGENT_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    validator_text = VALIDATE_AGENTS_SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")

    d2_line_match = re.search(r"^- D2:\s*(.+)$", agent_text, re.MULTILINE)
    if not d2_line_match:
        failures.append(f"{rel(AGENT_FILE)}: no '- D2: ...' line found")
        return
    agent_d2 = d2_line_match.group(1).strip()

    if D2_AMENDED_MUST_MENTION not in agent_d2:
        failures.append(
            f"{rel(AGENT_FILE)}: D2 does not mention e2e/package.json — a repo scaffolded "
            "by scaffold-bdd would still print the D1 'not detected' notice"
        )

    # F3: the byte-identity check below only forces agents/page-scanner.md
    # and validate_agents.py's pin to agree with *each other* -- it would
    # pass just as happily if both were amended to add only the
    # e2e/package.json clause and drop the e2e/ playwright.config clause the
    # plan also requires. Pin that clause independently.
    if D2_AMENDED_MUST_MENTION_CONFIG not in agent_d2:
        failures.append(
            f"{rel(AGENT_FILE)}: D2 does not mention an e2e/ playwright.config clause — the "
            "byte-identity check with validate_agents.py's pin alone only forces the two files "
            "to agree with each other, not that this clause was actually added"
        )

    validator_d2_match = re.search(r'\("D2",\s*"((?:[^"\\]|\\.)*)"\)', validator_text)
    if not validator_d2_match:
        failures.append(f"{rel(VALIDATE_AGENTS_SCRIPT)}: no pinned D2 literal tuple found")
        return
    validator_d2 = validator_d2_match.group(1)

    if agent_d2 != validator_d2:
        failures.append(
            f"{rel(AGENT_FILE)}'s D2 line and {rel(VALIDATE_AGENTS_SCRIPT)}'s pinned D2 literal "
            f"are not byte-identical: agent={agent_d2!r} validator={validator_d2!r}"
        )


def check_validate_agents_regression(failures):
    """R4's additional edge-case coverage: python .github/scripts/validate_agents.py
    still exits 0 -- the regression guard for the two-file D2 edit."""
    if not VALIDATE_AGENTS_SCRIPT.is_file():
        return  # already reported by check_d2_amendment
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE_AGENTS_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(f"{rel(VALIDATE_AGENTS_SCRIPT)}: could not run as a subprocess ({exc})")
        return
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        failures.append(
            f"{rel(VALIDATE_AGENTS_SCRIPT)}: exited {result.returncode}, expected 0 "
            f"(regression from the D2 edit); tail:\n{tail}"
        )


# ---------------------------------------------------------------------------
# R5 -- release/staging and repo-shape invariants
# ---------------------------------------------------------------------------

def check_release_staging_skills(failures):
    if not RELEASE_YML.is_file():
        failures.append(f"{rel(RELEASE_YML)}: file not found")
        return

    text = RELEASE_YML.read_text(encoding="utf-8").replace("\r\n", "\n")
    stage_match = re.search(
        r"Stage install tree and build release zip.*?(?=\n\s*- name:|\Z)", text, re.DOTALL
    )
    if not stage_match:
        failures.append(f"{rel(RELEASE_YML)}: could not locate the 'Stage install tree and build release zip' step")
        return
    stage_text = stage_match.group(0)

    skills_re = re.compile(r'cp\s+-a\s+skills/\.\s+"\$STAGE/skills/"')
    skills_pos = _find_live_cp_match(skills_re, stage_text)
    if skills_pos is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy skills/. wholesale into the staging tree")
        return

    zip_idx = stage_text.find("zip -r")
    if zip_idx != -1 and skills_pos > zip_idx:
        failures.append(f"{rel(RELEASE_YML)}: skills/ copy appears after 'zip -r', must precede it")


AGENTS_MD_BULLET_SUBSTRINGS = [
    ("skills/ is staged wholesale", ["staged", "wholesale", "cp -a skills/."]),
    ("scaffold-bdd writes into the target repo under test", [
        "target repo under test", "docs/examples/scaffold-bdd-run.md", "validate_scaffold.py",
    ]),
    ("page-scanner's literals are pinned byte-for-byte", [
        "pinned byte-for-byte", "validate_agents.py", "same commit",
    ]),
    ("the catalog carries no Gherkin keyword", ["Gherkin keyword", "G2", "P3"]),
    ("the demo is deliberately one step/row/line", [
        "one step definition", "one catalog row", "one feature line",
    ]),
]


def check_agents_md_bullets(failures):
    if not AGENTS_MD.is_file():
        failures.append(f"{rel(AGENTS_MD)}: file not found")
        return

    text = AGENTS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    bullet_lines = [line for line in text.split("\n") if line.strip().startswith("-")]

    for label, substrings in AGENTS_MD_BULLET_SUBSTRINGS:
        found = any(all(s in line for s in substrings) for line in bullet_lines)
        if not found:
            failures.append(f"{rel(AGENTS_MD)}: missing the '{label}' contract bullet")


def check_no_committed_e2e_tree(failures):
    """R5: this plugin repo must carry no *committed* e2e/ tree. Checked via
    `git ls-files`, not a raw filesystem exists() -- a stray *untracked*
    local e2e/ (e.g. left over from running scaffold-bdd against this repo
    as a smoke test) is not itself a violation; only a tracked/staged one
    is, since that is what would actually land in a commit."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--", "e2e"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(
            f"{rel(E2E_DIR)}: could not run git ls-files to check for a committed e2e/ tree ({exc})"
        )
        return
    if result.returncode != 0:
        failures.append(
            f"{rel(E2E_DIR)}: git ls-files exited {result.returncode}: {result.stderr.strip()}"
        )
        return
    if result.stdout.strip():
        failures.append(f"{rel(E2E_DIR)}: this plugin repo must carry no committed e2e/ tree")


# ---------------------------------------------------------------------------
# R6 -- CI actually runs the new validator (self-referential; the lint.yml
# step itself lands in the implement phase, not this one)
# ---------------------------------------------------------------------------

def check_lint_workflow_wires_validator(failures):
    if not LINT_YML.is_file():
        failures.append(f"{rel(LINT_YML)}: file not found")
        return

    text = LINT_YML.read_text(encoding="utf-8").replace("\r\n", "\n")
    # F4: a plain whole-file substring test passes for a commented-out step
    # (e.g. "# run: python3 .github/scripts/validate_scaffold.py"). Reuse
    # the same live-line/comment-skipping approach _find_live_cp_match
    # already proves out for release.yml's cp -a checks.
    needle_re = re.compile(re.escape("python3 .github/scripts/validate_scaffold.py"))
    if _find_live_cp_match(needle_re, text) is None:
        failures.append(
            f"{rel(LINT_YML)}: no *live* step runs .github/scripts/validate_scaffold.py "
            "(a commented-out line does not count)"
        )


# ---------------------------------------------------------------------------
# R7 -- the catalog-row -> Given/When/Then mapping is pinned, total, and
# obeyed by both worked examples
# ---------------------------------------------------------------------------

def check_catalog_keyword_mapping(failures, skill_text):
    # (0) G1-G4 verbatim in their own span -- same assertion check_skill_hard_rules
    # makes, restated here as R7's own driving test per the plan's explicit
    # expected RED reason for this behaviour.
    heading = "## Hard rule: catalog → step mapping"
    span = None
    if skill_text is not None:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text
        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get(heading)
    # Unconditional, mirroring check_skill_hard_rules: span stays None when
    # the file (or the heading within it) is absent, so each G1-G4 literal
    # still produces its own per-literal RED reason -- the same message
    # shape the plan predicts (R7's expected RED reason names G2
    # specifically) -- rather than one generic "file not found" summary.
    for _label, literal in PINNED_LITERALS[heading]:
        if span is None or literal not in span:
            snippet = literal[:60]
            failures.append(
                f'{rel(SKILL_FILE)}: section "{heading}" is missing the pinned literal: "{snippet}..."'
            )

    # (0b) F1 hardening: check_skill_hard_rules's substring test proves G2's
    # *text* is present, but nothing ties that text to derive_keyword's
    # actual behaviour -- rewording G2 in the doc without touching the
    # function would sail through. Parse the G2 sentence as it actually
    # appears in the file (not the PINNED_LITERALS constant) for its two
    # quoted prefixes and their keywords, and assert they match what
    # derive_keyword implements.
    if span is not None:
        g2_pairs = re.findall(r'phrase beginning with "([^"]*)" is a (Given|When|Then) step', span)
        if not g2_pairs:
            failures.append(
                f"{rel(SKILL_FILE)}: could not find any 'phrase beginning with \"...\" is a "
                "<Keyword> step' clause in G2 to bind to derive_keyword"
            )
        for prefix, keyword in g2_pairs:
            actual = derive_keyword(prefix)
            if actual != keyword:
                failures.append(
                    f"{rel(SKILL_FILE)}: G2 says a phrase beginning with {prefix!r} is a "
                    f"{keyword} step, but derive_keyword({prefix!r}) returns {actual!r} -- the "
                    "doc and the function have drifted apart"
                )

    # (i) The adversarial table, entry by entry -- pure-function totality,
    # independent of any file on disk.
    for phrase, expected in ADVERSARIAL_TABLE:
        actual = derive_keyword(phrase)
        if actual != expected:
            failures.append(
                f"derive_keyword({phrase!r}) returned {actual!r}, expected {expected!r} "
                "(adversarial totality table)"
            )
        if actual not in ("Given", "When", "Then"):
            failures.append(f"derive_keyword({phrase!r}) returned {actual!r}, not a member of "
                             "{Given, When, Then}")

    # (ii) The demo's single row derives Given, and Given is the keyword
    # actually used in both demo.steps.ts and demo.feature.
    if EXAMPLE_FILE.is_file():
        example_text = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
        blocks = parse_headed_code_blocks(example_text)
        catalog_block = blocks.get("e2e/catalog.md")
        steps_block = blocks.get("e2e/steps/demo.steps.ts")
        feature_block = blocks.get("e2e/features/demo.feature")

        demo_rows = parse_catalog_table(catalog_block, EXAMPLE_FILE, []) if catalog_block is not None else []
        if demo_rows:
            demo_phrase = demo_rows[0][0].strip()
            derived = derive_keyword(demo_phrase)
            if derived != "Given":
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: derive_keyword({demo_phrase!r}) returned {derived!r}, "
                    "expected 'Given' for the demo's single catalog row"
                )
            if steps_block is not None:
                step_pairs = _demo_step_phrases(steps_block)
                if not any(kw == "Given" and p.strip() == demo_phrase for kw, p in step_pairs):
                    failures.append(
                        f"{rel(EXAMPLE_FILE)}: e2e/steps/demo.steps.ts does not use 'Given(' "
                        f"for the demo phrase {demo_phrase!r}"
                    )
            if feature_block is not None:
                feature_lines = _feature_step_lines(feature_block)
                if not any(l.startswith("Given ") for l in feature_lines):
                    failures.append(
                        f"{rel(EXAMPLE_FILE)}: e2e/features/demo.feature does not use a 'Given ' "
                        "step line for the demo scenario"
                    )
            if "{" in demo_phrase:
                failures.append(f"{rel(EXAMPLE_FILE)}: the demo catalog phrase must be parameter-free (no '{{')")
        if steps_block is not None and "new DemoPage(page)" in steps_block and demo_rows:
            if demo_rows[0][1].strip("`") != "DemoPage":
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: G4 -- the demo catalog row's Page object cell "
                    f"{demo_rows[0][1]!r} does not name the class instantiated by 'new DemoPage(page)'"
                )
    else:
        failures.append(f"{rel(EXAMPLE_FILE)}: file not found (cannot verify the demo's Given derivation)")

    # (iii) Apply the same function to the four rows of the already-merged
    # todomvc-scan.md and assert it reproduces its committed keywords
    # exactly (3 When, 1 Then), against that example's actual When(/Then(
    # calls -- may already pass, since todomvc-scan.md is already merged.
    if not TODOMVC_FILE.is_file():
        failures.append(f"{rel(TODOMVC_FILE)}: file not found (cannot verify the todomvc totality branches)")
        return

    todomvc_text = TODOMVC_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    todomvc_blocks = parse_headed_code_blocks(todomvc_text)
    todomvc_steps = todomvc_blocks.get("e2e/steps/todo.steps.ts")
    if todomvc_steps is None:
        failures.append(f"{rel(TODOMVC_FILE)}: missing fenced block for heading 'e2e/steps/todo.steps.ts'")
        return

    todomvc_pairs = _demo_step_phrases(todomvc_steps)
    if len(todomvc_pairs) == 0:
        failures.append(f"{rel(TODOMVC_FILE)}: found zero Given/When/Then step phrases")
        return

    when_count = sum(1 for kw, _p in todomvc_pairs if kw == "When")
    then_count = sum(1 for kw, _p in todomvc_pairs if kw == "Then")
    if when_count != 3 or then_count != 1:
        failures.append(
            f"{rel(TODOMVC_FILE)}: found {when_count} When / {then_count} Then step definitions, "
            "expected exactly 3 When and 1 Then"
        )

    for actual_kw, phrase in todomvc_pairs:
        derived = derive_keyword(phrase.strip())
        if derived != actual_kw:
            failures.append(
                f"{rel(TODOMVC_FILE)}: derive_keyword({phrase.strip()!r}) returned {derived!r}, "
                f"but the committed step definition uses {actual_kw!r}"
            )
        if derived not in ("Given", "When", "Then"):
            failures.append(f"derive_keyword({phrase!r}) returned {derived!r}, not a member of "
                             "{Given, When, Then}")


def main():
    failures = []

    skill_text = check_skill_frontmatter(failures)
    check_skill_hard_rules(failures, skill_text)
    check_web_tester_body(failures)
    check_worked_example(failures)
    check_d2_amendment(failures)
    check_validate_agents_regression(failures)
    check_release_staging_skills(failures)
    check_agents_md_bullets(failures)
    check_no_committed_e2e_tree(failures)
    check_lint_workflow_wires_validator(failures)
    check_catalog_keyword_mapping(failures, skill_text)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_scaffold: OK (scaffold-bdd skill + worked example + D2 amendment + CI wiring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
