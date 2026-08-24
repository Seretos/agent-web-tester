#!/usr/bin/env python3
"""Validate that the Claude and Codex plugin manifests agree on their
``mcpServers`` key sets (which must include ``playwright``), that both
``playwright`` server entries are deep-equal and pinned to an exact
``@playwright/mcp`` version with the required flags, and that the docs no
longer claim this plugin ships no MCP server.

This does not assert that ``playwright`` is the *only* server either
manifest declares — only that the two manifests agree with each other and
that the ``playwright`` entry itself is well-formed.

Usage:
    python .github/scripts/validate_manifests.py     (local, Windows or *nix)
    python3 .github/scripts/validate_manifests.py    (CI, matches lint.yml)

Repo paths are resolved relative to this script's own location, so it works
the same regardless of the caller's current working directory.

Exits 0 when every assertion passes. Exits 1 otherwise, after printing every
failed assertion (not just the first) so one run shows the whole picture.
Each failure line is prefixed with ``::error::`` to match the CI-annotation
style already used by the SKILL.md frontmatter check in lint.yml.
"""
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLAUDE_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MANIFEST = REPO_ROOT / ".codex-plugin" / "plugin.json"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
README_MD = REPO_ROOT / "README.md"

# Exact version only: no 'latest', no '^'/'~', no ranges, no pre-release suffixes.
PIN_RE = re.compile(r"^@playwright/mcp@\d+\.\d+\.\d+$")

# The literal placeholder bullet currently in AGENTS.md (see line beginning
# "Planned `@playwright/mcp` wrapper.") that must be gone once the real
# contract is documented.
PLACEHOLDER_BULLET = "Planned `@playwright/mcp` wrapper."


def _flag_present(args, flag):
    """True if ``flag`` appears as a standalone arg (``--headless``) or as
    the prefix of a ``--flag=value`` arg. A naive ``flag in args`` check
    only matches an exact list element, so ``--headless=true`` or
    ``--user-data-dir=C:/tmp/pw`` would silently slip past a settled
    decision — match on the flag itself, not on incidental spelling.
    """
    prefix = flag + "="
    return any(isinstance(a, str) and (a == flag or a.startswith(prefix)) for a in args)


def load_json(path, failures):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{path}: could not read file ({exc})")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        failures.append(f"{path}: not valid JSON ({exc})")
        return None
    if not isinstance(data, dict):
        failures.append(f"{path}: top-level JSON value is not an object")
        return None
    return data


def check_playwright_server(label, server, failures):
    if not isinstance(server, dict):
        failures.append(f"{label} manifest: 'playwright' server entry is not an object")
        return

    command = server.get("command")
    if command != "npx":
        failures.append(
            f"{label} manifest: playwright server 'command' is {command!r}, expected 'npx'"
        )

    args = server.get("args")
    if not isinstance(args, list):
        failures.append(f"{label} manifest: playwright server 'args' is not a list")
        args = []

    # Index of the package-spec arg (the pin), used below to check that
    # npx's own flags precede it and the launched server's own flags follow
    # it — npx's positional parsing means everything from the package spec
    # onward is forwarded to the *launched* command, not consumed by npx
    # itself.
    pin_index = next(
        (i for i, a in enumerate(args) if isinstance(a, str) and PIN_RE.match(a)), None
    )
    if pin_index is None:
        failures.append(
            f"{label} manifest: no arg matches an exact pin '^@playwright/mcp@X.Y.Z$' "
            f"(got args={args!r}) — 'latest', ranges, '^'/'~' and pre-release suffixes "
            "are rejected"
        )

    y_index = next((i for i, a in enumerate(args) if a == "-y"), None)
    if y_index is None:
        failures.append(
            f"{label} manifest: 'npx' args must include '-y' "
            "(otherwise npx can stop at an interactive install prompt)"
        )
    elif pin_index is not None and y_index > pin_index:
        failures.append(
            f"{label} manifest: '-y' (at index {y_index}) must precede the "
            f"'@playwright/mcp@X.Y.Z' package-spec argument (at index {pin_index}) — "
            "npx treats everything from the package spec onward as arguments to the "
            "launched server, so a '-y' positioned after it no longer auto-confirms "
            "npx's own install prompt (got args="
            f"{args!r})"
        )

    if _flag_present(args, "--headless"):
        failures.append(
            f"{label} manifest: '--headless' (bare or '=value') must be absent "
            "(server must run headed by default)"
        )

    if _flag_present(args, "--user-data-dir"):
        failures.append(
            f"{label} manifest: '--user-data-dir' (bare or '=value') must be absent "
            "(use the server's own default persistent profile)"
        )

    if _flag_present(args, "--isolated"):
        failures.append(
            f"{label} manifest: '--isolated' (bare or '=value') must be absent "
            "(use the server's own default persistent profile)"
        )

    # Accept both the space-separated pair ("--browser", "chromium") and the
    # "--browser=chromium" spelling as equivalent — the decision under test
    # is *which browser*, not which of the two equally-valid CLI spellings
    # was used to say so.
    browser_index = next(
        (
            i
            for i, a in enumerate(args)
            if (a == "--browser" and i + 1 < len(args) and args[i + 1] == "chromium")
            or (isinstance(a, str) and a == "--browser=chromium")
        ),
        None,
    )
    if browser_index is None:
        failures.append(
            f"{label} manifest: playwright server args must include '--browser chromium' "
            f"(or '--browser=chromium') (got {args!r})"
        )
    elif pin_index is not None and browser_index < pin_index:
        failures.append(
            f"{label} manifest: '--browser chromium' (at index {browser_index}) must follow "
            f"the '@playwright/mcp@X.Y.Z' package-spec argument (at index {pin_index}) — "
            "npx only forwards args from the package spec onward to the launched server; "
            "before it, npx would try (and fail) to interpret '--browser' as its own "
            f"option (got args={args!r})"
        )


