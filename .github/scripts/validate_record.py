#!/usr/bin/env python3
"""Validate the `record-scenario` skill package (WP #5): that
``skills/record-scenario/SKILL.md`` exists with sibling-convention
frontmatter and carries its eight pinned ``## Hard rule:`` sections
(recording session, meaningful actions, catalog matching, file ownership,
proposed Then steps, secrets, confirmation gates, verification run); that
the worked example at ``docs/examples/record-scenario-run.md`` round-trips
against itself and against the already-merged
``docs/examples/todomvc-scan.md`` (reuse is genuinely reuse, not a
re-mint); that the N1-N5 pruning rules are mechanically re-derivable in
Python from the example's deliberately noisy raw recording block and match
the feature block's ``When`` lines exactly; that no literal secret reaches
an emitted artifact; that the two-stage verification run (unfiltered
``bddgen`` compile, then a gated/scoped ``playwright test`` replay) is
pinned and reported with the exact ``Verify: `` shapes; that the F7/F8
dedupe rules exist for both directions of drift; that ``skills/web-tester/
SKILL.md`` routes to the new skill without gutting #2/#3's routing; that
``lint.yml`` wires this validator in; and that release staging, the
no-committed-``e2e/`` invariant, and the five new ``AGENTS.md`` bullets all
hold, alongside a subprocess regression run of ``validate_agents.py`` and
``validate_scaffold.py``.

Usage:
    python .github/scripts/validate_record.py     (local, Windows or *nix)
    python3 .github/scripts/validate_record.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

This validator deliberately reuses ``validate_scaffold.py``'s proven helpers
(``derive_keyword``, ``get_section_spans``, ``parse_headed_code_blocks``,
``parse_catalog_table``, ``_find_live_cp_match``, plus its
``check_release_staging_skills``/``check_no_committed_e2e_tree`` checks and
its ``PAGE_SCANNER_SECTION_HEADING`` constant) by loading that sibling
module via ``importlib``, so G2's keyword mapping and the release/e2e-tree
invariants cannot drift between the two validators.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::``, matching the style already
used by ``validate_agents.py`` and ``validate_scaffold.py``.
"""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

SKILL_FILE = REPO_ROOT / "skills" / "record-scenario" / "SKILL.md"
WEB_TESTER_FILE = REPO_ROOT / "skills" / "web-tester" / "SKILL.md"
EXAMPLE_FILE = REPO_ROOT / "docs" / "examples" / "record-scenario-run.md"
TODOMVC_FILE = REPO_ROOT / "docs" / "examples" / "todomvc-scan.md"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
VALIDATE_AGENTS_SCRIPT = SCRIPTS_DIR / "validate_agents.py"
VALIDATE_SCAFFOLD_SCRIPT = SCRIPTS_DIR / "validate_scaffold.py"


