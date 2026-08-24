#!/usr/bin/env python3
"""Validate the `page-scanner` subagent package (WP #2): that
``agents/page-scanner.md`` exists with sibling-convention frontmatter and
carries its five pinned ``## Hard rule:`` sections, that the worked example
at ``docs/examples/todomvc-scan.md`` is internally consistent (its catalog
table round-trips against its step definitions and its page-object locators
are accessibility-first), that ``release.yml`` stages ``agents/`` and
``docs/`` for installed users, that ``AGENTS.md`` carries the two new
contract bullets, and that neither plugin manifest grew an ``agents`` key.

Usage:
    python .github/scripts/validate_agents.py     (local, Windows or *nix)
    python3 .github/scripts/validate_agents.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_manifests.py`` and the SKILL.md frontmatter check in
lint.yml.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AGENT_FILE = REPO_ROOT / "agents" / "page-scanner.md"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
EXAMPLE_FILE = REPO_ROOT / "docs" / "examples" / "todomvc-scan.md"
CLAUDE_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = REPO_ROOT / ".codex-plugin" / "plugin.json"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Tools the scanner needs to author e2e/ files and read the target repo's
# toolchain config; the denylist must never shadow these (plan Approach,
# "Use a denylist, never a tools: allowlist").
TOOLS_THAT_MUST_STAY_ALLOWED = ("Read", "Write", "Edit", "Glob", "Grep")

HARD_RULE_HEADINGS = [
    "## Hard rule: write scope",
    "## Hard rule: scope selection",
    "## Hard rule: locator style",
    "## Hard rule: re-scan reconciliation",
    "## Hard rule: playwright-bdd detection",
]

# The 20 pinned literals from plan Amendment A1 (W1-W2, S1-S5, L1-L4,
# C1-C7, D1-D2 — the enumeration in A6 governs over A6's prose, which
# mistakenly says 22), keyed by the section
# heading whose span must contain them. Text and punctuation (including the
# EM DASH "—", the ARROW "→", and the straight apostrophe "'") are copied
# verbatim from the plan.
PINNED_LITERALS = {
    "## Hard rule: write scope": [
        ("W1", "Write scope is e2e/** only: the scanner must never create or modify any path outside e2e/."),
        ("W2", "package.json, package-lock.json, playwright.config.*, and every CI file are read-only: read them to detect the toolchain, never edit them."),
    ],
    "## Hard rule: scope selection": [
        ("S1", "With a task hint, scan the elements the hint names plus those directly required to perform or assert them, and nothing else."),
        ("S2", "With no task hint, scan the primary interactive elements only: form controls, buttons, and named links."),
        ("S3", "Skip nav chrome and footers: any element inside a navigation or contentinfo landmark is out of scope unless the task hint names it."),
        ("S4", "Applied scope: task hint — <hint>"),
        ("S5", "Applied scope: no task hint — primary interactive elements (form controls, buttons, named links); navigation and contentinfo landmarks skipped"),
    ],
    "## Hard rule: locator style": [
        ("L1", "Locator preference order, highest first: (1) getByRole with an accessible name; (2) getByLabel, getByPlaceholder, getByAltText, getByTitle, and getByText; (3) getByTestId; (4) page.locator with CSS or XPath, last resort only."),
        ("L2", "getByText is tier 2 and is permitted only for non-interactive text assertions, never for an interactive control."),
        ("L3", "A chained or filtered locator rooted at getByRole counts as tier 1."),
        ("L4", "Every tier-4 locator must be listed in the summary under the heading Locator fallbacks:, naming the element, the emitted selector, and the reason; a silent CSS selector is a contract violation."),
    ],
    "## Hard rule: re-scan reconciliation": [
        ("C1", "The match key is the (role, accessible name) pair from the snapshot, with internal whitespace collapsed to single spaces, trimmed, and compared case-sensitively."),
        ("C2", "The locator expression is mutable payload, never part of the key."),
        ("C3", "If the key matches an existing accessor, reuse that entry's phrase verbatim and never mint a new phrase for that element."),
        ("C4", "If the re-derived locator differs from the one already in the page object, update it in place and report it as old → new."),
        ("C5", "If the (role, accessible name) pair itself changed there is no key match, so the element is treated as new and its phrase is minted, then the phrase pass applies."),
        ("C6", "Never delete or reword an existing entry that this scan did not match; list every such entry in the summary under Unmatched existing entries:."),
        ("C7", "The page object TypeScript is the source of truth; e2e/catalog.md is regenerated from it on every run and is only consulted to find the phrase attached to an accessor."),
    ],
    "## Hard rule: playwright-bdd detection": [
        ("D1", "playwright-bdd not detected — run scaffold-bdd (#3) to make these runnable."),
        ("D2", "Detection succeeds if the root package.json lists playwright-bdd under dependencies or devDependencies, or a root playwright.config file contains playwright-bdd or defineBddConfig."),
    ],
}

# Not one of A1's 20 enumerated pinned literals, but pinned here so the
# DOM/HTML-scraping prohibition is checked by polarity-aware substring
# match rather than the vacuous "dom" and "scrap" keyword co-occurrence
# (test-critic hardening finding #1 — that check passed for bodies
# containing e.g. "scrapbook" or a sentence that *permits* DOM scraping).
DOM_SCRAPING_PROHIBITION = (
    "Read the page only through browser_snapshot's accessibility tree; "
    "never scrape the DOM or parse raw HTML."
)

# Ties the "links to the worked example" check to a real markdown link
# rather than a bare path substring, which passed for prose like "Do not
# read docs/examples/todomvc-scan.md." (test-critic hardening finding #4).
WORKED_EXAMPLE_LINK_RE = re.compile(
    r"\[[^\]\n]*\]\([^)\n]*docs/examples/todomvc-scan\.md[^)\n]*\)"
)

APPLIED_SCOPE_HINT_LINE = (
    "Applied scope: task hint — adding a todo, completing it, and clearing completed todos"
)
PLAYWRIGHT_BDD_NOTICE = "playwright-bdd not detected — run scaffold-bdd (#3) to make these runnable."

ACCEPTED_LOCATOR_METHODS = {
    "getByRole", "getByLabel", "getByPlaceholder", "getByTestId",
    "getByText", "getByAltText", "getByTitle",
}
LOCATOR_METHOD_RE = re.compile(r"\.(getBy\w+|locator)\(")
# Applied verbatim (no exemptions) to the steps block; applied to the
# page-object block with disclosed-tier-4-call spans exempted from
# 'page.locator(' / 'css=' / 'xpath=' -- see check_locator_style_block's
# docstring for why the two blocks differ.
FORBIDDEN_LOCATOR_SUBSTRINGS = ["page.locator(", "page.$", "css=", "xpath="]


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages —
    matches the shape the plan's own 'Expected RED reason' strings use."""
    return path.relative_to(REPO_ROOT).as_posix()


