#!/usr/bin/env python3
"""Driving tests for work package #21 (children #19 + #17): the two new
release-support scripts ``.github/scripts/prev-release-tag.sh`` and
``.github/scripts/marketplace-payload.sh``, plus a parity check between the
version-validation regex in ``.github/workflows/release.yml`` and the strict
semver filter the first script uses.

Standalone runner in this repo's ``validate_*.py`` style (collect every
failure, print all, exit 1 if any fail) but with ``test_*``-named,
zero-argument functions using plain ``assert`` statements, so ``pytest
tests/`` also works for anyone who has it installed. CI does not depend on
pytest.

Usage:
    python tests/test_release_scripts.py      (local, Windows or *nix)
    python3 tests/test_release_scripts.py     (CI, matches lint.yml)
    pytest tests/                             (optional, if installed)

Repo paths are resolved relative to this file's own location, so it works
the same regardless of the caller's current working directory.

Cross-platform invocation: scripts under test are POSIX bash, and on
Windows ``bash`` bare resolves to the WSL stub (or nothing at all), never
Git-for-Windows bash. ``_bash()`` therefore returns the absolute path
``C:\\Program Files\\Git\\bin\\bash.exe`` on ``sys.platform == "win32"`` and
plain ``"bash"`` elsewhere. If bash or ``jq`` is unavailable, the affected
tests print a notice and are skipped locally (``unittest.SkipTest``, which
both this runner and pytest understand) -- unless the ``CI`` environment
variable is set, in which case missing tooling is a hard failure, never a
silent skip.
"""
import json
import os
import random
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / ".github" / "scripts"
PREV_RELEASE_TAG_SH = SCRIPTS_DIR / "prev-release-tag.sh"
MARKETPLACE_PAYLOAD_SH = SCRIPTS_DIR / "marketplace-payload.sh"
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"

PLUGIN = "agent-web-tester"

# Corpus shared by test_regex_parity -- see Requirement 4 in the plan.
REGEX_ACCEPT = ["1.0.0", "1.0.0-rc.10", "0.0.0"]
REGEX_REJECT = ["01.0.0", "1.0", "1.0.0+build", "1.0.0-"]


# ---------------------------------------------------------------------------
# Tool availability / cross-platform invocation
# ---------------------------------------------------------------------------

def _bash():
    if sys.platform == "win32":
        return r"C:\Program Files\Git\bin\bash.exe"
    return "bash"


def _bash_available():
    try:
        proc = subprocess.run(
            [_bash(), "-c", "true"], capture_output=True, timeout=10
        )
        return proc.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _jq_available():
    try:
        proc = subprocess.run(["jq", "--version"], capture_output=True, timeout=10)
        return proc.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _require_tools(need_jq):
    """Skip locally when a required tool is missing; hard-fail instead when
    the ``CI`` env var is set, so CI can never quietly report green with a
    tool missing."""
    missing = []
    if not _bash_available():
        missing.append("bash")
    if need_jq and not _jq_available():
        missing.append("jq")
    if missing:
        message = f"required tool(s) not available: {', '.join(missing)}"
        if os.environ.get("CI"):
            raise AssertionError(f"{message} (CI is set -- this is a hard failure, not a skip)")
        raise unittest.SkipTest(message)


# ---------------------------------------------------------------------------
# Script-invocation helpers
# ---------------------------------------------------------------------------