def _load_sibling_module(name):
    """Load a sibling validator module by file path via importlib, per the
    plan's Approach D, rather than re-deriving its proven helpers."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_scaffold = _load_sibling_module("validate_scaffold")

derive_keyword = validate_scaffold.derive_keyword
get_section_spans = validate_scaffold.get_section_spans
parse_headed_code_blocks = validate_scaffold.parse_headed_code_blocks
parse_catalog_table = validate_scaffold.parse_catalog_table
_find_live_cp_match = validate_scaffold._find_live_cp_match

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

HARD_RULE_HEADINGS = [
    "## Hard rule: recording session",
    "## Hard rule: meaningful actions",
    "## Hard rule: catalog matching",
    "## Hard rule: file ownership",
    "## Hard rule: proposed Then steps",
    "## Hard rule: secrets",
    "## Hard rule: confirmation gates",
    "## Hard rule: verification run",
]

# Pinned-literal inventory (plan "Pinned-literal inventory (M6)"): every
# byte-pinned string appears exactly once, in one form, keyed by the
# Hard-rule span it must live inside. Text (including the EM DASH "—")
# copied verbatim from the plan.
PINNED_LITERALS = {
    "## Hard rule: recording session": [
        ("R2", "cd e2e && npx playwright codegen --target playwright-test --browser chromium "
               "--output .recordings/"),
        ("R3", "Recording: EMPTY — nothing captured at e2e/.recordings/"),
    ],
    "## Hard rule: proposed Then steps": [
        ("T2", "unverified guess"),
    ],
    "## Hard rule: secrets": [
        ("S2", "Missing environment variable "),
        ("S3", "Required environment variables:"),
    ],
    "## Hard rule: confirmation gates": [
        ("U1-A1", "reuse (A1)"),
        ("U1-A2", "reuse (A2)"),
        ("U1-A3", "reuse (A3)"),
        ("U1-mint", "mint"),
        ("U2", "Gate (2) runs after the files are written; it gates running, not writing."),
    ],
    "## Hard rule: verification run": [
        ("V1", "Verification runs in two stages: stage 1 runs npx bddgen unfiltered over the "
               "whole e2e/ tree, stage 2 runs npx playwright test scoped to the generated spec "
               "after the replay gate."),
        ("V2-PASS", "Verify: COMPILE PASS — "),
        ("V2-FAIL", "Verify: COMPILE FAIL — "),
        ("V3-a", "Run the suite unfiltered never."),
        ("V3-b", "Never target another feature file."),
        ("V4", "The recorded actions will be performed again against the real app."),
        ("V5-PASS", "Verify: PASS — "),
        ("V5-FAIL", "Verify: FAIL — "),
        ("V5-SKIPPED", "Verify: SKIPPED — replay declined at the verification gate"),
    ],
}

# The summary-checklist vocabulary (plan's "Summary checklist" paragraph),
# checked over the whole document body rather than one section span.
SUMMARY_VOCABULARY = [
    "Recording: ",
    "Pruned: ",
    "Reused (catalog): ",
    "Minted: ",
    "Removed (deduped): ",
    "Required environment variables:",
    "Created:",
    "Updated (appended ",
    "Kept (already present):",
]

# S1's case-insensitive secret-field detector token list, pinned verbatim
# (plan line 36) -- Behaviour 4's additional coverage.
S1_TOKEN_LIST = "password|passwd|pwd|secret|token|api key|apikey|otp|cvv|pin|card number"

SECRET_STEP_PHRASE_RE = re.compile(r"I fill in the .* with the secret \{string\}")
ENV_VAR_ARG_RE = re.compile(r'"(E2E_[A-Z0-9_]+)"')

# Recording-block action classification (Behaviour 3). One statement per
# line, in codegen's own shape: `await page.<chain>.<method>(<args>);` for
# an interaction, `await page.goto('<url>')` for navigation, `await
# page.waitForTimeout(<ms>)` / `await page.mouse.wheel(...)` for the two
# forms of unconditional noise, `await expect(...)` for a recorded
# assertion (handled by T-rules elsewhere, excluded from N-pruning).
ACTION_METHOD_RE = re.compile(
    r"\.(click|fill|pressSequentially|press|check|uncheck|hover|scrollIntoViewIfNeeded)"
    r"\(([^;]*)\);?\s*$"
)
GOTO_RE = re.compile(r"^page\.goto\(\s*['\"]([^'\"]+)['\"]")
WAIT_RE = re.compile(r"^page\.waitForTimeout\(")
WHEEL_RE = re.compile(r"^page\.mouse\.wheel\(")
NOISE_TYPES = {"hover", "scroll", "waitForTimeout", "unknown"}


def rel(path):
    """Path relative to the repo root, posix-style, for failure messages."""
    return path.relative_to(REPO_ROOT).as_posix()


def _feature_step_lines(feature_block):
    """Lines of a .feature block (stripped) that open with an explicit
    Given/When/Then/And/But keyword."""
    out = []
    for line in (feature_block or "").split("\n"):
        stripped = line.strip()
        for kw in ("Given ", "When ", "Then ", "And ", "But "):
            if stripped.startswith(kw):
                out.append(stripped)
                break
    return out


def _step_registrations(steps_block):
    """(keyword, phrase) pairs for every Given/When/Then(...) call in a
    steps block."""
    return re.findall(r"(Given|When|Then)\(\s*['\"](.*?)['\"]", steps_block or "")


def _phrase_matches_feature_line(catalog_phrase, feature_phrase):
    """G3: a catalog/step phrase's `{string}` placeholder is a Cucumber
    expression compiled to `"([^"]*)"`; a `.feature` scenario line carries a
    *concrete* quoted value there instead of the literal placeholder text.
    True if `feature_phrase` matches `catalog_phrase` with each `{string}`
    substituted for that pattern (or, for a non-parametrized phrase, if the
    two are byte-identical)."""
    if catalog_phrase == feature_phrase:
        return True
    if "{string}" not in catalog_phrase:
        return False
    pattern = r'"([^"]*)"'.join(re.escape(part) for part in catalog_phrase.split("{string}"))
    return re.match(r"^" + pattern + r"$", feature_phrase) is not None


def _resolve_catalog_phrase(feature_phrase, phrase_pool):
    """Resolve a `.feature` scenario line's literal phrase text back to the
    canonical (still-parametrized) catalog/step phrase it was derived from,
    so downstream comparisons don't require byte-for-byte equality between a
    `.feature` line (concrete quoted value) and a catalog/step phrase
    (`{string}` placeholder). Returns `feature_phrase` unchanged if it is
    already an exact match in `phrase_pool`, or if no parametrized candidate
    in the pool matches it."""
    if feature_phrase in phrase_pool:
        return feature_phrase
    for candidate in phrase_pool:
        if "{string}" in candidate and _phrase_matches_feature_line(candidate, feature_phrase):
            return candidate
    return feature_phrase


def _find_block(blocks, prefix=None, suffix=None, exact=None):
    """Find a '### <heading>' -> content entry by exact heading, or by
    prefix+suffix when the heading embeds a variable slug (e.g.
    'e2e/.recordings/<slug>.spec.ts')."""
    for heading, content in blocks.items():
        if exact is not None:
            if heading == exact:
                return heading, content
            continue
        if prefix is not None and not heading.startswith(prefix):
            continue
        if suffix is not None and not heading.endswith(suffix):
            continue
        return heading, content
    return None, None


def _get_markdown_section(text, heading):
    """F2/F3: content between a top-level '## <heading>' line and the next
    top-level '## ' heading (or EOF), exclusive of the heading line itself.
    Returns None if the heading is not present. Used to scope a check to one
    named section of the worked example instead of the whole document, so a
    literal quoted elsewhere in the file cannot satisfy a check that is
    supposed to require the literal live inside a specific block."""
    pattern = re.compile(r"^" + re.escape(heading) + r"\s*$", re.MULTILINE)
    m = pattern.search(text)
    if m is None:
        return None
    line_end = text.find("\n", m.end())
    start = line_end + 1 if line_end != -1 else len(text)
    next_m = re.search(r"^## ", text[start:], re.MULTILINE)
    end = start + next_m.start() if next_m else len(text)
    return text[start:end]


def _normalize_locator(s):
    s = (s or "").strip()
    if s.startswith("this."):
        s = s[len("this."):]
    return re.sub(r"\s+", " ", s)


def parse_recording_actions(recording_text):
    """Classify each statement line of a raw codegen recording block into
    an ordered action list (Behaviour 3: 'regex classifying goto / click /
    fill / press / check / hover / scroll / waitForTimeout / expect')."""
    actions = []
    for raw_line in (recording_text or "").split("\n"):
        line = raw_line.strip()
        if not line.startswith("await "):
            continue
        stmt = line[len("await "):]
        if stmt.startswith("expect("):
            actions.append({"type": "expect", "raw": raw_line})
            continue
        if not stmt.startswith("page."):
            actions.append({"type": "unknown", "raw": raw_line})
            continue
        rest = stmt[len("page."):]
        goto_m = GOTO_RE.match(stmt)
        if goto_m:
            actions.append({"type": "goto", "url": goto_m.group(1), "raw": raw_line})
            continue
        if WAIT_RE.match(stmt):
            actions.append({"type": "waitForTimeout", "raw": raw_line})
            continue
        if WHEEL_RE.match(stmt):
            actions.append({"type": "scroll", "raw": raw_line})
            continue
        m = ACTION_METHOD_RE.search(rest)
        if not m:
            actions.append({"type": "unknown", "raw": raw_line})
            continue
        method = m.group(1)
        args = m.group(2)
        locator_expr = "page." + rest[:m.start()]
        action_type = "scroll" if method == "scrollIntoViewIfNeeded" else method
        entry = {"type": action_type, "locator": _normalize_locator(locator_expr), "raw": raw_line}
        if method in ("fill", "pressSequentially"):
            # F5 fix: capture the closing delimiter along with the value
            # (`value_quoted`), not just the bare text between quotes. The
            # bare capture alone made the leak-check below unsound: the
            # pruned intermediate value 'Buy mil' is a *prefix* of the
            # surviving 'Buy milk', so a bare-substring containment check
            # fired a false leak on a perfectly faithful example. Comparing
            # with the trailing quote included ("Buy mil'" vs "Buy milk'")
            # is exactly the discriminator the plan pins.
            value_m = re.search(r"""(['"])((?:[^'"\\]|\\.)*)\1""", args)
            entry["value"] = value_m.group(2) if value_m else None
            entry["value_quoted"] = value_m.group(0) if value_m else None
        actions.append(entry)
    return actions


def _derive_survivors(actions):
    """Mechanically apply N2-N5 to a flat action list (the leading N1 goto
    is stripped by the caller before this is called), returning
    (survivors, dropped) -- the pruning re-derivation Behaviour 3 checks
    against the example's own feature block."""
    dropped = []
    filtered = []
    for a in actions:
        if a["type"] in NOISE_TYPES:
            dropped.append(dict(a))
            continue
        filtered.append(a)

    survivors = []
    i, n = 0, len(filtered)
    while i < n:
        a = filtered[i]
        if a["type"] == "click":
            nxt = filtered[i + 1] if i + 1 < n else None
            if (nxt is not None and nxt["type"] in ("fill", "pressSequentially")
                    and nxt.get("locator") == a.get("locator")):
                dropped.append(dict(a, type="focus_click"))
                i += 1
                continue
        if a["type"] == "fill":
            j = i
            while (j + 1 < n and filtered[j + 1]["type"] == "fill"
                   and filtered[j + 1].get("locator") == a.get("locator")):
                dropped.append(dict(filtered[j], type="fill_collapsed"))
                j += 1
            survivors.append(filtered[j])
            i = j + 1
            continue
        survivors.append(a)
        i += 1
    return survivors, dropped


# ---------------------------------------------------------------------------
# Behaviour 1 -- the skill exists and carries its pinned contract
# ---------------------------------------------------------------------------

def check_skill_frontmatter(failures):
    """Returns the normalised (LF-only) full file text on success, or None
    if the file could not be read at all."""
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
        if name_value != "record-scenario":
            failures.append(f"{rel(SKILL_FILE)}: frontmatter 'name' is {name_value!r}, expected 'record-scenario'")
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
    """No-op if the file could not be read at all -- check_skill_frontmatter
    already reported that."""
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

    if heading_offsets[-1] is not None:
        after_last = body[heading_offsets[-1] + len(HARD_RULE_HEADINGS[-1]):]
        if re.search(r"^## Hard rule: ", after_last, re.MULTILINE):
            failures.append(
                f"{rel(SKILL_FILE)}: another '## Hard rule: ' heading appears after "
                f"{HARD_RULE_HEADINGS[-1]!r}, which must be the last of exactly eight"
            )

    spans = get_section_spans(body, HARD_RULE_HEADINGS)
    for heading, literals in PINNED_LITERALS.items():
        span = spans.get(heading)
        for _label, literal in literals:
            if literal == "mint":
                # F7 fix: a bare substring search for "mint" is
                # unconditionally true wherever "minted"/"minting" appear
                # (which the rest of this section discusses at length), so
                # it could never actually come out false. Require "mint" as
                # its own standalone word instead -- satisfiable only if the
                # U1 mapping-label form ("... or `mint` with the new
                # phrase") is actually present.
                found = span is not None and re.search(r"\bmint\b", span) is not None
            else:
                found = span is not None and literal in span
            if not found:
                snippet = literal[:60]
                failures.append(
                    f'{rel(SKILL_FILE)}: section "{heading}" is missing the pinned literal: "{snippet}..."'
                )

    secrets_span = spans.get("## Hard rule: secrets")
    if secrets_span is not None and S1_TOKEN_LIST not in secrets_span:
        failures.append(
            f'{rel(SKILL_FILE)}: "## Hard rule: secrets" span is missing the pinned S1 token '
            f"list {S1_TOKEN_LIST!r}"
        )

    for token in SUMMARY_VOCABULARY:
        if token not in body:
            failures.append(f"{rel(SKILL_FILE)}: missing summary vocabulary literal: {token!r}")

    # M6 anti-drift regression: 'Run the suite unfiltered never.' occurs
    # exactly once, and is never extended inline with the X1 clause on the
    # same line -- the two skills' V3/X1 sentences must stay byte-identical
    # single literals, not one merged sentence.
    count = body.count("Run the suite unfiltered never.")
    if count != 1:
        failures.append(
            f"{rel(SKILL_FILE)}: 'Run the suite unfiltered never.' appears {count} time(s), "
            "expected exactly 1"
        )
    for line in body.split("\n"):
        if "Run the suite unfiltered never." in line and ", and never target another feature file" in line:
            failures.append(
                f"{rel(SKILL_FILE)}: 'Run the suite unfiltered never.' is followed on the same "
                "line by an extra clause -- it must stay its own separate literal (M6)"
            )


# ---------------------------------------------------------------------------
# Behaviour 2 (+2b) -- the worked example round-trips and reuse is reuse
# ---------------------------------------------------------------------------

def check_worked_example(failures):
    """Behaviour 2. Returns a context dict (possibly partial/empty) so the
    later behaviour checks (2b, 3, 4, 5, 6) can reuse the parse without
    re-reading the file."""
    context = {}
    if not EXAMPLE_FILE.is_file():
        failures.append(f"{rel(EXAMPLE_FILE)}: file not found")
        return context

    text = EXAMPLE_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
    context["text"] = text
    blocks = parse_headed_code_blocks(text)
    context["blocks"] = blocks

    _rh, recording_content = _find_block(blocks, prefix="e2e/.recordings/", suffix=".spec.ts")
    _fh, feature_content = _find_block(blocks, prefix="e2e/features/", suffix=".feature")
    steps_content = blocks.get("e2e/steps/recorded.steps.ts")
    _ph, pages_content = _find_block(blocks, prefix="e2e/pages/recorded/", suffix="Page.ts")
    catalog_content = blocks.get("e2e/catalog.md")
    gitignore_content = blocks.get("e2e/.gitignore")

    if recording_content is None:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: missing fenced block for a heading matching "
            "'e2e/.recordings/*.spec.ts'"
        )
    if feature_content is None:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: missing fenced block for a heading matching 'e2e/features/*.feature'"
        )
    if steps_content is None:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing fenced block for heading 'e2e/steps/recorded.steps.ts'")
    if pages_content is None:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: missing fenced block for a heading matching "
            "'e2e/pages/recorded/*Page.ts'"
        )
    if catalog_content is None:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing fenced block for heading 'e2e/catalog.md'")
    if gitignore_content is None:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing fenced block for heading 'e2e/.gitignore'")

    context.update({
        "recording_content": recording_content,
        "feature_content": feature_content,
        "steps_content": steps_content,
        "pages_content": pages_content,
        "catalog_content": catalog_content,
        "gitignore_content": gitignore_content,
    })

    example_catalog_rows = parse_catalog_table(catalog_content, EXAMPLE_FILE, failures) \
        if catalog_content is not None else []
    context["example_catalog_rows"] = example_catalog_rows

    todomvc_catalog_rows = []
    todomvc_steps_content = None
    if TODOMVC_FILE.is_file():
        todomvc_text = TODOMVC_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")
        todomvc_blocks = parse_headed_code_blocks(todomvc_text)
        todomvc_catalog_block = todomvc_blocks.get("e2e/catalog.md")
        todomvc_steps_content = todomvc_blocks.get("e2e/steps/todo.steps.ts")
        if todomvc_catalog_block is not None:
            todomvc_catalog_rows = parse_catalog_table(todomvc_catalog_block, TODOMVC_FILE, [])
    else:
        failures.append(
            f"{rel(TODOMVC_FILE)}: file not found (cannot verify reuse against the committed "
            "todomvc-scan.md catalog)"
        )
    context["todomvc_steps_content"] = todomvc_steps_content

    merged_catalog_rows = list(todomvc_catalog_rows) + list(example_catalog_rows)
    context["merged_catalog_rows"] = merged_catalog_rows
    todomvc_phrases = {row[0].strip() for row in todomvc_catalog_rows}

    if feature_content is None:
        return context

    feature_lines = _feature_step_lines(feature_content)
    context["feature_lines"] = feature_lines
    feature_phrases_raw = [line.partition(" ")[2].strip() for line in feature_lines]

    example_registrations = _step_registrations(steps_content) if steps_content is not None else []
    context["example_registrations"] = example_registrations
    todomvc_registrations = _step_registrations(todomvc_steps_content) \
        if todomvc_steps_content is not None else []

    merged_phrase_set = {row[0].strip() for row in merged_catalog_rows}
    todomvc_registration_phrases = {p.strip() for _kw, p in todomvc_registrations}
    example_registration_phrases = {p.strip() for _kw, p in example_registrations}

    # G3: resolve each `.feature` line's literal phrase (a concrete quoted
    # value substituted for any `{string}` placeholder) back to the
    # canonical, still-parametrized catalog/step phrase it was derived from,
    # so the membership/reuse checks below don't require byte-for-byte
    # equality between a `.feature` line and a catalog/step phrase.
    phrase_pool = merged_phrase_set | todomvc_registration_phrases | example_registration_phrases
    feature_phrases = [_resolve_catalog_phrase(p, phrase_pool) for p in feature_phrases_raw]
    context["feature_phrases_raw"] = feature_phrases_raw

    reused_phrases = sorted({p for p in feature_phrases if p in todomvc_phrases})
    minted_phrases = sorted({p for p in feature_phrases if p not in todomvc_phrases})
    context["reused_phrases"] = reused_phrases
    context["minted_phrases"] = minted_phrases

    for phrase in feature_phrases:
        if phrase not in merged_phrase_set:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: feature step phrase {phrase!r} does not appear as a "
                "catalog phrase in either the appended e2e/catalog.md block or "
                "docs/examples/todomvc-scan.md's committed catalog"
            )
        if phrase not in todomvc_registration_phrases and phrase not in example_registration_phrases:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: feature step phrase {phrase!r} is not defined by any "
                "Given(/When(/Then( registration reachable from the example (neither "
                "e2e/steps/recorded.steps.ts nor todomvc-scan.md's e2e/steps/todo.steps.ts)"
            )

    for line in feature_lines:
        keyword, _sep, phrase = line.partition(" ")
        expected = derive_keyword(phrase.strip())
        if expected != keyword:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: feature line {line!r} uses keyword {keyword!r}, but "
                f"derive_keyword({phrase.strip()!r}) returns {expected!r}"
            )

    if len(reused_phrases) < 2:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: only {len(reused_phrases)} feature phrase(s) are byte-identical "
            "to a phrase committed in docs/examples/todomvc-scan.md's catalog, expected at least 2"
        )
    if len(minted_phrases) < 1:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: no feature phrase is newly minted (absent from "
            "docs/examples/todomvc-scan.md's catalog), expected at least 1"
        )

    if pages_content is not None:
        class_match = re.search(r"class\s+(\w+)", pages_content)
        class_name = class_match.group(1) if class_match else None
        # F9 fix: nothing previously required the recorded page-object class
        # to actually follow the pinned 'Recorded<Route>Page' shape (F3 of
        # the skill's file-ownership rules) -- assert it here.
        if class_name is None or not re.match(r"^Recorded[A-Za-z0-9]*Page$", class_name):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: recorded page-object class name {class_name!r} does not "
                "match the pinned 'Recorded<Route>Page' shape"
            )
        for phrase, page_obj, locator in example_catalog_rows:
            if phrase.strip() not in minted_phrases:
                continue
            if locator.strip("`") not in pages_content:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: minted catalog row {phrase!r}'s Locator cell "
                    f"{locator!r} does not appear verbatim in the recorded page-object block"
                )
            if class_name is None or page_obj.strip("`") != class_name:
                failures.append(
                    f"{rel(EXAMPLE_FILE)}: minted catalog row {phrase!r}'s Page object cell "
                    f"{page_obj!r} does not match the instantiated class {class_name!r}"
                )

    if "Scenario Outline" in feature_content:
        failures.append(f"{rel(EXAMPLE_FILE)}: feature block must not use 'Scenario Outline'")
    if "Examples:" in feature_content:
        failures.append(f"{rel(EXAMPLE_FILE)}: feature block must not use 'Examples:'")
    for line in feature_content.split("\n"):
        if line.strip().startswith("|"):
            failures.append(f"{rel(EXAMPLE_FILE)}: feature block must not use a data table")
            break

    if pages_content is not None and "constructor(private readonly page: Page) {}" not in pages_content:
        failures.append(
            f"{rel(EXAMPLE_FILE)}: recorded page-object block missing "
            "'constructor(private readonly page: Page) {}'"
        )
    if steps_content is not None and "createBdd(test)" not in steps_content:
        failures.append(f"{rel(EXAMPLE_FILE)}: e2e/steps/recorded.steps.ts block missing 'createBdd(test)'")

    return context


