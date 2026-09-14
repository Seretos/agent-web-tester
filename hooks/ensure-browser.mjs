#!/usr/bin/env node
// PreToolUse hook for every `mcp__.*playwright__browser_.*` tool call
// (wired via hooks/hooks.json). Ensures the exact browser revision this
// plugin's pinned `@playwright/mcp` server expects is installed before the
// call reaches the live server -- see AGENTS.md and
// agents/page-scanner.md's "Hard rule: browser install" (B1-B3) for the
// contract this implements.
//
// Guard branches (checked in this order, each an unconditional early
// return -- none of them may spawn npx or touch the browsers cache):
//   1. Manifest at ${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json is
//      missing, unreadable, or not valid JSON.
//   2. The manifest has no mcpServers.playwright entry, or that entry has
//      no args array.
//   3. The entry's args carry no '@playwright/mcp@<pin>' argument.
//   4. The parsed <pin> does not match this repo's own strict semver
//      grammar (PIN_RE below, reused verbatim from
//      .github/scripts/prev-release-tag.sh's SEMVER_RE). This repo's own
//      manifest always pins an exact MAJOR.MINOR.PATCH with no pre-release
//      tag (see AGENTS.md's "Exact pin, no ranges" contract), so this is
//      never expected to fire in practice -- it exists so an unexpected
//      manifest value can never reach the shell command string built below
//      un-vetted. Treated like any other unparsable-manifest guard: allow,
//      don't attempt install.
//   5. The entry's --browser value is not exactly 'chromium' (covers a
//      missing --browser flag too, since the server's own default channel
//      is 'chrome', not 'chromium').
// Past those five guards, PLAYWRIGHT_BROWSERS_PATH=0 gets its own branch,
// not a sixth allow-and-skip guard: it is Playwright's documented
// per-project-local install convention, not an opt-out of installation.
// Confirmed by reading the installed @playwright/mcp's own playwright-core
// dependency (lib/coreBundle.js's registryDirectory resolver): '0' resolves
// to path.join(packageRoot, ".local-browsers"), where packageRoot is
// derived from *that particular* npx-resolved playwright-core install --
// not a path this hook can predict or reproduce from here (a different
// ephemeral npx cache directory per invocation, keyed by npm's own
// package-hash algorithm). A caller with this env var set still needs the
// browser installed somewhere, so this hook cannot allow unconditionally.
// What it CAN'T safely do is the sentinel/directory-existence fast path
// below -- it has no reliable location to check readiness against -- so it
// skips straight to provisioning on every call instead of guard-and-allow.
// This is safe because `npx ... install-browser` is itself idempotent
// (Playwright's own installer already skips a revision it finds on disk),
// so the cost is an extra fast npx invocation per call, never a genuinely
// unprovisioned browser left behind.
// Past all five guards (or the PLAYWRIGHT_BROWSERS_PATH=0 branch above): the
// fast path requires BOTH a per-pin sentinel file AND at least one
// 'chromium-*' directory containing its own 'INSTALLATION_COMPLETE' marker
// under the resolved browsers cache -- requiring only the sentinel would let
// a deleted/corrupted cache with a surviving sentinel file wrongly
// short-circuit to 'allow' and then fail inside the live server anyway (the
// exact failure this hook exists to prevent). This does not verify the
// chromium-* dir is the *expected* revision -- a stale wrong-revision dir
// with a fresh sentinel still fast paths; that is a separate,
// already-accepted residual limitation.
// Only when that combined check fails (or is skipped, for
// PLAYWRIGHT_BROWSERS_PATH=0) does this hook synchronously run
// `npx -y @playwright/mcp@<pin> install-browser chrome-for-testing` --
// cli.js rewrites the 'install-browser' positional to 'install' against
// the server's OWN pinned registry, so this installs the exact revision
// the running server expects (never a plain '@playwright/mcp@latest').
// 'chrome-for-testing' is the channel '--browser chromium' resolves to.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function allowPayload(suppressOutput) {
  const payload = {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow",
    },
  };
  if (suppressOutput) payload.suppressOutput = true;
  return payload;
}