def _run_prev_release_tag(tag_list, creating_tag):
    """Feed ``tag_list`` (already in whatever order the caller wants) on
    stdin, one tag per line, and invoke
    ``prev-release-tag.sh "$creating_tag"``. Returns the completed process --
    never raises on a nonzero exit, so the caller can assert on it."""
    stdin_text = "\n".join(tag_list) + "\n" if tag_list else ""
    return subprocess.run(
        [_bash(), PREV_RELEASE_TAG_SH.as_posix(), creating_tag],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def _run_marketplace_payload(env_overrides):
    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [_bash(), MARKETPLACE_PAYLOAD_SH.as_posix()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )


DEFAULT_PAYLOAD_ENV = {
    "NAME": "agent-web-tester",
    "DESCRIPTION": "Assistant for creating E2E web tests.",
    "REPO": "Seretos/agent-web-tester",
    "CATEGORY": "skill",
    "VERSION": "1.2.3",
    "TAG": "agent-web-tester--v1.2.3",
    "CHANGELOG": "- did a thing (#1)\n- did another thing (#2)\n",
}


def _expected_client_payload(env, changelog=None):
    """Build the expected ``client_payload`` dict for ``env`` (the exact
    field set release.yml sends today, per re-verification against the live
    file, plus the new optional ``changelog`` key)."""
    payload = {
        "name": env["NAME"],
        "description": env["DESCRIPTION"],
        "repo": env["REPO"],
        "category": env["CATEGORY"],
        "version": env["VERSION"],
        "ref": env["TAG"],
        "icon": f"https://raw.githubusercontent.com/{env['REPO']}/{env['TAG']}/assets/icon.png",
        "description_url": f"https://raw.githubusercontent.com/{env['REPO']}/{env['TAG']}/description.md",
    }
    if changelog is not None:
        payload["changelog"] = changelog
    return payload


# ===========================================================================
# Requirement 1+2 -- .github/scripts/prev-release-tag.sh
# ===========================================================================

def test_semver_ordering():
    """`prev-release-tag.sh "$TAG"` prints the highest-semver-precedence
    candidate below TAG, with correct prerelease precedence: a release beats
    its own prerelease (1.0.0 > 1.0.0-rc.1), prerelease identifiers compare
    numerically not lexically (rc.10 > rc.2), and minor/patch compare
    numerically not lexically (0.10.0 > 0.9.0). Fed with shuffled stdin
    order so the script cannot rely on input already being sorted.

    Expected RED reason: .github/scripts/prev-release-tag.sh does not exist
    yet -- bash reports "No such file or directory" and the process exits
    non-zero with empty stdout, so every assertion below fails.
    """
    _require_tools(need_jq=False)

    cases = [
        (
            [
                f"{PLUGIN}--v0.9.0",
                f"{PLUGIN}--v0.10.0",
                f"{PLUGIN}--v1.0.0-rc.2",
                f"{PLUGIN}--v1.0.0-rc.10",
                f"{PLUGIN}--v1.0.0",
            ],
            f"{PLUGIN}--v1.0.1",
            f"{PLUGIN}--v1.0.0",
            "a release (1.0.0) must win over minor/patch and prerelease candidates",
        ),
        (
            [f"{PLUGIN}--v1.0.0-rc.2", f"{PLUGIN}--v1.0.0-rc.10"],
            f"{PLUGIN}--v1.0.0",
            f"{PLUGIN}--v1.0.0-rc.10",
            "rc.10 must outrank rc.2 numerically, not lexically",
        ),
        (
            [f"{PLUGIN}--v0.9.0", f"{PLUGIN}--v0.10.0"],
            f"{PLUGIN}--v0.11.0",
            f"{PLUGIN}--v0.10.0",
            "0.10.0 must outrank 0.9.0 numerically, not lexically",
        ),
        (
            [f"{PLUGIN}--v1.0.0-rc.1", f"{PLUGIN}--v1.0.0"],
            f"{PLUGIN}--v1.0.1",
            f"{PLUGIN}--v1.0.0",
            "1.0.0 (a release) must outrank its own prerelease 1.0.0-rc.1",
        ),
    ]

    for tags, creating_tag, expected, why in cases:
        shuffled = tags[:]
        random.shuffle(shuffled)
        result = _run_prev_release_tag(shuffled, creating_tag)
        assert result.returncode == 0, (
            f"prev-release-tag.sh exited {result.returncode} for input {shuffled!r} "
            f"(creating {creating_tag!r}); stderr={result.stderr!r}"
        )
        actual = result.stdout.strip()
        assert actual == expected, (
            f"{why}: expected {expected!r}, got {actual!r} for shuffled input {shuffled!r} "
            f"(creating {creating_tag!r}); stderr={result.stderr!r}"
        )


def test_semver_ordering_single_tag():
    """Additional edge-case coverage: a single-tag candidate list."""
    _require_tools(need_jq=False)

    result = _run_prev_release_tag([f"{PLUGIN}--v0.5.0"], f"{PLUGIN}--v0.6.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v0.5.0"


def test_semver_ordering_prerelease_only_history():
    """Additional edge-case coverage: every existing tag is a prerelease."""
    _require_tools(need_jq=False)

    tags = [f"{PLUGIN}--v0.5.0-rc.1", f"{PLUGIN}--v0.5.0-rc.2", f"{PLUGIN}--v0.5.0-beta.1"]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v0.5.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v0.5.0-rc.2"


def test_excludes_non_candidates():
    """The candidate set excludes src/* markers, foreign-plugin tags,
    malformed versions, and the tag currently being created -- only a
    genuinely valid, lower, same-plugin release tag may win.

    Expected RED reason: .github/scripts/prev-release-tag.sh does not exist
    yet.
    """
    _require_tools(need_jq=False)

    creating_tag = f"{PLUGIN}--v1.0.0"
    tags = [
        f"src/{PLUGIN}--v0.9.0",       # src/* marker -- must never win
        "other-plugin--v9.9.9",        # foreign plugin -- must never win
        f"{PLUGIN}--v01.2.3",          # malformed: leading zero -- must never win
        f"{PLUGIN}--vfoo",             # malformed: not semver at all -- must never win
        creating_tag,                  # the tag being created -- must be dropped
        f"{PLUGIN}--v0.5.0",           # the one genuinely valid, lower candidate
    ]
    random.shuffle(tags)
    result = _run_prev_release_tag(tags, creating_tag)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v0.5.0", (
        f"expected only the genuinely valid candidate to win, got {result.stdout.strip()!r}"
    )


def test_excludes_only_src_tags_is_empty():
    """Additional edge-case coverage: a candidate list of only src/* tags
    (no real <plugin>--v* tags at all) must resolve exactly like an empty
    list -- src/* markers are never candidates."""
    _require_tools(need_jq=False)

    tags = [f"src/{PLUGIN}--v0.1.0", f"src/{PLUGIN}--v0.2.0"]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v1.0.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout == "", f"expected empty stdout, got {result.stdout!r}"


def test_excludes_crlf_terminated_lines():
    """Additional edge-case coverage: CRLF-terminated stdin lines (as a
    Windows-authored tag list might carry) must not defeat the exact-match
    filtering or leave a stray '\\r' in the printed tag.

    Asserts on the raw (only-newline-stripped) stdout rather than a full
    ``.strip()`` -- a full strip would remove a stray trailing '\\r' too and
    silently hide exactly the defect this test claims to catch."""
    _require_tools(need_jq=False)

    creating_tag = f"{PLUGIN}--v1.0.0"
    stdin_text = f"{PLUGIN}--v0.4.0\r\n{PLUGIN}--v0.5.0\r\n"
    result = subprocess.run(
        [_bash(), PREV_RELEASE_TAG_SH.as_posix(), creating_tag],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert "\r" not in result.stdout, (
        f"stray '\\r' in output -- CRLF input must not leak into the printed "
        f"tag: {result.stdout!r}"
    )
    assert result.stdout.rstrip("\n") == f"{PLUGIN}--v0.5.0", (
        f"CRLF-terminated input must resolve like LF input, got {result.stdout!r}"
    )


def test_excludes_higher_precedence_candidate():
    """A candidate with strictly HIGHER semver precedence than the tag being
    created must never be selected as PREV_TAG, however it sorts among the
    other candidates -- e.g. creating a backport release
    ``agent-web-tester--v0.9.1`` after ``agent-web-tester--v1.0.0`` already
    exists must resolve to ``agent-web-tester--v0.9.0``, never ``v1.0.0``.
    Regression test for reviewer finding #3 on work package #21: the
    original filter excluded only the exact tag being created, so the
    highest-precedence tag in the WHOLE candidate set won even when it
    postdated the tag being created -- silently reproducing, in the new
    script, the exact class of wrong/empty-release-notes bug this ticket
    exists to fix.
    """
    _require_tools(need_jq=False)

    tags = [f"{PLUGIN}--v1.0.0", f"{PLUGIN}--v0.9.0"]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v0.9.1")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v0.9.0", (
        f"a higher-precedence candidate ({PLUGIN}--v1.0.0) must never be "
        f"selected as PREV_TAG for a lower-precedence tag being created "
        f"({PLUGIN}--v0.9.1); got {result.stdout.strip()!r}"
    )


def test_semver_ordering_wide_numeric_component():
    """Regression test for reviewer finding (work package #21, round 2):
    the sort-key builder used a fixed PAD=20 and `printf '%0*d'` to
    zero-pad every numeric field before a byte-wise sort. SEMVER_RE places
    no length limit on a numeric field, and `printf %d` converts its
    argument through a fixed-width integer type (intmax_t, ~19 decimal
    digits) first -- so two candidates whose patch components both exceed
    that width silently clamp to the *same* overflowed value (verified
    directly: bash's own `printf` prints ``09223372036854775807`` for any
    of several distinct 24-29-digit inputs, with a "Numerical result out of
    range" warning). Old code then produces identical sort keys for both,
    and the tie-break falls through to a raw, unpadded string compare of
    the tag text itself -- which ranks a 24-digit run of 9s (numerically
    ~9.99e23) ABOVE a 29-digit "1" followed by zeros (numerically ~1e28),
    the wrong answer, because '9' > '1' lexically at the first differing
    character despite the second number being far larger. This was
    confirmed directly against the pre-fix script (git-staged blob) before
    writing this test: it printed the 24-nines tag instead of the
    29-digit-with-more-magnitude tag. PAD must instead be sized
    dynamically, per invocation, from the actual widths of every numeric
    component across the whole candidate set plus the creating tag, and
    padding must be pure string manipulation (never `printf %d`) so a wide
    numeral is never pushed through a fixed-width integer conversion.
    """
    _require_tools(need_jq=False)

    # Both patches are pathologically wide -- comfortably past both the old
    # fixed PAD=20 and the ~19 digits an intmax_t-based `printf %d`
    # conversion can hold -- but of genuinely different numeric magnitude
    # and different digit-count, so a correct implementation must still
    # rank them by true numeric value rather than by raw lexical/tag-text
    # order.
    smaller_but_lexically_bigger_leading_digit = "9" * 24          # ~9.99e23
    larger_but_lexically_smaller_leading_digit = "1" + "0" * 28    # ~1e28
    tags = [
        f"{PLUGIN}--v1.0.{smaller_but_lexically_bigger_leading_digit}",
        f"{PLUGIN}--v1.0.{larger_but_lexically_smaller_leading_digit}",
    ]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v2.0.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v1.0.{larger_but_lexically_smaller_leading_digit}", (
        f"the numerically larger (29-digit) patch must win over the "
        f"numerically smaller (24-digit) one, regardless of which sorts "
        f"first lexically as raw tag text; got {result.stdout.strip()!r}"
    )


def test_semver_ordering_prerelease_identifier_trailing_hyphen():
    """Regression test for reviewer finding (Codex, work package #21, round
    3): version_key()'s per-identifier sort-key encoding butted a variable-
    length identifier's own content directly against whatever followed --
    either the next identifier's leading '.' separator, or plain
    end-of-string -- with no delimiter of its own. That made the key
    non-self-delimiting: an identifier ending in a byte lower than '.'
    (0x2E), such as a trailing '-' (0x2D), could compare against a
    *sibling* key's following '.' instead of against a real terminator.

    Per SemVer 11.4.4, ``1.0.0-alpha-`` must have strictly HIGHER precedence
    than ``1.0.0-alpha.0``: comparing the first identifiers alone settles
    it -- ``alpha`` is a proper prefix of ``alpha-``, so ``alpha-`` (one
    character longer, same shared prefix) is lexically greater, and
    precedence is decided right there without ever looking at ``alpha.0``'s
    second identifier ``0``. The unfixed script instead compared
    ``alpha-``'s own trailing '-' against ``alpha.0``'s following '.'
    (leading its second, zero-padded numeric identifier) and got '-' < '.',
    printing ``1.0.0-alpha.0`` as the higher-precedence tag -- backwards.

    Expected RED reason (pre-fix code): prints
    ``agent-web-tester--v1.0.0-alpha.0`` instead of
    ``agent-web-tester--v1.0.0-alpha-``.
    """
    _require_tools(need_jq=False)

    tags = [f"{PLUGIN}--v1.0.0-alpha-", f"{PLUGIN}--v1.0.0-alpha.0"]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v2.0.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v1.0.0-alpha-", (
        f"1.0.0-alpha- must outrank 1.0.0-alpha.0 per SemVer 11.4.4 "
        f"(comparing first identifiers 'alpha-' vs 'alpha' alone settles "
        f"it); got {result.stdout.strip()!r}"
    )