def extract_calls(text, func_name):
    """Return the argument text of every ``func_name(...)`` call in
    ``text``, matched with balanced-paren scanning (a plain regex would stop
    at the first nested paren, e.g. inside a RegExp literal)."""
    calls = []
    needle = func_name + "("
    idx = 0
    while True:
        pos = text.find(needle, idx)
        if pos == -1:
            break
        start = pos + len(needle)
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        calls.append(text[start:i - 1])
        idx = i
    return calls


def extract_calls_with_end(text, func_name):
    """Like ``extract_calls``, but also returns the index immediately after
    each call's closing paren, so a caller can inspect what is chained onto
    it (e.g. a following ``.filter(...)``)."""
    calls = []
    needle = func_name + "("
    idx = 0
    while True:
        pos = text.find(needle, idx)
        if pos == -1:
            break
        start = pos + len(needle)
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        calls.append((text[start:i - 1], i))
        idx = i
    return calls


# ---------------------------------------------------------------------------
# R1 + R6 — agents/page-scanner.md
# ---------------------------------------------------------------------------

def check_agent_frontmatter(failures):
    """R1. Returns the normalised (LF-only) full file text on success, or
    None if the file could not be read at all."""
    if not AGENT_FILE.is_file():
        failures.append(f"{rel(AGENT_FILE)}: file not found")
        return None

    raw = AGENT_FILE.read_bytes()
    if b"\r\n" in raw:
        failures.append(f"{rel(AGENT_FILE)}: file contains CRLF line endings (\\r\\n); must be LF-only")

    text = raw.decode("utf-8").replace("\r\n", "\n")

    m = FRONTMATTER_RE.match(text)
    if not m:
        failures.append(f"{rel(AGENT_FILE)}: missing YAML frontmatter matching '^---\\n(.*?)\\n---\\n'")
        return text

    fm = m.group(1)
    if not fm.strip():
        failures.append(f"{rel(AGENT_FILE)}: frontmatter is empty")

    for key in ("name:", "description:", "disallowedTools:"):
        if key not in fm:
            failures.append(f"{rel(AGENT_FILE)}: frontmatter missing '{key}' key")

    name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.MULTILINE)
    if name_match:
        name_value = name_match.group(1).strip().strip("\"'")
        # Note: AGENT_FILE is a fixed constant path (agents/page-scanner.md),
        # so comparing name_value against the literal "page-scanner" and
        # against AGENT_FILE.stem are the same assertion under a different
        # spelling — they can never independently fail. Keep only the
        # literal comparison (test-critic hardening finding #6).
        if name_value != "page-scanner":
            failures.append(f"{rel(AGENT_FILE)}: frontmatter 'name' is {name_value!r}, expected 'page-scanner'")
    elif "name:" in fm:
        failures.append(f"{rel(AGENT_FILE)}: could not parse 'name:' value from frontmatter")

    if re.search(r"^tools:", fm, re.MULTILINE):
        failures.append(
            f"{rel(AGENT_FILE)}: frontmatter must not declare a 'tools:' allowlist key "
            "(a tools: glob grant leaves the deferred MCP index empty)"
        )

    deny_match = re.search(r"^disallowedTools:\s*(.+)$", fm, re.MULTILINE)
    if deny_match:
        deny_list = [t.strip() for t in deny_match.group(1).split(",") if t.strip()]
        if not deny_list:
            failures.append(f"{rel(AGENT_FILE)}: 'disallowedTools' parses to an empty list")
        if "Bash" not in deny_list:
            failures.append(f"{rel(AGENT_FILE)}: 'disallowedTools' does not contain 'Bash'")
        for must_keep in TOOLS_THAT_MUST_STAY_ALLOWED:
            if must_keep in deny_list:
                failures.append(
                    f"{rel(AGENT_FILE)}: 'disallowedTools' must not contain '{must_keep}' "
                    "(the scanner needs it to author e2e/ files)"
                )
    elif "disallowedTools:" in fm:
        failures.append(f"{rel(AGENT_FILE)}: could not parse 'disallowedTools:' value from frontmatter")

    return text


