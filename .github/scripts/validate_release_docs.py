#!/usr/bin/env python3
"""Validate the release-readiness docs and marketplace assets bundled by
work package #10 (epic bundling tickets #6 and #7): that every
``skills/*/SKILL.md`` (widened from just ``skills/web-tester/SKILL.md``)
carries valid sibling-convention frontmatter; that ``description.md``'s
``## Key features`` section names all four shipped capabilities instead of
its scaffold ``TODO`` placeholders; that ``README.md`` is a real install +
first-scan + first-scenario + running-the-tests walkthrough instead of the
scaffold stub; that ``AGENTS.md`` carries the missing #6 design-decision
bullets; that ``skills/web-tester/SKILL.md`` no longer implies authoring is
future work (the stale "later authoring skills" phrase); that
``assets/icon.png`` is structurally a valid, release-shippable square PNG
(with a soft, non-blocking freshness advisory pinned to today's content
hash); that ``lint.yml`` is wired to this validator and the old
single-skill frontmatter heredoc step is gone (narrowly scoped -- see
``check_lint_workflow_wiring``'s own docstring for why); and that
``release.yml``'s staging step already copies both ``assets/`` and
``description.md`` into the install tree, and the marketplace dispatch
payload's URL tails resolve (a regression pin on already-correct behaviour,
not a production gap).

Usage:
    python .github/scripts/validate_release_docs.py     (local, Windows or *nix)
    python3 .github/scripts/validate_release_docs.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

This validator reuses ``validate_scaffold.py``'s proven ``_find_live_cp_match``
helper (live-line/comment-skipping search) and its ``PLACEHOLDER_MARKER`` /
``PLACEHOLDER_SURVIVOR_LINES`` constants, loaded via the same ``importlib``
sibling-module pattern ``validate_record.py`` already established, rather
than re-deriving them.

Every check function also runs a battery of self-fixture assertions against
synthetic in-memory data (never a real repo file) immediately before the
real check, proving the check logic itself actually rejects known-bad input
rather than being vacuously true. A self-fixture failure is reported with
the ``self-fixture <BR-id>: ...`` prefix so it reads distinctly from a real
content gap in this repo's tracked files.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_agents.py``, ``validate_scaffold.py``, and
``validate_record.py``. The icon freshness advisory is a soft, non-blocking
``::warning::`` -- it never contributes to the exit code.
"""
import hashlib
import importlib.util
import re
import struct
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"

DESCRIPTION_MD = REPO_ROOT / "description.md"
README_MD = REPO_ROOT / "README.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
WEB_TESTER_FILE = SKILLS_DIR / "web-tester" / "SKILL.md"
LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
ICON_FILE = REPO_ROOT / "assets" / "icon.png"


