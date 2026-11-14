// Re-runnable training-video recorder.
//
//   node scripts/training-videos/lib/recorder.mjs <video-id> [--no-voice]
//
// A video is a spec in ../videos/<id>.mjs: a title plus ordered steps, each step carrying
// its on-screen caption (en), its Malay subtitle (ms), its voice line (say, defaults to en)
// and the browser action. One run = voice clips first (so each step knows how long its
// narration lasts), then a Playwright recording at 1280x720 that holds every step at least
// as long as its narration, then ffmpeg lays the clips on the video at the step start times.
// An amendment to a screen means editing the step and re-running; nothing is re-shot by hand.
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const BASE = process.env.TV_BASE_URL || 'http://localhost:3000';
const OUT = process.env.TV_OUT_DIR || path.join(ROOT, 'out');
const VOICE = process.env.TV_VOICE || 'af_heart';
const TTS_PY = process.env.TV_TTS_PY || path.join(process.env.HOME, 'tts/venv/bin/python');
const W = 1280;
const H = 720;

const args = process.argv.slice(2);
const id = args.find((a) => !a.startsWith('--'));
const noVoice = args.includes('--no-voice');
if (!id) {
  console.error('usage: recorder.mjs <video-id> [--no-voice]');
  process.exit(2);
}
const spec = (await import(pathToFileURL(path.join(ROOT, 'videos', `${id}.mjs`)).href)).default;
fs.mkdirSync(path.join(OUT, 'clips'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'raw'), { recursive: true });

const steps = [{ title: true, en: spec.title, ms: spec.titleMs, say: spec.intro }, ...spec.steps];

// 1. Voice clips.
const sayOf = (s) => s.say ?? s.en;
const items = steps.map((s) => {
  const text = sayOf(s) || '';
  const h = createHash('sha1').update(`${VOICE}|${text}`).digest('hex').slice(0, 12);
  return { text, out: path.join(OUT, 'clips', `${h}.wav`) };
});
let durs = steps.map(() => 0);
if (!noVoice) {
  const todo = items.filter((i) => i.text);
  const res = JSON.parse(
    execFileSync(TTS_PY, [path.join(HERE, 'tts.py')], {
      input: JSON.stringify({ voice: VOICE, speed: 1.0, items: todo }),
      maxBuffer: 1 << 24,
    }).toString(),
  );
  let j = 0;
  durs = items.map((i) => (i.text ? res[j++] : 0));
} else {
  // Reading pace for captions only: about 2.6 words a second.
  durs = items.map((i) => (i.text ? i.text.split(/\s+/).length / 2.6 : 0));
}

// 2. Sign in outside the recording, so the video opens on the app, not the login page.
// Playwright's pinned Chromium build, else TV_CHROMIUM, else the newest headless shell already
// in the browser cache (so a version bump in node_modules never forces a download).
function cachedShell() {
  const dir = path.join(process.env.HOME, 'Library/Caches/ms-playwright');
  const builds = fs.existsSync(dir) ? fs.readdirSync(dir).filter((d) => d.startsWith('chromium_headless_shell-')) : [];
  builds.sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]));
  for (const b of builds) {
    const exe = path.join(dir, b, 'chrome-headless-shell-mac-arm64', 'chrome-headless-shell');
    if (fs.existsSync(exe)) return exe;
  }
  return undefined;
}
let exe = process.env.TV_CHROMIUM;
if (!exe && !fs.existsSync(chromium.executablePath())) exe = cachedShell();
const browser = await chromium.launch(exe ? { executablePath: exe } : {});
const user = spec.user;
const pre = await browser.newContext({ viewport: { width: W, height: H } });
const lp = await pre.newPage();
for (let attempt = 0; ; attempt++) {
  await lp.goto(`${process.env.TV_BASE_URL || 'http://localhost:3000'}/signin`, { waitUntil: 'networkidle', timeout: 180000 });
  await lp.waitForTimeout(1500);
  await lp.getByPlaceholder('Your email').fill(user.email);
  await lp.getByPlaceholder('Your password').fill(user.password);
  await lp.locator('button[type="submit"]').first().click();
  try {
    await lp.waitForURL((u) => !u.pathname.startsWith('/signin'), { timeout: 60000 });
    await lp.waitForLoadState('networkidle');
    break;
  } catch (e) {
    if (attempt >= 2) throw e;
  }
}
const storageState = await pre.storageState();
// Warm the dev server's compile of every route the video visits, so the recording never
// waits on Turbopack compiling a page.
for (const w of spec.warm || []) {
  await lp.goto(`${BASE}${w}`, { waitUntil: 'networkidle', timeout: 120000 }).catch(() => {});
}
await pre.close();