def check_reuse_is_not_remint(failures, context):
    """Behaviour 2b."""
    reused_phrases = context.get("reused_phrases") or []
    if not reused_phrases:
        return  # already reported by check_worked_example

    text = context.get("text", "")
    example_catalog_rows = context.get("example_catalog_rows") or []
    example_registrations = context.get("example_registrations") or []
    example_catalog_phrases = {row[0].strip() for row in example_catalog_rows}
    example_registration_phrases = {p.strip() for _kw, p in example_registrations}
    lines = text.split("\n")
    reused_summary_lines = [l for l in lines if l.strip().startswith("Reused (catalog): ")]

    for phrase in reused_phrases:
        if phrase in example_catalog_phrases:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: reused phrase {phrase!r} has its own appended row in "
                "e2e/catalog.md -- reuse must add no row"
            )
        if phrase in example_registration_phrases:
            failures.append(
                f"{rel(EXAMPLE_FILE)}: reused phrase {phrase!r} has its own Given(/When(/Then( "
                "registration in e2e/steps/recorded.steps.ts -- reuse must not re-mint a "
                "definition (npx bddgen would flag this as ambiguous)"
            )
        if not any(f"reuse (A{n})" in l and phrase in l for l in lines for n in (1, 2, 3)):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: no 'reuse (A1)'/'reuse (A2)'/'reuse (A3)' transcript line "
                f"names the reused phrase {phrase!r}"
            )
        if not any(phrase in l for l in reused_summary_lines):
            failures.append(
                f"{rel(EXAMPLE_FILE)}: the summary's 'Reused (catalog): ' line does not name "
                f"the reused phrase {phrase!r}"
            )