def get_section_spans(body_text):
    """Section spans per plan A1: from a hard-rule heading (verbatim, start
    of line) to the next line starting with '## ', or EOF."""
    spans = {}
    generic_heading_re = re.compile(r"^## ", re.MULTILINE)
    for heading in HARD_RULE_HEADINGS:
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


def check_agent_body_contract(failures, agent_text):
    """R6 (restated by A6). No-op if the file could not be read at all —
    check_agent_frontmatter already reported that."""
    if agent_text is None:
        return

    m = FRONTMATTER_RE.match(agent_text)
    body = agent_text[m.end():] if m else agent_text

    heading_offsets = []
    for heading in HARD_RULE_HEADINGS:
        pattern = re.compile(r"^" + re.escape(heading) + r"\s*$", re.MULTILINE)
        match = pattern.search(body)
        if match is None:
            failures.append(f'{rel(AGENT_FILE)}: missing hard-rule heading "{heading}"')
            heading_offsets.append(None)
        else:
            heading_offsets.append(match.start())

    present_offsets = [o for o in heading_offsets if o is not None]
    if present_offsets != sorted(present_offsets):
        failures.append(
            f"{rel(AGENT_FILE)}: hard-rule headings are present but not in the required order "
            f"({HARD_RULE_HEADINGS})"
        )

    spans = get_section_spans(body)
    for heading, literals in PINNED_LITERALS.items():
        span = spans.get(heading)
        for _label, literal in literals:
            if span is None or literal not in span:
                snippet = literal[:60]
                failures.append(
                    f'{rel(AGENT_FILE)}: section "{heading}" is missing the pinned literal: "{snippet}..."'
                )

    # Additional edge-case coverage (R6).
    if not WORKED_EXAMPLE_LINK_RE.search(body):
        failures.append(
            f"{rel(AGENT_FILE)}: body does not contain a markdown link to docs/examples/todomvc-scan.md"
        )
    if "browser_snapshot" not in body:
        failures.append(f"{rel(AGENT_FILE)}: body does not mention 'browser_snapshot'")
    if DOM_SCRAPING_PROHIBITION not in body:
        failures.append(
            f"{rel(AGENT_FILE)}: body is missing the DOM-scraping prohibition literal: "
            f"{DOM_SCRAPING_PROHIBITION!r}"
        )
    if 'ToolSearch(query="select:' not in body:
        failures.append(f'{rel(AGENT_FILE)}: body missing the ToolSearch(query="select:...") bootstrap paragraph')