def _load_sibling_module(name):
    """Load a sibling validator module by file path via importlib, per the
    plan's Approach (2) and the pattern validate_record.py already
    established, rather than re-deriving its proven helpers."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_scaffold = _load_sibling_module("validate_scaffold")
_find_live_cp_match = validate_scaffold._find_live_cp_match

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def _get_section(text, heading):
    """Content between a top-level '## <heading>'-style line (any '#'
    level, matched verbatim) and the next same-or-higher-level heading line,
    or EOF. Returns None if the heading is not present."""
    pattern = re.compile(r"^" + re.escape(heading) + r"\s*$", re.MULTILINE)
    m = pattern.search(text)
    if m is None:
        return None
    line_end = text.find("\n", m.end())
    start = line_end + 1 if line_end != -1 else len(text)
    next_m = re.search(r"^#{1,6} ", text[start:], re.MULTILINE)
    end = start + next_m.start() if next_m else len(text)
    return text[start:end]


def _get_section_from(text, heading_substring):
    """Content after the first line-start occurrence of ``heading_substring``
    -- a line that *begins with* ``heading_substring``, matched via a
    MULTILINE regex anchored to column 0 of the line, not a bare
    ``str.find`` substring search -- up to the next same-or-higher-level
    '#'-heading line, or EOF. Returns None only when no line starts with
    ``heading_substring``. Unlike ``_get_section`` (an exact whole-line
    match), this is a prefix match, so a heading suffix like "## First
    scenario: quickstart" still matches "## First scenario" -- but the
    match must anchor at the start of a line, so a mid-line occurrence of
    the same text earlier in the document (inline prose, a fenced
    code-block example quoting the heading, a future sentence mentioning
    it, etc.) can no longer be mistaken for the real heading. Found by
    review: the previous ``text.find(heading_substring)`` implementation
    had no such anchoring and would silently extract from the wrong
    position in that scenario."""
    pattern = re.compile(r"^" + re.escape(heading_substring), re.MULTILINE)
    m = pattern.search(text)
    if m is None:
        return None
    line_end = text.find("\n", m.end())
    start = line_end + 1 if line_end != -1 else len(text)
    next_m = re.search(r"^#{1,6} ", text[start:], re.MULTILINE)
    end = start + next_m.start() if next_m else len(text)
    return text[start:end]


def _run_section_helper_fixtures(failures):
    """Self-fixtures for ``_get_section`` and ``_get_section_from`` --
    proving each helper's line-anchoring guarantee against synthetic
    in-memory text, per this file's established convention. Neither helper
    had self-fixture coverage before the review finding that added this
    function; both are otherwise the only check helpers in this file
    without one."""
    # --- _get_section (exact whole-line match) ---
    normal = "intro\n## Key features\n- a\n- b\n## Next\nother\n"
    section = _get_section(normal, "## Key features")
    if section != "- a\n- b\n":
        failures.append(
            "self-fixture _get_section: normal heading-then-content case should extract "
            f"'- a\\n- b\\n', got {section!r}"
        )

    early_mention = "This mentions ## Key features inline, not as a heading.\n## Key features\nreal content\n"
    section = _get_section(early_mention, "## Key features")
    if section != "real content\n":
        failures.append(
            "self-fixture _get_section: an earlier non-heading (mid-line) occurrence of the "
            f"heading text must not be mistaken for the real heading, expected 'real content\\n', "
            f"got {section!r}"
        )

    absent = "no heading here at all\njust prose\n"
    if _get_section(absent, "## Key features") is not None:
        failures.append("self-fixture _get_section: a wholly absent heading should return None")

    # --- _get_section_from (line-start prefix match) ---
    normal_from = "intro\n## First scenario: quickstart\ncontent line\n## Next\nmore\n"
    section = _get_section_from(normal_from, "## First scenario")
    if section != "content line\n":
        failures.append(
            "self-fixture _get_section_from: a heading-suffix line ('## First scenario: "
            f"quickstart') should still be matched as a prefix and its content extracted, "
            f"expected 'content line\\n', got {section!r}"
        )

    early_mention_from = (
        "See the section titled ## First scenario in the code sample below.\n"
        "## First scenario\nreal content\n"
    )
    section = _get_section_from(early_mention_from, "## First scenario")
    if section != "real content\n":
        failures.append(
            "self-fixture _get_section_from: an earlier mid-line occurrence of the heading "
            "substring (inline prose quoting it) must not be mistaken for the real heading -- "
            f"expected 'real content\\n', got {section!r}"
        )

    absent_from = "no such heading anywhere\njust prose\n"
    if _get_section_from(absent_from, "## First scenario") is not None:
        failures.append("self-fixture _get_section_from: a wholly absent heading should return None")


def _top_level_bullets(section_text):
    """Top-level '- ' bullet bodies (text after the marker) in a section,
    one per top-level bullet line -- continuation/indented lines are not
    reattached here since none of BR-B's co-occurrence checks need them."""
    return [line.strip()[2:].strip() for line in section_text.split("\n") if line.strip().startswith("- ")]


def _bullet_blocks(text):
    """Group each top-level '- ' bullet with its contiguous continuation
    lines (indented sub-lines, wrapped prose) up to the next top-level '- '
    bullet or EOF -- one entry per bullet, not one entry per physical line.
    Mirrors validate_record.py's _top_level_bullet_blocks."""
    lines = text.split("\n")
    blocks = []
    current = None
    for line in lines:
        if line.startswith("- "):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


# ---------------------------------------------------------------------------
# BR-A -- every skills/*/SKILL.md has valid frontmatter (widened from
# web-tester only)
# ---------------------------------------------------------------------------

def _frontmatter_failures(label, raw_bytes, expected_name=None):
    """Structural + content checks on one SKILL.md's raw bytes. ``label`` is
    used only for failure messages (a real rel path, or a fixture name) --
    this function never touches the filesystem itself, so it is directly
    unit-testable against synthetic bytes. Returns a list of failure
    strings; an empty list means the frontmatter is valid."""
    failures = []
    if not raw_bytes:
        failures.append(f"{label}: file is empty")
        return failures
    if b"\r\n" in raw_bytes:
        failures.append(f"{label}: file contains CRLF line endings (\\r\\n); must be LF-only")
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        failures.append(f"{label}: could not decode as UTF-8 ({exc})")
        return failures
    text = text.replace("\r\n", "\n")

    m = FRONTMATTER_RE.match(text)
    if not m:
        failures.append(f"{label}: missing YAML frontmatter matching '^---\\n(.*?)\\n---\\n'")
        return failures

    fm = m.group(1)
    if not fm.strip():
        failures.append(f"{label}: frontmatter is empty")

    for key in ("name:", "description:"):
        if key not in fm:
            failures.append(f"{label}: frontmatter missing '{key}' key")

    name_match = re.search(r"^name:\s*(\S+)\s*$", fm, re.MULTILINE)
    if name_match:
        name_value = name_match.group(1).strip().strip("\"'")
        if expected_name is not None and name_value != expected_name:
            failures.append(f"{label}: frontmatter 'name' is {name_value!r}, expected {expected_name!r}")
    elif "name:" in fm:
        failures.append(f"{label}: could not parse 'name:' value from frontmatter")

    desc_match = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if desc_match:
        if not desc_match.group(1).strip():
            failures.append(f"{label}: frontmatter 'description' is empty")
    elif "description:" in fm:
        failures.append(f"{label}: could not parse 'description:' value from frontmatter")

    return failures


