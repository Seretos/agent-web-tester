#!/usr/bin/env python3
"""Validate the release-readiness docs/config package (WP #10): that every
shipped skill's frontmatter is swept (not just ``skills/web-tester/SKILL.md``)
and ``lint.yml`` wires in this script instead of its old single-skill
heredoc; that ``description.md`` carries no scaffold placeholders and claims
no un-shipped "recording" capability; that the two manifest ``description``
strings, ``skills/web-tester/SKILL.md``'s frontmatter ``description``, and
``README.md`` claim no un-shipped "recording" capability either, while still
naming what does ship; that ``README.md`` grew into a real first-scan/
first-scenario/running-the-tests walkthrough with the pinned v0.0.1 honesty
sentence and at least one working link into ``docs/examples/``; that
``AGENTS.md`` documents the four new design decisions this package adds,
without disturbing the two existing bullets it must not touch; that
``skills/web-tester/SKILL.md`` no longer calls scenario authoring "a future
package"/"not-yet-built" and instead positively says it is a separate,
already-shipped skill in this plugin; that ``assets/icon.png`` is still a
well-formed PNG; and that ``release.yml``'s staging + dispatch-payload wiring
for ``assets/``, ``description.md``, ``agents/``, ``docs/`` and ``skills/``
has not regressed.

Usage:
    python .github/scripts/validate_release_docs.py     (local, Windows or *nix)
    python3 .github/scripts/validate_release_docs.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_manifests.py``, ``validate_agents.py``,
``validate_scaffold.py`` and ``validate_author_scenario.py``.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
DESCRIPTION_MD = REPO_ROOT / "description.md"
README_MD = REPO_ROOT / "README.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
WEB_TESTER_SKILL = REPO_ROOT / "skills" / "web-tester" / "SKILL.md"
CLAUDE_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = REPO_ROOT / ".codex-plugin" / "plugin.json"
ICON_PNG = REPO_ROOT / "assets" / "icon.png"
LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# The exact README-only honesty sentence (plan step 5) and the exact
# e2e run command (plan's BR-C), pinned verbatim.
HONESTY_SENTENCE = (
    "v0.0.1: the worked examples under docs/ are hand-written and not yet "
    "executed end-to-end."
)
RUN_COMMAND = "cd e2e && npx bddgen && npx playwright test --config playwright.config.ts"

# BR-D: the four new AGENTS.md design-decision bullets, each a conjunction
# of substrings that must all appear (anywhere in the file -- the plan does
# not pin exact bullet text, only the required vocabulary per bullet).
AGENTS_MD_BULLET_CHECKS = [
    ("playwright-bdd vs plain Playwright Test / Cucumber.js rationale",
     ["playwright-bdd", "Playwright Test", "Cucumber.js"]),
    ("dictionary format lives in the target repo under test",
     ["e2e/catalog.md", "e2e/pages/", "e2e/steps/", "target repo"]),
    ("authoring/execution split -- LLM at authoring time only, CI is zero-LLM",
     ["authoring", "zero", "LLM", "CI"]),
    ("hybrid package, marketplace category stays \"skill\" deliberately",
     ["category", "\"skill\"", "hybrid"]),
]

# Regression pins: bullets AGENTS.md already has today that step 6 of the
# plan says must NOT be touched. Read verbatim from the current file.
AGENTS_MD_EXISTING_LITERALS = [
    "agent-chrome-wrapper",
    "is deliberately not wired to `author-scenario`",
]

# BR-E: the stale phrasing that must be gone, and the literals/heading that
# must survive the reword untouched.
WEB_TESTER_STALE_PHRASES = ["a future package", "not-yet-built", "not yet built"]
WEB_TESTER_SURVIVING_LITERALS = [
    "## Scanning a page: delegate to the page-scanner subagent",
    "scaffold-bdd",
    "page-scanner",
    "e2e/catalog.md",
    "e2e/features/*.feature",
]

# BR-A / BR-B2 / BR-C: description strings, description.md and README.md must
# not claim the un-shipped "records" capability -- one sharp, non-interpretive
# rule: the case-insensitive literal "record" must not appear anywhere in any
# of these documents.
FORBIDDEN_RECORD_LITERAL = "record"

# Release-plumbing regression pins (plan's "Verified state" section: no gap
# found today, add pins so a future edit can't silently remove them).
# Each entry is the artifact target the stage step must ``cp`` into
# "$STAGE/" -- matched with a flag-tolerant regex (see
# _staging_target_regex) rather than one exact "cp -a <target>" literal per
# artifact, so an equivalent staging rewrite (different flag order, `cp -r`
# instead of `cp -a`, etc.) doesn't false-fail while a genuinely dropped
# artifact still does.
RELEASE_YML_STAGING_TARGETS = ["skills/.", "assets", "description.md", "agents", "docs"]
RELEASE_YML_DISPATCH_LITERALS = [
    "${TAG}/assets/icon.png",
    "${TAG}/description.md",
]


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def _read_text(path):
    """Read a file as LF-normalised text, or None if it does not exist or
    cannot be read."""
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").replace("\r\n", "\n")
    except OSError:
        return None


def has_crlf(raw_bytes):
    """True if the raw file bytes contain a CRLF line ending."""
    return b"\r\n" in raw_bytes


def frontmatter_failures(text, expected_name):
    """The sweep's per-skill contract, applied to already LF-normalised
    ``text``: a '---'-delimited frontmatter block is present, 'name:' and
    'description:' are both present and non-empty, and 'name' equals
    ``expected_name`` (the skill's own parent directory name). Returns a
    list of failure strings with no path prefix -- callers own that -- so
    this function is directly unit-testable against fixture text."""
    failures = []
    m = FRONTMATTER_RE.match(text)
    if not m:
        failures.append("missing '---'-delimited frontmatter block")
        return failures

    fm = m.group(1)

    name_match = re.search(r"^name:\s*(.*)$", fm, re.MULTILINE)
    if not name_match or not name_match.group(1).strip():
        failures.append("frontmatter missing non-empty 'name:'")
    else:
        name_value = name_match.group(1).strip()
        if name_value != expected_name:
            failures.append(
                f"frontmatter 'name' is {name_value!r}, expected {expected_name!r} "
                "(must equal the parent directory name)"
            )

    desc_match = re.search(r"^description:\s*(.*)$", fm, re.MULTILINE)
    if not desc_match or not desc_match.group(1).strip():
        failures.append("frontmatter missing non-empty 'description:'")

    return failures


# ---------------------------------------------------------------------------
# BR-A -- lint validates every shipped skill's frontmatter, not just
# web-tester's.
# ---------------------------------------------------------------------------

def check_skill_frontmatter_sweep(failures):
    skill_files = sorted(SKILLS_DIR.glob("*/SKILL.md"))
    # Not a hardcoded absolute minimum (that would go stale the moment a
    # legitimate future tree ships fewer than N skills, or false-pass once it
    # ships more): compare the sweep's own find-count against how many skill
    # directories actually exist under skills/ right now, so the check still
    # catches its real target -- a glob typo silently degrading the sweep to
    # fewer files than the tree actually has -- without pinning a number.
    skill_dirs = [d for d in SKILLS_DIR.glob("*/") if d.is_dir()]
    if len(skill_files) < len(skill_dirs):
        failures.append(
            f"skills/*/SKILL.md sweep: found {len(skill_files)} skill(s) via "
            f"sorted(REPO_ROOT.glob('skills/*/SKILL.md')), but {len(skill_dirs)} "
            "skill director(ies) exist under skills/ -- the sweep must check every "
            "shipped skill's frontmatter, not silently degrade to fewer"
        )

    for path in skill_files:
        dir_name = path.parent.name
        try:
            raw = path.read_bytes()
        except OSError as exc:
            failures.append(f"{rel(path)}: could not read file ({exc})")
            continue

        if has_crlf(raw):
            failures.append(f"{rel(path)}: file contains CRLF line endings (\\r\\n); must be LF-only")

        text = raw.decode("utf-8").replace("\r\n", "\n")
        for msg in frontmatter_failures(text, dir_name):
            failures.append(f"{rel(path)}: {msg}")


# A bash/heredoc opener -- '<<EOF', "<<'EOF'", '<<-EOF', or a bare EOF
# terminator line -- the shape of the old single-skill inline-heredoc step
# this check exists to catch coming back.
_HEREDOC_MARKER_RE = re.compile(r"<<-?['\"]?\w+['\"]?|^\s*EOF\s*$", re.MULTILINE)

_STEPS_KEY_RE = re.compile(r"^([ \t]*)steps:\s*$")
_LIST_ITEM_RE = re.compile(r"^([ \t]*)-\s")

# A step's 'if:' key with a literal 'false' (bare or the '${{ false }}'
# expression form), whitespace around the value tolerated. Only this exact
# literal disqualifies a step -- a real conditional expression, 'if: true',
# or no 'if:' at all all count as live, same as before.
_IF_FALSE_RE = re.compile(
    r"^if:\s*(false|\$\{\{\s*false\s*\}\})\s*$", re.IGNORECASE
)


def _step_blocks(text):
    """Split a GitHub Actions ``steps:`` list into per-step text blocks, each
    starting at its own top-level list-item line and running to the line
    before the next one (or EOF).

    A real workflow step is allowed to start with ANY key -- '- run:',
    '- id:', '- if:', '- uses:', '- name:', '- with:', ... -- 'name:' is
    optional, so boundaries are detected structurally rather than via an
    allowlist of specific key names: find the 'steps:' key, then take the
    indentation of the first '- ' list item that follows it as the
    steps-list's own indentation level (derived from the file itself, never
    hardcoded), and treat every line at exactly that indentation starting
    with '- ' as a new step boundary, regardless of which key follows the
    dash. Lets a check ask "do these two things co-occur within the same
    step" instead of "anywhere in the whole file". Falls back to returning
    the whole text as a single block when no 'steps:' key (or no list item
    under it) is found."""
    lines = text.split("\n")

    steps_line_idx = None
    for i, line in enumerate(lines):
        if _STEPS_KEY_RE.match(line):
            steps_line_idx = i
            break
    if steps_line_idx is None:
        return [text]

    item_indent = None
    for line in lines[steps_line_idx + 1:]:
        m = _LIST_ITEM_RE.match(line)
        if m:
            item_indent = m.group(1)
            break
    if item_indent is None:
        return [text]

    item_start_re = re.compile(r"^" + re.escape(item_indent) + r"-\s")
    starts = [
        i for i, line in enumerate(lines)
        if i > steps_line_idx and item_start_re.match(line)
    ]
    if not starts:
        return [text]

    blocks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return blocks


def _step_disabled(block):
    """True if this step's own block carries a sibling 'if:' key whose value
    is the literal 'false' or '${{ false }}' (whitespace-tolerant) -- a step
    disabled this way never actually executes in CI, so its 'run:' must not
    count as live. Only that literal disqualifies; a real conditional
    expression, 'if: true', or no 'if:' at all are all treated as live, same
    as before. A commented-out 'if: false' line does not disqualify -- it
    is not actually applied."""
    for line in block.split("\n"):
        stripped = re.sub(r"^-\s*", "", line.strip())
        if stripped.startswith("#"):
            continue
        if _IF_FALSE_RE.match(stripped):
            return True
    return False


def _block_run_invokes(block, literal):
    """True if this step's block contains a non-commented 'run:' line
    invoking ``literal``, either on the same line (``run: <cmd>``) or, for a
    block-scalar step (``run: |``/``run: >``), on a following indented line
    belonging to that same block. Unlike a bare substring search, a
    '# run: ...  <literal>' comment line does not count, and neither does a
    commented-out line inside an otherwise-live block."""
    lines = block.split("\n")
    for i, line in enumerate(lines):
        stripped = re.sub(r"^-\s*", "", line.strip())
        if stripped.startswith("#"):
            continue
        if not stripped.startswith("run:"):
            continue
        if literal in stripped:
            return True

        # Block-scalar 'run: |' step: the command lives on the indented
        # line(s) that follow, not on the 'run:' line itself. Scan forward
        # until the indentation dedents back to (or below) the 'run:'
        # line's own indentation -- that marks either a sibling step key
        # or the start of the next step.
        run_indent = len(line) - len(line.lstrip(" "))
        for follow in lines[i + 1:]:
            if follow.strip() == "":
                continue
            follow_indent = len(follow) - len(follow.lstrip(" "))
            if follow_indent <= run_indent:
                break
            follow_stripped = follow.strip()
            if follow_stripped.startswith("#"):
                continue
            if literal in follow_stripped:
                return True
    return False


def _active_run_invokes(text, literal):
    """True if some step, not disqualified by a sibling 'if: false'/
    'if: ${{ false }}' on that same step, has a non-commented 'run:' line
    invoking ``literal`` (see ``_block_run_invokes`` for the per-step
    matching rules). Scans per step block (see ``_step_blocks``) so a
    disabled step's 'run:' does not count, while a different, non-disabled
    step elsewhere in the file can still satisfy the check."""
    for block in _step_blocks(text):
        if _step_disabled(block):
            continue
        if _block_run_invokes(block, literal):
            return True
    return False


def lint_workflow_wiring_failures(text):
    """The pure text -> failure-message-list core of
    ``check_lint_workflow_wiring``, split out (mirroring
    ``frontmatter_failures(text, name)`` above) so it is directly
    unit-testable against fixture text without touching disk. Returns
    failure strings with no path prefix -- the caller owns that."""
    failures = []

    if not _active_run_invokes(text, "validate_release_docs.py"):
        failures.append(
            "no live (non-commented) 'run:' step invokes 'validate_release_docs.py'"
        )

    # The real regression this guards against is the *old hardcoded
    # single-skill heredoc step* coming back, not the path string existing
    # anywhere in the file for an unrelated reason -- so only fire when the
    # literal path co-occurs with a heredoc construct inside the same step.
    for block in _step_blocks(text):
        if "skills/web-tester/SKILL.md" in block and _HEREDOC_MARKER_RE.search(block):
            failures.append(
                "a step still hardcodes 'skills/web-tester/SKILL.md' inside an inline heredoc -- "
                "the old single-skill heredoc step must not come back; frontmatter validation must "
                "cover every shipped skill via validate_release_docs.py instead"
            )
            break

    return failures


def check_lint_workflow_wiring(failures):
    text = _read_text(LINT_YML)
    if text is None:
        failures.append(f"{rel(LINT_YML)}: file not found")
        return

    for msg in lint_workflow_wiring_failures(text):
        failures.append(f"{rel(LINT_YML)}: {msg}")


# A small fixture table exercising frontmatter_failures(text, label) in
# isolation, per the plan's request -- missing block, missing name, missing
# description, empty description, name/dir mismatch, CRLF bytes, and one
# valid control case that must produce zero failures.
FRONTMATTER_FIXTURES = [
    ("missing block", "no frontmatter here at all", "web-tester",
     "missing '---'-delimited frontmatter block"),
    ("missing name", "---\ndescription: hi\n---\n", "web-tester",
     "frontmatter missing non-empty 'name:'"),
    ("missing description", "---\nname: web-tester\n---\n", "web-tester",
     "frontmatter missing non-empty 'description:'"),
    ("empty description", "---\nname: web-tester\ndescription: \n---\n", "web-tester",
     "frontmatter missing non-empty 'description:'"),
    ("name/dir mismatch", "---\nname: other-name\ndescription: hi\n---\n", "web-tester",
     "frontmatter 'name' is 'other-name'"),
]


def check_frontmatter_failures_fixture_table(failures):
    for case_label, text, expected_name, expected_substring in FRONTMATTER_FIXTURES:
        got = frontmatter_failures(text, expected_name)
        if not any(expected_substring in msg for msg in got):
            failures.append(
                f"frontmatter_failures fixture {case_label!r}: expected a failure containing "
                f"{expected_substring!r}, got {got!r}"
            )

    # Valid control case: well-formed frontmatter with matching name produces
    # zero failures.
    control_text = "---\nname: web-tester\ndescription: does things\n---\n\nbody\n"
    control_got = frontmatter_failures(control_text, "web-tester")
    if control_got:
        failures.append(
            f"frontmatter_failures valid-control fixture: expected zero failures, got {control_got!r}"
        )

    # CRLF bytes fixture: has_crlf detects a CRLF frontmatter block, and does
    # not false-positive on a plain LF block.
    if not has_crlf(b"---\r\nname: web-tester\r\ndescription: hi\r\n---\r\n"):
        failures.append("has_crlf fixture: expected True for a CRLF-containing byte string, got False")
    if has_crlf(b"---\nname: web-tester\ndescription: hi\n---\n"):
        failures.append("has_crlf fixture: expected False for an LF-only byte string, got True")


# A fixture table exercising lint_workflow_wiring_failures(text) in
# isolation. Regression coverage for the bug this file's own history caught:
# a bare substring search would let a *commented-out* invocation satisfy the
# "is it wired" check, and would ban the literal path string
# 'skills/web-tester/SKILL.md' from appearing anywhere at all, instead of
# only when the old single-skill inline-heredoc step has actually come back.
LINT_WIRING_FIXTURES = [
    (
        "live run: step wires the validator -- zero failures",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n",
        [],
    ),
    (
        "commented-out run: line must NOT count as wired",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    # run: python3 .github/scripts/validate_release_docs.py\n",
        ["no live (non-commented) 'run:' step invokes 'validate_release_docs.py'"],
    ),
    (
        "SKILL.md path mentioned with no heredoc anywhere -- must NOT fire",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - name: Some other step\n"
        "    run: echo 'see skills/web-tester/SKILL.md for details'\n",
        [],
    ),
    (
        "SKILL.md path + heredoc marker in the SAME step -- must fire",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - name: Old single-skill sweep\n"
        "    run: |\n"
        "      cat <<'EOF' > /tmp/check.py\n"
        "      path = 'skills/web-tester/SKILL.md'\n"
        "      EOF\n",
        [
            "a step still hardcodes 'skills/web-tester/SKILL.md' inside an inline heredoc",
        ],
    ),
    (
        "SKILL.md path in one step, unrelated heredoc in ANOTHER step -- must NOT fire",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - name: Mentions the path\n"
        "    run: echo 'skills/web-tester/SKILL.md'\n"
        "  - name: Unrelated heredoc step\n"
        "    run: |\n"
        "      cat <<'EOF' > /tmp/notes.txt\n"
        "      unrelated content\n"
        "      EOF\n",
        [],
    ),
    (
        "multi-line 'run: |' block with the invocation on a following indented "
        "line -- must be recognized as live-wired",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: |\n"
        "      python3 .github/scripts/validate_release_docs.py\n",
        [],
    ),
    (
        "multi-line 'run: |' block entirely commented out -- must NOT count as wired",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    # run: |\n"
        "    #   python3 .github/scripts/validate_release_docs.py\n",
        ["no live (non-commented) 'run:' step invokes 'validate_release_docs.py'"],
    ),
    (
        "SKILL.md path in one step, NEXT step starts with '- run:' (no 'name:') "
        "and has an unrelated heredoc -- steps must not be merged, must NOT fire "
        "(regression coverage for a step-boundary regex that only recognized "
        "'- name:'/'- uses:' as a step start)",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - name: Mentions the path\n"
        "    run: echo 'skills/web-tester/SKILL.md'\n"
        "  - run: |\n"
        "      cat <<'EOF' > /tmp/notes.txt\n"
        "      unrelated content\n"
        "      EOF\n",
        [],
    ),
    (
        "SKILL.md path + heredoc marker in the SAME step, that step starting "
        "with '- run:' (no 'name:') -- must still fire (proves the boundary "
        "fix isn't overly permissive: a nameless step is still its own block)",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - run: |\n"
        "      cat <<'EOF' > /tmp/check.py\n"
        "      path = 'skills/web-tester/SKILL.md'\n"
        "      EOF\n",
        [
            "a step still hardcodes 'skills/web-tester/SKILL.md' inside an inline heredoc",
        ],
    ),
    (
        "the only 'run:' invoking the validator sits in a step carrying "
        "'if: false', no other live invocation exists -- must NOT count as "
        "wired (a disabled step never executes in CI)",
        "steps:\n"
        "  - name: Validate release docs (disabled)\n"
        "    if: false\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n",
        ["no live (non-commented) 'run:' step invokes 'validate_release_docs.py'"],
    ),
    (
        "the only 'run:' invoking the validator sits in a step carrying "
        "'if: ${{ false }}' -- same disqualification as the bare 'false' form",
        "steps:\n"
        "  - name: Validate release docs (disabled)\n"
        "    if: ${{ false }}\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n",
        ["no live (non-commented) 'run:' step invokes 'validate_release_docs.py'"],
    ),
    (
        "'if: false' disables one step's invocation, but a DIFFERENT, "
        "non-disabled step also invokes the validator -- must count as wired "
        "(disqualification is scoped to the disabled step only)",
        "steps:\n"
        "  - name: Validate release docs (disabled)\n"
        "    if: false\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n"
        "  - name: Validate release docs (live)\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n",
        [],
    ),
    (
        "a real conditional expression on 'if:' (not the literal 'false') "
        "must NOT disqualify the step -- still counts as wired",
        "steps:\n"
        "  - name: Validate release docs\n"
        "    if: github.event_name == 'push'\n"
        "    run: python3 .github/scripts/validate_release_docs.py\n",
        [],
    ),
]


def check_lint_wiring_fixture_table(failures):
    for case_label, text, expected_substrings in LINT_WIRING_FIXTURES:
        got = lint_workflow_wiring_failures(text)
        if not expected_substrings:
            if got:
                failures.append(
                    f"lint_workflow_wiring_failures fixture {case_label!r}: expected zero failures, "
                    f"got {got!r}"
                )
            continue
        for expected_substring in expected_substrings:
            if not any(expected_substring in msg for msg in got):
                failures.append(
                    f"lint_workflow_wiring_failures fixture {case_label!r}: expected a failure "
                    f"containing {expected_substring!r}, got {got!r}"
                )


# ---------------------------------------------------------------------------
# BR-B -- description.md carries no placeholders, lists only shipped
# capabilities.
# ---------------------------------------------------------------------------

def check_description_md(failures):
    text = _read_text(DESCRIPTION_MD)
    if text is None:
        failures.append(f"{rel(DESCRIPTION_MD)}: file not found")
        return

    if "TODO" in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: still contains a 'TODO' marker")

    if "<!--" in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: still contains the placeholder HTML comment")

    heading = "## Key features"
    if heading not in text:
        failures.append(f"{rel(DESCRIPTION_MD)}: missing '{heading}' heading")
    else:
        idx = text.find(heading)
        rest = text[idx + len(heading):]
        next_h2 = re.search(r"^## ", rest, re.MULTILINE)
        span = rest[: next_h2.start()] if next_h2 else rest
        bullets = [line for line in span.split("\n") if line.strip().startswith("- ")]
        if len(bullets) < 3:
            failures.append(
                f"{rel(DESCRIPTION_MD)}: '{heading}' has {len(bullets)} bullet(s), expected >= 3"
            )

    if HONESTY_SENTENCE in text:
        failures.append(
            f"{rel(DESCRIPTION_MD)}: contains the README-only honesty sentence -- that belongs in "
            "README.md, not description.md"
        )

    if FORBIDDEN_RECORD_LITERAL in text.lower():
        failures.append(
            f"{rel(DESCRIPTION_MD)}: contains the case-insensitive literal 'record' -- no un-shipped "
            "recording capability may be claimed"
        )


# ---------------------------------------------------------------------------
# BR-B2 -- manifest description strings claim no capability that does not
# ship.
# ---------------------------------------------------------------------------

def _load_json(path, failures):
    text = _read_text(path)
    if text is None:
        failures.append(f"{rel(path)}: file not found")
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        failures.append(f"{rel(path)}: not valid JSON ({exc})")
        return None


def check_plugin_json_description(failures):
    strings = {}

    claude = _load_json(CLAUDE_MANIFEST, failures)
    if claude is not None:
        strings[f"{rel(CLAUDE_MANIFEST)}#description"] = claude.get("description")

    codex = _load_json(CODEX_MANIFEST, failures)
    if codex is not None:
        strings[f"{rel(CODEX_MANIFEST)}#description"] = codex.get("description")
        interface = codex.get("interface")
        if isinstance(interface, dict):
            strings[f"{rel(CODEX_MANIFEST)}#interface.shortDescription"] = interface.get("shortDescription")
        else:
            failures.append(f"{rel(CODEX_MANIFEST)}: 'interface' key is not an object")

    skill_text = _read_text(WEB_TESTER_SKILL)
    if skill_text is None:
        failures.append(f"{rel(WEB_TESTER_SKILL)}: file not found")
    else:
        m = FRONTMATTER_RE.match(skill_text)
        if not m:
            failures.append(f"{rel(WEB_TESTER_SKILL)}: missing '---'-delimited frontmatter block")
        else:
            desc_match = re.search(r"^description:\s*(.*)$", m.group(1), re.MULTILINE)
            if desc_match and desc_match.group(1).strip():
                strings[f"{rel(WEB_TESTER_SKILL)}#frontmatter.description"] = desc_match.group(1).strip()
            else:
                failures.append(f"{rel(WEB_TESTER_SKILL)}: frontmatter missing non-empty 'description:'")

    for label, value in strings.items():
        if not value:
            failures.append(f"{label}: description string is missing/empty")
            continue
        if FORBIDDEN_RECORD_LITERAL in value.lower():
            failures.append(
                f"{label}: description string contains 'record' (case-insensitive): {value!r}"
            )
        if "playwright-bdd" not in value:
            failures.append(f"{label}: description string does not mention 'playwright-bdd': {value!r}")
        if "Gherkin step catalog" not in value and not ("Gherkin" in value and "catalog" in value):
            failures.append(
                f"{label}: description string does not mention 'Gherkin step catalog' (or 'Gherkin' + "
                f"'catalog'): {value!r}"
            )


# ---------------------------------------------------------------------------
# BR-C -- README is a real walkthrough with honesty note, and claims no
# un-shipped "recording" capability either.
# ---------------------------------------------------------------------------

def check_readme_md(failures):
    text = _read_text(README_MD)
    if text is None:
        failures.append(f"{rel(README_MD)}: file not found")
        return

    for heading in ("## First scan", "## First scenario", "## Running the tests"):
        if heading not in text:
            failures.append(f"{rel(README_MD)}: missing heading {heading!r}")

    if HONESTY_SENTENCE not in text:
        failures.append(f"{rel(README_MD)}: missing the exact honesty sentence {HONESTY_SENTENCE!r}")

    if RUN_COMMAND not in text:
        failures.append(f"{rel(README_MD)}: missing the exact run command {RUN_COMMAND!r}")

    if "no mcp server" in text.lower():
        failures.append(f"{rel(README_MD)}: contains the forbidden phrase 'no MCP server' (case-insensitive)")

    # Same case-insensitive ban check_description_md and
    # check_plugin_json_description already apply to their respective
    # documents: README.md must not claim the un-shipped "records"
    # capability either.
    if FORBIDDEN_RECORD_LITERAL in text.lower():
        failures.append(
            f"{rel(README_MD)}: contains the case-insensitive literal 'record' -- no un-shipped "
            "recording capability may be claimed"
        )

    link_targets = re.findall(r"\]\((docs/examples/[^)\s]+)\)", text)
    if not link_targets:
        failures.append(f"{rel(README_MD)}: no markdown link into docs/examples/ found")
    else:
        for target in link_targets:
            target_path = REPO_ROOT / target
            if not target_path.is_file():
                failures.append(
                    f"{rel(README_MD)}: linked path '{target}' does not resolve on disk"
                )


# ---------------------------------------------------------------------------
# BR-D -- AGENTS.md documents the four missing design decisions, without
# disturbing the bullets already there.
# ---------------------------------------------------------------------------

def check_agents_md_design_bullets(failures):
    text = _read_text(AGENTS_MD)
    if text is None:
        failures.append(f"{rel(AGENTS_MD)}: file not found")
        return

    for label, substrings in AGENTS_MD_BULLET_CHECKS:
        missing = [s for s in substrings if s not in text]
        if missing:
            failures.append(
                f"{rel(AGENTS_MD)}: '{label}' bullet is missing substring(s) {missing!r}"
            )

    for literal in AGENTS_MD_EXISTING_LITERALS:
        if literal not in text:
            failures.append(
                f"{rel(AGENTS_MD)}: regression -- existing literal {literal!r} is missing "
                "(this bullet must not be touched)"
            )


# ---------------------------------------------------------------------------
# BR-E -- skills/web-tester/SKILL.md no longer calls scenario authoring
# unbuilt, and positively states it's a separate shipped skill.
# ---------------------------------------------------------------------------

def check_web_tester_not_stale(failures):
    text = _read_text(WEB_TESTER_SKILL)
    if text is None:
        failures.append(f"{rel(WEB_TESTER_SKILL)}: file not found")
        return

    for phrase in WEB_TESTER_STALE_PHRASES:
        if phrase in text:
            failures.append(f"{rel(WEB_TESTER_SKILL)}: still contains the stale phrase {phrase!r}")

    if "author-scenario" in text:
        failures.append(
            f"{rel(WEB_TESTER_SKILL)}: contains the literal 'author-scenario' -- this skill stays "
            "deliberately unwired, discovery is via its own frontmatter description"
        )

    for literal in WEB_TESTER_SURVIVING_LITERALS:
        if literal not in text:
            failures.append(
                f"{rel(WEB_TESTER_SKILL)}: missing required surviving literal {literal!r}"
            )

    paragraphs = text.split("\n\n")
    if not any("separate skill" in p and "this plugin" in p for p in paragraphs):
        failures.append(
            f"{rel(WEB_TESTER_SKILL)}: no paragraph (delimited by a blank line) contains both "
            "'separate skill' and 'this plugin' -- the positive statement must co-occur, not just "
            "appear anywhere in the file"
        )


# ---------------------------------------------------------------------------
# BR-F -- icon sanity (invariant only; not a replaced-vs-fallback assertion).
# ---------------------------------------------------------------------------

def check_icon_sanity(failures):
    if not ICON_PNG.is_file():
        failures.append(f"{rel(ICON_PNG)}: file not found")
        return
    try:
        data = ICON_PNG.read_bytes()
    except OSError as exc:
        failures.append(f"{rel(ICON_PNG)}: could not read file ({exc})")
        return
    if not data.startswith(PNG_MAGIC):
        failures.append(f"{rel(ICON_PNG)}: does not start with the PNG magic bytes")


# ---------------------------------------------------------------------------
# Release-plumbing regression pins -- expected to already pass; guards
# against a future edit silently dropping the staging/dispatch wiring the
# plan's "Verified state" section found intact.
# ---------------------------------------------------------------------------

def _staging_target_regex(target):
    """A ``cp`` invocation copying ``target`` into the staging tree,
    tolerant of common flag spellings (``-a``, ``-r``, ``-R``, ``-rf``, ...)
    rather than pinned to the exact literal ``cp -a <target>``. An
    equivalent, still-correct rewrite of the stage step (different flag
    order, ``cp -r`` instead of ``cp -a``, etc.) must not false-fail here --
    only a genuinely dropped artifact should."""
    # A trailing '\b' word-boundary assertion breaks for a target ending in
    # a non-word character (e.g. "skills/." ends in '.', and the character
    # that follows it in the workflow -- a space -- is also non-word, so no
    # word/non-word transition exists there for '\b' to match). A lookahead
    # for "whitespace, a quote, or end of string" is what "the target ends
    # here" actually means in this shell-script context, regardless of the
    # target's own trailing character.
    return re.compile(r"cp\s+-\w+\s+" + re.escape(target) + r"(?=[\s\"']|$)")


def check_release_yml_staging(failures):
    text = _read_text(RELEASE_YML)
    if text is None:
        failures.append(f"{rel(RELEASE_YML)}: file not found")
        return

    for target in RELEASE_YML_STAGING_TARGETS:
        if not _staging_target_regex(target).search(text):
            failures.append(
                f"{rel(RELEASE_YML)}: stage step does not appear to copy '{target}' into the "
                f"staging tree (no 'cp -<flags> {target}' found)"
            )

    for literal in RELEASE_YML_DISPATCH_LITERALS:
        if literal not in text:
            failures.append(f"{rel(RELEASE_YML)}: dispatch payload missing {literal!r}")


def main():
    failures = []

    check_skill_frontmatter_sweep(failures)
    check_frontmatter_failures_fixture_table(failures)
    check_lint_workflow_wiring(failures)
    check_lint_wiring_fixture_table(failures)
    check_description_md(failures)
    check_plugin_json_description(failures)
    check_readme_md(failures)
    check_agents_md_design_bullets(failures)
    check_web_tester_not_stale(failures)
    check_icon_sanity(failures)
    check_release_yml_staging(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_release_docs: OK (skill frontmatter sweep, description.md, manifests, README, AGENTS.md, "
          "SKILL.md staleness, icon, release.yml wiring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