# ---------------------------------------------------------------------------
# Behaviour 3 -- the pruning actually prunes (mechanical N1-N5 re-derivation)
# ---------------------------------------------------------------------------

def check_pruning_derivation(failures, context):
    label = rel(EXAMPLE_FILE)
    recording_content = context.get("recording_content")
    feature_content = context.get("feature_content")
    steps_content = context.get("steps_content")
    catalog_content = context.get("catalog_content")
    merged_catalog_rows = context.get("merged_catalog_rows") or []

    if recording_content is None or feature_content is None:
        return

    actions = parse_recording_actions(recording_content)
    non_expect = [a for a in actions if a["type"] != "expect"]
    if not non_expect or non_expect[0]["type"] != "goto":
        failures.append(f"{label}: the raw recording's first action is not a page.goto(...)")
        return
    raw_action_count = len(non_expect)

    survivors, dropped = _derive_survivors(non_expect[1:])

    feature_lines = context.get("feature_lines") or []
    given_lines = [l for l in feature_lines if l.startswith("Given ")]
    when_lines = [l for l in feature_lines if l.startswith("When ")]

    if len(given_lines) != 1:
        failures.append(f"{label}: feature has {len(given_lines)} 'Given' line(s), expected exactly 1")
    elif not given_lines[0][len("Given "):].strip().startswith("I am "):
        failures.append(
            f"{label}: the feature's Given phrase does not use the pinned 'I am ' minting "
            f"form: {given_lines[0]!r}"
        )

    if len(when_lines) != len(survivors):
        failures.append(
            f"{label}: feature has {len(when_lines)} 'When' line(s), but mechanically "
            f"re-deriving N1-N5 from the raw recording block finds {len(survivors)} surviving "
            "action(s) -- these must be equal and in the same order"
        )
    else:
        locator_by_phrase = {}
        for phrase, _page_obj, locator in merged_catalog_rows:
            locator_by_phrase.setdefault(phrase.strip(), locator.strip("`"))
        for idx, (when_line, survivor) in enumerate(zip(when_lines, survivors), start=1):
            # G3: resolve the When-line's literal phrase (concrete quoted
            # value) back to its canonical, parametrized catalog phrase
            # before the locator lookup below.
            phrase = _resolve_catalog_phrase(
                when_line[len("When "):].strip(), set(locator_by_phrase.keys())
            )
            if survivor["type"] == "goto":
                continue
            catalog_locator = locator_by_phrase.get(phrase)
            loc = survivor.get("locator") or ""
            if catalog_locator is None:
                failures.append(
                    f"{label}: When-line #{idx} phrase {phrase!r} does not resolve to any row "
                    "in the merged catalog (todomvc-scan.md + this example's appended rows)"
                )
            elif _normalize_locator(loc) not in _normalize_locator(catalog_locator):
                failures.append(
                    f"{label}: When-line #{idx} phrase {phrase!r} resolves to Locator cell "
                    f"{catalog_locator!r}, which does not contain the recorded action's "
                    f"locator {loc!r}"
                )

    drop_types = [d["type"] for d in dropped]
    if not any(t in ("hover", "scroll") for t in drop_types):
        failures.append(f"{label}: the raw recording block contains no hover or scroll noise (M2)")
    if "focus_click" not in drop_types:
        failures.append(
            f"{label}: the raw recording block contains no focus-click-immediately-before-fill "
            "pair on the same locator (M2/N2)"
        )
    if "fill_collapsed" not in drop_types:
        failures.append(
            f"{label}: the raw recording block contains no consecutive-fill-on-one-locator pair "
            "(M2/N3)"
        )

    emitted = "\n".join(filter(None, [feature_content, steps_content, catalog_content]))
    for d in dropped:
        # F5 fix: compare the quoted form ("Buy mil'") rather than the bare
        # value ("Buy mil"), since the bare value is a legitimate substring
        # of the surviving "Buy milk" and would false-positive here.
        if d["type"] == "fill_collapsed" and d.get("value_quoted") and d["value_quoted"] in emitted:
            failures.append(
                f"{label}: the pruned intermediate fill value {d['value']!r} leaks into an "
                "emitted artifact (feature/steps/catalog)"
            )
        if d["type"] in ("hover", "scroll"):
            loc = d.get("locator")
            if loc and loc in emitted:
                failures.append(
                    f"{label}: the hover/scroll-only locator {loc!r} leaks into an emitted "
                    "artifact (feature/steps/catalog)"
                )

    pruned_count_expected = raw_action_count - len(survivors) - 1
    text = context.get("text", "")
    pruned_match = re.search(r"^Pruned:\s*(\d+)", text, re.MULTILINE)
    if pruned_match is None:
        failures.append(f"{label}: no 'Pruned: <n>' summary line found")
    elif int(pruned_match.group(1)) != pruned_count_expected:
        failures.append(
            f"{label}: summary says 'Pruned: {pruned_match.group(1)}', but raw actions "
            f"({raw_action_count}) - survivors ({len(survivors)}) - 1 (goto) = "
            f"{pruned_count_expected}"
        )


