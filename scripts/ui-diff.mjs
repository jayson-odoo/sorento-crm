#!/usr/bin/env node
// UI v2 visual diff (phase 0, G-3). Compares two capture folders written by scripts/ui-capture.mjs.
//
// usage: node scripts/ui-diff.mjs <baseline-dir> <candidate-dir> <out-dir> [--threshold 0.001]
//
// For every PNG present in both folders it counts differing pixels (per-channel tolerance 16/255)
// inside a headless Chromium canvas, so it needs no image library beyond the pre-installed
// `playwright`. A pair whose differing share is above the threshold (default 0.1%) is a failure.
// Writes <out-dir>/diff.json and <out-dir>/index.html (side by side + diff mask) and exits 1 when
// any pair fails. Run it from sorento_crm_frontend/ so `playwright` resolves.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';

const require = createRequire(path.join(process.cwd(), 'package.json'));
const { chromium } = require('playwright');

const [baseDir, candDir, outDir] = process.argv.slice(2);
const tIdx = process.argv.indexOf('--threshold');
const threshold = tIdx > 0 ? Number(process.argv[tIdx + 1]) : 0.001;
if (!baseDir || !candDir || !outDir) {
  console.error('usage: node scripts/ui-diff.mjs <baseline> <candidate> <out> [--threshold 0.001]');
  process.exit(2);
}
const list = (d) =>
  fs.existsSync(path.join(d, 'shots'))
    ? fs.readdirSync(path.join(d, 'shots')).filter((f) => f.endsWith('.png'))
    : [];
const both = list(baseDir).filter((f) => list(candDir).includes(f));
fs.mkdirSync(path.join(outDir, 'masks'), { recursive: true });

// The repo may pin a Playwright whose browser build is not downloaded; fall back to the sandbox's
// pre-installed Chromium (or PW_CHROMIUM) instead of running `playwright install`.
const browser = await chromium
  .launch()
  .catch(() => chromium.launch({ executablePath: process.env.PW_CHROMIUM || '/opt/pw-browsers/chromium' }));
const page = await browser.newPage();
await page.setContent('<canvas id="c"></canvas>');
const results = [];
for (const f of both) {
  const a = fs.readFileSync(path.join(baseDir, 'shots', f)).toString('base64');
  const b = fs.readFileSync(path.join(candDir, 'shots', f)).toString('base64');
  const r = await page.evaluate(
    async ([a64, b64]) => {
      const load = (s) =>
        new Promise((res, rej) => {
          const i = new Image();
          i.onload = () => res(i);
          i.onerror = rej;
          i.src = `data:image/png;base64,${s}`;
        });
      const [ia, ib] = await Promise.all([load(a64), load(b64)]);
      const w = Math.max(ia.width, ib.width);
      const h = Math.max(ia.height, ib.height);
      const px = (img) => {
        const c = document.createElement('canvas');
        c.width = w; c.height = h;
        const x = c.getContext('2d');
        x.drawImage(img, 0, 0);
        return x.getImageData(0, 0, w, h).data;
      };
      const da = px(ia);
      const db = px(ib);
      const out = document.getElementById('c');
      out.width = w; out.height = h;
      const ctx = out.getContext('2d');
      const mask = ctx.createImageData(w, h);
      let diff = 0;
      for (let i = 0; i < da.length; i += 4) {
        const d =
          Math.abs(da[i] - db[i]) > 16 || Math.abs(da[i + 1] - db[i + 1]) > 16 || Math.abs(da[i + 2] - db[i + 2]) > 16;
        if (d) diff++;
        mask.data[i] = d ? 255 : da[i] * 0.3;
        mask.data[i + 1] = d ? 0 : da[i + 1] * 0.3;
        mask.data[i + 2] = d ? 0 : da[i + 2] * 0.3;
        mask.data[i + 3] = 255;
      }
      ctx.putImageData(mask, 0, 0);
      return { ratio: diff / (w * h), sizeChanged: ia.width !== ib.width || ia.height !== ib.height, mask: out.toDataURL('image/png') };
    },
    [a, b],
  );
  fs.writeFileSync(path.join(outDir, 'masks', f), Buffer.from(r.mask.split(',')[1], 'base64'));
  results.push({ file: f, ratio: r.ratio, sizeChanged: r.sizeChanged, fail: r.ratio > threshold || r.sizeChanged });
}
await browser.close();
const rel = (d) => path.relative(outDir, d);
const rows = results
  .sort((x, y) => y.ratio - x.ratio)
  .map(
    (r) => `<tr class="${r.fail ? 'fail' : ''}"><td>${r.file}</td><td>${(r.ratio * 100).toFixed(3)}%</td>
<td><img src="${rel(path.join(baseDir, 'shots', r.file))}"></td><td><img src="${rel(path.join(candDir, 'shots', r.file))}"></td>
<td><img src="masks/${r.file}"></td></tr>`,
  )
  .join('\n');
fs.writeFileSync(path.join(outDir, 'diff.json'), JSON.stringify({ threshold, results }, null, 1));
fs.writeFileSync(
  path.join(outDir, 'index.html'),
  `<!doctype html><meta charset="utf-8"><title>UI diff</title><style>body{font:13px system-ui;margin:16px}
img{width:320px}td{vertical-align:top;padding:4px}tr.fail td:first-child{color:#b42318;font-weight:600}</style>
<h1>UI diff (threshold ${(threshold * 100).toFixed(2)}%)</h1><table><tr><th>Shot</th><th>Changed</th><th>Baseline</th><th>Candidate</th><th>Diff</th></tr>${rows}</table>`,
);
const failed = results.filter((r) => r.fail).length;
console.log(`${results.length} compared, ${failed} over threshold`);
process.exit(failed ? 1 : 0);