def _run_frontmatter_fixtures(failures):
    """BR-A self-fixtures: prove _frontmatter_failures actually rejects
    known-bad synthetic input -- glob-widening alone would be vacuous if the
    helper never actually flagged a broken SKILL.md. Synthetic bytes only,
    never a real file."""
    valid = b"---\nname: right-name\ndescription: does a thing\n---\nbody\n"
    msgs = _frontmatter_failures("fixture:valid", valid, expected_name="right-name")
    if msgs:
        failures.append(f"self-fixture BR-A: a structurally valid SKILL.md should pass, but got {msgs!r}")

    if not _frontmatter_failures("fixture:empty", b""):
        failures.append("self-fixture BR-A: an empty file should fail _frontmatter_failures")

    missing_close = b"---\nname: foo\ndescription: bar\n\n# body, no closing marker\n"
    if not _frontmatter_failures("fixture:missing-close", missing_close):
        failures.append(
            "self-fixture BR-A: a SKILL.md missing its closing '---' should fail "
            "_frontmatter_failures, but it reported no failures"
        )

    not_at_byte_zero = b"intro text\n---\nname: x\ndescription: y\n---\n"
    if not _frontmatter_failures("fixture:not-at-byte-0", not_at_byte_zero):
        failures.append(
            "self-fixture BR-A: a frontmatter '---' block not starting at byte 0 should fail "
            "_frontmatter_failures"
        )

    blank_block = b"---\n   \n---\nbody\n"
    if not _frontmatter_failures("fixture:blank-block", blank_block):
        failures.append("self-fixture BR-A: a blank frontmatter block should fail _frontmatter_failures")

    mismatched_name = b"---\nname: wrong-name\ndescription: bar\n---\nbody\n"
    msgs = _frontmatter_failures("fixture:mismatched-name", mismatched_name, expected_name="right-name")
    if not any("expected 'right-name'" in m for m in msgs):
        failures.append(
            "self-fixture BR-A: a SKILL.md whose frontmatter 'name' does not match its parent "
            f"directory should fail with a name-mismatch message, but got {msgs!r}"
        )

    empty_description = b"---\nname: x\ndescription:\n---\nbody\n"
    msgs = _frontmatter_failures("fixture:empty-description", empty_description, expected_name="x")
    if not any("description" in m and "empty" in m for m in msgs):
        failures.append(
            f"self-fixture BR-A: an empty 'description:' value should fail with a description-empty "
            f"message, but got {msgs!r}"
        )

    crlf_file = b"---\r\nname: x\r\ndescription: y\r\n---\r\nbody\r\n"
    msgs = _frontmatter_failures("fixture:crlf", crlf_file, expected_name="x")
    if not any("CRLF" in m for m in msgs):
        failures.append(f"self-fixture BR-A: a CRLF SKILL.md should fail with a CRLF message, but got {msgs!r}")


EXPECTED_SKILL_PATHS = {
    SKILLS_DIR / "author-scenario" / "SKILL.md",
    SKILLS_DIR / "record-scenario" / "SKILL.md",
    SKILLS_DIR / "scaffold-bdd" / "SKILL.md",
    SKILLS_DIR / "web-tester" / "SKILL.md",
}


def check_all_skill_frontmatter(failures):
    discovered = sorted(SKILLS_DIR.glob("*/SKILL.md"))

    missing = EXPECTED_SKILL_PATHS - set(discovered)
    if missing:
        failures.append(
            f"skills/*/SKILL.md glob discovered {[rel(p) for p in discovered]!r}, which is missing "
            f"{sorted(rel(p) for p in missing)!r} -- discovery must be a superset of the four "
            "current skill paths"
        )
    if len(discovered) < 2:
        failures.append(
            f"skills/*/SKILL.md glob discovered only {len(discovered)} file(s) "
            f"({[rel(p) for p in discovered]!r}), expected at least 2 -- the frontmatter sweep "
            "must widen beyond a single skill"
        )
    for path in discovered:
        raw = path.read_bytes()
        for msg in _frontmatter_failures(rel(path), raw, expected_name=path.parent.name):
            failures.append(msg)


# ---------------------------------------------------------------------------
# BR-B -- description.md's Key Features cover all four named capabilities
# ---------------------------------------------------------------------------

DESCRIPTION_KEY_FEATURES_HEADING = "## Key features"
DESCRIPTION_TAGLINE_SUBSTRING = "Assistant for creating E2E web tests"


