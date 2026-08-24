#!/usr/bin/env python3
"""Validate the `author-scenario` skill package (WP #4): that
``skills/author-scenario/SKILL.md`` exists with sibling-convention
frontmatter and carries its seven pinned ``## Hard rule:`` sections (route
determination, catalog reuse, file placement, skill-owned step files,
unresolvable UI, target URL, self-check) verbatim, in that order -- route
determination first, because route determination happens before anything
reads the catalog; that the two hand-written worked examples under
``docs/examples/author-scenario/`` (``README.md`` for the happy path,
``unresolvable-ui.md`` for the unresolvable-UI path) are internally
consistent: the catalog before/after arithmetic holds, the delegation to
page-scanner is observable (not merely asserted), the derived keywords agree
with ``derive_keyword`` (imported from ``validate_scaffold.py`` via
``importlib``, never re-implemented, per plan A6), the derived route
round-trips into the feature-file path and the navigation step, and the
skill-owned/scanner-owned step-file boundary is honoured including the A5
collision fallback; that ``lint.yml`` wires in this validator; that
``release.yml`` still stages ``skills/`` and ``docs/`` before ``zip -r``;
that ``AGENTS.md`` carries the five new contract bullets; that this repo
still carries no committed ``e2e/`` tree; that ``skills/web-tester/SKILL.md``
is untouched (no 'author-scenario' mention); and that
``validate_scaffold.py`` still exits 0 (no regression in #2/#3's
territory).

Usage:
    python .github/scripts/validate_author_scenario.py     (local, Windows or *nix)
    python3 .github/scripts/validate_author_scenario.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_manifests.py``, ``validate_agents.py`` and
``validate_scaffold.py``.

Both worked example docs are hand-written and deliberately never executed
(round-4 decision, see the plan) -- this validator's honest guarantee is
*internal consistency*, the same limit ``validate_scaffold.py`` already
accepts for ``docs/examples/scaffold-bdd-run.md``, not a green ``bddgen``
run.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_FILE = REPO_ROOT / "skills" / "author-scenario" / "SKILL.md"
WEB_TESTER_FILE = REPO_ROOT / "skills" / "web-tester" / "SKILL.md"
README_FILE = REPO_ROOT / "docs" / "examples" / "author-scenario" / "README.md"
UNRESOLVABLE_FILE = REPO_ROOT / "docs" / "examples" / "author-scenario" / "unresolvable-ui.md"
VALIDATE_SCAFFOLD_SCRIPT = REPO_ROOT / ".github" / "scripts" / "validate_scaffold.py"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
E2E_DIR = REPO_ROOT / "e2e"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# A2's seven pinned headings, in the plan's fixed order -- route
# determination first (it happens before anything reads the catalog), then
# catalog reuse, file placement, skill-owned step files, unresolvable UI,
# target URL, self-check last.
HARD_RULE_HEADINGS = [
    "## Hard rule: route determination",
    "## Hard rule: catalog reuse",
    "## Hard rule: file placement",
    "## Hard rule: skill-owned step files",
    "## Hard rule: unresolvable UI",
    "## Hard rule: target URL",
    "## Hard rule: self-check",
]

# The pinned literals from plan section A2 (N1-N6, R1-R4, F1-F4, A1-A5,
# U1-U4, T1-T2, V1-V3), keyed by the section heading whose span must contain
# them. Copied verbatim from the plan, punctuation (including the EM DASH
# "--") included.
PINNED_LITERALS = {
    "## Hard rule: route determination": [
        ("N1", "N1: Before reading e2e/catalog.md, derive from the description an "
               "ordered list of the route paths the scenario visits — one entry "
               "per navigation the sentences imply, in the order they are "
               "visited, duplicates collapsed only when consecutive. Every later "
               "rule consumes that list; nothing re-derives it."),
        ("N2", "N2: When a sentence names a route literally — a token beginning "
               "with / or a full URL — that is the route: reproduce it verbatim, "
               "normalising a full URL down to its path component only."),
        ("N3", "N3: Otherwise recover the route from the target repo, never from "
               "imagination: a route already recorded as the parameter of a "
               "Given I am on the '<route>' page line under e2e/features/**, or "
               "the route a page object under e2e/pages/ was scanned against as "
               "recorded in that file, matches when the description names that "
               "page. A page object's class name is never itself turned into a "
               "route path — TodoPage was scanned from /todomvc, not from "
               "/todo."),
        ("N4", "N4: When neither N2 nor N3 yields a route, ask the user once for "
               "the route path, use the answer for this run only, and never "
               "write it into e2e/playwright.config.ts or any other file. Never "
               "guess a path from a page name and never extrapolate one from a "
               "URL pattern seen elsewhere in the repo."),
        ("N5", "N5: The N1 list is what decides F1's branch — exactly one "
               "distinct route means e2e/features/<route-slug>.feature, more "
               "than one means e2e/features/flows/<flow-slug>.feature — and "
               "each route in it is the route a page-scanner delegation under "
               "R3 is made against, resolved against the base URL from T1/T2."),
        ("N6", "N6: Report the derived list in the summary as exactly one line "
               "Routes: <route>[, <route>...] (<source>), where <source> is "
               "exactly one of from description, from e2e/, or asked user."),
    ],
    "## Hard rule: catalog reuse": [
        ("R1", "R1: Read e2e/catalog.md before writing anything; every step "
               "line you emit is either an existing catalog phrase reproduced "
               "verbatim or a phrase minted through R3 — never a phrase you "
               "invented on your own."),
        ("R2", "R2: A catalog row is a semantic match when it names the same "
               "element and the same interaction as the sentence you need; "
               "prefer an existing parameterized row (with {string}) over "
               "minting a fixed-value twin, and never mint a second phrase for "
               "an element the catalog already covers."),
        ("R3", "R3: Never invent a locator and never write or edit a page "
               "object yourself. When no catalog row matches, delegate that "
               "element to the page-scanner subagent with a task hint naming "
               "exactly the missing interactions, then re-read e2e/catalog.md "
               "and reproduce the phrase the scanner minted, verbatim."),
        ("R4", "R4: Gherkin keywords are derived, never chosen: a phrase "
               "beginning with \"I should \" is a Then line, a phrase beginning "
               "with \"I am \" is a Given line, every other phrase is a When "
               "line — scaffold-bdd's G2 applied to the catalog phrase you "
               "selected. A line whose derived keyword equals the previous "
               "line's is written with And."),
    ],
    "## Hard rule: file placement": [
        ("F1", "F1: A scenario that visits exactly one route goes in "
               "e2e/features/<route-slug>.feature; a scenario that visits more "
               "than one route goes in e2e/features/flows/<flow-slug>.feature. "
               "The route slug is the route path lowercased with the leading "
               "slash dropped and every remaining run of non-alphanumeric "
               "characters replaced by a single hyphen; the empty result "
               "(route \"/\") is written as home."),
        ("F2", "F2: Append a new Scenario: block at the end of the target "
               "file, preserving every existing byte before it; create the "
               "file with a single Feature: line only when it does not already "
               "exist."),
        ("F3", "F3: A scenario whose name equals an existing Scenario: name in "
               "the target file (compared after trimming) replaces that block "
               "in place, from its Scenario: line to the line before the next "
               "Scenario:, Feature: or end of file, leaving every other block "
               "byte-identical — never appended as a duplicate."),
        ("F4", "F4: Never write, move or delete anything under e2e/ other "
               "than e2e/features/**, e2e/steps/authored.steps.ts, "
               "e2e/steps/todo.steps.ts and e2e/steps/todo.authored.steps.ts; "
               "e2e/catalog.md, e2e/pages/**, e2e/playwright.config.ts and "
               "every scanner-owned step file are read-only to this skill."),
        ("F5", "F5: The flow slug is the N1 route list's slugs, each "
               "computed by F1's per-route slug function, joined in visit "
               "order with a single hyphen between consecutive slugs — the "
               "same ordered route list therefore always produces the same "
               "flow slug, so re-authoring the same flow replaces the "
               "existing e2e/features/flows/<flow-slug>.feature file rather "
               "than duplicating it."),
    ],
    "## Hard rule: skill-owned step files": [
        ("A1", "A1: This skill writes step definitions to at most three "
               "paths: e2e/steps/authored.steps.ts (the navigation and data "
               "steps it mints itself), e2e/steps/todo.steps.ts (placeholder "
               "steps for @skip'd scenarios) and e2e/steps/todo.authored.steps.ts "
               "(the A5 collision fallback, written only when A5 applies). "
               "Every other file under e2e/steps/ is scanner-owned and "
               "read-only."),
        ("A2", "A2: Every skill-owned file begins with the exact first line "
               "// author-scenario: skill-owned. page-scanner never writes "
               "here. A file at any of the three paths whose first line is "
               "not that marker is scanner-owned: do not edit it."),
        ("A3", "A3: e2e/steps/authored.steps.ts contains only steps whose "
               "body navigates (page.goto) or calls an accessor that already "
               "exists on a page object under e2e/pages/; it never contains a "
               "locator expression of its own. The navigation step is "
               "Given('I am on the {string} page', ...), taking the route "
               "path as its parameter."),
        ("A4", "A4: Extend a skill-owned step file by appending new step "
               "definitions and, where needed, extending its import list; an "
               "existing definition for the same phrase is left byte-identical "
               "and never duplicated."),
        ("A5", "A5: When e2e/steps/todo.steps.ts already exists and its "
               "first line is not the A2 marker, it is scanner-owned: leave "
               "every byte of it untouched and write the placeholders to "
               "e2e/steps/todo.authored.steps.ts instead, beginning that file "
               "with the same A2 marker line, then print exactly Collision: "
               "e2e/steps/todo.steps.ts is scanner-owned — placeholders "
               "written to e2e/steps/todo.authored.steps.ts"),
    ],
    "## Hard rule: unresolvable UI": [
        ("U1", "U1: A sentence whose element is neither in e2e/catalog.md "
               "nor found by the page-scanner scan of the route is "
               "unresolvable. Never guess a locator, never invent a phrase for "
               "it, and never silently drop the sentence."),
        ("U2", "U2: Write the scenario anyway, with the tag line @todo @skip "
               "directly above its Scenario: line — @skip is playwright-bdd's "
               "own tag, so the scenario is skipped and the rest of the suite "
               "still runs green."),
        ("U3", "U3: Every step line of a @skip'd scenario whose phrase is "
               "not in the catalog gets a placeholder definition in "
               "e2e/steps/todo.steps.ts — or, when A5 applies, in "
               "e2e/steps/todo.authored.steps.ts — whose body is exactly "
               "throw new Error('TODO: UI not present'); — an undefined step "
               "would fail bddgen for the whole suite, which is what U2 exists "
               "to prevent."),
        ("U4", "U4: Report each one in the summary as Unresolved: <sentence> "
               "— no matching element on <route>; scenario tagged @todo "
               "@skip."),
    ],
    "## Hard rule: target URL": [
        ("T1", "T1: Read baseURL from the target repo's "
               "e2e/playwright.config.ts before scanning, and use it as the "
               "scan origin whenever it is set (uncommented)."),
        ("T2", "T2: When baseURL is still the commented-out TODO that "
               "scaffold-bdd wrote, ask the user once for the base URL, use "
               "the answer for this run's scan requests only, and never write "
               "it into e2e/playwright.config.ts or any other file."),
        ("T3", "T3: When T2 applies, the URL you asked for is used only for "
               "this run's scan requests and, per T2, is never persisted; "
               "before the exact command V3 prints can resolve routes, the "
               "user must set baseURL in e2e/playwright.config.ts themselves "
               "— printing that command does not by itself make it runnable "
               "in this branch."),
    ],
    "## Hard rule: self-check": [
        ("V1", "V1: After writing, run cd e2e && npx bddgen once and nothing "
               "else — never npx playwright test, never a browser, never the "
               "user's app."),
        ("V2", "V2: Print exactly one of three lines per run — \"Self-check: "
               "PASS — bddgen resolved every step\", \"Self-check: FAIL — "
               "bddgen exited <code>\" followed by the offending phrases under "
               "\"Undefined or ambiguous steps:\", or \"Self-check: SKIPPED — no "
               "runnable e2e/ project; run scaffold-bdd (#3) first\"."),
        ("V3", "V3: End every summary with the exact line \"Run it yourself: "
               "cd e2e && npx bddgen && npx playwright test --config "
               "playwright.config.ts\" — this skill never runs the scenario "
               "itself."),
    ],
}

# The Summary checklist vocabulary (plan A2, trailing paragraph): Routes:
# listed first, matching the flow order (route determination precedes
# catalog reuse).
SUMMARY_VOCABULARY = [
    "Routes: ",
    "Reused (catalog): ",
    "Scanned (new steps): ",
    "Created: ",
    "Updated: ",
    "Replaced scenario: ",
    "Unresolved: ",
    "Collision: ",
    "Self-check: PASS — bddgen resolved every step",
    "Self-check: FAIL — bddgen exited <code>",
    "Undefined or ambiguous steps:",
    "Self-check: SKIPPED — no runnable e2e/ project; run scaffold-bdd (#3) first",
    "Run it yourself: cd e2e && npx bddgen && npx playwright test --config playwright.config.ts",
]

# The exact Collision line (A5 / U3), pinned once and reused everywhere it
# must appear verbatim: the skill body and unresolvable-ui.md's prose note.
COLLISION_LINE = ("Collision: e2e/steps/todo.steps.ts is scanner-owned — "
                   "placeholders written to e2e/steps/todo.authored.steps.ts")

# A2's skill-owned marker, the exact first line of every skill-owned step file.
MARKER_LINE = "// author-scenario: skill-owned. page-scanner never writes here."

# U3's exact placeholder body.
PLACEHOLDER_BODY = "throw new Error('TODO: UI not present');"

# U2's exact tag line, directly above a @skip'd Scenario: line.
TAG_LINE = "@todo @skip"

# A3's navigation phrase, minted by the skill itself into
# e2e/steps/authored.steps.ts -- never a scanner catalog row, so both
# check_reuse_example (F6, test-critic round 1) and check_unresolvable_example
# exempt it from the catalog-row lookup while still checking its keyword.
NAV_PHRASE = "I am on the {string} page"

# A locator expression of its own -- forbidden in any skill-owned step file
# (A3's "never contains a locator expression of its own").
LOCATOR_PATTERNS = ["getByRole(", "getByLabel(", "getByTestId(", "page.locator("]

# The pinned heading suffix for every scanner-owned artefact shown for
# context in either worked example (plan A4, fifth bullet).
SCANNER_OWNED_SUFFIX = " (read-only, scanner-owned)"

# F3 (test-critic round 1): the README's own description prose must contain
# the literal route it claims BR0's 'Routes: ... (from description)' line
# was derived from -- a doc that only mentions /signin in the summary must
# not pass.
DESCRIPTION_HEADING = "## Description"

# F4 (test-critic round 1): the '## Summary checklist' heading must exist,
# and 'Routes: ' must be the first vocabulary entry listed under it.
CHECKLIST_HEADING = "## Summary checklist"

# F7 (test-critic round 1): the interaction verbs a task-hint delegation
# block must name at least one of, alongside the route, so the block
# structurally names "the missing interaction" and not just an accessible
# name in isolation.
TASK_HINT_INTERACTION_VERBS = ["click", "fill", "check", "select", "navigate"]

RUN_IT_YOURSELF_LINE = ("Run it yourself: cd e2e && npx bddgen && npx playwright "
                         "test --config playwright.config.ts")
SELF_CHECK_LINES = [
    "Self-check: PASS — bddgen resolved every step",
    "Self-check: FAIL — bddgen exited <code>",
    "Self-check: SKIPPED — no runnable e2e/ project; run scaffold-bdd (#3) first",
]

# The two exact README sentences pinned by plan A4 (check_file_placement
# asserts them as substrings; they are the observable, not a "mention").
FLOWS_SENTENCE = ("A scenario that visits more than one route is written to "
                   "e2e/features/flows/<flow-slug>.feature instead; this example "
                   "visits only /signin, so it lands in the per-route file.")
HOME_SLUG_SENTENCE = ("The route / has an empty slug, so its feature file is "
                       "written as e2e/features/home.feature.")

# The worked example's fixed headings (plan A4 / BR2 / BR3 / BR4). These are
# this developer's pinned choice of concrete heading text for the
# sign-in fixture the plan describes but does not spell out letter-for-letter
# beyond "SignInPage.ts" / "signin.html" / "/signin" -- the implement phase
# must reproduce them verbatim for this validator to go green.
CATALOG_BEFORE_HEADING = "e2e/catalog.md (before)"
CATALOG_AFTER_HEADING = "e2e/catalog.md (after)"
TASK_HINT_HEADING = "page-scanner task hint"
AUTHORED_STEPS_HEADING = "e2e/steps/authored.steps.ts"
FEATURE_HEADING = "e2e/features/signin.feature"
SIGNIN_PAGE_HEADING = "e2e/pages/SignInPage.ts" + SCANNER_OWNED_SUFFIX
SIGNIN_FIXTURE_HEADING = "e2e/fixtures/signin.html" + SCANNER_OWNED_SUFFIX
SIGNIN_STEPS_SCANNER_HEADING = "e2e/steps/signin.steps.ts" + SCANNER_OWNED_SUFFIX

REQUIRED_README_HEADINGS = [
    CATALOG_BEFORE_HEADING,
    TASK_HINT_HEADING,
    CATALOG_AFTER_HEADING,
    AUTHORED_STEPS_HEADING,
    FEATURE_HEADING,
    SIGNIN_PAGE_HEADING,
    SIGNIN_FIXTURE_HEADING,
    SIGNIN_STEPS_SCANNER_HEADING,
]

# The adversarial totality table (same one validate_scaffold.py pins),
# applied to the *imported* derive_keyword per BR2's additional coverage --
# its value here is pinning that #4 did not fork the function.
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

# AGENTS.md contract bullets pinned by plan A7 (five bullets, additional
# hardening per BR7's expected GREEN outcome: the route-determination bullet
# must mention /todomvc and e2e/features/flows/; the ownership bullet must
# mention e2e/steps/todo.authored.steps.ts).
AGENTS_MD_BULLET_SUBSTRINGS = [
    ("route determination is derived, never inferred from names", [
        "Route determination is derived", "TodoPage", "/todomvc", "e2e/features/flows/",
    ]),
    ("author-scenario owns its step files by a first-line marker", [
        "owns its step files by a first-line marker", "e2e/steps/todo.authored.steps.ts", "Collision: ",
    ]),
    ("the navigation phrase must stay in the 'I am' form", [
        "navigation phrase", "I am", "G2",
    ]),
    ("docs/examples/author-scenario/ is a release artifact", [
        "docs/examples/author-scenario/", "release artifact", "validate_author_scenario.py",
    ]),
    ("skills/web-tester/SKILL.md is deliberately not wired to author-scenario", [
        "skills/web-tester/SKILL.md", "is deliberately not wired to", "author-scenario",
    ]),
]


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def _read_text(path):
    """Read a file as LF-normalised text, or None if it does not exist or
    cannot be read -- callers that already reported "file not found"
    themselves just get a silent None back."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError:
        return None