# ---------------------------------------------------------------------------
# R2 — release.yml staging
# ---------------------------------------------------------------------------

def _find_live_cp_match(regex, stage_text):
    """Search ``stage_text`` line-by-line for ``regex`` and return the
    absolute character offset of the first match found on a *live* (not
    commented-out) line, or None. A plain ``regex.search`` over the whole
    step text matches a commented-out ``# cp -a agents ...`` line just as
    readily as a real one (test-critic hardening finding #3); this skips
    any line whose stripped text starts with ``#``."""
    offset = 0
    for line in stage_text.split("\n"):
        if not line.strip().startswith("#"):
            m = regex.search(line)
            if m:
                return offset + m.start()
        offset += len(line) + 1
    return None


def check_release_staging(failures):
    if not RELEASE_YML.is_file():
        failures.append("release.yml: file not found")
        return

    text = RELEASE_YML.read_text(encoding="utf-8").replace("\r\n", "\n")

    stage_match = re.search(
        r"Stage install tree and build release zip.*?(?=\n\s*- name:|\Z)", text, re.DOTALL
    )
    if not stage_match:
        failures.append("release.yml: could not locate the 'Stage install tree and build release zip' step")
        return
    stage_text = stage_match.group(0)

    agents_re = re.compile(r'cp\s+-a\s+agents\b.*"\$STAGE/')
    docs_re = re.compile(r'cp\s+-a\s+docs\b.*"\$STAGE/')
    agents_pos = _find_live_cp_match(agents_re, stage_text)
    docs_pos = _find_live_cp_match(docs_re, stage_text)

    if agents_pos is None:
        failures.append("release.yml: stage step does not copy agents/ into the staging tree")
    if docs_pos is None:
        failures.append("release.yml: stage step does not copy docs/ into the staging tree")

    zip_idx = stage_text.find("zip -r")
    if zip_idx != -1:
        if agents_pos is not None and agents_pos > zip_idx:
            failures.append("release.yml: agents/ copy appears after 'zip -r', must precede it")
        if docs_pos is not None and docs_pos > zip_idx:
            failures.append("release.yml: docs/ copy appears after 'zip -r', must precede it")

    # Note: deliberately no separate "agents/ and docs/ directories exist on
    # disk" assertion here. check_agent_frontmatter's AGENT_FILE.is_file()
    # and check_worked_example's EXAMPLE_FILE.is_file() checks already imply
    # their parent directories exist whenever they pass; a directory-only
    # liveness check here could never fail independently of those (it would
    # only ever fire alongside the file-not-found error), so it was dead
    # weight (test-critic hardening finding #6) and is dropped rather than
    # kept as a duplicate signal.


# ---------------------------------------------------------------------------
# R3 — AGENTS.md contract bullets
# ---------------------------------------------------------------------------