def check_description_md(failures):
    if not DESCRIPTION_MD.is_file():
        failures.append(f"{rel(DESCRIPTION_MD)}: file not found")
        return
    text = DESCRIPTION_MD.read_text(encoding="utf-8").replace("\r\n", "\n")

    if "TODO" in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: still contains a 'TODO' placeholder bullet")
    if "placeholder" in text.lower():
        failures.append(f"{rel(DESCRIPTION_MD)}: still contains the word 'placeholder'")
    if DESCRIPTION_TAGLINE_SUBSTRING not in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: tagline sentence {DESCRIPTION_TAGLINE_SUBSTRING!r} is missing")

    if DESCRIPTION_KEY_FEATURES_HEADING not in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: missing heading {DESCRIPTION_KEY_FEATURES_HEADING!r}")
        return

    section = _get_section(text, DESCRIPTION_KEY_FEATURES_HEADING)
    if section is None:
        failures.append(
            f"{rel(DESCRIPTION_MD)}: could not extract the {DESCRIPTION_KEY_FEATURES_HEADING!r} section"
        )
        return

    bullets = [b for b in _top_level_bullets(section) if b]
    if len(bullets) < 4:
        failures.append(
            f"{rel(DESCRIPTION_MD)}: {DESCRIPTION_KEY_FEATURES_HEADING!r} has {len(bullets)} non-empty "
            "bullet(s), expected at least 4"
        )

    lower_bullets = [b.lower() for b in bullets]

    def any_co_occur(*terms):
        return any(all(t in b for t in terms) for b in lower_bullets)

    if not any_co_occur("live", "browser"):
        failures.append(
            f"{rel(DESCRIPTION_MD)}: no Key Features bullet co-occurs 'live' and 'browser' "
            "(page-scanner capability)"
        )
    if not any_co_occur("gherkin", "catalog"):
        failures.append(
            f"{rel(DESCRIPTION_MD)}: no Key Features bullet co-occurs 'gherkin' and 'catalog' "
            "(step-catalog capability)"
        )

    record_bullet = any("record" in b or "recording" in b for b in lower_bullets)
    author_bullet = any(
        ("description" in b or "from a description" in b) and "author" in b for b in lower_bullets
    )
    if not record_bullet:
        failures.append(
            f"{rel(DESCRIPTION_MD)}: no Key Features bullet mentions 'record'/'recording' "
            "(record-scenario capability)"
        )
    if not author_bullet:
        failures.append(
            f"{rel(DESCRIPTION_MD)}: no Key Features bullet co-occurs 'description'/'from a "
            "description' with 'author' (author-scenario capability)"
        )

    if not (any_co_occur("playwright-bdd", "determinis") or any_co_occur("playwright-bdd", "zero-llm")):
        failures.append(
            f"{rel(DESCRIPTION_MD)}: no Key Features bullet co-occurs 'playwright-bdd' with "
            "'determinis*' or 'zero-LLM' (deterministic CI-run capability)"
        )


# ---------------------------------------------------------------------------
# BR-C -- README.md is a real walkthrough, not the scaffold stub
# ---------------------------------------------------------------------------

README_REQUIRED_LITERALS = [
    "## Install",
    "/plugin marketplace add Seretos/agent-marketplace",
    "/plugin install agent-web-tester@agent-marketplace",
    "**Prerequisite:** Node.js with `npx` on `PATH`.",
    "## First scan",
    "## First scenario",
    "## Running the tests",
    "npx bddgen",
    "npx playwright test",
    "not yet executed end-to-end",
]

# The exact stale scaffold-author-instruction sentence README.md line 16
# currently carries, plus the stub closing heading/sentence -- read verbatim
# from the file, not paraphrased, per the plan's explicit instruction.
README_STALE_LITERALS = [
    "If the skill teaches Claude how to use a specific MCP, declare that MCP as a dependency in "
    "`.claude-plugin/plugin.json` (`dependencies` array). Claude Code will install/load it automatically.",
    "## What the skill teaches",
    "See `skills/web-tester/SKILL.md` for the full content.",
]


def check_readme_md(failures):
    if not README_MD.is_file():
        failures.append(f"{rel(README_MD)}: file not found")
        return
    text = README_MD.read_text(encoding="utf-8").replace("\r\n", "\n")

    for literal in README_REQUIRED_LITERALS:
        if literal not in text:
            failures.append(f"{rel(README_MD)}: missing required literal {literal!r}")

    for literal in README_STALE_LITERALS:
        if literal in text:
            failures.append(f"{rel(README_MD)}: still contains the stale literal {literal!r}")

    if "no mcp server" in text.lower():
        failures.append(
            f"{rel(README_MD)}: contains the phrase 'no MCP server' (case-insensitive) -- would "
            "regress validate_manifests.py::check_docs"
        )

    # Deliberately NOT `_get_section` here: that helper requires an exact
    # whole-line match (`^heading\s*$`), while the presence check above
    # (and README_REQUIRED_LITERALS in general) is a plain substring
    # match. A heading suffix (e.g. "## First scenario: quickstart") would
    # satisfy the substring presence check but silently fail the exact
    # whole-line regex, returning None and skipping the mention checks
    # below with no failure at all -- caught by test-critic round 1.
    # `_get_section_from` instead does a *prefix* match anchored to the
    # start of a line (not a bare substring search -- see its docstring
    # for the review finding that fixed this), so it still matches a
    # heading suffix like the presence check does, while no longer risking
    # a false match on an earlier mid-line occurrence of the same text.
    section = _get_section_from(text, "## First scenario")
    if section is None:
        failures.append(f"{rel(README_MD)}: could not extract the '## First scenario' section")
    else:
        if "author-scenario" not in section:
            failures.append(f"{rel(README_MD)}: '## First scenario' section does not mention 'author-scenario'")
        if "record-scenario" not in section:
            failures.append(f"{rel(README_MD)}: '## First scenario' section does not mention 'record-scenario'")