# ---------------------------------------------------------------------------
# Behaviour 4 -- no literal secret reaches an emitted artifact
# ---------------------------------------------------------------------------

SECRET_TOKEN_RE = re.compile(S1_TOKEN_LIST, re.IGNORECASE)


def _find_secret_literal(recording_content):
    """F1: find the raw literal value fill()'d into a password/secret-looking
    locator in the raw recording block (per S1's token list), so the leak
    check below has a real value to look for instead of being unreachable
    dead code."""
    if not recording_content:
        return None
    for line in recording_content.split("\n"):
        if SECRET_TOKEN_RE.search(line) and ".fill(" in line:
            m = re.search(r"""\.fill\(\s*(['"])((?:[^'"\\]|\\.)*)\1""", line)
            if m:
                return m.group(2)
    return None


def check_secret_handling(failures, context):
    label = rel(EXAMPLE_FILE)
    steps_content = context.get("steps_content")
    feature_content = context.get("feature_content")
    catalog_content = context.get("catalog_content")
    gitignore_content = context.get("gitignore_content")
    recording_content = context.get("recording_content")
    text = context.get("text", "")

    if steps_content is None or feature_content is None:
        return

    if "process.env[" not in steps_content:
        failures.append(f"{label}: e2e/steps/recorded.steps.ts has no secret step body using 'process.env['")
    if "Missing environment variable " not in steps_content:
        failures.append(
            f"{label}: e2e/steps/recorded.steps.ts is missing the literal 'Missing environment variable '"
        )

    secret_phrase = None
    for _kw, phrase in _step_registrations(steps_content):
        if SECRET_STEP_PHRASE_RE.search(phrase):
            secret_phrase = phrase.strip()
            break
    if secret_phrase is None:
        # Blocking-1 fix: record this as one failure among possibly several,
        # rather than returning early -- the checks below (gitignore's
        # '.recordings/' line, the summary's 'Required environment
        # variables:' token, etc.) are independent of whether a secret-phrase
        # registration was found and must still run in the same pass, per
        # this validator's own "collect every failure in one run" design.
        failures.append(
            f"{label}: no Given/When/Then registration whose phrase matches "
            "'I fill in the <field> with the secret {string}'"
        )

    feature_secret_lines = [l for l in feature_content.split("\n") if "with the secret" in l]
    if not feature_secret_lines:
        failures.append(f"{label}: e2e/features/*.feature has no step line for the secret phrase")

    # S2: the env-var name lives in the secret step's own quoted argument in
    # the `.feature` line -- e.g. `When I fill in the Sync password field
    # with the secret "E2E_SYNC_PASSWORD"`. G3's `{string}` placeholder in
    # the catalog/step phrase is compiled to a concrete quoted value on the
    # `.feature` line (not left as the literal placeholder text), so this is
    # a per-step-line assertion, not a whole-block search.
    if feature_secret_lines and not any(ENV_VAR_ARG_RE.search(l) for l in feature_secret_lines):
        failures.append(
            f"{label}: the secret step's own e2e/features/*.feature line does not carry an "
            "E2E_-prefixed environment variable name in its quoted argument (S2)"
        )

    # F1 fix: the catalog-leak assertion used to be dead code (`... and
    # False`, immediately discarded). Make it real: find the actual raw
    # secret literal codegen recorded, and reject it appearing anywhere in
    # the appended catalog rows (or the feature/steps blocks, which is the
    # same surface the plan names in Behaviour 4).
    secret_literal = _find_secret_literal(recording_content)
    if secret_literal is None:
        failures.append(
            f"{label}: could not find a raw recorded fill() on a password/secret-looking "
            "locator in the e2e/.recordings/*.spec.ts block (S1)"
        )
    else:
        if catalog_content is not None and secret_literal in catalog_content:
            failures.append(
                f"{label}: the raw recorded secret value {secret_literal!r} leaks into "
                "e2e/catalog.md"
            )
        if secret_literal in feature_content:
            failures.append(
                f"{label}: the raw recorded secret value {secret_literal!r} leaks into "
                "e2e/features/*.feature"
            )
        if steps_content is not None and secret_literal in steps_content:
            failures.append(
                f"{label}: the raw recorded secret value {secret_literal!r} leaks into "
                "e2e/steps/recorded.steps.ts"
            )

    if gitignore_content is None:
        failures.append(f"{label}: missing fenced block for heading 'e2e/.gitignore' (cannot verify "
                         "'.recordings/' coverage)")
    else:
        gi_lines = [l.rstrip() for l in gitignore_content.split("\n")]
        if ".recordings/" not in gi_lines:
            failures.append(f"{label}: e2e/.gitignore block does not contain the '.recordings/' line")

    if "Required environment variables:" not in text:
        failures.append(f"{label}: summary is missing 'Required environment variables:'")


