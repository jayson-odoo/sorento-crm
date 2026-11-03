// DESIGNER-PASTE evidence: real Chromium, stub page carrying the same window
// listeners TagCanvasEditor ships (keydown not cancelled for c/x/v, before*
// cancelled, copy writes the marker, paste reads the clipboard).
// Run: NODE_PATH=$(npm root -g) node chromium-clipboard-check.js
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  await page.route('https://local.test/', (r) =>
    r.fulfill({ contentType: 'text/html', body: '<body><div id=c style="width:300px;height:300px">canvas</div><input id=i></body>' }),
  );
  await page.goto('https://local.test/');
  await page.evaluate(() => {
    window.log = [];
    let pending = false;
    const inInput = (t) => t instanceof HTMLInputElement;
    addEventListener('keydown', (e) => {
      log.push('keydown ' + e.key);
      pending = false;
      if ((e.ctrlKey || e.metaKey) && e.key === 'c') pending = true;
    });
    addEventListener('beforecopy', (e) => { if (pending) e.preventDefault(); });
    addEventListener('beforepaste', (e) => { if (!inInput(e.target)) e.preventDefault(); });
    addEventListener('copy', (e) => {
      if (!pending) return;
      pending = false;
      e.clipboardData.setData('application/x-sorento-tag-layers', 'doc');
      e.clipboardData.setData('text/plain', 'words');
      e.preventDefault();
      log.push('copy: marker written');
    });
    addEventListener('paste', (e) => {
      const d = e.clipboardData;
      log.push('paste on ' + e.target.tagName + ' types=' + [...d.types].join(',') + ' files=' +
        [...d.files].map((f) => f.type + ':' + f.size).join(',') + ' marker=' + d.getData('application/x-sorento-tag-layers'));
    });
  });
  await page.click('#c');
  await page.evaluate(async () => {
    const cv = document.createElement('canvas'); cv.width = 50; cv.height = 20;
    const blob = await new Promise((r) => cv.toBlob(r, 'image/png'));
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  });
  await page.keyboard.press('Control+v'); // screenshot on the clipboard
  await page.keyboard.press('Control+c'); // editor copy
  await page.keyboard.press('Control+v'); // marker comes back
  await page.evaluate(() => navigator.clipboard.writeText('typed'));
  await page.click('#i');
  await page.keyboard.press('Control+v'); // input paste stays native
  await page.waitForTimeout(200);
  console.log((await page.evaluate(() => log.filter((l) => l !== 'keydown Control'))).join('\n'));
  console.log('input value: ' + (await page.inputValue('#i')));
  await browser.close();
})();