# ---------------------------------------------------------------------------
# BR-D -- AGENTS.md carries the missing #6 design-decision bullets
# ---------------------------------------------------------------------------
# BR-D(v) (the OPTIONAL @playwright/mcp-vs-agent-chrome-wrapper rationale
# bullet) is deliberately NOT implemented here: reading AGENTS.md during
# this dispatch found it already carries a full rationale bullet -- "Why
# `@playwright/mcp` and not the sibling `agent-chrome-wrapper` plugin." --
# so the ambiguity the plan flagged is resolved as "rationale already
# present", not "rationale missing". See this developer's change report.

def check_agents_md_decisions(failures):
    if not AGENTS_MD.is_file():
        failures.append(f"{rel(AGENTS_MD)}: file not found")
        return
    text = AGENTS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    blocks = _bullet_blocks(text)

    def any_block_has(*terms):
        return any(all(t in b for t in terms) for b in blocks)

    if not any_block_has("playwright-bdd", "Gherkin", "Cucumber", "Playwright Test"):
        failures.append(
            f"{rel(AGENTS_MD)}: missing a bullet co-occurring 'playwright-bdd', 'Gherkin', "
            "'Cucumber', and 'Playwright Test' (the #6 alternatives-considered decision)"
        )

    if not any_block_has(
        "e2e/pages/", "e2e/steps/", "e2e/catalog.md", "createBdd",
        "| Phrase | Page object | Locator |", "target repo",
    ):
        failures.append(
            f"{rel(AGENTS_MD)}: missing a bullet co-occurring the e2e/ layout paths, 'createBdd', "
            "the catalog header, and 'target repo'"
        )

    zero_llm = any(
        ("zero-LLM" in b or "no LLM" in b) and "CI" in b and "authoring" in b for b in blocks
    )
    if not zero_llm:
        failures.append(
            f"{rel(AGENTS_MD)}: missing a bullet co-occurring 'zero-LLM'/'no LLM' with 'CI' and "
            "'authoring'"
        )

    if not any_block_has("category", '"skill"', "marketplace", "hybrid"):
        failures.append(
            f"{rel(AGENTS_MD)}: missing a bullet co-occurring 'category', '\"skill\"', "
            "'marketplace', and 'hybrid'"
        )


# ---------------------------------------------------------------------------
# BR-E -- lint.yml is wired to the new validator, old heredoc gone
# ---------------------------------------------------------------------------

NEW_VALIDATOR_INVOCATION = "python3 .github/scripts/validate_release_docs.py"
HEREDOC_MARKER = "python3 - <<'EOF'"
OLD_SKILL_PATH_LITERAL = 'open("skills/web-tester/SKILL.md"'

PRE_EXISTING_LIVE_STEPS = [
    "jq empty .claude-plugin/plugin.json",
    "python3 .github/scripts/validate_manifests.py",
    "python3 .github/scripts/validate_agents.py",
    "python3 .github/scripts/validate_scaffold.py",
    "python3 .github/scripts/validate_author_scenario.py",
    "python3 .github/scripts/validate_record.py",
]


def _lint_wiring_failures(lint_text):
    """Narrowly-scoped regression check for lint.yml's wiring.

    Binding orchestrator decision (this is the 3rd attempt at this package;
    the prior two both burned their review-round cap chasing an
    over-general YAML/shell-aware parser inside this exact function): this
    check must stay scoped to only the *exact* regression pattern this
    repo's actual git history contains, never a general heredoc/shell
    parser. Concretely: a live 'python3 - <<'EOF'' step is not itself an
    error (a future step could legitimately use a heredoc for something
    else); the only thing that must go away is *this repo's specific*
    heredoc, identified by the co-occurrence of that live heredoc marker
    AND a live 'open("skills/web-tester/SKILL.md"' line -- the two literals
    the old step actually contains together. A standalone heredoc marker
    with no SKILL.md-path literal must NOT trip this."""
    failures = []
    if _find_live_cp_match(re.compile(re.escape(NEW_VALIDATOR_INVOCATION)), lint_text) is None:
        failures.append(
            f"no *live* step runs {NEW_VALIDATOR_INVOCATION!r} (a commented-out line does not count)"
        )

    heredoc_present = _find_live_cp_match(re.compile(re.escape(HEREDOC_MARKER)), lint_text) is not None
    skill_path_present = _find_live_cp_match(re.compile(re.escape(OLD_SKILL_PATH_LITERAL)), lint_text) is not None
    if heredoc_present and skill_path_present:
        failures.append(
            "the old single-skill frontmatter heredoc step (a live 'python3 - <<'EOF'' line "
            "co-occurring with a live 'open(\"skills/web-tester/SKILL.md\"' line) is still "
            "present -- it must be replaced by the new validator invocation"
        )
    return failures


