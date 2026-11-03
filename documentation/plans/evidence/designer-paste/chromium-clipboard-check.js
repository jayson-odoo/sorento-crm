const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  await page.route('https://local.test/', r => r.fulfill({ contentType: 'text/html', body: '<body><div id=c style="width:300px;height:300px">canvas</div><input id=i></body>' }));
  await page.goto('https://local.test/');
  await page.evaluate(() => {
    window.log = [];
    let pending = false;
    addEventListener('keydown', e => { log.push('kd:'+e.key+':'+e.ctrlKey); pending = false; if ((e.ctrlKey||e.metaKey) && e.key === 'c') { pending = true; } });
    addEventListener('copy', e => { if (!pending) return; pending = false;
      e.clipboardData.setData('application/x-sorento-tag-layers', 'doc'); e.clipboardData.setData('text/plain', 'words'); e.preventDefault(); log.push('copy-marked'); });
    addEventListener('paste', e => { const d = e.clipboardData;
      log.push({ target: e.target.tagName, types: [...d.types], files: [...d.files].map(f => f.type + ':' + f.size), text: d.getData('text/plain'), marker: d.getData('application/x-sorento-tag-layers') }); });
  });
  await page.click('#c');
  // 1. image on the clipboard
  await page.evaluate(async () => {
    const cv = document.createElement('canvas'); cv.width = 50; cv.height = 20;
    const blob = await new Promise(r => cv.toBlob(r, 'image/png'));
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  });
  await page.keyboard.press('Control+v');
  // 2. editor copy then paste
  await page.keyboard.press('Control+c');
  await page.keyboard.press('Control+v');
  // 3. paste into input
  await page.evaluate(() => navigator.clipboard.writeText('typed'));
  await page.click('#i'); await page.keyboard.press('Control+v');
  await page.waitForTimeout(200);
  console.log(JSON.stringify(await page.evaluate(() => log), null, 1));
  console.log('input value:', await page.inputValue('#i'));
  await browser.close();
})();