def check_agents_md_contracts(failures):
    if not AGENTS_MD.is_file():
        failures.append(f"{rel(AGENTS_MD)}: file not found")
        return

    text = AGENTS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    bullet_lines = [line for line in text.split("\n") if line.strip().startswith("-")]

    docs_bullet_found = any("docs/" in line and "release artifact" in line for line in bullet_lines)
    if not docs_bullet_found:
        failures.append(f"{rel(AGENTS_MD)}: missing the 'docs/ is a release artifact' contract bullet")

    subagent_literal = "subagents are a Claude-Code-only, convention-discovered feature"
    subagent_bullet_found = any(
        subagent_literal in line
        and ".claude-plugin/plugin.json" in line
        and ".codex-plugin/plugin.json" in line
        for line in bullet_lines
    )
    if not subagent_bullet_found:
        failures.append(
            f"{rel(AGENTS_MD)}: missing the subagent-convention bullet "
            f'(expected literal "{subagent_literal}")'
        )


# ---------------------------------------------------------------------------
# R4 + R5 — worked example
# ---------------------------------------------------------------------------

def parse_headed_code_blocks(text):
    """Map '### <heading>' -> the content of the first fenced code block
    that follows it (before the next '### ' heading or EOF)."""
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


def parse_catalog_table(block_text, failures):
    lines = [l for l in block_text.split("\n") if l.strip() != ""]
    if not lines:
        failures.append(f"{rel(EXAMPLE_FILE)}: e2e/catalog.md block is empty")
        return []

    header = lines[0].strip()
    if header != "| Phrase | Page object | Locator |":
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/catalog.md header line is {header!r}, "
            "expected '| Phrase | Page object | Locator |'"
        )

    if len(lines) < 2:
        failures.append(f"{rel(EXAMPLE_FILE)}: e2e/catalog.md missing separator row")
        return []

    sep_cells = lines[1].strip().strip("|").split("|")
    if len(sep_cells) != 3:
        failures.append(f"{rel(EXAMPLE_FILE)}: e2e/catalog.md separator row does not have 3 cells: {lines[1]!r}")

    rows = []
    for row_line in lines[2:]:
        cells = [c.strip() for c in row_line.strip().strip("|").split("|")]
        if len(cells) != 3:
            failures.append(f"{rel(EXAMPLE_FILE)}: e2e/catalog.md row does not have exactly 3 cells: {row_line!r}")
            continue
        rows.append(tuple(cells))
    return rows