// 3. Record.
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  storageState,
  recordVideo: { dir: path.join(OUT, 'raw'), size: { width: W, height: H } },
});
await ctx.addInitScript({ path: path.join(HERE, 'overlay.js') });
const t0 = Date.now();
const page = await ctx.newPage();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function moveTo(loc) {
  await loc.waitFor({ state: 'visible', timeout: 30000 });
  await loc.scrollIntoViewIfNeeded();
  const b = await loc.boundingBox();
  if (!b) return;
  const x = b.x + b.width / 2;
  const y = b.y + b.height / 2;
  await page.mouse.move(x, y, { steps: 25 });
  await sleep(250);
}
const h = {
  page,
  base: BASE,
  sleep,
  async click(loc, { hold = 450 } = {}) {
    await moveTo(loc);
    await loc.evaluate((el) => el.classList.add('tv-focus')).catch(() => {});
    await sleep(hold);
    await loc.evaluate((el) => el.classList.remove('tv-focus')).catch(() => {});
    await loc.click();
    await sleep(500);
  },
  async type(loc, text, { delay = 70 } = {}) {
    await moveTo(loc);
    await loc.click();
    await loc.pressSequentially(text, { delay });
    await sleep(400);
  },
  async point(loc, ms = 900) {
    await moveTo(loc);
    await loc.evaluate((el) => el.classList.add('tv-focus')).catch(() => {});
    await sleep(ms);
    await loc.evaluate((el) => el.classList.remove('tv-focus')).catch(() => {});
  },
  async nav(text) {
    // Sidebar navigation from the menu, never a deep link (CLAUDE.md browser rule).
    await h.click(page.getByRole('link', { name: text, exact: true }).first());
  },
};

const timeline = [];
await page.goto(`${BASE}${spec.start || '/'}`, { waitUntil: 'networkidle' });
await sleep(2500);
for (let i = 0; i < steps.length; i++) {
  const s = steps[i];
  const at = (Date.now() - t0) / 1000;
  if (s.title) {
    await page.evaluate(
      ([t, sub]) => {
        const d = document.createElement('div');
        d.id = 'tv-title';
        d.innerHTML = `<h1></h1><p></p>`;
        d.querySelector('h1').textContent = t;
        d.querySelector('p').textContent = sub || '';
        document.body.appendChild(d);
      },
      [spec.title, spec.subtitle],
    );
  } else {
    await page.evaluate((t) => window.__tvSetCaption(t), s.en);
  }
  const started = Date.now();
  if (s.run) {
    try {
      await s.run(h);
    } catch (e) {
      // Leave evidence of the failing step: a still of the screen and its accessibility tree.
      await page.screenshot({ path: path.join(OUT, `${id}.fail.png`) }).catch(() => {});
      const tree = await page.locator('body').ariaSnapshot().catch(() => '');
      fs.writeFileSync(path.join(OUT, `${id}.fail.aria.txt`), tree);
      console.error(`step ${i} failed: ${s.en}`);
      await ctx.close();
      await browser.close();
      throw e;
    }
  }
  const need = durs[i] * 1000 + (s.title ? 900 : 600);
  const spent = Date.now() - started;
  if (spent < need) await sleep(need - spent);
  if (s.title) await page.evaluate(() => document.getElementById('tv-title')?.remove());
  timeline.push({ i, at, end: (Date.now() - t0) / 1000, dur: durs[i], en: s.en, ms: s.ms, clip: items[i].out, say: !!items[i].text });
  console.log(`step ${i} ${at.toFixed(1)}s ${s.en}`);
}
await page.evaluate(() => window.__tvSetCaption(''));
await sleep(1500);
const total = (Date.now() - t0) / 1000;
const video = page.video();
await ctx.close();
await browser.close();
const raw = await video.path();

// 4. Captions (.srt) and the voice mux.
const ts = (t) => {
  const ms = Math.max(0, Math.round(t * 1000));
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
};
const srt = (lang) =>
  timeline
    .filter((t) => t[lang])
    .map((t, k) => `${k + 1}\n${ts(t.at)} --> ${ts(t.end)}\n${t[lang]}\n`)
    .join('\n');
fs.writeFileSync(path.join(OUT, `${id}.en.srt`), srt('en'));
fs.writeFileSync(path.join(OUT, `${id}.ms.srt`), srt('ms'));
fs.writeFileSync(path.join(OUT, `${id}.timeline.json`), JSON.stringify({ total, timeline }, null, 1));

const mp4 = path.join(OUT, `${id}.mp4`);
const voiced = timeline.filter((t) => t.say && !noVoice);
const ff = ['-y', '-loglevel', 'error', '-i', raw];
voiced.forEach((t) => ff.push('-i', t.clip));
const enc = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '24', '-pix_fmt', 'yuv420p', '-r', '25'];
if (voiced.length) {
  const parts = voiced.map((t, k) => `[${k + 1}:a]adelay=${Math.round((t.at + 0.25) * 1000)}:all=1[a${k}]`);
  const mix = `${voiced.map((_, k) => `[a${k}]`).join('')}amix=inputs=${voiced.length}:normalize=0[aout]`;
  ff.push('-filter_complex', `${parts.join(';')};${mix}`, '-map', '0:v', '-map', '[aout]', ...enc, '-c:a', 'aac', '-b:a', '128k', '-t', String(total), mp4);
} else {
  ff.push(...enc, '-an', mp4);
}
execFileSync('ffmpeg', ff, { stdio: 'inherit' });
console.log(`done ${mp4} ${total.toFixed(1)}s`);