def test_semver_ordering_prerelease_hyphen_before_dotted_numeric():
    """Additional edge-case coverage for the same delimiter-confusion class:
    a single identifier containing an embedded hyphen immediately before
    where a following dotted numeric identifier's separator would land.
    ``1.0.0-rc-1`` (one identifier, ``rc-1``) must outrank ``1.0.0-rc.1``
    (two identifiers, ``rc`` then numeric ``1``) -- comparing first
    identifiers ``rc-1`` vs ``rc`` alone settles it the same way as the
    trailing-hyphen case above."""
    _require_tools(need_jq=False)

    tags = [f"{PLUGIN}--v1.0.0-rc-1", f"{PLUGIN}--v1.0.0-rc.1"]
    result = _run_prev_release_tag(tags, f"{PLUGIN}--v2.0.0")
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    assert result.stdout.strip() == f"{PLUGIN}--v1.0.0-rc-1", (
        f"1.0.0-rc-1 must outrank 1.0.0-rc.1 per SemVer 11.4.4; got "
        f"{result.stdout.strip()!r}"
    )


def test_first_release_is_empty():
    """An empty candidate set (first release ever, or every input tag
    excluded) prints nothing on stdout and exits 0 -- not an error.

    Expected RED reason: .github/scripts/prev-release-tag.sh does not exist
    yet -- bash reports "No such file or directory" and returncode is
    non-zero (127), not 0.
    """
    _require_tools(need_jq=False)

    result = _run_prev_release_tag([], f"{PLUGIN}--v0.1.0")
    assert result.returncode == 0, (
        f"first release with an empty candidate set must exit 0, got {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert result.stdout == "", f"expected empty stdout, got {result.stdout!r}"


# ===========================================================================
# Requirement 3 -- .github/scripts/marketplace-payload.sh
# ===========================================================================

def test_payload_field_set():
    """The dispatch payload's client_payload carries exactly today's fields
    (name, description, repo, category, version, ref, icon,
    description_url -- re-verified against the live 'Dispatch to
    agent-marketplace' step) plus the new changelog key, and event_type is
    unchanged.

    Run across two environments that vary REPO and VERSION/TAG (not just the
    fixture's fixed values) -- a script that hardcoded all 8 fields and
    ignored the environment would still pass a single-environment check, so
    this also asserts that repo/version/ref/icon/description_url in the
    output actually track this variant's input, closing that tautology gap.

    Expected RED reason: .github/scripts/marketplace-payload.sh does not
    exist yet.
    """
    _require_tools(need_jq=True)

    variants = [
        dict(DEFAULT_PAYLOAD_ENV),
        {
            **DEFAULT_PAYLOAD_ENV,
            "REPO": "Seretos/some-other-plugin",
            "VERSION": "9.9.9",
            "TAG": "some-other-plugin--v9.9.9",
        },
    ]

    for env in variants:
        result = _run_marketplace_payload(env)
        assert result.returncode == 0, (
            f"marketplace-payload.sh exited {result.returncode} for env "
            f"{env!r}; stderr={result.stderr!r}"
        )
        payload = json.loads(result.stdout)
        assert payload.get("event_type") == "plugin-release", (
            f"expected event_type 'plugin-release', got {payload.get('event_type')!r}"
        )
        expected_client_payload = _expected_client_payload(env, changelog=env["CHANGELOG"])
        actual_client_payload = payload.get("client_payload")
        assert actual_client_payload == expected_client_payload, (
            f"client_payload mismatch for env {env!r}:\nexpected={expected_client_payload!r}\n"
            f"actual  ={actual_client_payload!r}"
        )
        # Guard against a hardcoded-fields implementation that ignores the
        # environment: these must genuinely track this variant's REPO and
        # VERSION/TAG, not the fixture's.
        assert actual_client_payload["repo"] == env["REPO"], (
            f"repo did not track env REPO={env['REPO']!r}: {actual_client_payload['repo']!r}"
        )
        assert actual_client_payload["version"] == env["VERSION"], (
            f"version did not track env VERSION={env['VERSION']!r}: "
            f"{actual_client_payload['version']!r}"
        )
        assert actual_client_payload["ref"] == env["TAG"], (
            f"ref did not track env TAG={env['TAG']!r}: {actual_client_payload['ref']!r}"
        )
        for field in ("icon", "description_url"):
            assert env["REPO"] in actual_client_payload[field], (
                f"{field} did not track env REPO={env['REPO']!r}: "
                f"{actual_client_payload[field]!r}"
            )
            assert env["TAG"] in actual_client_payload[field], (
                f"{field} did not track env TAG={env['TAG']!r}: "
                f"{actual_client_payload[field]!r}"
            )


def test_payload_roundtrip_hostile_changelog():
    """A changelog containing double quotes, backticks, a command
    substitution sequence, embedded newlines and a trailing blank line must
    round-trip through client_payload.changelog byte-for-byte -- proving the
    payload is built with a JSON-aware tool (jq -n), never an unquoted
    heredoc, which would corrupt or fail to parse on exactly this input.

    Expected RED reason: .github/scripts/marketplace-payload.sh does not
    exist yet.
    """
    _require_tools(need_jq=True)

    hostile_changelog = (
        'Release notes with "double quotes", `backticks`, and $(rm -rf /) '
        "inside them.\n"
        "- second line\n"
        "- third line with a trailing blank line below\n"
        "\n"
    )
    env = dict(DEFAULT_PAYLOAD_ENV)
    env["CHANGELOG"] = hostile_changelog
    result = _run_marketplace_payload(env)
    assert result.returncode == 0, (
        f"marketplace-payload.sh exited {result.returncode}; stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    actual_changelog = payload.get("client_payload", {}).get("changelog")
    assert actual_changelog == hostile_changelog, (
        f"changelog did not round-trip byte-for-byte:\nexpected={hostile_changelog!r}\n"
        f"actual  ={actual_changelog!r}"
    )


def test_payload_roundtrip_non_ascii_changelog():
    """Additional edge-case coverage: non-ASCII characters in the
    changelog must also round-trip exactly."""
    _require_tools(need_jq=True)

    changelog = "Notes with non-ASCII: caf\u00e9, \u2014 em dash, \u4e2d\u6587.\n"
    env = dict(DEFAULT_PAYLOAD_ENV)
    env["CHANGELOG"] = changelog
    result = _run_marketplace_payload(env)
    assert result.returncode == 0, f"stderr={result.stderr!r}"
    payload = json.loads(result.stdout)
    assert payload.get("client_payload", {}).get("changelog") == changelog


def test_payload_omits_empty_changelog():
    """When CHANGELOG is the empty string (the workflow has already done
    its one-time trailing-newline strip before invoking this script -- the
    script itself only checks for emptiness, it does not strip), the
    'changelog' key must be entirely absent from client_payload: not
    present as null, not present as "". Absence is the contract the
    marketplace consumer relies on to mean "no changelog section".

    Expected RED reason: .github/scripts/marketplace-payload.sh does not
    exist yet.
    """
    _require_tools(need_jq=True)

    env = dict(DEFAULT_PAYLOAD_ENV)
    env["CHANGELOG"] = ""
    result = _run_marketplace_payload(env)
    assert result.returncode == 0, (
        f"marketplace-payload.sh exited {result.returncode}; stderr={result.stderr!r}"
    )
    payload = json.loads(result.stdout)
    client_payload = payload.get("client_payload", {})
    assert "changelog" not in client_payload, (
        f"'changelog' key must be absent when CHANGELOG is empty, got "
        f"{client_payload.get('changelog')!r} present in {client_payload!r}"
    )
    # All pre-existing fields must still be present and unchanged.
    expected_client_payload = _expected_client_payload(env, changelog=None)
    assert client_payload == expected_client_payload, (
        f"client_payload mismatch with empty changelog:\nexpected={expected_client_payload!r}\n"
        f"actual  ={client_payload!r}"
    )


# ===========================================================================
# Requirement 4 -- regex parity between release.yml and prev-release-tag.sh
# ===========================================================================

def _extract_workflow_version_regex():
    """Pull the version-validation regex out of release.yml's 'Validate
    version is semver' step (`[[ ! "$V" =~ ^...$ ]]`)."""
    text = RELEASE_YML.read_text(encoding="utf-8")
    match = re.search(r'\[\[\s*!\s*"\$V"\s*=~\s*(\^.*?\$)\s*\]\]', text)
    assert match is not None, (
        "could not locate the version-validation regex in release.yml's "
        "'Validate version is semver' step -- has the step been renamed or "
        "rewritten?"
    )
    return match.group(1)


def _extract_script_version_regex():
    """Pull the strict-semver filter regex out of prev-release-tag.sh.

    Raises FileNotFoundError (via Path.read_text) when the script does not
    exist yet -- this is the expected RED reason for this half of the
    parity check before phase=implement creates the script.

    Matches a `SEMVER_RE=<quote>^...$<same quote>` assignment and captures
    everything between the anchors, verbatim -- deliberately NOT a
    character-by-character shape match against the grammar's internals (an
    earlier version of this helper anchored on the literal sequence
    "[1-9][0-9]*" right after "^(0|", which can never match a *correct*
    "no leading zero, unbounded digits" numeral pattern: the real filter
    needs a second bracket expression --"[0-9]*"-- immediately after
    "[1-9]", and no valid multi-digit grammar can place a literal digit
    character there instead without breaking correctness. That was a bug in
    the extraction helper, not a limitation of the script it inspects, so it
    is fixed here rather than worked around with a weaker implementation).
    """
    text = PREV_RELEASE_TAG_SH.read_text(encoding="utf-8")
    match = re.search(r"SEMVER_RE=(['\"])(\^.*\$)\1", text)
    assert match is not None, (
        "could not locate the strict semver filter regex in "
        "prev-release-tag.sh"
    )
    return match.group(2)


def _bash_regex_accepts(pattern, candidate):
    """Evaluate `[[ "$candidate" =~ $pattern ]]` via the same bash `=~`
    operator release.yml itself uses, rather than translating the ERE into
    Python's re syntax and risking a subtly different dialect."""
    script = (
        'if [[ "$1" =~ $2 ]]; then exit 0; else exit 1; fi'
    )
    result = subprocess.run(
        [_bash(), "-c", script, "_", candidate, pattern],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def test_regex_parity():
    """The workflow's version-validation regex and prev-release-tag.sh's
    strict semver filter must accept/reject exactly the same corpus.

    Expected RED reason (re-verified against the live release.yml, not
    assumed): the current workflow regex is
    '^[0-9]+\\.[0-9]+\\.[0-9]+(-[0-9A-Za-z.-]+)?$', which has no
    leading-zero restriction and therefore wrongly *accepts* '01.0.0' (it
    should reject it) -- that mismatch alone fails this test even before
    prev-release-tag.sh exists. Additionally, prev-release-tag.sh itself
    does not exist yet, so extracting its regex raises FileNotFoundError.
    """
    _require_tools(need_jq=False)

    workflow_regex = _extract_workflow_version_regex()

    for candidate in REGEX_ACCEPT:
        assert _bash_regex_accepts(workflow_regex, candidate), (
            f"release.yml's version regex {workflow_regex!r} must ACCEPT "
            f"{candidate!r}, but rejected it"
        )
    for candidate in REGEX_REJECT:
        assert not _bash_regex_accepts(workflow_regex, candidate), (
            f"release.yml's version regex {workflow_regex!r} must REJECT "
            f"{candidate!r}, but accepted it (this is the known looseness "
            "requirement 4 exists to close)"
        )

    # Only reached once the script (and therefore its regex) exists.
    script_regex = _extract_script_version_regex()

    for candidate in REGEX_ACCEPT:
        assert _bash_regex_accepts(script_regex, candidate), (
            f"prev-release-tag.sh's filter regex {script_regex!r} must ACCEPT "
            f"{candidate!r}, but rejected it"
        )
    for candidate in REGEX_REJECT:
        assert not _bash_regex_accepts(script_regex, candidate), (
            f"prev-release-tag.sh's filter regex {script_regex!r} must REJECT "
            f"{candidate!r}, but accepted it"
        )

    # The two preceding per-regex loops already prove each regex matches the
    # corpus's expected verdicts independently; re-running the same corpus a
    # third time to compare verdicts would be entailed by those two loops and
    # add no new information (if both loops pass, the verdicts necessarily
    # agree on this corpus). What is NOT yet proven is that the two files
    # actually share the same grammar rather than two independently-written
    # regexes that merely happen to agree on this one corpus -- so assert the
    # two extracted regex source strings are byte-identical instead, which is
    # the real, load-bearing parity contract (plan step 7: "duplicated in
    # exactly two places... both asserted by Requirement 4").
    assert workflow_regex == script_regex, (
        f"release.yml's version regex and prev-release-tag.sh's filter regex "
        f"must be byte-identical (the same grammar, duplicated verbatim):\n"
        f"workflow={workflow_regex!r}\nscript  ={script_regex!r}"
    )


def test_regex_parity_long_prerelease_chain():
    """Additional edge-case coverage: a long, valid dot-separated
    pre-release identifier chain must be accepted by both regexes."""
    _require_tools(need_jq=False)

    workflow_regex = _extract_workflow_version_regex()
    script_regex = _extract_script_version_regex()
    candidate = "1.0.0-alpha.1.2.beta"

    assert _bash_regex_accepts(workflow_regex, candidate), (
        f"release.yml's version regex must accept the long prerelease chain {candidate!r}"
    )
    assert _bash_regex_accepts(script_regex, candidate), (
        f"prev-release-tag.sh's filter regex must accept the long prerelease chain {candidate!r}"
    )


# ===========================================================================
# Runner
# ===========================================================================

TESTS = [
    test_semver_ordering,
    test_semver_ordering_single_tag,
    test_semver_ordering_prerelease_only_history,
    test_excludes_non_candidates,
    test_excludes_only_src_tags_is_empty,
    test_excludes_crlf_terminated_lines,
    test_excludes_higher_precedence_candidate,
    test_semver_ordering_wide_numeric_component,
    test_semver_ordering_prerelease_identifier_trailing_hyphen,
    test_semver_ordering_prerelease_hyphen_before_dotted_numeric,
    test_first_release_is_empty,
    test_payload_field_set,
    test_payload_roundtrip_hostile_changelog,
    test_payload_roundtrip_non_ascii_changelog,
    test_payload_omits_empty_changelog,
    test_regex_parity,
    test_regex_parity_long_prerelease_chain,
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

    print(f"test_release_scripts: OK ({len(TESTS)} test(s), {len(skipped)} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