def check_worked_example(failures):
    """R4 + the A3/A6 additions. Returns the parsed heading->block dict
    (possibly empty/partial) so check_example_locator_style (R5) can reuse
    it without re-reading the file."""
    if not EXAMPLE_FILE.is_file():
        failures.append(f"{rel(EXAMPLE_FILE)}: file not found")
        return {}

    try:
        text = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError as exc:
        failures.append(f"{rel(EXAMPLE_FILE)}: could not read file ({exc})")
        return {}

    blocks = parse_headed_code_blocks(text)

    required_headings = ["e2e/pages/TodoPage.ts", "e2e/steps/todo.steps.ts", "e2e/catalog.md"]
    for heading in required_headings:
        if heading not in blocks:
            failures.append(f"{rel(EXAMPLE_FILE)}: missing fenced block for heading '{heading}'")

    pages_block = blocks.get("e2e/pages/TodoPage.ts")
    steps_block = blocks.get("e2e/steps/todo.steps.ts")
    catalog_block = blocks.get("e2e/catalog.md")

    step_phrases = []
    if steps_block is not None:
        step_phrases = re.findall(r"(?:Given|When|Then)\(\s*['\"](.+?)['\"]", steps_block)

    catalog_rows = parse_catalog_table(catalog_block, failures) if catalog_block is not None else []

    # Non-emptiness floors (test-critic hardening finding #2): a catalog
    # block with only header+separator, or a steps block with zero
    # Given/When/Then phrases, makes the forward/backward round-trip loops
    # below iterate zero times — vacuously "passing" while proving nothing.
    # Require a real, non-trivial worked example, and require the row and
    # phrase counts to agree (manual acceptance Step 1's own observable).
    if steps_block is not None and len(step_phrases) < 4:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/steps/todo.steps.ts has only {len(step_phrases)} "
            "Given/When/Then step phrases, expected at least 4"
        )
    if catalog_block is not None and len(catalog_rows) < 4:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/catalog.md has only {len(catalog_rows)} data rows, "
            "expected at least 4"
        )
    if catalog_block is not None and steps_block is not None and len(catalog_rows) != len(step_phrases):
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/catalog.md has {len(catalog_rows)} rows but "
            f"e2e/steps/todo.steps.ts has {len(step_phrases)} step phrases; the catalog row "
            "count must equal the step-definition count"
        )

    if catalog_block is not None and steps_block is not None:
        step_phrase_set = {p.strip() for p in step_phrases}
        catalog_phrase_counts = {}
        phrase_to_locators = {}
        locator_to_phrases = {}
        for phrase, _page_obj, locator in catalog_rows:
            catalog_phrase_counts[phrase] = catalog_phrase_counts.get(phrase, 0) + 1
            phrase_to_locators.setdefault(phrase, set()).add(locator)
            locator_to_phrases.setdefault(locator, set()).add(phrase)

        for phrase in catalog_phrase_counts:
            if phrase not in step_phrase_set:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: catalog phrase {phrase!r} has no matching step phrase "
                    "in e2e/steps/todo.steps.ts"
                )
        for phrase in step_phrase_set:
            count = catalog_phrase_counts.get(phrase, 0)
            if count != 1:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: step phrase {phrase!r} has {count} catalog rows, expected exactly 1"
                )
        for phrase, count in catalog_phrase_counts.items():
            if count > 1:
                failures.append(f"{rel(EXAMPLE_FILE)}: duplicate catalog phrase row {phrase!r}")
        for phrase, locators in phrase_to_locators.items():
            if len(locators) > 1:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: phrase {phrase!r} maps to multiple locators: {sorted(locators)!r}"
                )
        for locator, phrases in locator_to_phrases.items():
            if len(phrases) > 1:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: locator {locator!r} appears under multiple phrases: {sorted(phrases)!r}"
                )

    if catalog_block is not None and pages_block is not None:
        class_match = re.search(r"class\s+(\w+)", pages_block)
        class_name = class_match.group(1) if class_match else None
        for _phrase, page_obj, locator in catalog_rows:
            if locator.strip("`") not in pages_block:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: catalog locator {locator!r} does not appear verbatim "
                    "in e2e/pages/TodoPage.ts"
                )
            if class_name is None or page_obj.strip("`") != class_name:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: catalog row page object {page_obj!r} does not match a "
                    "class defined in e2e/pages/TodoPage.ts"
                )

    if APPLIED_SCOPE_HINT_LINE not in text:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing exact line {APPLIED_SCOPE_HINT_LINE!r}")

    applied_scope_lines = [l for l in text.split("\n") if l.startswith("Applied scope: ")]
    if len(applied_scope_lines) != 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: expected exactly one line with prefix 'Applied scope: ', "
            f"found {len(applied_scope_lines)}"
        )

    if "Locator fallbacks:" not in text:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing 'Locator fallbacks:' heading")

    if PLAYWRIGHT_BDD_NOTICE not in text:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing exact notice {PLAYWRIGHT_BDD_NOTICE!r}")

    return blocks


