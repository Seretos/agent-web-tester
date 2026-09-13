#!/usr/bin/env python3
"""Driving tests for work package #27: `playwright-bdd@9`'s `createBdd(test)`
rejects a `test` object imported from `@playwright/test` -- it must come from
`playwright-bdd` itself. Every shipped step-definition template this plugin
ships, and the rule texts describing them (`skills/scaffold-bdd/SKILL.md`'s
`P2`, `agents/page-scanner.md`'s pipeline step 5), currently produce/describe
the broken `import { test } from '@playwright/test'` shape, so `npx bddgen`
fails on a fresh first-time use of this plugin's scan -> author -> scaffold
pipeline (ticket #27's exact repro).

Per the ticket's own stated lesson from #20/#25 ("must be demonstrated live,
not asserted in prose"), this module does NOT string-match the fix -- it
really materialises each shipped template into a real npm project and really
runs `npx bddgen` against it.

Standalone runner in this repo's `tests/test_browser_bootstrap.py` style:
module-level zero-argument `test_*` functions using plain `assert`
statements (so `pytest tests/` also works), a `TESTS` list, and a `main()`
that collects every failure/skip and prints a summary before exiting
1/0 -- never stopping at the first failure.

Usage:
    python tests/test_bddgen_step_files.py       (local; live sub-tests skip)
    python3 tests/test_bddgen_step_files.py      (CI, matches lint.yml style)
    AWT_LIVE_BDDGEN=1 python tests/test_bddgen_step_files.py   (full; Node +
                                                                 network)
    pytest tests/                                (optional, if installed)

Repo paths are resolved relative to this file's own location.

Live-test gating (`AWT_LIVE_BDDGEN=1`, mirroring `test_browser_bootstrap.py`'s
`AWT_LIVE_BROWSER`): every test that actually spawns `npm install`/`bddgen`
requires this env var, since it needs network access and is comparatively
slow; reusing `AWT_LIVE_BROWSER` would make every bddgen run also pay a
~150 MiB browser download it does not need. Without the var, those tests are
skipped with an explicit message -- never silently omitted. Pure
doc-parsing/regex assertions that need no subprocess are NOT gated, since
they are fast, need no network, and still provide signal in an ordinary
local/CI lint run. As with `test_browser_bootstrap.py`, missing `node`/`npm`/
`npx` tooling is an `unittest.SkipTest` locally but a hard failure whenever
the `CI` env var is set, so CI can never quietly report green with a tool
missing.

Efficiency: every live sub-test shares ONE `npm install` (of `@playwright/test`
+ `playwright-bdd`, at the caret ranges read live out of
`docs/examples/scaffold-bdd-run.md`'s own `e2e/package.json` fenced block --
never hardcoded) in one shared parent temp root; every per-doc/per-case
project directory is created *nested inside* that shared root (so Node's
ordinary upward `node_modules` resolution finds the shared install with no
extra configuration) and each `bddgen` invocation runs with that root's
`node_modules/.bin` prepended to `PATH`. The shared state is built lazily,
once, and cached for the rest of the process.

Known staleness (plan-acknowledged): `scaffold-bdd-run.md` currently still
pins the stale `^1.48.0` / `^7.5.0` versions (the plan's version bump to
`^1.63.0` / `^9.2.1` is a phase=implement doc edit, not a phase=tests one).
This module reads whatever is in the doc dynamically rather than hardcoding
a version -- but installs it as an EXACT pin (`_exact_version`), not the
caret range verbatim: verified live this session, plain `npm install` of the
doc's own `^1.48.0`/`^7.5.0` carets floats to `@playwright/test@1.63.0`
(today's latest 1.x) + `playwright-bdd@7.5.0` (latest 7.x), a pairing
playwright-bdd@7.5.0 was never built against and that fails with an
unrelated `MODULE_NOT_FOUND` on `playwright/lib/common/configLoader.js`
before ever reaching the bug this ticket is about. Pinning the doc's own
literal version numbers exactly (`1.48.0` + `7.5.0`, confirmed mutually
compatible this session) reproduces the real, ticket-described `createBdd()`
error instead -- see the change report for the full comparison. This means
the module needs no edit at all once the version bump lands: it will simply
start installing `1.63.0`/`9.2.1` exactly, which is also the pair already
confirmed compatible.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs" / "examples"

TODOMVC_SCAN_DOC = DOCS_DIR / "todomvc-scan.md"
SCAFFOLD_DOC = DOCS_DIR / "scaffold-bdd-run.md"
AUTHOR_README_DOC = DOCS_DIR / "author-scenario" / "README.md"
UNRESOLVABLE_UI_DOC = DOCS_DIR / "author-scenario" / "unresolvable-ui.md"
RECORD_SCENARIO_DOC = DOCS_DIR / "record-scenario-run.md"

FIVE_DOCS = [
    ("todomvc-scan.md", TODOMVC_SCAN_DOC),
    ("scaffold-bdd-run.md", SCAFFOLD_DOC),
    ("author-scenario/README.md", AUTHOR_README_DOC),
    ("author-scenario/unresolvable-ui.md", UNRESOLVABLE_UI_DOC),
    ("record-scenario-run.md", RECORD_SCENARIO_DOC),
]

SKILL_MD = REPO_ROOT / "skills" / "scaffold-bdd" / "SKILL.md"
PAGE_SCANNER_MD = REPO_ROOT / "agents" / "page-scanner.md"

LIVE_ENV_VAR = "AWT_LIVE_BDDGEN"

SCANNER_STEP_PATH_IN_TODOMVC_DOC = "e2e/steps/todo.steps.ts"

TEST_IMPORT_ERROR_TEXT = "should use 'test' extended"


# ---------------------------------------------------------------------------
# Tool availability / gating
# ---------------------------------------------------------------------------

def _require_tools():
    """Skip locally when node/npm/npx are missing; hard-fail instead when the
    ``CI`` env var is set, so CI can never quietly report green with a tool
    missing (same pattern as test_release_scripts.py's _require_tools and
    test_browser_bootstrap.py's copy of it)."""
    missing = [name for name in ("node", "npm", "npx") if shutil.which(name) is None]
    if missing:
        message = f"required tool(s) not available: {', '.join(missing)}"
        if os.environ.get("CI"):
            raise AssertionError(f"{message} (CI is set -- this is a hard failure, not a skip)")
        raise unittest.SkipTest(message)


def _require_live():
    if os.environ.get(LIVE_ENV_VAR) != "1":
        raise unittest.SkipTest(
            f"requires {LIVE_ENV_VAR}=1 -- runs a real 'npm install' (network access) "
            "and real 'npx bddgen'/bddgen-binary invocations"
        )


def _resolve_command(command, path=None):
    resolved = shutil.which(command, path=path)
    if resolved is None:
        raise AssertionError(f"command {command!r} not found on PATH ({path!r})")
    return resolved


VERSION_RANGE_PREFIX_RE = re.compile(r"^[\^~>=<\s]+")


def _exact_version(version_spec):
    """Strip a leading semver-range operator (^, ~, >=, ...) so the shared
    install root pins the EXACT version named in the doc rather than
    whatever a caret range floats to at install time.

    This matters in practice, not just in theory: verified live this
    session, `scaffold-bdd-run.md`'s current (stale, pre-version-bump)
    `^1.48.0` / `^7.5.0` caret ranges resolve via plain `npm install` to
    `@playwright/test@1.63.0` (today's latest 1.x) paired with
    `playwright-bdd@7.5.0` (latest 7.x) -- a combination playwright-bdd@7.5.0
    was never built against, which fails with an unrelated
    `Cannot find module '.../playwright/lib/common/configLoader.js'`
    MODULE_NOT_FOUND before ever reaching the createBdd() check this ticket
    is about. Installing the exact pair named in the doc
    (`@playwright/test@1.48.0` + `playwright-bdd@7.5.0`, confirmed
    mutually compatible this session) reproduces the real, ticket-described
    `Error: createBdd() should use 'test' extended from "playwright-bdd"`
    instead. See the change report for the full manual before/after
    comparison."""
    return VERSION_RANGE_PREFIX_RE.sub("", version_spec).strip()


# ---------------------------------------------------------------------------
# Doc block parsing: "### <path>" headings followed (possibly after prose) by
# one fenced code block, per the plan's R1 materialisation recipe.
# ---------------------------------------------------------------------------

HEADING_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n```", re.DOTALL)
PARENTHETICAL_TAIL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _strip_parenthetical(raw_heading):
    """Strip a trailing parenthetical like '(read-only, scanner-owned)',
    '(before)', '(after)', or '(excerpt)' from a heading's path text."""
    return PARENTHETICAL_TAIL_RE.sub("", raw_heading).strip()


def _parse_doc_blocks(doc_path):
    """Return {normalised_path: fenced_block_content} for every '### <path>'
    heading in doc_path whose next fenced code block is reached before any
    other '### ' heading. A path heading repeated (e.g. catalog.md's
    '(before)'/'(after)' pair) is overwritten by the later occurrence."""
    text = doc_path.read_text(encoding="utf-8")
    blocks = {}
    headings = list(HEADING_RE.finditer(text))
    for i, m in enumerate(headings):
        path = _strip_parenthetical(m.group(1))
        search_start = m.end()
        search_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        # A heading with no fenced block before the next heading (e.g. pure
        # prose subheadings) contributes nothing.
        window = text[search_start:search_end]
        fence_match = FENCE_RE.search(window)
        if fence_match is None:
            continue
        blocks[path] = fence_match.group(1)
    return blocks


def _materializable_blocks(blocks):
    """The plan's R1 scope: every e2e/** block with a .ts/.feature/.html
    extension, excluding e2e/.recordings/** (raw codegen output, never
    globbed by playwright-bdd's `steps` pattern, deliberately left using
    `@playwright/test` -- see test_recordings_block_still_imports_playwright_test)."""
    result = {}
    for path, content in blocks.items():
        if not path.startswith("e2e/"):
            continue
        if path.startswith("e2e/.recordings/"):
            continue
        if not path.endswith((".ts", ".feature", ".html")):
            continue
        result[path] = content
    return result


STEP_REGISTRATION_RE = re.compile(r"\b(Given|When|Then)\(\s*'([^']+)'")


def _synthesize_feature_from_steps(files):
    """Build a minimal one-scenario .feature file whose lines are exactly the
    step phrases registered by the e2e/steps/*.ts blocks in `files`, in
    registration order, using each registration's own Given/When/Then
    keyword. {string} placeholders are replaced with a literal quoted value
    so the compiled cucumber expression binds. Used only for docs that ship
    no .feature block of their own (today: todomvc-scan.md)."""
    lines = []
    for path in sorted(files):
        if not (path.startswith("e2e/steps/") and path.endswith(".ts")):
            continue
        for keyword, phrase in STEP_REGISTRATION_RE.findall(files[path]):
            concrete = phrase.replace("{string}", '"x"')
            lines.append(f"    {keyword} {concrete}")
    if not lines:
        raise AssertionError("no step registrations found to synthesize a feature from")
    return (
        "Feature: Synthesized from step phrases\n\n"
        "  Scenario: synthesized\n" + "\n".join(lines) + "\n"
    )


# ---------------------------------------------------------------------------
# Import-fix / import-break simulation, used only by the R1c negative
# control to force exactly one file broken regardless of whether the real
# production fix has landed in the docs yet.
# ---------------------------------------------------------------------------

BROKEN_TEST_IMPORT_RE = re.compile(r"^import \{([^}]*)\} from '@playwright/test';[ \t]*$", re.MULTILINE)
STANDALONE_CREATEBDD_IMPORT_RE = re.compile(r"^import \{ createBdd \} from 'playwright-bdd';\n", re.MULTILINE)
FIXED_TEST_IMPORT_RE = re.compile(r"^import \{([^}]*)\} from 'playwright-bdd';[ \t]*$", re.MULTILINE)


def _fix_import(ts_source):
    """Simulate the plan's decided fix -- `import { test, createBdd } from
    'playwright-bdd';`, with any other named import (e.g. expect) kept on its
    own `@playwright/test` import -- on a step file that still uses the
    broken `@playwright/test`-sourced `test` import. Idempotent / a no-op if
    that pattern is not present (already fixed, or never had a `test`
    import at all)."""
    m = BROKEN_TEST_IMPORT_RE.search(ts_source)
    if not m:
        return ts_source
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    if "test" not in names:
        return ts_source
    other_names = [n for n in names if n != "test"]
    replacement = "import { test, createBdd } from 'playwright-bdd';"
    if other_names:
        replacement += "\nimport { " + ", ".join(other_names) + " } from '@playwright/test';"
    fixed = ts_source[: m.start()] + replacement + ts_source[m.end() :]
    fixed = STANDALONE_CREATEBDD_IMPORT_RE.sub("", fixed)
    return fixed


def _break_import(ts_source):
    """Inverse of _fix_import: force this step file's `test` import back to
    the broken `@playwright/test` source, regardless of whether it is
    currently fixed or already broken. Used only by the R1c negative control
    to deliberately re-introduce the bug in exactly one file."""
    m = FIXED_TEST_IMPORT_RE.search(ts_source)
    if not m:
        return ts_source
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    if "test" not in names:
        return ts_source
    other_names = [n for n in names if n not in ("test", "createBdd")]
    lines = ["import { createBdd } from 'playwright-bdd';"]
    test_line = "import { test"
    if other_names:
        test_line += ", " + ", ".join(other_names)
    test_line += " } from '@playwright/test';"
    lines.append(test_line)
    return ts_source[: m.start()] + "\n".join(lines) + ts_source[m.end() :]


# ---------------------------------------------------------------------------
# Rule-text import-source extraction (R2)
# ---------------------------------------------------------------------------

TEST_IMPORT_LINE_RE = re.compile(r"import \{[^}]*\btest\b[^}]*\} from '([^']+)';?")


def _extract_test_import_source(text, label):
    """Regex-extract the import-of-`test` line from a rule text span.
    Returns (source, full_import_statement). Raises AssertionError with a
    specific, plan-mandated message if none or more than one is found --
    this IS the expected RED signal for R2 today, since neither P2 nor
    page-scanner step 5 currently names any import source at all."""
    matches = list(TEST_IMPORT_LINE_RE.finditer(text))
    if not matches:
        raise AssertionError(f"no 'test' import source named in {label}")
    if len(matches) > 1:
        sources = [m.group(1) for m in matches]
        raise AssertionError(
            f"expected exactly one 'test' import source named in {label}, "
            f"found {len(matches)}: {sources}"
        )
    m = matches[0]
    statement = m.group(0)
    if not statement.endswith(";"):
        statement += ";"
    return m.group(1), statement


def _skill_p2_span_text():
    text = SKILL_MD.read_text(encoding="utf-8")
    heading_re = re.compile(r"^## Hard rule: layout\s*$", re.MULTILINE)
    hm = heading_re.search(text)
    if not hm:
        raise AssertionError("'## Hard rule: layout' heading not found in skills/scaffold-bdd/SKILL.md")
    line_end = text.find("\n", hm.end())
    search_from = line_end + 1 if line_end != -1 else len(text)
    next_heading = re.compile(r"^## ", re.MULTILINE).search(text, search_from)
    end = next_heading.start() if next_heading else len(text)
    return text[hm.start() : end]


def _page_scanner_step5_span_text():
    text = PAGE_SCANNER_MD.read_text(encoding="utf-8")
    heading_re = re.compile(r"^### Scanning and emission pipeline\s*$", re.MULTILINE)
    hm = heading_re.search(text)
    if not hm:
        raise AssertionError("'### Scanning and emission pipeline' heading not found in agents/page-scanner.md")
    line_end = text.find("\n", hm.end())
    section_start = line_end + 1 if line_end != -1 else len(text)
    next_heading = re.compile(r"^##", re.MULTILINE).search(text, section_start)
    section_end = next_heading.start() if next_heading else len(text)
    section = text[section_start:section_end]
    item_re = re.compile(r"^5\.\s.*?(?=^\d+\.\s|\Z)", re.MULTILINE | re.DOTALL)
    im = item_re.search(section)
    if not im:
        raise AssertionError("pipeline step 5 not found in agents/page-scanner.md")
    return im.group(0)


# ---------------------------------------------------------------------------
# Shared live state: one npm install root, shared by every live sub-test.
# ---------------------------------------------------------------------------

_STATE = {"built": False, "value": None, "error": None}


def _slug(text):
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()


def _write_project(project_dir, files):
    for rel_path, content in files.items():
        full = project_dir / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8", newline="\n")


def _finalize_files(files, scaffold_pkg_json_text, scaffold_playwright_config_text):
    """Apply the plan's package.json/playwright.config.ts injection: a
    project that ships neither gets scaffold-bdd-run.md's own copies."""
    out = dict(files)
    if "e2e/package.json" not in out:
        out["e2e/package.json"] = scaffold_pkg_json_text
    if "e2e/playwright.config.ts" not in out:
        out["e2e/playwright.config.ts"] = scaffold_playwright_config_text
    if not any(p.endswith(".feature") for p in out):
        out["e2e/features/synthesized.feature"] = _synthesize_feature_from_steps(out)
    return out


def _build_state():
    _require_tools()

    doc_blocks = {label: _parse_doc_blocks(path) for label, path in FIVE_DOCS}
    scaffold_blocks = doc_blocks["scaffold-bdd-run.md"]
    if "e2e/package.json" not in scaffold_blocks:
        raise AssertionError("scaffold-bdd-run.md ships no 'e2e/package.json' block to read versions from")
    scaffold_pkg_json_text = scaffold_blocks["e2e/package.json"]
    scaffold_pkg_json = json.loads(scaffold_pkg_json_text)
    dev_deps = scaffold_pkg_json.get("devDependencies", {})
    playwright_version = dev_deps.get("@playwright/test")
    bdd_version = dev_deps.get("playwright-bdd")
    if not playwright_version or not bdd_version:
        raise AssertionError(
            f"scaffold-bdd-run.md's e2e/package.json devDependencies missing "
            f"@playwright/test/playwright-bdd versions: {dev_deps!r}"
        )
    scaffold_playwright_config_text = scaffold_blocks.get("e2e/playwright.config.ts")
    if not scaffold_playwright_config_text:
        raise AssertionError("scaffold-bdd-run.md ships no 'e2e/playwright.config.ts' block")

    root = Path(tempfile.mkdtemp(prefix="awt-bddgen-root-"))
    root_pkg = {
        "name": "awt-bddgen-shared-root",
        "private": True,
        "version": "0.0.0",
        "devDependencies": {
            "@playwright/test": _exact_version(playwright_version),
            "playwright-bdd": _exact_version(bdd_version),
        },
    }
    (root / "package.json").write_text(json.dumps(root_pkg, indent=2), encoding="utf-8")

    npm = _resolve_command("npm")
    install = subprocess.run(
        [npm, "install", "--no-audit", "--no-fund"],
        cwd=str(root), capture_output=True, text=True, encoding="utf-8", timeout=480,
    )
    if install.returncode != 0:
        raise AssertionError(
            f"shared 'npm install' failed (exit {install.returncode}) in {root}:\n"
            f"stdout={install.stdout}\nstderr={install.stderr}"
        )

    bin_dir = root / "node_modules" / ".bin"
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    return {
        "root": root,
        "env": env,
        "doc_blocks": doc_blocks,
        "scaffold_pkg_json_text": scaffold_pkg_json_text,
        "scaffold_playwright_config_text": scaffold_playwright_config_text,
        "playwright_version": playwright_version,
        "bdd_version": bdd_version,
        "install_output": install.stdout + install.stderr,
    }


def _get_state():
    if not _STATE["built"]:
        try:
            _STATE["value"] = _build_state()
        except Exception as exc:  # noqa: BLE001 - cache any build failure, re-raise consistently
            _STATE["error"] = exc
        _STATE["built"] = True
    if _STATE["error"] is not None:
        raise _STATE["error"]
    return _STATE["value"]


_PROJECT_COUNTER = {"n": 0}


def _new_project_dir(state, name):
    _PROJECT_COUNTER["n"] += 1
    project = state["root"] / f"proj-{_PROJECT_COUNTER['n']:02d}-{_slug(name)}"
    project.mkdir(parents=True, exist_ok=True)
    return project


def _run_bddgen(cwd, env, timeout=180):
    bddgen_path = shutil.which("bddgen", path=env.get("PATH"))
    if bddgen_path is None:
        raise AssertionError(
            f"'bddgen' not found on PATH ({env.get('PATH')!r}) -- shared npm "
            "install root is missing node_modules/.bin/bddgen"
        )
    return subprocess.run(
        [bddgen_path], cwd=str(cwd), env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=timeout,
    )


def _project_files_for_doc(state, label):
    blocks = state["doc_blocks"][label]
    files = _materializable_blocks(blocks)
    if label == "record-scenario-run.md":
        # record-scenario-run.md's own prose says it is "continuing the same
        # TodoMVC story docs/examples/todomvc-scan.md started": its feature
        # file reuses three step phrases byte-identically from that scan's
        # e2e/steps/todo.steps.ts (fill-in-textbox, check-checkbox,
        # click-button) instead of redefining them -- per AGENTS.md's F7/F8
        # reuse contract, record-scenario never duplicates a step a prior
        # scan already owns. So this doc was never meant to bddgen alone;
        # bring in the scan's steps/page object it explicitly depends on,
        # exactly as the doc's own narrative describes, or bddgen's default
        # missingSteps: 'fail-on-gen' fails it for a reason that has nothing
        # to do with the import fix this module drives.
        todomvc_files = _materializable_blocks(state["doc_blocks"]["todomvc-scan.md"])
        merged = dict(todomvc_files)
        merged.update(files)
        files = merged
    return _finalize_files(files, state["scaffold_pkg_json_text"], state["scaffold_playwright_config_text"])


# ===========================================================================
# R1 -- every shipped step-definition template survives a real `npx bddgen`
# ===========================================================================

def test_shipped_step_templates_pass_bddgen():
    """One sub-case per doc: materialise it into a real e2e/ project and run
    a real bddgen binary against it.

    Expected RED reason (today): exit 1 for all five, with
    "Error: createBdd() should use 'test' extended from \"playwright-bdd\""
    in the output -- every shipped step-file block imports `test` from
    '@playwright/test' instead of 'playwright-bdd'.
    """
    _require_tools()
    _require_live()
    state = _get_state()

    failures = []
    for label, _path in FIVE_DOCS:
        files = _project_files_for_doc(state, label)
        project = _new_project_dir(state, label)
        _write_project(project, files)
        result = _run_bddgen(project / "e2e", state["env"])
        combined = result.stdout + result.stderr
        if result.returncode != 0:
            failures.append(f"{label}: bddgen exited {result.returncode}: {combined.strip()[-800:]}")
        elif TEST_IMPORT_ERROR_TEXT in combined:
            failures.append(f"{label}: bddgen exited 0 but output still contains {TEST_IMPORT_ERROR_TEXT!r}: {combined.strip()[-800:]}")

    assert not failures, "shipped step templates failed bddgen:\n" + "\n".join(failures)



# author-scenario/unresolvable-ui.md's own worked example ships exactly one
# scenario, tagged `@todo @skip` (its whole point is to demonstrate the
# failure path where a sentence's element cannot be resolved). Verified live
# against real playwright-bdd@9 source (generate/index.js's `buildFiles()`
# renders "only files that have at least one executable test"): a feature
# whose sole scenario is force-skipped has no executable test, so bddgen
# legitimately exits 0 having generated ZERO spec files and never even
# creates .features-gen -- this is the doc's intended, described output, not
# a bug the import fix touches. The general "non-empty .features-gen" guard
# below would otherwise flag this doc's correct behaviour as a vacuous pass.
DOCS_WHERE_ZERO_GENERATED_SPECS_IS_EXPECTED = {"author-scenario/unresolvable-ui.md"}


def test_bddgen_emits_generated_specs():
    """Edge case (a): .features-gen/ must be non-empty per project, so
    exit-0-but-did-nothing cannot pass vacuously -- except the one doc whose
    entire scenario is deliberately `@todo @skip`'d, where zero generated
    specs is the documented, correct outcome (see
    DOCS_WHERE_ZERO_GENERATED_SPECS_IS_EXPECTED above).

    Expected RED reason (today): same createBdd() error as
    test_shipped_step_templates_pass_bddgen -- bddgen never reaches the
    generation step.
    """
    _require_tools()
    _require_live()
    state = _get_state()

    failures = []
    for label, _path in FIVE_DOCS:
        files = _project_files_for_doc(state, label)
        project = _new_project_dir(state, label + "-specs")
        _write_project(project, files)
        result = _run_bddgen(project / "e2e", state["env"])
        combined = result.stdout + result.stderr
        if result.returncode != 0:
            failures.append(f"{label}: bddgen exited {result.returncode}: {combined.strip()[-800:]}")
            continue
        gen_dir = project / "e2e" / ".features-gen"
        generated = list(gen_dir.rglob("*")) if gen_dir.is_dir() else []
        generated_files = [p for p in generated if p.is_file()]
        if not generated_files and label not in DOCS_WHERE_ZERO_GENERATED_SPECS_IS_EXPECTED:
            failures.append(f"{label}: bddgen exited 0 but {gen_dir} has no generated files")

    assert not failures, "bddgen did not emit generated specs:\n" + "\n".join(failures)


def test_step_blocks_were_actually_found():
    """Edge case (b): the doc-parsing step itself must find at least one
    e2e/steps/**.ts block per doc, and at least 6 overall -- a parser bug
    that silently found zero blocks would make every bddgen assertion above
    vacuously true. No subprocess involved; not live-gated."""
    total = 0
    failures = []
    for label, path in FIVE_DOCS:
        blocks = _parse_doc_blocks(path)
        step_blocks = [p for p in blocks if p.startswith("e2e/steps/") and p.endswith(".ts")]
        if not step_blocks:
            failures.append(f"{label}: found 0 e2e/steps/**.ts blocks")
        total += len(step_blocks)

    assert not failures, "\n".join(failures)
    assert total >= 6, f"expected >= 6 step blocks across all 5 docs, found {total}"


def test_recordings_block_still_imports_playwright_test():
    """Edge case (c): the .recordings/*.spec.ts block in
    record-scenario-run.md is raw codegen output, never passed to
    createBdd(), never globbed by playwright-bdd's `steps` pattern -- it
    must NOT be touched by the fix. This may already pass today; that is
    expected, not a defect."""
    blocks = _parse_doc_blocks(RECORD_SCENARIO_DOC)
    path = "e2e/.recordings/todomvc-add-complete-clear.spec.ts"
    assert path in blocks, f"expected {path!r} block in record-scenario-run.md, found {sorted(blocks)}"
    content = blocks[path]
    assert "from '@playwright/test'" in content, (
        f"{path} must still import from '@playwright/test' (out of scope for this fix); "
        f"content={content!r}"
    )


# ===========================================================================
# R1c -- a bddgen run from e2e/, as X1/V1/V2 mandate, compiles page-scanner's
# output together with scaffold-bdd's canary
# ===========================================================================

def _combined_r1c_files(state):
    scaffold_files = _materializable_blocks(state["doc_blocks"]["scaffold-bdd-run.md"])
    todomvc_files = _materializable_blocks(state["doc_blocks"]["todomvc-scan.md"])
    combined = dict(scaffold_files)
    combined.update(todomvc_files)
    if not any(p.endswith(".feature") for p in todomvc_files):
        combined["e2e/features/todomvc-synth.feature"] = _synthesize_feature_from_steps(todomvc_files)
    combined = _finalize_files(combined, state["scaffold_pkg_json_text"], state["scaffold_playwright_config_text"])
    return combined


def test_scanner_and_scaffold_compile_together():
    """R1c: scaffold-bdd-run.md's full scaffold + todomvc-scan.md's scanner
    output, in one e2e/ tree, bddgen run unfiltered from e2e/ exactly as X1
    mandates.

    Expected RED reason (today): exit 1, createBdd() error -- the ticket's
    repro, reproduced at document level.
    """
    _require_tools()
    _require_live()
    state = _get_state()

    files = _combined_r1c_files(state)
    project = _new_project_dir(state, "r1c-combined")
    _write_project(project, files)
    result = _run_bddgen(project / "e2e", state["env"])
    combined_output = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"expected bddgen exit 0 for the combined scanner+scaffold tree, got "
        f"{result.returncode}: {combined_output.strip()[-1500:]}"
    )
    gen_dir = project / "e2e" / ".features-gen"
    generated = [p for p in gen_dir.rglob("*.js")] if gen_dir.is_dir() else []
    assert generated, f"expected generated specs under {gen_dir}, found none"
    names = " ".join(p.name for p in generated)
    assert "demo" in names, f"expected a generated spec for the demo feature, got: {names}"
    assert ("todomvc" in names) or ("synth" in names), (
        f"expected a generated spec for the todomvc/scanner feature, got: {names}"
    )


def _r1c_negative_control_files(files, scanner_broken):
    result_files = {}
    for path, content in files.items():
        if path.startswith("e2e/steps/") and path.endswith(".ts"):
            if path == SCANNER_STEP_PATH_IN_TODOMVC_DOC and scanner_broken:
                result_files[path] = _break_import(content)
            else:
                result_files[path] = _fix_import(content)
        else:
            result_files[path] = content
    return result_files


def test_scanner_and_scaffold_negative_control():
    """R1c negative control: same combined tree, but with every step file
    fixed EXCEPT page-scanner's own (todomvc-scan.md's e2e/steps/todo.steps.ts),
    which is force-reverted (or, today, simply left as-is) to the broken
    '@playwright/test' import. Proves the bddgen `steps: 'steps/**/*.ts'`
    glob really reaches page-scanner's file -- if this control ever goes
    green, X1's scope claim (that scaffold-bdd's own bddgen self-check would
    have caught this) is false.

    tautology::F2 note and reality check (verified live this session against
    the installed playwright-bdd@9 source): createBdd()'s runtime check
    (steps/createBdd.js's assertTestHasBddFixtures) reports its failure via
    playwright-bdd's own utils/exit.js, which prints only
    `Error: <message>` and calls `process.exit(1)` directly -- never a stack
    trace, never the failing file's path, by design (the source comment
    reads "to have less stack" / "show only needed error"). loadSteps()
    requires each step file in sequence and the process exits the instant
    one throws, so no combined stdout/stderr from a real, unmodified bddgen
    run can ever literally name which file was mid-load when it crashed --
    asserting a filename substring in that output would assert something
    genuine tool behaviour can never produce.

    The strongest attribution actually available -- and what this control
    performs instead -- is single-variable isolation: build two trees that
    are byte-identical except for the state of exactly the scanner's own
    step file (every other file always fixed in both), run bddgen on both,
    and require the all-fixed tree to succeed while the scanner-broken tree
    fails with the pinned createBdd() error. Because every other variable is
    held constant across the two runs, the pass/fail delta is attributable
    to that one file by construction -- the substance of "the error must
    name that file" when the tool itself structurally cannot.

    Expected RED reason (today): both runs exit 1 with the same createBdd()
    error, since nothing is fixed yet -- the all-fixed control run cannot
    yet succeed either, so the isolation this control performs is not yet
    demonstrated; that is itself the RED for this sub-case.
    """
    _require_tools()
    _require_live()
    state = _get_state()

    files = _combined_r1c_files(state)

    control_project = _new_project_dir(state, "r1c-negative-control-fixed")
    _write_project(control_project, _r1c_negative_control_files(files, scanner_broken=False))
    control_result = _run_bddgen(control_project / "e2e", state["env"])
    control_output = control_result.stdout + control_result.stderr
    assert control_result.returncode == 0, (
        "negative control's all-fixed baseline (every step file, including the "
        "scanner's own, importing 'test' from playwright-bdd) must succeed for the "
        "scanner-broken run below to isolate that one file as the cause; got exit "
        f"{control_result.returncode}: {control_output.strip()[-1000:]}"
    )

    project = _new_project_dir(state, "r1c-negative-control")
    _write_project(project, _r1c_negative_control_files(files, scanner_broken=True))
    result = _run_bddgen(project / "e2e", state["env"])
    combined_output = result.stdout + result.stderr

    assert result.returncode != 0, (
        "negative control must fail: the scanner's step file was deliberately "
        f"left/reverted to the broken import, but bddgen exited 0. Output: {combined_output.strip()[-1500:]}"
    )
    assert TEST_IMPORT_ERROR_TEXT in combined_output, (
        f"expected the createBdd() extended-test error in bddgen output, got: {combined_output.strip()[-1500:]}"
    )


# ===========================================================================
# R2 -- the rule *sentences* name an import source, executed rather than
# compared
# ===========================================================================

IMPORT_STATEMENT_PARTS_RE = re.compile(r"^import \{([^}]*)\} from '([^']+)';?$")


def _r2_project_files(source, import_line):
    """Build a minimal step file + feature from the extracted/mutated `test`
    import line, while independently guaranteeing `createBdd` is always
    importable from 'playwright-bdd' regardless of whether the extracted
    line also names `createBdd` itself (the plan's decided fix imports both
    `test` and `createBdd` from the same 'playwright-bdd' specifier).

    tautology::F1 fix: without stripping `createBdd` out of a mutated
    (now-'@playwright/test') import line and re-supplying it from a
    separate 'playwright-bdd' import, the R2 mutation control's synthesized
    step file would leave `createBdd` undefined at runtime -- bddgen would
    then fail with an unrelated ReferenceError instead of the pinned
    createBdd() 'should use test extended' error the control exists to
    prove, making that assertion pass or fail for the wrong reason."""
    m = IMPORT_STATEMENT_PARTS_RE.match(import_line.strip())
    names = [n.strip() for n in m.group(1).split(",") if n.strip()] if m else []
    if source == "playwright-bdd" and "createBdd" in names:
        lines = [import_line]
    else:
        kept_names = [n for n in names if n != "createBdd"] or names or ["test"]
        rebuilt = f"import {{ {', '.join(kept_names)} }} from '{source}';" if m else import_line
        lines = [rebuilt, "import { createBdd } from 'playwright-bdd';"]
    steps_ts = (
        "\n".join(lines) + "\n\n"
        "const { When } = createBdd(test);\n\n"
        "When('rule text import resolves', async () => {});\n"
    )
    feature = (
        "Feature: Rule text import check\n\n"
        "  Scenario: import source resolves\n"
        "    When rule text import resolves\n"
    )
    return {"e2e/steps/rule.steps.ts": steps_ts, "e2e/features/rule.feature": feature}


def _check_rule_source_main(state, label, span_text):
    source, import_line = _extract_test_import_source(span_text, label)
    files = _finalize_files(
        _r2_project_files(source, import_line),
        state["scaffold_pkg_json_text"], state["scaffold_playwright_config_text"],
    )
    project = _new_project_dir(state, f"r2-{label}")
    _write_project(project, files)
    result = _run_bddgen(project / "e2e", state["env"])
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"{label}: expected bddgen exit 0 using the extracted import "
        f"{import_line!r} (source={source!r}), got {result.returncode}: {combined.strip()[-1000:]}"
    )


def _check_rule_source_mutation(state, label, span_text):
    mutated = span_text.replace("playwright-bdd", "@playwright/test")
    source, import_line = _extract_test_import_source(mutated, f"{label} (mutation control)")
    files = _finalize_files(
        _r2_project_files(source, import_line),
        state["scaffold_pkg_json_text"], state["scaffold_playwright_config_text"],
    )
    project = _new_project_dir(state, f"r2-{label}-mutation")
    _write_project(project, files)
    result = _run_bddgen(project / "e2e", state["env"])
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"{label} mutation control: expected bddgen to FAIL after swapping "
        f"'playwright-bdd' for '@playwright/test' in the extracted import "
        f"({import_line!r}, source={source!r}) -- if it exits 0 the extracted "
        f"string is not being genuinely executed. Output: {combined.strip()[-1000:]}"
    )
    assert TEST_IMPORT_ERROR_TEXT in combined, (
        f"{label} mutation control: expected the createBdd() extended-test error, "
        f"got: {combined.strip()[-1000:]}"
    )


def test_rule_text_import_source_bddgens():
    """R2: two sub-cases (skills/scaffold-bdd/SKILL.md's P2, inside
    '## Hard rule: layout'; agents/page-scanner.md's pipeline step 5). Each
    regex-extracts the import-of-`test` line from the rule's own text,
    synthesises a minimal step file + feature from it, and runs bddgen.

    Expected RED reason (today, per sub-case, differing from R1/R1c):
    extraction itself fails with "no 'test' import source named in <label>"
    -- neither P2 nor page-scanner step 5 currently names any import source
    at all (P2 says only `createBdd(test)`; step 5 says `createBdd(test)`
    and plain instantiation, no import line anywhere).

    Also runs, per sub-case, a mutation control: swap 'playwright-bdd' for
    '@playwright/test' in the extracted span and require bddgen to then
    FAIL -- proving the extracted string is actually executed, not just
    compared. Today this mutation is a no-op (neither span contains the
    substring 'playwright-bdd' at all yet), so it fails for the same
    extraction reason as the main sub-case.
    """
    _require_tools()
    _require_live()
    state = _get_state()

    cases = [
        ("P2 (skills/scaffold-bdd/SKILL.md ## Hard rule: layout)", _skill_p2_span_text),
        ("page-scanner step 5 (agents/page-scanner.md)", _page_scanner_step5_span_text),
    ]

    failures = []
    for label, get_text in cases:
        span_text = get_text()
        try:
            _check_rule_source_main(state, label, span_text)
        except AssertionError as exc:
            failures.append(f"[main] {label}: {exc}")
        try:
            _check_rule_source_mutation(state, label, span_text)
        except AssertionError as exc:
            failures.append(f"[mutation] {label}: {exc}")

    assert not failures, "rule-text import source checks failed:\n" + "\n".join(failures)


# ===========================================================================
# Runner
# ===========================================================================

TESTS = [
    test_shipped_step_templates_pass_bddgen,
    test_bddgen_emits_generated_specs,
    test_step_blocks_were_actually_found,
    test_recordings_block_still_imports_playwright_test,
    test_scanner_and_scaffold_compile_together,
    test_scanner_and_scaffold_negative_control,
    test_rule_text_import_source_bddgens,
]


def main():
    failures = []
    skipped = []
    for test_fn in TESTS:
        name = test_fn.__name__
        try:
            test_fn()
        except unittest.SkipTest as exc:
            skipped.append((name, str(exc)))
        except AssertionError as exc:
            failures.append((name, str(exc)))
        except Exception as exc:  # noqa: BLE001 - report every failure, not just AssertionError
            failures.append((name, f"{type(exc).__name__}: {exc}"))

    for name, reason in skipped:
        print(f"SKIP: {name}: {reason}")

    if failures:
        for name, msg in failures:
            print(f"::error::{name}: {msg}")
        print(f"\n{len(failures)} test(s) failed, {len(skipped)} skipped.")
        return 1

    print(f"test_bddgen_step_files: OK ({len(TESTS)} test(s), {len(skipped)} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
