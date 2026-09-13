#!/usr/bin/env python3
"""Driving tests for work package #25: the first `browser_navigate` call
through this plugin's `playwright` MCP server (`@playwright/mcp@<pin>
--browser chromium`) must succeed even on a machine whose Playwright browser
cache is empty or holds only the wrong revision -- for ANY caller of the
tool surface, not only ones that first read this plugin's markdown.

The fix under test is a Claude-Code `PreToolUse` hook
(``hooks/ensure-browser.mjs``, wired via ``hooks/hooks.json``) that
provisions the pinned browser build before a `browser_*` tool call reaches
the live server, replacing #20's mechanism (telling the `page-scanner`
subagent to call a `browser_install` MCP tool that this ticket proved does
not exist in the server's live `tools/list`, at either 0.0.79 or 0.0.80).

Standalone runner in this repo's ``validate_*.py`` / ``test_release_scripts.py``
style (collect every failure, print all, exit 1 if any fail), ``test_*``-named
zero-argument functions using plain ``assert`` statements, so ``pytest tests/``
also works for anyone who has it installed. CI does not depend on pytest.

Usage:
    python tests/test_browser_bootstrap.py       (local, Windows or *nix)
    python3 tests/test_browser_bootstrap.py      (CI, matches lint.yml style)
    AWT_LIVE_BROWSER=1 python tests/test_browser_bootstrap.py   (run the live tests)
    pytest tests/                                (optional, if installed)

Repo paths are resolved relative to this file's own location, so it works
the same regardless of the caller's current working directory.

Live-test gating (``AWT_LIVE_BROWSER=1``): every test in this module spawns
a real ``node`` process running ``hooks/ensure-browser.mjs`` and/or a real
``npx``-launched Playwright MCP server over stdio -- several of them also
perform a genuine browser-binary install (network access, up to ~150 MiB
download) or a genuine failing ``npx`` install against a deliberately
nonexistent package version. None of that is mocked -- the ticket's own
premise (regression chain #20/#23) is that a markdown-only or mocked "fix"
ships broken, so this suite only ever exercises the real server binary and
the real installer. Because that is slow and needs network, every test
requires ``AWT_LIVE_BROWSER=1`` to run at all; without it, every test in
this module is skipped with an explicit message, never silently omitted. A
dedicated `browser-bootstrap` CI job (added in phase=implement) sets this
unconditionally; local runs skip by default. Separately, ``node``/``npx``
themselves are required tooling for this module (the hook script is
JavaScript) -- missing tooling is an ``unittest.SkipTest`` locally but a
hard failure whenever the ``CI`` env var is set, so CI can never quietly
report green with a tool missing (same discipline as
``tests/test_release_scripts.py``'s ``_require_tools``).

Claude Code PreToolUse hook JSON contract used to build the stdin payloads
and to assert on the hook's stdout below (``hook_event_name``, ``session_id``,
``transcript_path``, ``cwd``, ``tool_name``, ``tool_input`` on stdin;
``hookSpecificOutput.permissionDecision`` / ``systemMessage`` on stdout) was
verified this session directly against the installed ``claude`` CLI binary's
own embedded documentation strings (its ``--help``/docs text is bundled
verbatim in the executable) -- not assumed, and not found in any project
file. The extra common dispatch fields (``session_id``, ``transcript_path``,
``cwd``) are included in every payload since a real dispatch always carries
them and a hook that required them would otherwise go untested.
"""
import contextlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
ENSURE_BROWSER_MJS = HOOKS_DIR / "ensure-browser.mjs"
CLAUDE_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
AGENTS_MD = REPO_ROOT / "AGENTS.md"
AGENTS_DIR = REPO_ROOT / "agents"
SKILLS_DIR = REPO_ROOT / "skills"
DOCS_DIR = REPO_ROOT / "docs"

LIVE_ENV_VAR = "AWT_LIVE_BROWSER"
# Single, consistent bound for the fast-path steady-state runtime (plan-critic
# note: an earlier review round stated two conflicting numbers -- 5s is the
# one bound used everywhere in this file).
FAST_PATH_TIMEOUT_S = 5