def _run_lint_wiring_fixtures(failures):
    """BR-E self-fixtures, per the plan: live passes; commented fails;
    absent fails; both heredoc literals co-occurring live fails; a heredoc
    marker alone (no SKILL.md-path literal) must NOT fail."""
    live_new = f"steps:\n  - run: {NEW_VALIDATOR_INVOCATION}\n"
    msgs = _lint_wiring_failures(live_new)
    if msgs:
        failures.append(
            f"self-fixture BR-E: a live invocation of the new validator alone should pass, but "
            f"got {msgs!r}"
        )

    commented = f"steps:\n  # run: {NEW_VALIDATOR_INVOCATION}\n"
    if not _lint_wiring_failures(commented):
        failures.append(
            "self-fixture BR-E: a commented-out invocation of the new validator should still "
            "fail (no live step runs it)"
        )

    absent = "steps:\n  - run: echo nothing\n"
    if not _lint_wiring_failures(absent):
        failures.append("self-fixture BR-E: no invocation at all should fail")

    both_live = (
        "steps:\n  - run: |\n"
        f"      {HEREDOC_MARKER}\n"
        f'      text = open("skills/web-tester/SKILL.md", encoding="utf-8").read()\n'
        f"  - run: {NEW_VALIDATOR_INVOCATION}\n"
    )
    msgs = _lint_wiring_failures(both_live)
    if not any("old single-skill frontmatter heredoc" in m for m in msgs):
        failures.append(
            "self-fixture BR-E: a live heredoc marker co-occurring with a live "
            "'open(\"skills/web-tester/SKILL.md\"' line should fail with the old-heredoc "
            f"message, but got {msgs!r}"
        )

    heredoc_alone = (
        "steps:\n  - run: |\n"
        f"      {HEREDOC_MARKER}\n"
        "      print('unrelated heredoc, no SKILL.md path here')\n"
        f"  - run: {NEW_VALIDATOR_INVOCATION}\n"
    )
    msgs = _lint_wiring_failures(heredoc_alone)
    if any("old single-skill frontmatter heredoc" in m for m in msgs):
        failures.append(
            "self-fixture BR-E: a live heredoc marker with NO SKILL.md-path literal must NOT "
            f"trip the old-heredoc check, but it did: {msgs!r}"
        )


def check_lint_workflow_wiring(failures):
    if not LINT_YML.is_file():
        failures.append(f"{rel(LINT_YML)}: file not found")
        return
    text = LINT_YML.read_text(encoding="utf-8").replace("\r\n", "\n")

    for msg in _lint_wiring_failures(text):
        failures.append(f"{rel(LINT_YML)}: {msg}")

    for existing in PRE_EXISTING_LIVE_STEPS:
        if _find_live_cp_match(re.compile(re.escape(existing)), text) is None:
            failures.append(f"{rel(LINT_YML)}: pre-existing live step {existing!r} is missing")


# ---------------------------------------------------------------------------
# BR-G -- skills/web-tester/SKILL.md no longer implies authoring is future
# work
# ---------------------------------------------------------------------------

STALE_FUTURE_MARKERS = ["later authoring skills", "not-yet-built", "not yet built", "coming soon"]

# Positive assertion (preferred over a pure blacklist per test-critic round
# 1): the specific present-tense, name-free replacement text the plan
# prescribes for the stale "(and later authoring skills)" phrase must
# actually be present, proving the intended fix landed rather than just
# proving the old wording is gone.
WEB_TESTER_REPLACEMENT_TEXT = "(and the scenario-authoring skills)"

WEB_TESTER_REQUIRED_HEADINGS = [
    "## Scanning a page: delegate to the page-scanner subagent",
    "## Making the catalog runnable: delegate to scaffold-bdd",
    "## Recording a scenario: delegate to record-scenario",
]

WEB_TESTER_REQUIRED_MENTIONS = ["scaffold-bdd", "page-scanner", "e2e/catalog.md", "record-scenario"]