# ---------------------------------------------------------------------------
# Behaviour 5 -- two-staged, gated, scoped verification with pinned shapes
# ---------------------------------------------------------------------------

def check_verification_run(failures, skill_text, context):
    label_skill = rel(SKILL_FILE)
    label_example = rel(EXAMPLE_FILE)

    span = None
    gate_span = None
    if skill_text is not None:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text
        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get("## Hard rule: verification run")
        gate_span = spans.get("## Hard rule: confirmation gates")

    verify_run_literals = [lit for (_lbl, lit) in PINNED_LITERALS["## Hard rule: verification run"]]
    for literal in verify_run_literals:
        count = span.count(literal) if span is not None else 0
        if count != 1:
            snippet = literal[:60]
            failures.append(
                f'{label_skill}: "## Hard rule: verification run" span contains the literal '
                f'"{snippet}..." {count} time(s), expected exactly 1'
            )

    if gate_span is not None:
        if "Gate (2) runs after the files are written; it gates running, not writing." not in gate_span:
            failures.append(
                f'{label_skill}: "## Hard rule: confirmation gates" span missing the literal '
                "'Gate (2) runs after the files are written; it gates running, not writing.'"
            )
        # F8 fix: "exactly two gates" used to be checked only as the absence
        # of the substring '(3)', which never actually counts anything.
        # Count the gate *definitions* instead -- 'Gate (N) is' clauses --
        # and require the set to be exactly {1, 2}.
        gate_def_numbers = sorted(set(int(n) for n in re.findall(r"Gate \((\d+)\) is", gate_span)))
        if gate_def_numbers != [1, 2]:
            failures.append(
                f'{label_skill}: "## Hard rule: confirmation gates" span defines gate(s) '
                f"{gate_def_numbers}, expected exactly gates [1, 2] (each as a 'Gate (N) is ...' "
                "definition)"
            )
    elif skill_text is not None:
        failures.append(f'{label_skill}: missing "## Hard rule: confirmation gates" section')

    text = context.get("text")
    if text is None:
        return

    # F2 fix: scope the 'Verify: ' shape check to the '## Record summary'
    # block, per the plan, instead of collecting matching lines from the
    # whole document -- otherwise a summary with zero 'Verify: ' lines of
    # its own could still pass by picking up lines quoted elsewhere (e.g.
    # inside a gate transcript that discusses what Verify: will print).
    summary_section = _get_markdown_section(text, "## Record summary")
    if summary_section is None:
        failures.append(f"{label_example}: missing '## Record summary' section")
        summary_section = ""

    verify_lines = [l.strip() for l in summary_section.split("\n") if l.strip().startswith("Verify: ")]

    def classify(line):
        if line.startswith("Verify: COMPILE FAIL — "):
            return "COMPILE_FAIL"
        if line.startswith("Verify: COMPILE PASS — "):
            return "COMPILE_PASS"
        if line.startswith("Verify: PASS — "):
            return "PASS"
        if line.startswith("Verify: FAIL — "):
            return "FAIL"
        if line.startswith("Verify: SKIPPED — replay declined at the verification gate"):
            return "SKIPPED"
        return "UNKNOWN"

    kinds = [classify(l) for l in verify_lines]
    valid = (kinds == ["COMPILE_FAIL"]) or (
        len(kinds) == 2 and kinds[0] == "COMPILE_PASS" and kinds[1] in ("PASS", "FAIL", "SKIPPED")
    )
    if not valid:
        failures.append(
            f"{label_example}: 'Verify: ' lines are {verify_lines!r}, which do not form one of "
            "the two legal shapes (['COMPILE FAIL'] alone, or ['COMPILE PASS', one of "
            "'PASS'/'FAIL'/'SKIPPED'])"
        )

    # F3 fix: require the gate-(2) transcript to exist as its own section,
    # and require the URL + real-app warning to appear *inside* it -- not
    # just anywhere in the document. The recording block already guarantees
    # the URL appears somewhere (its own page.goto), so a whole-document
    # substring search here was unconstrained: it would pass even if the
    # gate-(2) transcript itself never showed the URL or the warning.
    gate2_section = _get_markdown_section(text, "## Gate (2) confirmation")
    if gate2_section is None:
        failures.append(f"{label_example}: missing '## Gate (2) confirmation' section")
        gate2_section = ""

    if "https://demo.playwright.dev/todomvc" not in gate2_section:
        failures.append(
            f"{label_example}: gate-(2) transcript is missing the target URL "
            "'https://demo.playwright.dev/todomvc'"
        )
    if "The recorded actions will be performed again against the real app." not in gate2_section:
        failures.append(
            f"{label_example}: gate-(2) transcript is missing the real-app warning literal "
            "'The recorded actions will be performed again against the real app.'"
        )

    # F6 fix: restrict the stage-1/stage-2 invocation checks to actual
    # command lines, not prose lines that merely mention the command. V2's
    # own pinned success line ("Verify: COMPILE PASS — npx bddgen generated
    # <n> spec(s) from the full e2e/ tree") has prose after "npx bddgen" and
    # would otherwise false-fail the "no filter argument" check; every such
    # prose line is one of the pinned 'Verify: ' report lines, so excluding
    # lines that start with that prefix isolates real invocations.
    def _is_command_line(line):
        return not line.strip().startswith("Verify: ")

    bddgen_lines = [l for l in text.split("\n") if "npx bddgen" in l and _is_command_line(l)]
    if not bddgen_lines:
        failures.append(f"{label_example}: no 'npx bddgen' invocation (command line) found")
    for l in bddgen_lines:
        idx = l.find("npx bddgen") + len("npx bddgen")
        remainder = l[idx:].lstrip()
        if remainder and not remainder.startswith(("&&", ";", "`")):
            failures.append(
                f"{label_example}: stage-1 invocation {l.strip()!r} carries a filter argument "
                "-- stage 1 must run npx bddgen unfiltered"
            )

    playwright_test_lines = [
        l for l in text.split("\n") if "npx playwright test" in l and _is_command_line(l)
    ]
    if not playwright_test_lines:
        failures.append(f"{label_example}: no 'npx playwright test' invocation (command line) found")
    for l in playwright_test_lines:
        if "--config playwright.config.ts" not in l:
            failures.append(
                f"{label_example}: stage-2 invocation {l.strip()!r} is missing "
                "'--config playwright.config.ts'"
            )
        if ".features-gen" not in l and ".feature" not in l:
            failures.append(
                f"{label_example}: stage-2 invocation {l.strip()!r} carries no '.features-gen' "
                "path or '<slug>.feature' filter -- stage 2 must never run unfiltered"
            )