TOOL_NAME_NAVIGATE = "mcp__plugin_agent-web-tester_playwright__browser_navigate"


# ---------------------------------------------------------------------------
# Tool availability / gating
# ---------------------------------------------------------------------------

def _require_tools():
    """Skip locally when node/npx are missing; hard-fail instead when the
    ``CI`` env var is set, so CI can never quietly report green with a tool
    missing (same pattern as test_release_scripts.py's _require_tools)."""
    missing = [name for name in ("node", "npx") if shutil.which(name) is None]
    if missing:
        message = f"required tool(s) not available: {', '.join(missing)}"
        if os.environ.get("CI"):
            raise AssertionError(f"{message} (CI is set -- this is a hard failure, not a skip)")
        raise unittest.SkipTest(message)


def _require_live():
    """Every test in this module spawns a real node process and/or a real
    npx-launched MCP server, and several perform a genuine network install.
    Skip unless the caller opted in -- the dedicated browser-bootstrap CI job
    sets this unconditionally; local/general-lint runs skip by default."""
    if os.environ.get(LIVE_ENV_VAR) != "1":
        raise unittest.SkipTest(
            f"requires {LIVE_ENV_VAR}=1 -- spawns a real npx-launched Playwright MCP "
            "server over stdio and/or performs a real browser-binary install (network "
            "access, up to ~150 MiB download)"
        )


def _resolve_command(command):
    resolved = shutil.which(command)
    if resolved is None:
        raise AssertionError(f"command {command!r} not found on PATH")
    return resolved


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def _manifest_playwright_entry(manifest_path=CLAUDE_MANIFEST):
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return data["mcpServers"]["playwright"]


def _manifest_pin(manifest_path=CLAUDE_MANIFEST):
    entry = _manifest_playwright_entry(manifest_path)
    for arg in entry["args"]:
        if arg.startswith("@playwright/mcp@"):
            return arg.split("@playwright/mcp@", 1)[1]
    raise AssertionError(
        f"no '@playwright/mcp@<pin>' argument found in {manifest_path}'s mcpServers.playwright.args"
    )


def _write_temp_plugin_manifest(root, playwright_entry):
    """Write a minimal .claude-plugin/plugin.json under ``root``.
    ``playwright_entry`` of None omits mcpServers.playwright entirely (the
    "missing key" guard case); otherwise it's the raw mcpServers.playwright
    dict (command/args)."""
    plugin_dir = root / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": "agent-web-tester",
        "version": "0.0.0",
        "mcpServers": {"playwright": playwright_entry} if playwright_entry is not None else {},
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Minimal MCP stdio client (initialize / notifications/initialized /
# tools/list / tools/call) -- drives the REAL server process, no mocking.
# ---------------------------------------------------------------------------

class McpSession:
    def __init__(self, args, env=None, cwd=None, command="npx"):
        full_env = dict(os.environ)
        if env is not None:
            full_env.update(env)
        self.proc = subprocess.Popen(
            [_resolve_command(command)] + list(args),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=full_env, cwd=cwd,
        )
        self._queue = queue.Queue()
        self._reader_thread = threading.Thread(target=self._reader, daemon=True)
        self._reader_thread.start()
        self._next_id = 1

    def _reader(self):
        try:
            for line in self.proc.stdout:
                line = line.strip()
                if line:
                    self._queue.put(line)
        except Exception:
            pass

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None, timeout=90):
        req_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = self._queue.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == req_id:
                return msg
        stderr_tail = self._drain_stderr()
        raise TimeoutError(
            f"no response to {method!r} within {timeout}s; stderr so far: {stderr_tail!r}"
        )

    def _drain_stderr(self):
        try:
            self.proc.stderr.flush()
        except Exception:
            pass
        return ""

    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def initialize(self):
        result = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test_browser_bootstrap", "version": "0"},
        })
        self.notify("notifications/initialized")
        return result

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


