#!/usr/bin/env node
/**
 * Layout smoke guardrail (issue #417, follow-up to the S8 sidebar regression
 * in LESSONS-LEARNT #89 - a mid-animation frame lied about end-state geometry
 * and jsdom cannot measure real geometry at all).
 *
 * Drives the ALREADY-RUNNING dev server via agent-browser (headless) and
 * asserts a handful of shell invariants after ROUND-TRIPS, never mid-frame:
 *
 *   1. Sidebar collapse -> expand -> collapse: at rest, the sidebar's
 *      rendered right edge lines up with the main content's left edge (no
 *      overlap, no gap), computed transform is `none`, and the toggle is
 *      visible + clickable.
 *   2. Command-palette dialog open -> close -> reopen: the old content is
 *      unmounted, not stacked (exactly one instance in the DOM).
 *   3. Notifications sheet open -> close -> reopen: same unmount check.
 *
 * Usage: BASE_URL=http://localhost:3090 node scripts/layout-smoke.mjs
 * (also wired as `npm run layout:smoke`). Exits 0 on pass, 1 with the named
 * failing assertion(s) on fail.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_DIR = path.join(__dirname, '..');

const BASE_URL = process.env.BASE_URL || 'http://localhost:3090';
// A fixed, isolated session so this script never shares a tab with whatever
// else is driving the daemon's default session - see browser-verification.md
// "SHARED across every agent on this machine".
const SESSION = process.env.LAYOUT_SMOKE_SESSION || 'layout-smoke';
const AB_PACKAGE = 'agent-browser@0.27.0';

function loadEnvLocal() {
  const envPath = path.join(FRONTEND_DIR, '.env.local');
  if (!existsSync(envPath)) return {};
  const out = {};
  for (const line of readFileSync(envPath, 'utf8').split('\n')) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (!match) continue;
    let value = match[2];
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[match[1]] = value;
  }
  return out;
}

const envLocal = loadEnvLocal();
const E2E_EMAIL = process.env.E2E_EMAIL || envLocal.E2E_EMAIL;
const E2E_PASSWORD = process.env.E2E_PASSWORD || envLocal.E2E_PASSWORD;

function sleepMs(ms) {
  const view = new Int32Array(new SharedArrayBuffer(4));
  Atomics.wait(view, 0, 0, ms);
}

/** Runs one agent-browser command in our isolated session and parses its
 * `--json` output. Throws with the raw command + error on failure. */
function ab(args, { input } = {}) {
  const result = spawnSync(
    'npx',
    ['-y', AB_PACKAGE, '--session', SESSION, '--json', ...args],
    { encoding: 'utf8', input, maxBuffer: 10 * 1024 * 1024 },
  );
  if (result.error) {
    throw new Error(`agent-browser spawn failed for [${args.join(' ')}]: ${result.error.message}`);
  }
  const stdout = (result.stdout || '').trim();
  let parsed;
  try {
    parsed = JSON.parse(stdout);
  } catch {
    throw new Error(
      `agent-browser did not return JSON for [${args.join(' ')}]\nstdout: ${stdout}\nstderr: ${result.stderr}`,
    );
  }
  if (!parsed.success) {
    throw new Error(`agent-browser command failed [${args.join(' ')}]: ${parsed.error}`);
  }
  return parsed.data;
}

/** Best-effort variant for cleanup steps that must never abort the run. */
function abQuiet(args, opts) {
  try {
    return ab(args, opts);
  } catch {
    return null;
  }
}

const results = [];
const failures = [];