def check_manifest_parity(failures):
    claude = load_json(CLAUDE_MANIFEST, failures)
    codex = load_json(CODEX_MANIFEST, failures)

    if claude is None or codex is None:
        failures.append(
            "manifest parity: skipping remaining manifest checks, a manifest failed to parse"
        )
        return

    # (i) version parity — require the key on both sides first, so
    # 'neither manifest has a version' can't pass as None == None.
    claude_has_version = "version" in claude
    codex_has_version = "version" in codex
    if not claude_has_version:
        failures.append(f"{CLAUDE_MANIFEST}: missing 'version' key")
    if not codex_has_version:
        failures.append(f"{CODEX_MANIFEST}: missing 'version' key")
    if claude_has_version and codex_has_version:
        claude_version = claude.get("version")
        codex_version = codex.get("version")
        if claude_version != codex_version:
            failures.append(
                f"manifest 'version' fields differ: claude={claude_version!r} codex={codex_version!r}"
            )

    claude_servers = claude.get("mcpServers")
    codex_servers = codex.get("mcpServers")

    if claude_servers is None:
        failures.append(f"{CLAUDE_MANIFEST}: missing 'mcpServers' key")
    if codex_servers is None:
        failures.append(f"{CODEX_MANIFEST}: missing 'mcpServers' key")
    if claude_servers is None or codex_servers is None:
        failures.append(
            "manifest parity: skipping remaining mcpServers checks, key missing on at least one side"
        )
        return

    if not isinstance(claude_servers, dict):
        failures.append(f"{CLAUDE_MANIFEST}: 'mcpServers' is not an object")
        claude_servers = {}
    if not isinstance(codex_servers, dict):
        failures.append(f"{CODEX_MANIFEST}: 'mcpServers' is not an object")
        codex_servers = {}

    claude_keys = set(claude_servers.keys())
    codex_keys = set(codex_servers.keys())
    if claude_keys != codex_keys:
        failures.append(
            f"mcpServers key sets differ: claude={sorted(claude_keys)} codex={sorted(codex_keys)}"
        )

    if "playwright" not in claude_keys:
        failures.append(f"{CLAUDE_MANIFEST}: mcpServers missing 'playwright' key")
    if "playwright" not in codex_keys:
        failures.append(f"{CODEX_MANIFEST}: mcpServers missing 'playwright' key")

    claude_pw = claude_servers.get("playwright")
    codex_pw = codex_servers.get("playwright")

    if claude_pw is not None and codex_pw is not None and claude_pw != codex_pw:
        failures.append(
            "playwright server objects are not deep-equal between manifests: "
            f"claude={claude_pw!r} codex={codex_pw!r}"
        )

    if claude_pw is not None:
        check_playwright_server("claude", claude_pw, failures)
    if codex_pw is not None:
        check_playwright_server("codex", codex_pw, failures)


def check_docs(failures):
    for path in (AGENTS_MD, README_MD):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"{path}: could not read file ({exc})")
            continue
        if "no mcp server" in text.lower():
            failures.append(f"{path}: still contains the phrase 'no MCP server' (case-insensitive)")

    try:
        agents_text = AGENTS_MD.read_text(encoding="utf-8")
    except OSError as exc:
        failures.append(f"{AGENTS_MD}: could not read file ({exc})")
        return

    if PLACEHOLDER_BULLET in agents_text:
        failures.append(
            f"{AGENTS_MD}: still contains the placeholder bullet {PLACEHOLDER_BULLET!r}"
        )

    if "@playwright/mcp" not in agents_text:
        failures.append(f"{AGENTS_MD}: does not mention '@playwright/mcp'")

    if "agent-chrome-wrapper" not in agents_text:
        failures.append(f"{AGENTS_MD}: does not mention 'agent-chrome-wrapper'")


def main():
    failures = []
    check_manifest_parity(failures)
    check_docs(failures)

    if failures:
        for msg in failures:
            print(f"::error::{msg}")
        print(f"\n{len(failures)} assertion(s) failed.")
        return 1

    print("validate_manifests: OK (manifest parity + docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