@contextlib.contextmanager
def _mcp_server(env=None, cwd=None, manifest_path=CLAUDE_MANIFEST):
    """Launch the playwright MCP server using the MANIFEST's own
    command/args (per the plan: never hardcode --browser chromium
    separately -- read it from .claude-plugin/plugin.json)."""
    entry = _manifest_playwright_entry(manifest_path)
    session = McpSession(entry["args"], env=env, cwd=cwd, command=entry["command"])
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Hook-invocation helpers
# ---------------------------------------------------------------------------

def _pretooluse_payload(tool_name=TOOL_NAME_NAVIGATE, tool_input=None, cwd=None):
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "test-browser-bootstrap-session",
        "transcript_path": str(Path(tempfile.gettempdir()) / "awt-test-transcript.jsonl"),
        "cwd": str(cwd if cwd is not None else REPO_ROOT),
        "tool_name": tool_name,
        "tool_input": tool_input if tool_input is not None else {"url": "about:blank"},
    }


def _run_hook(payload, env=None, plugin_root=None, timeout=180):
    """Run hooks/ensure-browser.mjs with ``payload`` piped to stdin as JSON,
    with CLAUDE_PLUGIN_ROOT pointing at ``plugin_root`` (defaults to this
    repo's own root -- the real layout when this plugin is installed and
    running from its own checkout)."""
    full_env = dict(os.environ)
    full_env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root if plugin_root is not None else REPO_ROOT)
    if env:
        full_env.update(env)
    return subprocess.run(
        [_resolve_command("node"), str(ENSURE_BROWSER_MJS)],
        input=json.dumps(payload),
        capture_output=True, text=True, encoding="utf-8",
        env=full_env, timeout=timeout,
    )


def _assert_hook_allows(proc, context=""):
    assert proc.returncode == 0, f"{context}hook exited {proc.returncode}; stderr={proc.stderr!r}"
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"{context}hook stdout was not valid JSON ({exc}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    hso = payload.get("hookSpecificOutput") or {}
    assert hso.get("permissionDecision") == "allow", (
        f"{context}expected hookSpecificOutput.permissionDecision == 'allow', got "
        f"payload={payload!r}; stderr={proc.stderr!r}"
    )
    return payload


# ===========================================================================
# Requirement 1 -- first browser_navigate succeeds on an unprovisioned machine
# ===========================================================================