# ---------------------------------------------------------------------------
# Behaviour 6 -- dedupe rules exist for both directions (F7/F8)
# ---------------------------------------------------------------------------

def check_dedupe_rules(failures, skill_text, context):
    label_skill = rel(SKILL_FILE)
    span = None
    catalog_span = None
    if skill_text is not None:
        m = FRONTMATTER_RE.match(skill_text)
        body = skill_text[m.end():] if m else skill_text
        spans = get_section_spans(body, HARD_RULE_HEADINGS)
        span = spans.get("## Hard rule: file ownership")
        catalog_span = spans.get("## Hard rule: catalog matching")

    if span is not None:
        if not all(kw in span for kw in (
            "F7", "merged in place", "reused, not re-emitted", "reused, not re-registered",
        )):
            failures.append(
                f'{label_skill}: "## Hard rule: file ownership" span is missing a complete F7 '
                "repeat-recording (merge, never duplicate) bullet"
            )
        if not all(kw in span for kw in (
            "F8", "scanner wins", "deleted", "re-pointed", "recorded.steps.ts",
        )):
            failures.append(
                f'{label_skill}: "## Hard rule: file ownership" span is missing a complete F8 '
                "scanner-ran-later dedupe bullet"
            )
    elif skill_text is not None:
        failures.append(f'{label_skill}: missing "## Hard rule: file ownership" section')

    if catalog_span is not None and ("F7" not in catalog_span or "F8" not in catalog_span):
        failures.append(
            f'{label_skill}: "## Hard rule: catalog matching" span (A5) does not reference '
            "both F7 and F8 by label"
        )

    if skill_text is not None and "Removed (deduped): " not in skill_text:
        failures.append(f"{label_skill}: missing 'Removed (deduped): ' token")

    example_text = context.get("text")
    if example_text is not None and "Removed (deduped): " not in example_text:
        failures.append(f"{rel(EXAMPLE_FILE)}: missing 'Removed (deduped): ' token")