def check_locator_style_block(block_text, block_label, failures, exempt_spans=()):
    """Forbidden-substring scan for a fenced code block.

    ``exempt_spans`` (only ever passed for the page-object block) marks the
    character ranges of ``this.page.locator(...)`` calls already verified,
    by the disclosure check in ``check_example_locator_style``, to be named
    under the summary's 'Locator fallbacks:' heading. Per L1/L4 a tier-4
    CSS/XPath locator is a permitted last resort *once disclosed* — so
    'page.locator(' and any 'css='/'xpath=' engine prefix that falls inside
    such a span is part of that permitted form, not a violation, and must
    not be flagged here (the substring match still fires for any *other*
    occurrence, e.g. an undisclosed call, since only verified spans are
    exempt). 'page.$' is never part of the tier-4 form -- only
    ``page.locator`` with a CSS/XPath selector is -- so it is excluded from
    the exemption and stays forbidden unconditionally, disclosed or not.
    The steps block is called with no exempt_spans at all: L1/L4's
    last-resort allowance covers the page object's own accessors, not
    inline locator construction inside step definitions, which the steps
    block keeps banned outright regardless of disclosure.
    """
    for forbidden in FORBIDDEN_LOCATOR_SUBSTRINGS:
        idx = 0
        while True:
            pos = block_text.find(forbidden, idx)
            if pos == -1:
                break
            idx = pos + 1
            if forbidden != "page.$" and any(start <= pos < end for start, end in exempt_spans):
                continue
            failures.append(
                f"{rel(EXAMPLE_FILE)}: {block_label} block uses a non-accessibility locator: {forbidden}"
            )

    for match in LOCATOR_METHOD_RE.finditer(block_text):
        method = match.group(1)
        if method not in ACCEPTED_LOCATOR_METHODS:
            # Same disclosed-tier-4 exemption as the substring scan above:
            # a disclosed 'this.page.locator(...)' call's own '.locator('
            # method use is the permitted form, not a disallowed method.
            if method == "locator" and any(start <= match.start() < end for start, end in exempt_spans):
                continue
            failures.append(
                f"{rel(EXAMPLE_FILE)}: {block_label} block uses disallowed locator method '{method}'"
            )

    for arg, end in extract_calls_with_end(block_text, "getByRole"):
        if "name:" in arg:
            continue
        # A name-less getByRole(...) is permitted only when it is a scoping
        # root immediately chained into .filter(...) (plan L3: "a chained or
        # filtered locator rooted at getByRole counts as tier 1") -- the
        # filter, not a name option, is what disambiguates it there. This is
        # the documented Playwright idiom for "one of several same-role
        # siblings, picked by content", e.g.
        # getByRole('listitem').filter({ hasText: '...' }).
        if block_text[end:end + 40].lstrip().startswith(".filter("):
            continue
        failures.append(
            f"{rel(EXAMPLE_FILE)}: {block_label} block has a getByRole(...) call without "
            f"a 'name:' option: getByRole({arg})"
        )


def _extract_this_page_calls(pages_block):
    """Return (method, full_call_text) for every ``this.page.<method>(...)``
    call in ``pages_block``, e.g. ("getByTestId", "this.page.getByTestId('todo-count')").
    A chained/filtered expression such as
    ``this.page.getByRole('listitem').filter(...).getByRole(...)`` is
    captured once, rooted at its leading ``this.page.`` call (plan L3) —
    only the first ``(role|locator|$)(`` immediately preceded by
    ``this.page.`` counts; a later chained call in the same expression is
    not preceded by another literal ``this.page.``, so it is not matched
    again."""
    calls = []
    for match in re.finditer(r"this\.page\.(getBy\w+|locator|\$)\(", pages_block):
        method = match.group(1)
        start = match.start()
        depth = 1
        i = match.end()
        while i < len(pages_block) and depth > 0:
            if pages_block[i] == "(":
                depth += 1
            elif pages_block[i] == ")":
                depth -= 1
            i += 1
        calls.append((method, pages_block[start:i]))
    return calls


def _disclosed_this_page_locator_spans(pages_block, fallbacks_section):
    """Character spans within ``pages_block`` covering a
    ``this.page.locator(...)`` call whose full call text is already present
    verbatim in the summary's disclosed 'Locator fallbacks:' section --
    i.e. a tier-4 CSS/XPath locator that has met L4's disclosure
    requirement and is therefore a permitted last resort under L1, not a
    contract violation. Used by check_locator_style_block to exempt exactly
    those spans (and only those) from the blanket 'page.locator(' /
    'css=' / 'xpath=' substring check -- an undisclosed call's span is
    simply absent from the returned list, so it stays flagged."""
    spans = []
    for match in re.finditer(r"this\.page\.locator\(", pages_block):
        start = match.start()
        depth = 1
        i = match.end()
        while i < len(pages_block) and depth > 0:
            if pages_block[i] == "(":
                depth += 1
            elif pages_block[i] == ")":
                depth -= 1
            i += 1
        call_text = pages_block[start:i]
        if call_text in fallbacks_section:
            spans.append((start, i))
    return spans