def test_hook_provisions_then_navigate_succeeds():
    """The hook provisions the pinned browser build on an empty
    PLAYWRIGHT_BROWSERS_PATH, then a real browser_navigate call against the
    manifest's own pinned server succeeds.

    Expected RED reason (today): hooks/ensure-browser.mjs does not exist --
    node reports a "Cannot find module" error and the hook subprocess exits
    non-zero, so _assert_hook_allows fails on the returncode check before
    ever reaching the MCP session. Once the script exists but its install
    logic is incomplete/missing, the driving assertion that fails instead is
    the live browser_navigate call still returning isError: true ("not
    installed").
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-browsers-", ignore_cleanup_errors=True) as browsers_dir, \
         tempfile.TemporaryDirectory(prefix="awt-mcp-cwd-", ignore_cleanup_errors=True) as mcp_cwd:
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, timeout=300)
        _assert_hook_allows(proc, context="provisioning run: ")

        pin = _manifest_pin()
        sentinel = Path(browsers_dir) / f".agent-web-tester-{pin}.installed"
        assert sentinel.is_file(), (
            f"expected sentinel file {sentinel} to exist after the hook provisioned the "
            f"browser; browsers_dir contents={sorted(p.name for p in Path(browsers_dir).iterdir())}"
        )

        with _mcp_server(env=env, cwd=mcp_cwd) as session:
            init = session.initialize()
            assert "result" in init, f"initialize failed: {init}"
            nav = session.request(
                "tools/call", {"name": "browser_navigate", "arguments": {"url": "about:blank"}}, timeout=60
            )
            assert "result" in nav, f"browser_navigate returned no result envelope: {nav}"
            result = nav["result"]
            assert result.get("isError") is not True, (
                f"browser_navigate returned an error after the hook claimed to provision the "
                f"browser: {nav}"
            )


def test_hook_provisions_over_wrong_revision_cache():
    """Additional edge-case coverage (not hypothetical -- this dev machine's
    own real Playwright cache already has exactly this shape: chromium-1223
    and chromium-1243 present, not the 1237 that @playwright/mcp@0.0.79
    expects, confirmed this session). A wrong-revision chromium-* dir with no
    sentinel must still provision the correct revision and succeed.

    Expected RED reason: same as test_hook_provisions_then_navigate_succeeds
    -- the hook script does not exist yet.
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-browsers-wrongrev-", ignore_cleanup_errors=True) as browsers_dir, \
         tempfile.TemporaryDirectory(prefix="awt-mcp-cwd-", ignore_cleanup_errors=True) as mcp_cwd:
        wrong_rev_dir = Path(browsers_dir) / "chromium-1223"
        wrong_rev_dir.mkdir(parents=True)
        (wrong_rev_dir / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")

        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, timeout=300)
        _assert_hook_allows(proc, context="wrong-revision provisioning run: ")

        with _mcp_server(env=env, cwd=mcp_cwd) as session:
            session.initialize()
            nav = session.request(
                "tools/call", {"name": "browser_navigate", "arguments": {"url": "about:blank"}}, timeout=60
            )
            assert "result" in nav, f"browser_navigate returned no result envelope: {nav}"
            result = nav["result"]
            assert result.get("isError") is not True, (
                f"browser_navigate still failed with a stale wrong-revision cache present: {nav}"
            )


# ===========================================================================
# Requirement 2 -- steady state costs no npx spawn
# ===========================================================================

def test_hook_fast_path_does_not_install():
    """With the sentinel AND a genuinely-installed chromium-* dir present
    (the true steady-state shape -- see test_hook_stale_sentinel_without_chromium_dir_falls_through_to_provisioning
    for the "sentinel survives a wiped cache" case, which must NOT take this
    path), the hook must allow immediately without spawning npx/installing
    anything, and must run well under FAST_PATH_TIMEOUT_S.

    Expected RED reason: hooks/ensure-browser.mjs does not exist yet -- the
    node subprocess errors and _assert_hook_allows fails on returncode. Once
    the script exists but has no sentinel fast path, it would spawn npx and
    create a real chromium-* dir / take much longer than the bound.
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-browsers-fastpath-", ignore_cleanup_errors=True) as browsers_dir:
        pin = _manifest_pin()
        sentinel = Path(browsers_dir) / f".agent-web-tester-{pin}.installed"
        sentinel.write_text("", encoding="utf-8")
        installed_dir = Path(browsers_dir) / "chromium-1237"
        installed_dir.mkdir(parents=True)
        (installed_dir / "INSTALLATION_COMPLETE").write_text("", encoding="utf-8")

        before = {p.name for p in Path(browsers_dir).iterdir()}
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}

        start = time.monotonic()
        proc = _run_hook(_pretooluse_payload(), env=env, timeout=60)
        elapsed = time.monotonic() - start

        _assert_hook_allows(proc, context="fast-path run: ")

        after = {p.name for p in Path(browsers_dir).iterdir()}
        new_chromium_dirs = {n for n in (after - before) if n.startswith("chromium-")}
        assert not new_chromium_dirs, (
            f"fast path must not spawn npx/install anything: found new chromium-* dir(s) "
            f"{sorted(new_chromium_dirs)} that were not present before the hook ran"
        )
        assert elapsed < FAST_PATH_TIMEOUT_S, (
            f"fast path took {elapsed:.2f}s, expected under {FAST_PATH_TIMEOUT_S}s (a hook "
            "without the sentinel short-circuit would spawn npx and take much longer)"
        )


def test_hook_stale_sentinel_without_chromium_dir_falls_through_to_provisioning():
    """R5 regression coverage: a sentinel file alone must NOT be trusted as
    proof the browser is installed. If the actual chromium-<rev> directory
    under the browsers cache was deleted or corrupted while the sentinel
    file survives, the hook must fall through to real provisioning instead
    of fast-path allowing (which would let browser_navigate fail anyway --
    the exact failure this hook exists to prevent).

    Seeds ONLY the sentinel (no chromium-* directory at all), then asserts
    the hook performs a genuine (re)install: it must still end in 'allow',
    but only after creating a real chromium-* directory -- proof it did not
    take the fast path.

    Expected RED reason (pre-fix): the fast path trusted the sentinel alone,
    so this run would allow immediately with NO new chromium-* dir created,
    failing the assertion below that one now exists.
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-browsers-stale-sentinel-", ignore_cleanup_errors=True) as browsers_dir:
        pin = _manifest_pin()
        sentinel = Path(browsers_dir) / f".agent-web-tester-{pin}.installed"
        sentinel.write_text("", encoding="utf-8")

        assert not any(p.name.startswith("chromium-") for p in Path(browsers_dir).iterdir()), (
            "test setup error: no chromium-* dir must exist yet"
        )

        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, timeout=300)
        _assert_hook_allows(proc, context="stale-sentinel fallthrough run: ")

        chromium_dirs = [p for p in Path(browsers_dir).iterdir() if p.name.startswith("chromium-")]
        assert chromium_dirs, (
            "expected the hook to fall through to real provisioning and create a "
            "chromium-* dir when the sentinel survives without one -- found none, "
            f"browsers_dir contents={sorted(p.name for p in Path(browsers_dir).iterdir())}"
        )