# ---------------------------------------------------------------------------
# Behaviour 7 -- web-tester routes to record-scenario without gutting #2/#3
# ---------------------------------------------------------------------------

NEW_ROUTING_HEADING = "## Recording a scenario: delegate to record-scenario"
OLD_CLOSER_SUBSTRING = "not-yet-built package"


def check_web_tester_routing(failures):
    if not WEB_TESTER_FILE.is_file():
        failures.append(f"{rel(WEB_TESTER_FILE)}: file not found")
        return
    text = WEB_TESTER_FILE.read_text(encoding="utf-8").replace("\r\n", "\n")

    if NEW_ROUTING_HEADING not in text:
        failures.append(f"{rel(WEB_TESTER_FILE)}: missing heading {NEW_ROUTING_HEADING!r}")
    if OLD_CLOSER_SUBSTRING in text:
        failures.append(f"{rel(WEB_TESTER_FILE)}: still contains the stale {OLD_CLOSER_SUBSTRING!r} closer")
    if validate_scaffold.PAGE_SCANNER_SECTION_HEADING not in text:
        failures.append(
            f"{rel(WEB_TESTER_FILE)}: missing the surviving page-scanner delegation heading "
            f"{validate_scaffold.PAGE_SCANNER_SECTION_HEADING!r}"
        )
    for required in ("scaffold-bdd", "e2e/catalog.md"):
        if required not in text:
            failures.append(f"{rel(WEB_TESTER_FILE)}: does not mention {required!r}")


# ---------------------------------------------------------------------------
# Behaviour 8 -- CI actually runs the new validator
# ---------------------------------------------------------------------------

def check_lint_workflow_wires_validator(failures):
    if not LINT_YML.is_file():
        failures.append(f"{rel(LINT_YML)}: file not found")
        return
    text = LINT_YML.read_text(encoding="utf-8").replace("\r\n", "\n")
    needle_re = re.compile(re.escape("python3 .github/scripts/validate_record.py"))
    if _find_live_cp_match(needle_re, text) is None:
        failures.append(
            f"{rel(LINT_YML)}: no *live* step runs .github/scripts/validate_record.py "
            "(a commented-out line does not count)"
        )


# ---------------------------------------------------------------------------
# Behaviour 9 -- release staging, no committed e2e/, AGENTS.md bullets,
# and a subprocess regression run of the sibling validators
# ---------------------------------------------------------------------------

AGENTS_MD_BULLET_SUBSTRINGS = [
    ("record-scenario records via a companion npx playwright codegen, a second browser/profile", [
        "npx playwright codegen", "second browser", "second profile",
    ]),
    ("step-file ownership is partitioned between recorded.steps.ts and authored.steps.ts", [
        "recorded.steps.ts", "authored.steps.ts",
    ]),
    ("recorded page objects live at e2e/pages/recorded/<Route>Page.ts, scanner file is read-only", [
        "pages/recorded/", "Recorded", "read-only",
    ]),
    ("record-scenario is the only thing that appends to e2e/catalog.md; .recordings/ is gitignored", [
        "appends", "e2e/catalog.md", ".recordings/", "secrets",
    ]),
    ("V-rules are the only place a skill runs against the real app; X3 forbids it; two-stage split", [
        "real", "X3", "stage 1", "stage 2", "npx bddgen", "npx playwright test",
    ]),
]


def _top_level_bullet_blocks(text):
    """F4: group each top-level '- ' bullet with its contiguous continuation
    lines (indented sub-lines, wrapped prose) up to the next top-level '- '
    bullet or EOF -- one entry per bullet, not one entry per physical line."""
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


def check_agents_md_bullets(failures):
    if not AGENTS_MD.is_file():
        failures.append(f"{rel(AGENTS_MD)}: file not found")
        return
    text = AGENTS_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    # F4 fix: the previous 'found_in_body' fallback accepted the substrings
    # scattered anywhere in the whole file, which is not "a real top-level
    # bullet" as the plan requires. Require every substring to live inside
    # one contiguous bullet block (a single '- ...' line, or that line plus
    # its own indented continuation) -- drop the whole-document fallback.
    bullet_blocks = _top_level_bullet_blocks(text)

    for label, substrings in AGENTS_MD_BULLET_SUBSTRINGS:
        found = any(all(s in block for s in substrings) for block in bullet_blocks)
        if not found:
            failures.append(f"{rel(AGENTS_MD)}: missing the '{label}' contract bullet")


def check_sibling_validators_regression(failures):
    for script in (VALIDATE_AGENTS_SCRIPT, VALIDATE_SCAFFOLD_SCRIPT):
        if not script.is_file():
            failures.append(f"{rel(script)}: file not found")
            continue
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"{rel(script)}: could not run as a subprocess ({exc})")
            continue
        if result.returncode != 0:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
            failures.append(
                f"{rel(script)}: exited {result.returncode}, expected 0 (regression); tail:\n{tail}"
            )


def main():
    failures = []

    skill_text = check_skill_frontmatter(failures)
    check_skill_hard_rules(failures, skill_text)

    context = check_worked_example(failures)
    check_reuse_is_not_remint(failures, context)
    check_pruning_derivation(failures, context)
    check_secret_handling(failures, context)
    check_verification_run(failures, skill_text, context)
    check_dedupe_rules(failures, skill_text, context)

    check_web_tester_routing(failures)
    check_lint_workflow_wires_validator(failures)

    validate_scaffold.check_release_staging_skills(failures)
    validate_scaffold.check_no_committed_e2e_tree(failures)
    check_agents_md_bullets(failures)
    check_sibling_validators_regression(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_record: OK (record-scenario skill + worked example + CI wiring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