function record(name, pass, detail) {
  results.push({ name, pass, detail });
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}${detail ? ' - ' + detail : ''}`);
  if (!pass) failures.push({ name, detail });
}

function ensureLoggedIn() {
  ab(['set', 'viewport', '1280', '800']);
  ab(['open', BASE_URL]);
  let { url } = ab(['get', 'url']);
  if (!url.includes('/signin')) return;

  if (!E2E_EMAIL || !E2E_PASSWORD) {
    throw new Error(
      'Not authenticated and no E2E_EMAIL/E2E_PASSWORD available ' +
        '(checked process env and sorento_crm_frontend/.env.local).',
    );
  }
  ab(['fill', 'input[name="email"]', E2E_EMAIL]);
  ab(['fill', 'input[name="password"]', E2E_PASSWORD]);
  ab(['click', 'button[type="submit"]']);
  ab(['wait', '--load', 'networkidle']);
  ({ url } = ab(['get', 'url']));
  if (url.includes('/signin')) {
    throw new Error(`Login did not complete - still on ${url}`);
  }
}

// Reads sidebar/content geometry. The mouse is parked away from the sidebar
// first: a real cursor left at (0,0) after navigation sits inside the
// collapsed 80px rail and trips the hover-only "peek to full width" rule,
// which would misreport rest-state geometry as if nothing had collapsed.
const GEOMETRY_SCRIPT = `(() => {
  const sb = document.querySelector('.sidebar');
  const wrap = document.querySelector('.wrapper');
  if (!sb || !wrap) return { error: 'shell-elements-missing' };
  const sbRect = sb.getBoundingClientRect();
  const wrapRect = wrap.getBoundingClientRect();
  const wrapCs = getComputedStyle(wrap);
  const round = (n) => Math.round(n * 100) / 100;
  return {
    sidebarWidth: round(sbRect.width),
    sidebarRight: round(sbRect.left + sbRect.width),
    contentLeft: round(wrapRect.left + parseFloat(wrapCs.paddingLeft || '0')),
    transform: getComputedStyle(sb).transform,
    collapsed: document.body.classList.contains('sidebar-collapse'),
  };
})()`;

function readSidebarGeometry() {
  ab(['mouse', 'move', '900', '400']);
  const data = ab(['eval', '--stdin'], { input: GEOMETRY_SCRIPT });
  return data.result;
}

function geometriesEqual(a, b) {
  if (!a || !b) return false;
  return (
    a.sidebarWidth === b.sidebarWidth &&
    a.sidebarRight === b.sidebarRight &&
    a.contentLeft === b.contentLeft &&
    a.transform === b.transform &&
    a.collapsed === b.collapsed
  );
}

// Never assert a mid-animation frame (LESSONS-LEARNT #89): poll until two
// consecutive reads agree, capped so a genuinely broken layout still fails
// fast instead of hanging.
function waitForSettledGeometry({ attempts = 12, intervalMs = 150 } = {}) {
  let previous = readSidebarGeometry();
  for (let i = 0; i < attempts; i++) {
    sleepMs(intervalMs);
    const current = readSidebarGeometry();
    if (geometriesEqual(previous, current)) return { geometry: current, settled: true };
    previous = current;
  }
  return { geometry: previous, settled: false };
}

function runSidebarRoundTrip() {
  const TOGGLE = '.sidebar-header button';

  // Normalize to expanded first, so the round trip really is
  // collapse -> expand -> collapse and not whatever a previous run (or
  // another agent on the shared daemon) left the sidebar in.
  const { geometry: initial } = waitForSettledGeometry();
  if (initial?.collapsed) {
    ab(['click', TOGGLE]);
    waitForSettledGeometry();
  }

  ab(['click', TOGGLE]); // collapse
  waitForSettledGeometry();
  ab(['click', TOGGLE]); // expand
  waitForSettledGeometry();
  ab(['click', TOGGLE]); // collapse - the round trip ends here
  const { geometry: end, settled } = waitForSettledGeometry();

  record(
    'sidebar-round-trip-no-overlap-no-gap',
    settled && !!end && end.collapsed === true && end.sidebarRight === end.contentLeft,
    `settled=${settled} collapsed=${end?.collapsed} sidebarRight=${end?.sidebarRight} contentLeft=${end?.contentLeft}`,
  );
  record(
    'sidebar-round-trip-transform-none',
    end?.transform === 'none',
    `transform=${end?.transform}`,
  );

  const visible = ab(['is', 'visible', TOGGLE]).visible;
  const enabled = ab(['is', 'enabled', TOGGLE]).enabled;
  record(
    'sidebar-toggle-visible-and-clickable',
    visible === true && enabled === true,
    `visible=${visible} enabled=${enabled}`,
  );

  // Leave the shared sidebar the way it's found most often - expanded - for
  // whoever drives the daemon next.
  abQuiet(['click', TOGGLE]);
}

function runSearchDialogRoundTrip() {
  const TRIGGER = 'button[title^="Open search"]';
  const CONTENT_SELECTOR = 'input[placeholder^="Search menu"]';

  ab(['click', TRIGGER]);
  sleepMs(300);
  const afterOpen = ab(['get', 'count', CONTENT_SELECTOR]).count;

  ab(['press', 'Escape']);
  sleepMs(400); // longer than the exit animation, so it has actually unmounted
  const afterClose = ab(['get', 'count', CONTENT_SELECTOR]).count;

  ab(['click', TRIGGER]);
  sleepMs(300);
  const afterReopen = ab(['get', 'count', CONTENT_SELECTOR]).count;

  record(
    'search-dialog-round-trip-unmounts-old-content',
    afterOpen === 1 && afterClose === 0 && afterReopen === 1,
    `afterOpen=${afterOpen} afterClose=${afterClose} afterReopen=${afterReopen}`,
  );

  abQuiet(['press', 'Escape']);
}

function runNotificationsSheetRoundTrip() {
  const CONTENT_SELECTOR = '[data-slot="sheet-content"]';
  const openBell = () => ab(['find', 'role', 'button', 'click', '--name', 'Notifications']);

  openBell();
  sleepMs(300);
  const afterOpen = ab(['get', 'count', CONTENT_SELECTOR]).count;

  ab(['click', `${CONTENT_SELECTOR} [data-slot="sheet-close"]`]);
  sleepMs(400); // longer than the exit animation, so it has actually unmounted
  const afterClose = ab(['get', 'count', CONTENT_SELECTOR]).count;

  openBell();
  sleepMs(300);
  const afterReopen = ab(['get', 'count', CONTENT_SELECTOR]).count;

  record(
    'notifications-sheet-round-trip-unmounts-old-content',
    afterOpen === 1 && afterClose === 0 && afterReopen === 1,
    `afterOpen=${afterOpen} afterClose=${afterClose} afterReopen=${afterReopen}`,
  );

  abQuiet(['press', 'Escape']);
}

function main() {
  try {
    ensureLoggedIn();
    runSidebarRoundTrip();
    runSearchDialogRoundTrip();
    runNotificationsSheetRoundTrip();
  } catch (err) {
    console.error(`[ERROR] ${err instanceof Error ? err.message : String(err)}`);
    failures.push({ name: 'unexpected-error', detail: String(err) });
  } finally {
    // Close only our own named session - never --all (that closes every
    // other agent's session on the shared daemon too).
    abQuiet(['close']);
  }

  console.log('');
  if (failures.length > 0) {
    console.log(`${failures.length} of ${results.length || failures.length} assertion(s) failed:`);
    for (const failure of failures) {
      console.log(`  - ${failure.name}: ${failure.detail}`);
    }
    process.exitCode = 1;
  } else {
    console.log(`All ${results.length} assertions passed against ${BASE_URL}.`);
    process.exitCode = 0;
  }
}

main();