def test_hook_guard_browsers_path_zero():
    """Round-3 correction: PLAYWRIGHT_BROWSERS_PATH=0 is NOT Playwright's
    opt-out of browser installation -- it is a documented, real
    per-project-local install convention (confirmed this round by reading
    the installed @playwright/mcp's own playwright-core dependency's
    lib/coreBundle.js: '0' makes registryDirectory resolve to
    path.join(packageRoot, ".local-browsers"), a real, resolvable directory
    under whatever npx-resolved playwright-core install is running -- never
    "nothing to install"). A caller with this env var set still needs the
    browser installed somewhere, so the corrected hook must still end in
    'allow' here only because it performed a real (idempotent) provisioning
    attempt, not as a blanket guard-and-skip.

    This test alone can only observe the happy-path outcome (allow); it
    cannot prove *why* the hook allowed (real work vs. a disguised blanket
    allow) since this hook cannot resolve the actual local install path to
    inspect it afterward. See
    test_hook_browsers_path_zero_bad_pin_reports_failure directly below for
    the positive proof that real provisioning -- not a shortcut -- is what
    is happening here.

    Expected RED reason (pre-fix): the guard returned an unconditional
    allow(false) for PLAYWRIGHT_BROWSERS_PATH=0 with no install attempt at
    all -- this assertion still passes trivially against that old code
    (both are 'allow'), which is exactly why the bad-pin companion test
    below is the one that actually distinguishes correct from incorrect
    behavior.
    """
    _require_tools()
    _require_live()

    env = {"PLAYWRIGHT_BROWSERS_PATH": "0"}
    proc = _run_hook(_pretooluse_payload(), env=env, timeout=300)
    _assert_hook_allows(proc, context="PLAYWRIGHT_BROWSERS_PATH=0 real-provisioning run: ")