def check_web_tester_currency(failures):
    if not WEB_TESTER_FILE.is_file():
        failures.append(f"{rel(WEB_TESTER_FILE)}: file not found")
        return
    text = WEB_TESTER_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    lower = text.lower()

    for marker in STALE_FUTURE_MARKERS:
        if marker.lower() in lower:
            failures.append(f"{rel(WEB_TESTER_FILE)}: still contains the stale future-tense marker {marker!r}")

    if WEB_TESTER_REPLACEMENT_TEXT not in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: missing the present-tense replacement text "
            f"{WEB_TESTER_REPLACEMENT_TEXT!r} -- a blacklist miss alone does not prove the "
            "intended fix landed"
        )

    # validate_author_scenario.py::check_web_tester_untouched already fails
    # the build if this literal appears; restated here as this validator's
    # own currency check so a regression shows up under this file's own
    # heading too, not only in a sibling script's output.
    if "author-scenario" in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: contains the literal 'author-scenario' -- this file must "
            "stay name-free per validate_author_scenario.py::check_web_tester_untouched"
        )

    for heading in WEB_TESTER_REQUIRED_HEADINGS:
        if heading not in text:
            failures.append(f"{rel(WEB_TESTER_FILE)}: missing delegation heading {heading!r}")

    for mention in WEB_TESTER_REQUIRED_MENTIONS:
        if mention not in text:
            failures.append(f"{rel(WEB_TESTER_FILE)}: does not mention {mention!r}")

    if validate_scaffold.PLACEHOLDER_MARKER in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: still contains the placeholder body marker "
            f"{validate_scaffold.PLACEHOLDER_MARKER!r}"
        )
    for survivor in validate_scaffold.PLACEHOLDER_SURVIVOR_LINES:
        if survivor in text:
            failures.append(f"{rel(WEB_TESTER_FILE)}: still contains placeholder scaffolding text {survivor!r}")


# ---------------------------------------------------------------------------
# BR-F -- assets/icon.png is valid, release-shippable (structural tier)
# ---------------------------------------------------------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_IHDR_CHUNK_TYPE = b"IHDR"
# Length (4 bytes, big-endian) + chunk type (4 bytes) that immediately follow
# the 8-byte PNG signature in a well-formed file, per the PNG spec -- IHDR is
# always the first chunk and is always 13 bytes long.
_VALID_IHDR_PREFIX = struct.pack(">I", 13) + PNG_IHDR_CHUNK_TYPE
ICON_MIN_SIZE_BYTES = 1024
ICON_MAX_SIZE_BYTES = 5 * 1024 * 1024
ICON_MIN_WIDTH = 256

# Computed now (this dispatch) with hashlib from the actual current
# assets/icon.png bytes -- hardcoded, not symbolic. A soft freshness
# advisory fires whenever the committed icon still hashes to this exact
# baseline, which is deliberately true on this first run (the icon has not
# been touched by this package yet); once the implement phase replaces it
# with real artwork the hash changes and the advisory stops firing.
BASELINE_ICON_SHA256 = "e96b8040be2e6ce21545042b678ce4b365c8184f811bc5d376970def12efe182"


def _icon_structural_failures(label, data):
    failures = []
    if data[:8] != PNG_MAGIC:
        failures.append(f"{label}: not a PNG file (bad magic bytes)")
        return failures
    if len(data) < 24:
        failures.append(f"{label}: too short to contain a PNG IHDR chunk")
        return failures
    if data[12:16] != PNG_IHDR_CHUNK_TYPE:
        failures.append(
            f"{label}: bytes 12:16 are {data[12:16]!r}, not the PNG IHDR chunk type {PNG_IHDR_CHUNK_TYPE!r}"
        )
        return failures

    width, height = struct.unpack(">II", data[16:24])
    if width != height:
        failures.append(f"{label}: image is {width}x{height}, not square")
    if width < ICON_MIN_WIDTH:
        failures.append(f"{label}: image width {width}px is below the minimum {ICON_MIN_WIDTH}px")

    size = len(data)
    if not (ICON_MIN_SIZE_BYTES <= size <= ICON_MAX_SIZE_BYTES):
        failures.append(
            f"{label}: file size {size} bytes is outside the {ICON_MIN_SIZE_BYTES}-"
            f"{ICON_MAX_SIZE_BYTES} byte range"
        )
    return failures


def _run_icon_fixtures(failures):
    valid_ihdr = struct.pack(">II", 512, 512)

    good = PNG_MAGIC + _VALID_IHDR_PREFIX + valid_ihdr + b"\x00" * 2000
    msgs = _icon_structural_failures("fixture:good", good)
    if msgs:
        failures.append(f"self-fixture BR-F: a well-formed 512x512 PNG-shaped blob should pass, got {msgs!r}")

    bad_magic = b"NOTPNGMAGIC" + _VALID_IHDR_PREFIX + valid_ihdr + b"\x00" * 2000
    if not _icon_structural_failures("fixture:bad-magic", bad_magic):
        failures.append("self-fixture BR-F: non-PNG magic bytes should fail")

    too_short = PNG_MAGIC + b"\x00" * 4
    if not _icon_structural_failures("fixture:too-short", too_short):
        failures.append("self-fixture BR-F: data too short to contain an IHDR chunk should fail")

    bad_ihdr_type = PNG_MAGIC + b"\x00" * 4 + b"XXXX" + valid_ihdr + b"\x00" * 2000
    msgs = _icon_structural_failures("fixture:bad-ihdr-type", bad_ihdr_type)
    if not any("IHDR chunk type" in m for m in msgs):
        failures.append(
            f"self-fixture BR-F: bytes 12:16 not equal to b'IHDR' should fail with an IHDR-chunk-type "
            f"message, but got {msgs!r}"
        )

    non_square = PNG_MAGIC + _VALID_IHDR_PREFIX + struct.pack(">II", 512, 256) + b"\x00" * 2000
    if not _icon_structural_failures("fixture:non-square", non_square):
        failures.append("self-fixture BR-F: a non-square image should fail")

    too_narrow = PNG_MAGIC + _VALID_IHDR_PREFIX + struct.pack(">II", 128, 128) + b"\x00" * 2000
    if not _icon_structural_failures("fixture:too-narrow", too_narrow):
        failures.append("self-fixture BR-F: width < 256px should fail")

    too_small_filesize = PNG_MAGIC + _VALID_IHDR_PREFIX + valid_ihdr  # 24 bytes total, well under 1KB
    if not _icon_structural_failures("fixture:too-small-filesize", too_small_filesize):
        failures.append("self-fixture BR-F: a structurally valid but sub-1KB file should fail on size range")

    too_big = PNG_MAGIC + _VALID_IHDR_PREFIX + valid_ihdr + b"\x00" * (ICON_MAX_SIZE_BYTES + 1)
    if not _icon_structural_failures("fixture:too-big", too_big):
        failures.append("self-fixture BR-F: a file over 5MB should fail on size range")