def _locator_fallbacks_section(text):
    """The text of the summary's 'Locator fallbacks:' line/paragraph, from
    the heading to the next blank line (or EOF). Empty string if the
    heading is absent (check_worked_example already reports that)."""
    idx = text.find("Locator fallbacks:")
    if idx == -1:
        return ""
    end = text.find("\n\n", idx)
    return text[idx: end if end != -1 else len(text)]


def check_example_locator_style(blocks, failures):
    """R5, strengthened by A5, then corrected by the B2 fix round: A5's
    ``tier1 == total`` assertion assumed every TodoMVC element has a usable
    role+accessible-name pair. That premise is false for the real app's
    per-item toggle checkbox (static ``aria-label="Toggle Todo"``,
    ambiguous without scoping) and its items-left counter (a bare
    ``<span data-testid="todo-count">`` with no ARIA role). The corrected
    assertion: at least 4 accessors, a strict tier-1 majority, and every
    non-tier-1 accessor named in the 'Locator fallbacks:' section."""
    pages_block = blocks.get("e2e/pages/TodoPage.ts")
    steps_block = blocks.get("e2e/steps/todo.steps.ts")

    if pages_block is None:
        # check_worked_example already reported the missing-heading error.
        return

    text = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n") if EXAMPLE_FILE.is_file() else ""
    fallbacks_section = _locator_fallbacks_section(text)
    exempt_spans = _disclosed_this_page_locator_spans(pages_block, fallbacks_section)

    check_locator_style_block(pages_block, "e2e/pages/TodoPage.ts", failures, exempt_spans=exempt_spans)
    if steps_block is not None:
        # No exempt_spans: the steps block's rule is stricter than the
        # page object's (see check_locator_style_block's docstring) -- no
        # inline locator construction at all, disclosed or not.
        check_locator_style_block(steps_block, "e2e/steps/todo.steps.ts", failures)

    if "constructor(private readonly page: Page) {}" not in pages_block:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/pages/TodoPage.ts block missing "
            "'constructor(private readonly page: Page) {}'"
        )

    this_page_calls = _extract_this_page_calls(pages_block)
    total = len(this_page_calls)
    tier1 = sum(1 for method, _call in this_page_calls if method == "getByRole")

    if total < 4:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/pages/TodoPage.ts has only {total} this.page.* locator "
            "accessors, expected at least 4"
        )
    if total > 0 and tier1 * 2 <= total:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: e2e/pages/TodoPage.ts has only {tier1} of {total} locator "
            "accessors at tier 1 (this.page.getByRole(...)); tier-1 must be a strict majority"
        )

    for method, full_call in this_page_calls:
        if method == "getByRole":
            continue
        if full_call not in fallbacks_section:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: e2e/pages/TodoPage.ts non-tier-1 accessor {full_call!r} "
                "is not named in the summary's 'Locator fallbacks:' section"
            )


# ---------------------------------------------------------------------------
# R7 — manifests stay untouched (regression guard)
# ---------------------------------------------------------------------------

def check_manifests_have_no_agents_key(failures):
    for manifest_path in (CLAUDE_MANIFEST, CODEX_MANIFEST):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{rel(manifest_path)}: could not read/parse JSON ({exc})")
            continue
        if isinstance(data, dict) and "agents" in data:
            failures.append(f"{rel(manifest_path)}: manifest must not declare an 'agents' key")


def main():
    failures = []

    agent_text = check_agent_frontmatter(failures)
    check_agent_body_contract(failures, agent_text)
    check_release_staging(failures)
    check_agents_md_contracts(failures)
    blocks = check_worked_example(failures)
    check_example_locator_style(blocks, failures)
    check_manifests_have_no_agents_key(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_agents: OK (page-scanner subagent + worked example)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