def test_hook_browsers_path_zero_bad_pin_reports_failure():
    """Positive proof that PLAYWRIGHT_BROWSERS_PATH=0 triggers REAL
    provisioning rather than a disguised blanket allow: pointing the
    manifest at a genuinely nonexistent @playwright/mcp version (same
    technique as test_hook_reports_install_failure) while
    PLAYWRIGHT_BROWSERS_PATH=0 is set must still surface a 'deny' with the
    real npx error text. A hook that still treated '0' as "nothing to
    check here, always allow" would never spawn npx at all in this branch
    and would wrongly allow even a pin that cannot possibly install.

    Expected RED reason (pre-fix): the PLAYWRIGHT_BROWSERS_PATH=0 guard
    unconditionally allowed before ever looking at the pin, so this
    bad-pin manifest incorrectly allowed instead of denying.
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-badpin-bp0-", ignore_cleanup_errors=True) as plugin_root_dir:
        plugin_root = Path(plugin_root_dir)
        _write_temp_plugin_manifest(plugin_root, {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@0.0.0-does-not-exist-awt-25", "--browser", "chromium"],
        })
        env = {"PLAYWRIGHT_BROWSERS_PATH": "0"}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=120)

        assert proc.returncode == 0, (
            f"hook must exit 0 even on install failure (never crash); got {proc.returncode}; "
            f"stderr={proc.stderr!r}"
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"hook stdout was not valid JSON ({exc}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        hso = payload.get("hookSpecificOutput") or {}
        assert hso.get("permissionDecision") == "deny", (
            "expected hookSpecificOutput.permissionDecision == 'deny' -- a hook that still "
            "treats PLAYWRIGHT_BROWSERS_PATH=0 as blanket-allow would wrongly allow this "
            f"doomed-to-fail pin instead of attempting (and failing) real provisioning; got "
            f"payload={payload!r}"
        )
        system_message = payload.get("systemMessage", "")
        assert system_message.startswith("Browser not provisioned: "), (
            f"systemMessage must start with the literal 'Browser not provisioned: ', "
            f"got {system_message!r}"
        )


def test_hook_guard_non_chromium_browser():
    """A manifest whose playwright entry pins a --browser value other than
    'chromium' must allow unchanged, with nothing written into the browsers
    path -- guard branch, may pass trivially once implemented.

    Expected RED reason: hooks/ensure-browser.mjs does not exist yet.
    """
    _require_tools()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-nonchromium-", ignore_cleanup_errors=True) as plugin_root_dir, \
         tempfile.TemporaryDirectory(prefix="awt-browsers-guard-nonchromium-", ignore_cleanup_errors=True) as browsers_dir:
        plugin_root = Path(plugin_root_dir)
        _write_temp_plugin_manifest(plugin_root, {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@0.0.79", "--browser", "firefox"],
        })
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=30)
        _assert_hook_allows(proc, context="non-chromium guard: ")
        assert list(Path(browsers_dir).iterdir()) == [], (
            "non-chromium guard must never write anything into the browsers path"
        )


# ===========================================================================
# Requirement 3 -- provisioning failure is reported, never silently swallowed
# ===========================================================================

def test_hook_reports_install_failure():
    """A manifest pinning a genuinely nonexistent @playwright/mcp version
    (no mocking -- the real npm registry really has no such version, and the
    real `npx install-browser` invocation really fails against it) must
    result in permissionDecision 'deny' with a systemMessage that starts
    with the literal 'Browser not provisioned: ' and includes the real npx
    error text.

    Expected RED reason: this code path does not exist today -- the whole
    script is absent.
    """
    _require_tools()
    _require_live()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-badpin-", ignore_cleanup_errors=True) as plugin_root_dir, \
         tempfile.TemporaryDirectory(prefix="awt-browsers-fail-", ignore_cleanup_errors=True) as browsers_dir:
        plugin_root = Path(plugin_root_dir)
        _write_temp_plugin_manifest(plugin_root, {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@0.0.0-does-not-exist-awt-25", "--browser", "chromium"],
        })
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=120)

        assert proc.returncode == 0, (
            f"hook must exit 0 even on install failure (never crash); got {proc.returncode}; "
            f"stderr={proc.stderr!r}"
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"hook stdout was not valid JSON ({exc}): stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
        hso = payload.get("hookSpecificOutput") or {}
        assert hso.get("permissionDecision") == "deny", (
            f"expected hookSpecificOutput.permissionDecision == 'deny', got payload={payload!r}"
        )
        system_message = payload.get("systemMessage", "")
        assert system_message.startswith("Browser not provisioned: "), (
            f"systemMessage must start with the literal 'Browser not provisioned: ', "
            f"got {system_message!r}"
        )
        assert len(system_message) > len("Browser not provisioned: "), (
            f"systemMessage has no installer error text appended after the prefix: {system_message!r}"
        )


def test_hook_guard_unparsable_manifest():
    """A .claude-plugin/plugin.json that is not valid JSON must never make a
    browser_* tool call worse than today: allow unchanged, no install
    attempt.

    Expected RED reason: hooks/ensure-browser.mjs does not exist yet.
    """
    _require_tools()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-badjson-", ignore_cleanup_errors=True) as plugin_root_dir, \
         tempfile.TemporaryDirectory(prefix="awt-browsers-guard-badjson-", ignore_cleanup_errors=True) as browsers_dir:
        plugin_root = Path(plugin_root_dir)
        plugin_dir = plugin_root / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text("{ not valid json", encoding="utf-8")

        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=30)
        _assert_hook_allows(proc, context="unparsable-manifest guard: ")
        assert list(Path(browsers_dir).iterdir()) == [], (
            "an unparsable manifest must never attempt to install/write anything"
        )


def test_hook_guard_unsafe_pin_value():
    """R6 regression coverage: a manifest pin that does not match this
    repo's strict semver grammar (PIN_RE in hooks/ensure-browser.mjs, reused
    from .github/scripts/prev-release-tag.sh's SEMVER_RE) must never reach
    the shell command string built from it. Uses a pin containing shell
    metacharacters ('$(whoami)') that
    would, if interpolated unguarded into spawnSync(cmd, {shell: true}),
    let a POSIX shell perform command substitution -- the quote() helper
    alone only escapes double-quotes and does not neutralize this.

    Asserts the hook allows unchanged (same as any other unparsable-manifest
    guard) and writes nothing into the browsers path, proving no shell
    command was ever built/run with the unsafe value.

    Expected RED reason (pre-fix): the hook had no pin-format guard, so it
    would proceed to build and run a real spawnSync command line containing
    the literal '$(whoami)' substring, spawning npx with an attempted
    (malformed) package spec instead of safely guarding.
    """
    _require_tools()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-unsafepin-", ignore_cleanup_errors=True) as plugin_root_dir, \
         tempfile.TemporaryDirectory(prefix="awt-browsers-guard-unsafepin-", ignore_cleanup_errors=True) as browsers_dir:
        plugin_root = Path(plugin_root_dir)
        _write_temp_plugin_manifest(plugin_root, {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@0.0.79$(whoami)", "--browser", "chromium"],
        })
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=30)
        _assert_hook_allows(proc, context="unsafe-pin guard: ")
        assert list(Path(browsers_dir).iterdir()) == [], (
            "an unsafe (non-semver) pin must never attempt to install/write anything"
        )


def test_hook_guard_missing_playwright_server_key():
    """Additional edge-case coverage: a manifest that parses fine but has no
    mcpServers.playwright key at all must also allow unchanged."""
    _require_tools()

    with tempfile.TemporaryDirectory(prefix="awt-plugin-root-nomcp-", ignore_cleanup_errors=True) as plugin_root_dir, \
         tempfile.TemporaryDirectory(prefix="awt-browsers-guard-nomcp-", ignore_cleanup_errors=True) as browsers_dir:
        plugin_root = Path(plugin_root_dir)
        _write_temp_plugin_manifest(plugin_root, None)
        env = {"PLAYWRIGHT_BROWSERS_PATH": browsers_dir}
        proc = _run_hook(_pretooluse_payload(), env=env, plugin_root=plugin_root, timeout=30)
        _assert_hook_allows(proc, context="missing mcpServers.playwright guard: ")


# ===========================================================================
# Requirement 4 -- no shipped document names a tool the live server does not
# expose (the direct guard against #20's failure mode)
# ===========================================================================

BROWSER_TOOL_RE = re.compile(r"\bbrowser_[a-z_]+\b")


def _iter_doc_files():
    files = []
    if AGENTS_MD.is_file():
        files.append(AGENTS_MD)
    if AGENTS_DIR.is_dir():
        files.extend(sorted(AGENTS_DIR.glob("*.md")))
    if SKILLS_DIR.is_dir():
        files.extend(sorted(SKILLS_DIR.glob("**/SKILL.md")))
    if DOCS_DIR.is_dir():
        files.extend(sorted(DOCS_DIR.rglob("*.md")))
    return files


def test_documented_browser_tools_exist_live():
    """Scan agents/*.md, skills/**/SKILL.md, AGENTS.md, and docs/** (all
    shipped release artifacts per AGENTS.md) for 'browser_[a-z_]+'
    identifiers, then spawn the manifest's own pinned server and assert the
    collected identifier set is a subset of the live tools/list.

    Expected RED reason (re-verified this session by actually spawning the
    pinned 0.0.79 server and reading its live tools/list): agents/page-scanner.md
    and AGENTS.md both name 'browser_install', which is absent from the live
    tool surface (confirmed directly; the tool names present instead include
    browser_navigate, browser_snapshot, browser_click, browser_type,
    browser_fill_form, browser_evaluate, and others, but never browser_install).
    """
    _require_tools()
    _require_live()

    identifiers = set()
    per_file = {}
    for f in _iter_doc_files():
        text = f.read_text(encoding="utf-8")
        found = set(BROWSER_TOOL_RE.findall(text))
        if found:
            per_file[f] = found
        identifiers |= found

    assert identifiers, (
        "expected at least one 'browser_*' identifier across the scanned docs -- "
        "the scan produced nothing, which would make the subset check below vacuous"
    )

    with tempfile.TemporaryDirectory(prefix="awt-mcp-cwd-toollist-", ignore_cleanup_errors=True) as mcp_cwd:
        with _mcp_server(cwd=mcp_cwd) as session:
            init = session.initialize()
            assert "result" in init, f"initialize failed: {init}"
            listing = session.request("tools/list", timeout=60)
            tools = listing.get("result", {}).get("tools", [])
            live_names = {t["name"] for t in tools}

    assert live_names, (
        "tools/list returned no tools at all -- a broken/empty response must not "
        "vacuously pass this test"
    )
    assert "browser_navigate" in live_names, (
        f"expected 'browser_navigate' in the live tool surface, got {sorted(live_names)}"
    )
    assert "browser_snapshot" in live_names, (
        f"expected 'browser_snapshot' in the live tool surface, got {sorted(live_names)}"
    )

    undocumented_but_named = identifiers - live_names
    assert not undocumented_but_named, (
        f"the following 'browser_*' identifiers are named in shipped docs but do not "
        f"exist in the live server's tools/list: {sorted(undocumented_but_named)} "
        f"(found in: {sorted(str(f.relative_to(REPO_ROOT)) for f, names in per_file.items() if names & undocumented_but_named)})"
    )


# ===========================================================================
# Runner
# ===========================================================================

TESTS = [
    test_hook_provisions_then_navigate_succeeds,
    test_hook_provisions_over_wrong_revision_cache,
    test_hook_fast_path_does_not_install,
    test_hook_stale_sentinel_without_chromium_dir_falls_through_to_provisioning,
    test_hook_guard_browsers_path_zero,
    test_hook_browsers_path_zero_bad_pin_reports_failure,
    test_hook_guard_non_chromium_browser,
    test_hook_reports_install_failure,
    test_hook_guard_unparsable_manifest,
    test_hook_guard_unsafe_pin_value,
    test_hook_guard_missing_playwright_server_key,
    test_documented_browser_tools_exist_live,
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

    print(f"test_browser_bootstrap: OK ({len(TESTS)} test(s), {len(skipped)} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
