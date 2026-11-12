#!/usr/bin/env node
// UI v2 capture (phase 0, G-3). A script, not a Playwright test spec (standing order: no new spec).
//
// usage: node scripts/ui-capture.mjs <manifest.json> <outdir> [--base http://127.0.0.1:3000]
//   manifest: { "email": "...", "password": "...", "routes": ["/project-sales/order-inquiries", ...],
//               "versions": ["v1","v2"], "modes": ["light","dark"], "widths": [1280, 360] }
//
// For every route x version x mode x width it signs in once (NextAuth credentials, like the never-stuck
// smoke), sets the user's UI version and theme mode through the real API, opens the route, saves a PNG,
// runs axe-core and records serious/critical violations and page-level sideways scroll. Writes
// <outdir>/report.json. Run it from sorento_crm_frontend/ so `playwright` and `axe-core` resolve.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(path.join(process.cwd(), 'package.json'));
const { chromium } = require('playwright');
const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');

const [manifestPath, outDir] = process.argv.slice(2);
const baseIdx = process.argv.indexOf('--base');
const base = baseIdx > 0 ? process.argv[baseIdx + 1] : 'http://127.0.0.1:3000';
if (!manifestPath || !outDir) {
  console.error('usage: node scripts/ui-capture.mjs <manifest.json> <outdir> [--base URL]');
  process.exit(2);
}
const m = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const versions = m.versions ?? ['v1', 'v2'];
const modes = m.modes ?? ['light', 'dark'];
const widths = m.widths ?? [1280, 360];
fs.mkdirSync(path.join(outDir, 'shots'), { recursive: true });

const slug = (s) => s.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home';

// The repo may pin a Playwright whose browser build is not downloaded; fall back to the sandbox's
// pre-installed Chromium (or PW_CHROMIUM) instead of running `playwright install`.
const browser = await chromium
  .launch()
  .catch(() => chromium.launch({ executablePath: process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium' }));
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const csrf = await (await ctx.request.get(`${base}/api/auth/csrf`)).json();
const signIn = await ctx.request.post(`${base}/api/auth/callback/credentials`, {
  form: { csrfToken: csrf.csrfToken, email: m.email, password: m.password, json: 'true', callbackUrl: `${base}/` },
  maxRedirects: 0,
});
const tokenRes = await ctx.request.get(`${base}/api/auth/token`);
if (!tokenRes.ok()) {
  console.error(`sign-in failed (${signIn.status()}), token ${tokenRes.status()}`);
  process.exit(1);
}
const { token } = await tokenRes.json();
const api = (p, body) =>
  ctx.request.put(`${base}/api/v1/user-management/users/me/${p}`, {
    data: body,
    headers: { Authorization: `Bearer ${token}` },
  });

const page = await ctx.newPage();
const report = [];
for (const version of versions) {
  const v = await api('ui-version', { ui_version: version });
  if (!v.ok()) console.warn(`could not set ui_version=${version}: HTTP ${v.status()}`);
  for (const mode of modes) {
    // v2 reads the server-side mode; v1 keeps next-themes in localStorage.
    await api('theme-mode', { theme_mode: mode });
    await page.addInitScript((md) => {
      try { localStorage.setItem('nextjs-theme', md); } catch {}
    }, mode);
    for (const width of widths) {
      await page.setViewportSize({ width, height: width < 720 ? 800 : 900 });
      for (const route of m.routes) {
        const file = `shots/${version}-${mode}-${width}-${slug(route)}.png`;
        const entry = { route, version, mode, width, file, status: 'ok' };
        try {
          await page.goto(base + route, { waitUntil: 'domcontentloaded', timeout: 120000 });
          await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
          await page.waitForTimeout(600);
          await page.screenshot({ path: path.join(outDir, file) });
          await page.addScriptTag({ content: axeSource });
          const axe = await page.evaluate(async () => {
            // eslint-disable-next-line no-undef
            const r = await axe.run(document, { resultTypes: ['violations'] });
            return r.violations
              .filter((x) => x.impact === 'serious' || x.impact === 'critical')
              .map((x) => ({ id: x.id, impact: x.impact, nodes: x.nodes.length }));
          });
          entry.axe = axe;
          entry.sidewaysScroll = await page.evaluate(
            () => document.documentElement.scrollWidth > window.innerWidth + 1,
          );
          entry.dataUi = await page.evaluate(() => document.documentElement.getAttribute('data-ui'));
        } catch (e) {
          entry.status = `fail: ${String(e.message).slice(0, 120)}`;
        }
        report.push(entry);
        fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 1));
        process.stdout.write('.');
      }
    }
  }
}
await browser.close();
const serious = report.filter((r) => (r.axe ?? []).length).length;
const sideways = report.filter((r) => r.sidewaysScroll).length;
console.log(`\n${report.length} captures, ${serious} with serious/critical axe findings, ${sideways} with sideways scroll`);