def check_icon(failures):
    if not ICON_FILE.is_file():
        failures.append(f"{rel(ICON_FILE)}: file not found")
        return
    data = ICON_FILE.read_bytes()
    for msg in _icon_structural_failures(rel(ICON_FILE), data):
        failures.append(msg)

    digest = hashlib.sha256(data).hexdigest()
    if digest == BASELINE_ICON_SHA256:
        print(
            f"::warning::{rel(ICON_FILE)}: content hash matches the baseline "
            f"({BASELINE_ICON_SHA256}) pinned when this validator was written -- confirm this is "
            "genuinely refreshed release artwork (ticket #7), not still the scaffold default, "
            "before cutting v0.0.1"
        )


# ---------------------------------------------------------------------------
# BR-H -- release.yml stages assets/ and description.md (regression pin,
# expected GREEN immediately -- real, already-correct behaviour)
# ---------------------------------------------------------------------------

def check_release_staging_marketplace_artifacts(failures):
    if not RELEASE_YML.is_file():
        failures.append(f"{rel(RELEASE_YML)}: file not found")
        return
    text = RELEASE_YML.read_text(encoding="utf-8").replace("\r\n", "\n")

    stage_match = re.search(
        r"Stage install tree and build release zip.*?(?=\n\s*- name:|\Z)", text, re.DOTALL
    )
    if not stage_match:
        failures.append(
            f"{rel(RELEASE_YML)}: could not locate the 'Stage install tree and build release zip' step"
        )
        return
    stage_text = stage_match.group(0)

    assets_re = re.compile(r'cp\s+-a\s+assets\b.*"?\$STAGE/')
    if _find_live_cp_match(assets_re, stage_text) is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy assets/ into the staging tree")

    desc_re = re.compile(r'cp\s+-a\s+description\.md\b.*"?\$STAGE/')
    if _find_live_cp_match(desc_re, stage_text) is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy description.md into the staging tree")

    # Redundant with validate_agents.py's check_release_staging (which already
    # pins agents/ and docs/), added purely to make this validator
    # self-contained for the release-staging story rather than to duplicate
    # that check's authority -- Codex review round 2 flagged docs/ staging as
    # unasserted here specifically.
    docs_re = re.compile(r'cp\s+-a\s+docs\b.*"?\$STAGE/')
    if _find_live_cp_match(docs_re, stage_text) is None:
        failures.append(f"{rel(RELEASE_YML)}: stage step does not copy docs/ into the staging tree")

    dispatch_match = re.search(
        r"Dispatch to agent-marketplace.*?(?=\n\s*- name:|\Z)", text, re.DOTALL
    )
    if not dispatch_match:
        failures.append(
            f"{rel(RELEASE_YML)}: could not locate the 'Dispatch to agent-marketplace' step"
        )
        return
    dispatch_text = dispatch_match.group(0)

    for tail in ("/assets/icon.png", "/description.md"):
        if _find_live_cp_match(re.compile(re.escape(tail)), dispatch_text) is None:
            failures.append(
                f"{rel(RELEASE_YML)}: no *live* line in the dispatch step carries the URL tail "
                f"{tail!r} (a commented-out line does not count)"
            )


def main():
    failures = []

    _run_frontmatter_fixtures(failures)
    check_all_skill_frontmatter(failures)

    _run_section_helper_fixtures(failures)
    check_description_md(failures)
    check_readme_md(failures)
    check_agents_md_decisions(failures)

    _run_lint_wiring_fixtures(failures)
    check_lint_workflow_wiring(failures)

    check_web_tester_currency(failures)

    _run_icon_fixtures(failures)
    check_icon(failures)

    check_release_staging_marketplace_artifacts(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_release_docs: OK (release docs + skill frontmatter sweep + icon + release staging)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