function denyPayload(systemMessage) {
  return {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      // permissionDecisionReason is NOT confirmed in the locally cached
      // official hook-development docs (plugin-dev/skills/hook-development/
      // SKILL.md documents only permissionDecision + top-level
      // systemMessage for PreToolUse) -- set defensively in addition to,
      // never instead of, systemMessage below. Harmless if the field does
      // not exist; covers the case where it does.
      permissionDecisionReason: systemMessage,
    },
    systemMessage,
  };
}

// Writes the JSON payload to stdout and marks the process to exit 0. Never
// calls process.exit() directly: on Windows a stdout pipe can be
// asynchronous, and an explicit exit() can truncate a write that hasn't
// flushed yet. Setting exitCode and returning lets Node drain stdout and
// exit naturally once nothing else is pending.
function output(payload) {
  process.stdout.write(JSON.stringify(payload));
  process.exitCode = 0;
}

function defaultBrowsersPath() {
  if (process.platform === "win32") {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    return path.join(base, "ms-playwright");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Caches", "ms-playwright");
  }
  return path.join(os.homedir(), ".cache", "ms-playwright");
}

// Reuses this repo's own strict semver grammar verbatim --
// .github/scripts/prev-release-tag.sh's SEMVER_RE (also duplicated in
// release.yml's "Validate version is semver" step; the two are asserted
// byte-identical by tests/test_release_scripts.py::test_regex_parity).
// AGENTS.md's "Exact pin, no ranges" contract says this plugin's own
// manifest always carries a bare X.Y.Z with no pre-release tag, so this
// guard is intentionally not narrowed to reject a pre-release-shaped pin
// too: the point of PIN_RE is closing the shell-interpolation gap (no
// '$(...)', backtick, '$VAR', quote, or other shell metacharacter can
// match this grammar), not re-enforcing the manifest contract a second
// time -- that would also reject legitimate non-shippable-but-well-formed
// test fixtures like '0.0.0-does-not-exist-awt-25'.
const PIN_RE =
  /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)(\.(0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?$/;

function hasInstalledChromiumDir(browsersPath) {
  let entries;
  try {
    entries = fs.readdirSync(browsersPath, { withFileTypes: true });
  } catch {
    return false; // browsers cache dir doesn't exist (or unreadable) at all
  }
  return entries.some(
    (entry) =>
      entry.isDirectory() &&
      entry.name.startsWith("chromium-") &&
      fs.existsSync(path.join(browsersPath, entry.name, "INSTALLATION_COMPLETE"))
  );
}

async function main() {
  // The PreToolUse payload itself (tool_name/tool_input/cwd/...) is only
  // relevant to the matcher in hooks.json, which already restricted
  // dispatch to browser_* tools -- this hook has nothing further to branch
  // on inside the payload, but it still must consume stdin fully.
  await readStdin();

  const pluginRoot = process.env.CLAUDE_PLUGIN_ROOT || process.cwd();
  const manifestPath = path.join(pluginRoot, ".claude-plugin", "plugin.json");

  let manifestText;
  try {
    manifestText = fs.readFileSync(manifestPath, "utf-8");
  } catch {
    output(allowPayload(false)); // guard: manifest missing/unreadable
    return;
  }

  let manifest;
  try {
    manifest = JSON.parse(manifestText);
  } catch {
    output(allowPayload(false)); // guard: manifest not valid JSON
    return;
  }

  const playwrightEntry = manifest && manifest.mcpServers && manifest.mcpServers.playwright;
  if (!playwrightEntry || !Array.isArray(playwrightEntry.args)) {
    output(allowPayload(false)); // guard: no mcpServers.playwright entry
    return;
  }

  const args = playwrightEntry.args;
  const pinArg = args.find((a) => typeof a === "string" && a.startsWith("@playwright/mcp@"));
  if (!pinArg) {
    output(allowPayload(false)); // guard: no pinned version to install
    return;
  }
  const pin = pinArg.slice("@playwright/mcp@".length);

  if (!PIN_RE.test(pin)) {
    output(allowPayload(false)); // guard: pin does not match strict semver -- never reaches the shell
    return;
  }

  const browserFlagIdx = args.indexOf("--browser");
  const browserValue = browserFlagIdx !== -1 ? args[browserFlagIdx + 1] : undefined;
  if (browserValue !== "chromium") {
    output(allowPayload(false)); // guard: not the chromium channel
    return;
  }

  // PLAYWRIGHT_BROWSERS_PATH=0 is Playwright's per-project-local install
  // convention (see header comment above), not an opt-out -- this hook
  // cannot predict the local install location a given npx-resolved
  // playwright-core would use, so it cannot verify readiness there. Skip
  // the sentinel/fast-path shortcut entirely in that case (no sentinel to
  // write or check) and fall straight through to real provisioning below,
  // every call -- safe because the installer itself is idempotent.
  const browsersPathIsLocalOptOut = process.env.PLAYWRIGHT_BROWSERS_PATH === "0";

  let browsersPath;
  let sentinel;
  if (!browsersPathIsLocalOptOut) {
    const browsersPathEnv = process.env.PLAYWRIGHT_BROWSERS_PATH;
    browsersPath = browsersPathEnv && browsersPathEnv.length > 0 ? browsersPathEnv : defaultBrowsersPath();
    sentinel = path.join(browsersPath, `.agent-web-tester-${pin}.installed`);

    if (fs.existsSync(sentinel) && hasInstalledChromiumDir(browsersPath)) {
      output(allowPayload(true)); // fast path: sentinel + a real installed chromium dir, no npx spawn
      return;
    }
    // Either no sentinel, or a sentinel that outlived its chromium-* dir
    // (cache wiped/corrupted after install) -- both fall through to a real
    // (re)provisioning run below rather than trusting a stale marker file.
  }

  // shell: true is required on Windows: npx resolves to npx.cmd, and
  // Node's spawnSync refuses to exec a .cmd/.bat file directly without a
  // shell (EINVAL) since the CVE-2024-27980 hardening. Passing a single
  // pre-quoted command string (rather than shell: true + an args array)
  // avoids Node's DEP0190 warning about unescaped concatenation -- every
  // token here is either a fixed literal or `pin`, which was itself parsed
  // out of this plugin's own manifest via a `startsWith` match on a known
  // prefix and already gated above by PIN_RE (this repo's strict semver
  // grammar -- digits, dots, letters and hyphens only, so no `$(...)`,
  // backtick, `$VAR`, or quote character can survive to reach this
  // string). The quote() below is layered defense in depth on top of that
  // gate, not a substitute for it -- it alone does not neutralize shell
  // metacharacters under a POSIX shell.
  const quote = (s) => `"${String(s).replace(/"/g, '\\"')}"`;
  // 'npx' itself must stay unquoted: npx.cmd's own path resolution breaks
  // (MODULE_NOT_FOUND on npm-prefix.js/npx-cli.js, confirmed by hand on
  // Windows) when the command token arrives pre-quoted -- only the
  // arguments after it need quoting.
  const commandLine = ["npx", ...["-y", `@playwright/mcp@${pin}`, "install-browser", "chrome-for-testing"].map(quote)].join(
    " "
  );
  const result = spawnSync(commandLine, { encoding: "utf-8", shell: true });

  if (result.error || result.status !== 0) {
    const stderrText = (result.stderr || "").trim();
    const stdoutText = (result.stdout || "").trim();
    const spawnErrText = result.error ? String(result.error.message || result.error) : "";
    const detail = [stderrText, stdoutText, spawnErrText].filter(Boolean).join("\n") || "(installer produced no output)";
    const command = `npx -y @playwright/mcp@${pin} install-browser chrome-for-testing`;
    output(denyPayload(`Browser not provisioned: ${detail}\n\nRun: ${command}`));
    return;
  }

  // No sentinel to write for PLAYWRIGHT_BROWSERS_PATH=0: there is no
  // filesystem location this hook resolved (and therefore none it could
  // reliably re-check next call) -- every call for that env value re-runs
  // the (idempotent) install command above instead.
  if (!browsersPathIsLocalOptOut) {
    try {
      fs.mkdirSync(browsersPath, { recursive: true });
      fs.writeFileSync(sentinel, "");
    } catch {
      // The install itself succeeded; a sentinel write failure just means the
      // next call re-runs (harmless and idempotent -- the installer skips a
      // revision it already finds on disk), so this is not a failure to report.
    }
  }

  output(allowPayload(false));
}

main().catch((err) => {
  // Never let an unexpected error crash the hook (and therefore block the
  // real tool call worse than a reported failure would) -- always exit 0
  // with a deny that carries the real error text.
  output(denyPayload(`Browser not provisioned: unexpected hook error: ${(err && err.stack) || err}`));
});