def get_section_spans(body_text, headings):
    """Section spans: from a hard-rule heading (verbatim, start of line) to
    the next line starting with '## ', or EOF. Mirrors validate_scaffold.py's
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
    validate_scaffold.py's parse_headed_code_blocks. Keys by the *full*
    heading text, so suffixed headings such as '### e2e/catalog.md (before)'
    and '### e2e/steps/signin.steps.ts (read-only, scanner-owned)' are
    distinct keys."""
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
    (not commented-out) line, or None. Mirrors validate_scaffold.py's
    _find_live_cp_match."""
    offset = 0
    for line in stage_text.split("\n"):
        if not line.strip().startswith("#"):
            m = regex.search(line)
            if m:
                return offset + m.start()
        offset += len(line) + 1
    return None


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


_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


def _normalise_to_catalog_phrase(step_text):
    """Replace quoted literals with {string}, mirroring how a parameterized
    catalog row's {string} placeholder round-trips into an emitted step
    line (R4's derivation input)."""
    return _QUOTED_RE.sub("{string}", step_text)


def _step_definition_phrases(steps_block):
    """(keyword, phrase) pairs for every Given/When/Then(...) call in a
    steps block."""
    return re.findall(r"(Given|When|Then)\(\s*['\"](.*?)['\"]", steps_block)


def _extract_accessible_name(locator_cell):
    """The accessible-name string inside a catalog row's Locator cell: the
    name: '...' value, or the sole quoted argument for
    getByLabel/getByPlaceholder/getByTestId (plan BR2, delegation check d)."""
    m = re.search(r"name:\s*'([^']*)'", locator_cell)
    if m:
        return m.group(1)
    m = re.search(r"get(?:ByLabel|ByPlaceholder|ByTestId)\('([^']*)'\)", locator_cell)
    if m:
        return m.group(1)
    return None


def _first_line(block_text):
    return block_text.split("\n", 1)[0]


def _strip_heading_suffix(heading):
    """Strip a trailing parenthesised suffix (e.g. ' (before)',
    ' (read-only, scanner-owned)') from a '### <heading>' key, recovering
    the underlying path (plan A4, third bullet)."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", heading).strip()


def slugify_route(route):
    """F1's route -> feature-file slug function: the route path lowercased
    with the leading slash dropped and every remaining run of
    non-alphanumeric characters replaced by a single hyphen; the empty
    result (route "/") is written as home."""
    slug = route.lower()
    if slug.startswith("/"):
        slug = slug[1:]
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug if slug else "home"


def _load_derive_keyword(failures):
    """A6: import derive_keyword from validate_scaffold.py via
    importlib.util.spec_from_file_location rather than re-implementing it,
    so #4's examples cannot drift from #3's G2. A failed import is itself a
    recorded failure."""
    if not VALIDATE_SCAFFOLD_SCRIPT.is_file():
        failures.append(f"{rel(VALIDATE_SCAFFOLD_SCRIPT)}: file not found (cannot import derive_keyword)")
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "validate_scaffold_for_author_scenario", VALIDATE_SCAFFOLD_SCRIPT
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.derive_keyword
    except Exception as exc:  # pragma: no cover - defensive, recorded as a failure
        failures.append(f"{rel(VALIDATE_SCAFFOLD_SCRIPT)}: could not import derive_keyword ({exc})")
        return None


# ---------------------------------------------------------------------------
# BR1 -- skills/author-scenario/SKILL.md exists and carries its pinned
# contract (also used by BR0's ordering/N1-N6 assertions).
# ---------------------------------------------------------------------------

def check_skill_frontmatter(failures):
    """BR1. Returns the normalised (LF-only) full file text on success, or
    "" if the file does not exist at all -- deliberately not None: every
    downstream heading/literal check still runs against the empty body, so
    a missing file surfaces the full per-literal breakdown the plan's
    expected RED reasons (BR0/BR1/BR3/BR4/BR6) name explicitly, the same
    way a heading present but a literal absent would, rather than being
    swallowed by a single short-circuited "file not found"."""
    if not SKILL_FILE.is_file():
        failures.append(f"{rel(SKILL_FILE)}: file not found")
        return ""

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
        if name_value != "author-scenario":
            failures.append(f"{rel(SKILL_FILE)}: frontmatter 'name' is {name_value!r}, expected 'author-scenario'")
    elif "name:" in fm:
        failures.append(f"{rel(SKILL_FILE)}: could not parse 'name:' value from frontmatter")

    desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if desc_match:
        if not desc_match.group(1).strip():
            failures.append(f"{rel(SKILL_FILE)}: frontmatter 'description' is empty")
    elif "description:" in fm:
        failures.append(f"{rel(SKILL_FILE)}: could not parse 'description:' value from frontmatter")

    if "docs/examples/author-scenario/README.md" not in text:
        failures.append(f"{rel(SKILL_FILE)}: does not link to docs/examples/author-scenario/README.md")

    return text


def check_skill_hard_rules(failures, skill_text):
    """BR1's heading-order and pinned-literal assertions across all seven
    sections. No-op if the file could not be read at all --
    check_skill_frontmatter already reported that."""
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

    for token in SUMMARY_VOCABULARY:
        if token not in body:
            failures.append(f"{rel(SKILL_FILE)}: missing summary vocabulary literal: {token!r}")


# ---------------------------------------------------------------------------
# BR0 -- route determination: the target route(s) are derived from the
# description, never invented.
# ---------------------------------------------------------------------------

def check_route_determination(failures, skill_text):
    route_heading = "## Hard rule: route determination"
    catalog_heading = "## Hard rule: catalog reuse"

    if skill_text is None:
        failures.append(f"{rel(SKILL_FILE)}: file not found")
    else:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text

        route_pat = re.compile(r"^" + re.escape(route_heading) + r"\s*$", re.MULTILINE)
        catalog_pat = re.compile(r"^" + re.escape(catalog_heading) + r"\s*$", re.MULTILINE)
        route_match = route_pat.search(body)
        catalog_match = catalog_pat.search(body)

        if route_match is None:
            failures.append(f"{rel(SKILL_FILE)}: missing '{route_heading}' heading")
        elif catalog_match is not None and route_match.start() > catalog_match.start():
            failures.append(
                f"{rel(SKILL_FILE)}: '{route_heading}' must appear before '{catalog_heading}' -- "
                "route determination happens before anything reads the catalog"
            )

        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get(route_heading)
        for _label, literal in PINNED_LITERALS[route_heading]:
            if span is None or literal not in span:
                snippet = literal[:60]
                failures.append(
                    f'{rel(SKILL_FILE)}: section "{route_heading}" is missing the pinned literal: "{snippet}..."'
                )

        # N6 edge coverage: each of the three source literals appears
        # somewhere in the skill.
        for source_literal in ("from description", "from e2e/", "asked user"):
            if source_literal not in body:
                failures.append(f"{rel(SKILL_FILE)}: missing N6 source literal {source_literal!r}")

        if span is not None:
            if "TodoPage" not in span:
                failures.append(f"{rel(SKILL_FILE)}: N3's pinned counter-example 'TodoPage' is missing")
            if "e2e/features/flows/" not in span:
                failures.append(f"{rel(SKILL_FILE)}: N5 does not mention 'e2e/features/flows/'")
            if "R3" not in span:
                failures.append(f"{rel(SKILL_FILE)}: N5 does not mention 'R3'")

    # README's Routes: line and its round-trip into the feature file / nav step.
    readme_text = _read_text(README_FILE)
    if readme_text is None:
        failures.append(f"{rel(README_FILE)}: no 'Routes: ' summary line")
    else:
        # F3 (test-critic round 1): the "(from description)" claim must be
        # tied to an actual description -- the README's own '## Description'
        # section must contain the route literally, not just the summary line.
        desc_idx = readme_text.find(DESCRIPTION_HEADING)
        if desc_idx == -1:
            failures.append(f"{rel(README_FILE)}: missing '{DESCRIPTION_HEADING}' heading")
        else:
            next_h2 = re.compile(r"^## ", re.MULTILINE)
            next_match = next_h2.search(readme_text, desc_idx + len(DESCRIPTION_HEADING))
            desc_span = readme_text[desc_idx: next_match.start() if next_match else len(readme_text)]
            if "/signin" not in desc_span:
                failures.append(
                    f"{rel(README_FILE)}: '{DESCRIPTION_HEADING}' section does not mention '/signin' "
                    "literally -- the '(from description)' claim must be tied to an actual description"
                )

        routes_lines = [l.strip() for l in readme_text.split("\n") if l.strip().startswith("Routes: ")]
        if len(routes_lines) != 1:
            failures.append(
                f"{rel(README_FILE)}: expected exactly one 'Routes: ' summary line, found {len(routes_lines)}"
            )
        elif routes_lines[0] != "Routes: /signin (from description)":
            failures.append(
                f"{rel(README_FILE)}: 'Routes: ' line is {routes_lines[0]!r}, expected "
                "'Routes: /signin (from description)'"
            )
        else:
            route = "/signin"
            slug = slugify_route(route)
            blocks = parse_headed_code_blocks(readme_text)
            expected_basename = f"e2e/features/{slug}.feature"
            feature_heading = next(
                (h for h in blocks if _strip_heading_suffix(h) == expected_basename), None
            )
            if feature_heading is None:
                failures.append(
                    f"{rel(README_FILE)}: no fenced block heading matches the derived route slug "
                    f"'{expected_basename}'"
                )
            else:
                feature_block = blocks[feature_heading]
                nav_line = f"Given I am on the '{route}' page"
                if nav_line not in feature_block:
                    failures.append(
                        f"{rel(README_FILE)}: '{feature_heading}' is missing the exact navigation "
                        f"line {nav_line!r}"
                    )

    # unresolvable-ui.md carries exactly one Routes: line too (its own
    # cross-check against its feature heading lives in check_unresolvable_example).
    unresolvable_text = _read_text(UNRESOLVABLE_FILE)
    if unresolvable_text is not None:
        u_routes_lines = [l.strip() for l in unresolvable_text.split("\n") if l.strip().startswith("Routes: ")]
        if len(u_routes_lines) != 1:
            failures.append(
                f"{rel(UNRESOLVABLE_FILE)}: expected exactly one 'Routes: ' summary line, found "
                f"{len(u_routes_lines)}"
            )


# ---------------------------------------------------------------------------
# BR2 -- reuse over minting, with the mint visibly delegated and keywords
# derived.
# ---------------------------------------------------------------------------

def check_reuse_example(failures, derive_keyword):
    if not README_FILE.is_file():
        failures.append(f"{rel(README_FILE)}: file not found")
        return

    text = _read_text(README_FILE)
    blocks = parse_headed_code_blocks(text)

    for heading in REQUIRED_README_HEADINGS:
        if heading not in blocks:
            failures.append(f"{rel(README_FILE)}: missing fenced block for heading '{heading}'")

    before_block = blocks.get(CATALOG_BEFORE_HEADING)
    after_block = blocks.get(CATALOG_AFTER_HEADING)
    hint_block = blocks.get(TASK_HINT_HEADING)

    before_rows = parse_catalog_table(before_block, README_FILE, failures) if before_block is not None else []
    after_rows = parse_catalog_table(after_block, README_FILE, failures) if after_block is not None else []

    if before_block is not None and len(before_rows) != 3:
        failures.append(
            f"{rel(README_FILE)}: '{CATALOG_BEFORE_HEADING}' has {len(before_rows)} data row(s), "
            "expected exactly 3"
        )
    if after_block is not None and len(after_rows) != 4:
        failures.append(
            f"{rel(README_FILE)}: '{CATALOG_AFTER_HEADING}' has {len(after_rows)} data row(s), "
            "expected exactly 4"
        )

    new_rows = []
    if before_rows and after_rows:
        after_set = set(after_rows)
        before_set = set(before_rows)
        for row in before_rows:
            if row not in after_set:
                failures.append(
                    f"{rel(README_FILE)}: before-catalog row {row!r} is missing from the after-catalog "
                    "(shared rows must stay byte-identical)"
                )
        new_rows = [row for row in after_rows if row not in before_set]
        if len(new_rows) != 1:
            failures.append(
                f"{rel(README_FILE)}: '{CATALOG_AFTER_HEADING}' has {len(new_rows)} row(s) not present "
                "before, expected exactly 1 minted row"
            )
        sorted_after = sorted(after_rows, key=lambda r: (r[1], r[0]))
        if list(after_rows) != sorted_after:
            failures.append(
                f"{rel(README_FILE)}: '{CATALOG_AFTER_HEADING}' rows are not sorted by page object "
                "then phrase"
            )

    if hint_block is not None and not hint_block.strip():
        failures.append(f"{rel(README_FILE)}: '{TASK_HINT_HEADING}' fenced block is empty")
    elif hint_block is not None:
        # F7 (test-critic round 1): a structural predicate beyond
        # non-empty + accessible name -- the delegation block must name the
        # route and the missing interaction, not just an isolated string.
        if "/signin" not in hint_block:
            failures.append(
                f"{rel(README_FILE)}: '{TASK_HINT_HEADING}' block does not name the route '/signin'"
            )
        if not any(verb in hint_block.lower() for verb in TASK_HINT_INTERACTION_VERBS):
            failures.append(
                f"{rel(README_FILE)}: '{TASK_HINT_HEADING}' block does not name the missing interaction "
                f"(expected one of {TASK_HINT_INTERACTION_VERBS})"
            )

    hint_heading_count = text.count(f"### {TASK_HINT_HEADING}")
    if hint_heading_count != 1:
        failures.append(
            f"{rel(README_FILE)}: expected exactly one '### {TASK_HINT_HEADING}' heading, found "
            f"{hint_heading_count}"
        )

    scanned_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("Scanned (new steps): ")]
    if len(scanned_lines) != 1:
        failures.append(
            f"{rel(README_FILE)}: expected exactly one 'Scanned (new steps): ' summary line, found "
            f"{len(scanned_lines)}"
        )
    elif new_rows:
        minted_phrase = new_rows[0][0].strip()
        scanned_value = scanned_lines[0][len("Scanned (new steps): "):].strip()
        if scanned_value != minted_phrase:
            failures.append(
                f"{rel(README_FILE)}: 'Scanned (new steps): ' line is {scanned_value!r}, expected the "
                f"minted catalog phrase {minted_phrase!r}"
            )
        if hint_block is not None:
            accessible_name = _extract_accessible_name(new_rows[0][2])
            if accessible_name is None:
                failures.append(
                    f"{rel(README_FILE)}: could not extract an accessible name from the minted row's "
                    f"Locator cell {new_rows[0][2]!r}"
                )
            elif accessible_name not in hint_block:
                failures.append(
                    f"{rel(README_FILE)}: the minted locator's accessible name {accessible_name!r} does "
                    f"not appear verbatim in the '{TASK_HINT_HEADING}' block"
                )

    reused_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("Reused (catalog): ")]
    before_phrases = {row[0].strip() for row in before_rows}
    for line in reused_lines:
        value = line[len("Reused (catalog): "):].strip()
        if value not in before_phrases:
            failures.append(f"{rel(README_FILE)}: 'Reused (catalog): {value}' is not a before-catalog phrase")

    feature_block = blocks.get(FEATURE_HEADING)
    if feature_block is not None and after_rows and derive_keyword is not None:
        after_phrases = {row[0].strip() for row in after_rows}
        prev_explicit = None
        for line in _feature_step_lines(feature_block):
            keyword, _, rest = line.partition(" ")
            rest = rest.strip()
            if keyword in ("And", "But"):
                resolved_keyword = prev_explicit
            else:
                resolved_keyword = keyword
                prev_explicit = keyword
            phrase_template = _normalise_to_catalog_phrase(rest)
            if phrase_template == NAV_PHRASE:
                # F6 (test-critic round 1): the skill-minted navigation phrase
                # is minted into e2e/steps/authored.steps.ts by A3, never a
                # scanner catalog row -- exempt it from the after-catalog
                # lookup the same way check_unresolvable_example already
                # does, but still verify its keyword derives to Given.
                expected = derive_keyword(phrase_template)
                if expected != resolved_keyword:
                    failures.append(
                        f"{rel(README_FILE)}: feature step {line!r} resolves to keyword "
                        f"{resolved_keyword!r}, but derive_keyword({phrase_template!r}) returns "
                        f"{expected!r}"
                    )
                continue
            if phrase_template not in after_phrases:
                failures.append(
                    f"{rel(README_FILE)}: feature step {line!r} (normalised to {phrase_template!r}) has "
                    "no matching after-catalog row"
                )
                continue
            expected = derive_keyword(phrase_template)
            if expected != resolved_keyword:
                failures.append(
                    f"{rel(README_FILE)}: feature step {line!r} resolves to keyword {resolved_keyword!r}, "
                    f"but derive_keyword({phrase_template!r}) returns {expected!r}"
                )

    pages_block = blocks.get(SIGNIN_PAGE_HEADING)
    fixture_block = blocks.get(SIGNIN_FIXTURE_HEADING)
    if after_rows and pages_block is not None:
        for _phrase, _page_obj, locator in after_rows:
            if locator.strip("`") not in pages_block:
                failures.append(
                    f"{rel(README_FILE)}: catalog locator {locator!r} does not appear verbatim in "
                    f"'{SIGNIN_PAGE_HEADING}'"
                )
    if pages_block is not None and fixture_block is not None:
        for name_match in re.finditer(r"name:\s*'([^']*)'", pages_block):
            heading_text = name_match.group(1)
            if heading_text not in fixture_block:
                failures.append(
                    f"{rel(README_FILE)}: '{SIGNIN_FIXTURE_HEADING}' does not contain the accessible "
                    f"name {heading_text!r} that '{SIGNIN_PAGE_HEADING}' selects -- the example could "
                    "pass on a blank page"
                )

    if derive_keyword is not None:
        for phrase, expected in ADVERSARIAL_TABLE:
            actual = derive_keyword(phrase)
            if actual != expected:
                failures.append(
                    f"derive_keyword({phrase!r}) returned {actual!r}, expected {expected!r} (adversarial "
                    "totality table)"
                )


# ---------------------------------------------------------------------------
# BR3 -- file placement (per-route file, flows file, append/replace).
# ---------------------------------------------------------------------------

def check_file_placement(failures, skill_text, readme_blocks, readme_text):
    block = readme_blocks.get(FEATURE_HEADING)
    if block is None:
        failures.append(f"{rel(README_FILE)}: missing fenced block for heading '{FEATURE_HEADING}'")
    else:
        count = block.count("Scenario:")
        if count != 1:
            failures.append(
                f"{rel(README_FILE)}: '{FEATURE_HEADING}' block has {count} 'Scenario:' line(s), "
                "expected exactly 1"
            )

    if readme_text is None:
        failures.append(f"{rel(README_FILE)}: missing the flows-convention sentence")
        failures.append(f"{rel(README_FILE)}: missing the home-slug sentence")
    else:
        if FLOWS_SENTENCE not in readme_text:
            failures.append(f"{rel(README_FILE)}: missing the flows-convention sentence")
        if HOME_SLUG_SENTENCE not in readme_text:
            failures.append(f"{rel(README_FILE)}: missing the home-slug sentence")

    if skill_text is not None:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text
        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get("## Hard rule: file placement")
        for label in ("F1", "F2", "F3"):
            literal = next(lit for lbl, lit in PINNED_LITERALS["## Hard rule: file placement"] if lbl == label)
            if span is None or literal not in span:
                failures.append(
                    f'{rel(SKILL_FILE)}: section "## Hard rule: file placement" is missing the pinned '
                    f"literal {label}"
                )

    unresolvable_text = _read_text(UNRESOLVABLE_FILE)
    for doc_path, text in ((README_FILE, readme_text), (UNRESOLVABLE_FILE, unresolvable_text)):
        if text is None:
            continue
        for line in text.split("\n"):
            if line.startswith("### ") and line.rstrip().endswith(".feature"):
                heading = line[4:].strip()
                base = _strip_heading_suffix(heading)
                if not base.startswith("e2e/features/"):
                    failures.append(f"{rel(doc_path)}: '.feature' heading '{heading}' is outside e2e/features/")


# ---------------------------------------------------------------------------
# BR4 -- skill-owned vs scanner-owned step files, including the collision
# fallback.
# ---------------------------------------------------------------------------

def check_step_file_ownership(failures, skill_text, readme_blocks, unresolvable_blocks):
    authored = readme_blocks.get(AUTHORED_STEPS_HEADING)
    if authored is None:
        failures.append(f"{rel(README_FILE)}: missing fenced block for heading '{AUTHORED_STEPS_HEADING}'")
    else:
        if _first_line(authored) != MARKER_LINE:
            failures.append(f"{rel(README_FILE)}: '{AUTHORED_STEPS_HEADING}'s first line is not the A2 marker")
        for pat in LOCATOR_PATTERNS:
            if pat in authored:
                failures.append(
                    f"{rel(README_FILE)}: '{AUTHORED_STEPS_HEADING}' must not contain a locator "
                    f"expression ({pat!r})"
                )
        if "createBdd(test)" not in authored:
            failures.append(f"{rel(README_FILE)}: '{AUTHORED_STEPS_HEADING}' missing 'createBdd(test)'")
        if "Given('I am on the {string} page'" not in authored:
            failures.append(
                f"{rel(README_FILE)}: '{AUTHORED_STEPS_HEADING}' missing the navigation step definition "
                "Given('I am on the {string} page', ...)"
            )

    todo_block = readme_blocks.get("e2e/steps/todo.steps.ts") or unresolvable_blocks.get("e2e/steps/todo.steps.ts")
    if todo_block is None:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: missing fenced block for heading 'e2e/steps/todo.steps.ts'")
    else:
        if _first_line(todo_block) != MARKER_LINE:
            failures.append("e2e/steps/todo.steps.ts's first line is not the A2 marker")
        for pat in LOCATOR_PATTERNS:
            if pat in todo_block:
                failures.append(f"e2e/steps/todo.steps.ts must not contain a locator expression ({pat!r})")

    scanner_block = readme_blocks.get(SIGNIN_STEPS_SCANNER_HEADING)
    if scanner_block is None:
        failures.append(f"{rel(README_FILE)}: missing fenced block for heading '{SIGNIN_STEPS_SCANNER_HEADING}'")
    elif _first_line(scanner_block) == MARKER_LINE:
        failures.append(
            f"{rel(README_FILE)}: the scanner-owned '{SIGNIN_STEPS_SCANNER_HEADING}' block must not "
            "carry the A2 marker"
        )

    # Ownership-labelling predicate: for every heading in either doc whose
    # text, after stripping a trailing parenthesised suffix, matches
    # e2e/steps/*.steps.ts, either the block is marker-first or the heading
    # ends with the scanner-owned suffix -- never neither, never both.
    for doc_path, blocks in ((README_FILE, readme_blocks), (UNRESOLVABLE_FILE, unresolvable_blocks)):
        for heading, block_text in blocks.items():
            base = _strip_heading_suffix(heading)
            if not re.match(r"^e2e/steps/[^/]+\.steps\.ts$", base):
                continue
            is_marker_first = _first_line(block_text) == MARKER_LINE
            is_labelled_scanner_owned = heading.endswith(SCANNER_OWNED_SUFFIX)
            if is_marker_first and is_labelled_scanner_owned:
                failures.append(
                    f"{rel(doc_path)}: heading '{heading}' is both marker-first and labelled "
                    "scanner-owned -- never both"
                )
            elif not is_marker_first and not is_labelled_scanner_owned:
                failures.append(
                    f"{rel(doc_path)}: heading '{heading}' is neither marker-first nor labelled "
                    "scanner-owned -- never neither"
                )

    if skill_text is not None:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text
        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get("## Hard rule: skill-owned step files")
        a5_literal = next(lit for lbl, lit in PINNED_LITERALS["## Hard rule: skill-owned step files"] if lbl == "A5")
        if span is None or a5_literal not in span:
            failures.append(
                f'{rel(SKILL_FILE)}: section "## Hard rule: skill-owned step files" is missing the '
                "pinned literal A5"
            )
        if COLLISION_LINE not in body:
            failures.append(f"{rel(SKILL_FILE)}: missing the exact Collision line")

    unresolvable_text = _read_text(UNRESOLVABLE_FILE)
    if unresolvable_text is not None and COLLISION_LINE not in unresolvable_text:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: missing the exact Collision line in its prose note")


# ---------------------------------------------------------------------------
# BR5 -- unresolvable UI is skipped, not guessed.
# ---------------------------------------------------------------------------

def check_unresolvable_example(failures, derive_keyword):
    if not UNRESOLVABLE_FILE.is_file():
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: file not found")
        return

    text = _read_text(UNRESOLVABLE_FILE)
    blocks = parse_headed_code_blocks(text)

    feature_heading = None
    feature_block = None
    for heading, block in blocks.items():
        base = _strip_heading_suffix(heading)
        if base.startswith("e2e/features/") and base.endswith(".feature"):
            feature_heading = heading
            feature_block = block
            break
    if feature_block is None:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: missing a fenced block for an e2e/features/*.feature heading")
    else:
        lines = feature_block.split("\n")
        found_tag_above_scenario = False
        for i, line in enumerate(lines):
            if line.strip().startswith("Scenario:"):
                prev = lines[i - 1].strip() if i > 0 else ""
                if prev == TAG_LINE:
                    found_tag_above_scenario = True
                break
        if not found_tag_above_scenario:
            failures.append(
                f"{rel(UNRESOLVABLE_FILE)}: '{TAG_LINE}' tag line is not directly above the Scenario: line"
            )

    # Intentionally scoped to e2e/steps/todo.steps.ts only -- not
    # todo.authored.steps.ts -- because plan A4 scopes this doc to the
    # non-collision path; A5's collision fallback is covered in prose only.
    todo_block = blocks.get("e2e/steps/todo.steps.ts")
    if todo_block is None:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: missing fenced block for heading 'e2e/steps/todo.steps.ts'")
    else:
        if PLACEHOLDER_BODY not in todo_block:
            failures.append(
                f"{rel(UNRESOLVABLE_FILE)}: e2e/steps/todo.steps.ts placeholder body is not exactly "
                f"{PLACEHOLDER_BODY!r}"
            )
        for pat in LOCATOR_PATTERNS:
            if pat in todo_block:
                failures.append(
                    f"{rel(UNRESOLVABLE_FILE)}: e2e/steps/todo.steps.ts must not contain a locator "
                    f"expression ({pat!r})"
                )
        if "expect(" in todo_block:
            failures.append(f"{rel(UNRESOLVABLE_FILE)}: e2e/steps/todo.steps.ts must not contain an assertion")

    unresolved_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("Unresolved: ")]
    if not unresolved_lines:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: no 'Unresolved: ' summary line")

    # F2 (test-critic round 1): assert the *full* U4 shape, not just the
    # 'Unresolved: ' prefix -- "Unresolved: <sentence> — no matching element
    # on <route>; scenario tagged @todo @skip."
    u4_pattern = re.compile(
        r"^Unresolved: .+ — no matching element on (\S+); scenario tagged @todo @skip\.$"
    )
    u4_matched_line = next((l for l in unresolved_lines if u4_pattern.match(l)), None)
    if unresolved_lines and u4_matched_line is None:
        failures.append(
            f"{rel(UNRESOLVABLE_FILE)}: no 'Unresolved: ' line matches the full U4 shape "
            "'Unresolved: <sentence> — no matching element on <route>; scenario tagged @todo @skip.'"
        )

    routes_lines = [l.strip() for l in text.split("\n") if l.strip().startswith("Routes: ")]
    if len(routes_lines) != 1:
        failures.append(f"{rel(UNRESOLVABLE_FILE)}: expected exactly one 'Routes: ' summary line, found {len(routes_lines)}")
    elif feature_heading is not None:
        route_match = re.match(r"Routes: (\S+)", routes_lines[0])
        if route_match:
            route = route_match.group(1)
            slug = slugify_route(route)
            base = _strip_heading_suffix(feature_heading)
            expected_basename = f"e2e/features/{slug}.feature"
            if base != expected_basename:
                failures.append(
                    f"{rel(UNRESOLVABLE_FILE)}: 'Routes: ' line's route {route!r} slugifies to {slug!r} "
                    f"(expected feature heading '{expected_basename}'), but the feature heading is "
                    f"'{feature_heading}'"
                )

    # F2: the route cross-check is now unconditional -- a missing/malformed
    # U4 clause is itself a failure (u4_matched_line is None above), and
    # whenever both lines are present their routes must agree.
    if u4_matched_line is not None and len(routes_lines) == 1:
        u4_route = u4_pattern.match(u4_matched_line).group(1)
        routes_route_match = re.match(r"Routes: (\S+)", routes_lines[0])
        if routes_route_match and u4_route != routes_route_match.group(1):
            failures.append(
                f"{rel(UNRESOLVABLE_FILE)}: 'Unresolved: ' line's route {u4_route!r} does not match "
                f"the 'Routes: ' line's route {routes_route_match.group(1)!r}"
            )

    if feature_block is not None and todo_block is not None:
        defined_phrases = {p for _kw, p in _step_definition_phrases(todo_block)}
        catalog_heading = next(
            (h for h in blocks if _strip_heading_suffix(h) == "e2e/catalog.md"), None
        )
        catalog_phrases = set()
        if catalog_heading is not None:
            # A malformed catalog table here must surface, exactly like
            # check_reuse_example's equivalent call does for README.md --
            # passing the real `failures` accumulator (not a throwaway list)
            # is what makes that visible instead of silently discarded.
            rows = parse_catalog_table(blocks[catalog_heading], UNRESOLVABLE_FILE, failures)
            catalog_phrases = {r[0].strip() for r in rows}
        for line in _feature_step_lines(feature_block):
            _kw, _, rest = line.partition(" ")
            phrase = _normalise_to_catalog_phrase(rest.strip())
            if phrase == NAV_PHRASE:
                continue
            if phrase not in defined_phrases and phrase not in catalog_phrases:
                failures.append(
                    f"{rel(UNRESOLVABLE_FILE)}: step phrase {phrase!r} has no catalog row and no "
                    "placeholder definition in e2e/steps/todo.steps.ts -- bddgen would fail on an "
                    "undefined step"
                )


# ---------------------------------------------------------------------------
# BR6 -- self-verification is bddgen-only and hands the run command back to
# the user.
# ---------------------------------------------------------------------------

def _find_all(text, sub):
    start = 0
    out = []
    while True:
        idx = text.find(sub, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + 1
    return out


def check_self_check_vocabulary(failures, skill_text):
    if skill_text is None:
        failures.append(f"{rel(SKILL_FILE)}: file not found (cannot verify self-check vocabulary)")
        return

    # F5 (test-critic round 1): the three Self-check: lines and the Run it
    # yourself: line are substrings of the pinned V2/V3 literals *and* A2
    # requires the Summary checklist to list them again -- a faithful
    # SKILL.md legitimately yields count 2 (once inside V2/V3, once in the
    # checklist). Require at least once overall, and separately require the
    # checklist occurrence (F4) below.
    for line in SELF_CHECK_LINES + [RUN_IT_YOURSELF_LINE]:
        count = skill_text.count(line)
        if count < 1:
            failures.append(f"{rel(SKILL_FILE)}: {line!r} appears {count} time(s) in the skill, expected at least 1")

    # F4 (test-critic round 1): nothing previously asserted the
    # '## Summary checklist' heading exists, since its tokens are substrings
    # of pinned literals. Assert the heading exists and that 'Routes: ' is
    # the first vocabulary entry listed under it (matching the flow order:
    # route determination precedes catalog reuse).
    checklist_idx = skill_text.find(CHECKLIST_HEADING)
    if checklist_idx == -1:
        failures.append(f"{rel(SKILL_FILE)}: missing '{CHECKLIST_HEADING}' heading")
    else:
        next_h2 = re.compile(r"^## ", re.MULTILINE)
        next_match = next_h2.search(skill_text, checklist_idx + len(CHECKLIST_HEADING))
        checklist_span = skill_text[checklist_idx: next_match.start() if next_match else len(skill_text)]

        for line in SELF_CHECK_LINES + [RUN_IT_YOURSELF_LINE]:
            if line not in checklist_span:
                failures.append(f"{rel(SKILL_FILE)}: '{CHECKLIST_HEADING}' section is missing {line!r}")

        first_positions = {}
        for token in SUMMARY_VOCABULARY:
            idx = checklist_span.find(token)
            if idx != -1:
                first_positions[token] = idx
        if "Routes: " not in first_positions:
            failures.append(f"{rel(SKILL_FILE)}: '{CHECKLIST_HEADING}' section does not list 'Routes: '")
        elif first_positions and min(first_positions.values()) != first_positions["Routes: "]:
            failures.append(
                f"{rel(SKILL_FILE)}: '{CHECKLIST_HEADING}' section must list 'Routes: ' first, matching "
                "the flow order (route determination precedes catalog reuse)"
            )

    for occ_idx in _find_all(skill_text, "npx playwright test"):
        # V1's own pinned literal prohibits running it -- "never npx
        # playwright test" -- which necessarily contains this phrase. That
        # explicit prohibition is exempt; only an occurrence NOT preceded by
        # "never " must live on the Run it yourself: line.
        if skill_text[max(0, occ_idx - 6):occ_idx] == "never ":
            continue
        line_start = skill_text.rfind("\n", 0, occ_idx) + 1
        line_end = skill_text.find("\n", occ_idx)
        line = skill_text[line_start: line_end if line_end != -1 else len(skill_text)]
        if RUN_IT_YOURSELF_LINE not in line:
            failures.append(
                f"{rel(SKILL_FILE)}: 'npx playwright test' appears outside the 'Run it yourself:' line: "
                f"{line.strip()!r}"
            )

    for doc_path in (README_FILE, UNRESOLVABLE_FILE):
        text = _read_text(doc_path)
        if text is None:
            failures.append(f"{rel(doc_path)}: summary block does not end with the exact 'Run it yourself:' line")
            continue
        stripped_lines = [l for l in text.split("\n") if l.strip() != ""]
        if not stripped_lines or stripped_lines[-1].strip() != RUN_IT_YOURSELF_LINE:
            failures.append(f"{rel(doc_path)}: summary block does not end with the exact 'Run it yourself:' line")


# ---------------------------------------------------------------------------
# BR7 -- CI wiring and no regression in #2/#3.
# ---------------------------------------------------------------------------

def check_lint_workflow_wires_validator(failures):
    if not LINT_YML.is_file():
        failures.append(f"{rel(LINT_YML)}: file not found")
        return

    text = LINT_YML.read_text(encoding="utf-8").replace("\r\n", "\n")
    needle_re = re.compile(re.escape("python3 .github/scripts/validate_author_scenario.py"))
    if _find_live_cp_match(needle_re, text) is None:
        failures.append(
            f"{rel(LINT_YML)}: no live step runs .github/scripts/validate_author_scenario.py "
            "(a commented-out line does not count)"
        )


def check_release_staging(failures):
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
    zip_idx = stage_text.find("zip -r")

    skills_re = re.compile(r'cp\s+-a\s+skills/\.\s+"\$STAGE/skills/"')
    skills_pos = _find_live_cp_match(skills_re, stage_text)
    if skills_pos is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy skills/. wholesale into the staging tree")
    elif zip_idx != -1 and skills_pos > zip_idx:
        failures.append(f"{rel(RELEASE_YML)}: skills/ copy appears after 'zip -r', must precede it")

    # Deliberately looser than skills_re above. skills_re inherits an
    # already-accepted hard-pin precedent from validate_scaffold.py's
    # check_release_staging_skills, which this repo's reviewers have already
    # signed off on for that exact literal. The docs/ pin is new with this
    # validator, and review round 2 flagged that pinning release.yml's exact
    # `cp -a docs "$STAGE/"` spelling would fail an equivalent staging
    # rewrite (different quoting/whitespace, or `cp -a docs/. "$STAGE/docs/"`)
    # for no real reason -- the actual contract this must guarantee is just
    # "release.yml stages docs/ into $STAGE before zipping", because docs/ is
    # a documented AGENTS.md release artifact. So this regex tolerates the
    # source spelled as docs, docs/ or docs/. and the destination spelled as
    # "$STAGE/" or "$STAGE/docs" or "$STAGE/docs/", with or without quotes,
    # while still requiring a real `cp -a ... docs ... $STAGE ...` line.
    docs_re = re.compile(r'''cp\s+-a\s+docs(?:/\.|/)?\s+['"]?\$STAGE/(?:docs/?)?['"]?''')
    docs_pos = _find_live_cp_match(docs_re, stage_text)
    if docs_pos is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy docs/ into the staging tree")
    elif zip_idx != -1 and docs_pos > zip_idx:
        failures.append(f"{rel(RELEASE_YML)}: docs/ copy appears after 'zip -r', must precede it")


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
    """This plugin repo must carry no *committed* e2e/ tree. Checked via
    `git ls-files`, not a raw filesystem exists() -- mirrors
    validate_scaffold.py's check_no_committed_e2e_tree."""
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
        failures.append(f"{rel(E2E_DIR)}: git ls-files exited {result.returncode}: {result.stderr.strip()}")
        return
    if result.stdout.strip():
        failures.append(f"{rel(E2E_DIR)}: this plugin repo must carry no committed e2e/ tree")


def check_web_tester_untouched(failures):
    """A5: zero edits to #2/#3 territory -- skills/web-tester/SKILL.md must
    contain no 'author-scenario' mention."""
    if not WEB_TESTER_FILE.is_file():
        failures.append(f"{rel(WEB_TESTER_FILE)}: file not found")
        return
    text = WEB_TESTER_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "author-scenario" in text:
        failures.append(f"{rel(WEB_TESTER_FILE)}: must not mention 'author-scenario' (A5: zero edits to #2/#3 territory)")


def check_scaffold_regression(failures):
    """Additional edge-case coverage (BR7): validate_scaffold.py still exits
    0 -- the regression guard against #4 accidentally editing #2/#3 files.
    Same subprocess-regression trick validate_scaffold.py:848 already uses
    for validate_agents.py."""
    if not VALIDATE_SCAFFOLD_SCRIPT.is_file():
        failures.append(f"{rel(VALIDATE_SCAFFOLD_SCRIPT)}: file not found")
        return
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCAFFOLD_SCRIPT)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        failures.append(f"{rel(VALIDATE_SCAFFOLD_SCRIPT)}: could not run as a subprocess ({exc})")
        return
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        failures.append(
            f"{rel(VALIDATE_SCAFFOLD_SCRIPT)}: exited {result.returncode}, expected 0 (regression check); "
            f"tail:\n{tail}"
        )


def main():
    failures = []

    derive_keyword = _load_derive_keyword(failures)

    skill_text = check_skill_frontmatter(failures)
    check_skill_hard_rules(failures, skill_text)
    check_route_determination(failures, skill_text)

    readme_text = _read_text(README_FILE)
    readme_blocks = parse_headed_code_blocks(readme_text) if readme_text is not None else {}
    unresolvable_text = _read_text(UNRESOLVABLE_FILE)
    unresolvable_blocks = parse_headed_code_blocks(unresolvable_text) if unresolvable_text is not None else {}

    check_reuse_example(failures, derive_keyword)
    check_file_placement(failures, skill_text, readme_blocks, readme_text)
    check_step_file_ownership(failures, skill_text, readme_blocks, unresolvable_blocks)
    check_unresolvable_example(failures, derive_keyword)
    check_self_check_vocabulary(failures, skill_text)

    check_lint_workflow_wires_validator(failures)
    check_release_staging(failures)
    check_agents_md_bullets(failures)
    check_no_committed_e2e_tree(failures)
    check_web_tester_untouched(failures)
    check_scaffold_regression(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_author_scenario: OK (author-scenario skill + worked examples + CI wiring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
