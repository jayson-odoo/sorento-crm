const { chromium } = require('playwright');
const http = require('http'); const fs = require('fs'); const path = require('path');
const root = path.join(__dirname, 'dist');
const server = http.createServer((req, res) => {
  const f = path.join(root, req.url === '/' ? 'index.html' : req.url);
  if (!fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': f.endsWith('.js') ? 'text/javascript' : 'text/html' });
  res.end(fs.readFileSync(f));
}).listen(4789);
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  const errors = []; p.on('pageerror', (e) => errors.push(e.message));
  await p.goto('http://127.0.0.1:4789/');
  const order = (id) => p.locator(`[data-order=${id}]`).textContent();
  for (const id of ['old', 'new']) {
    // Mouse: drag basin onto wc.
    const from = await p.getByLabel(`${id}-drag-basin`).boundingBox();
    const to = await p.getByLabel(`${id}-drag-wc`).boundingBox();
    await p.mouse.move(from.x + 70, from.y + 40);
    await p.mouse.down();
    for (let i = 1; i <= 15; i++) await p.mouse.move(from.x + 70 - (i * (from.x - to.x)) / 15, from.y + 40);
    await p.mouse.up();
    await p.waitForTimeout(300);
    const afterMouse = await order(id);
    // Keyboard: trap one step left.
    await p.getByLabel(`${id}-drag-trap`).focus();
    await p.keyboard.press('Space'); await p.waitForTimeout(150);
    await p.keyboard.press('ArrowLeft'); await p.waitForTimeout(250);
    await p.keyboard.press('Space'); await p.waitForTimeout(300);
    console.log(id, 'mouse ->', afterMouse, '| keyboard ->', await order(id));
  }
  console.log('page errors:', errors.length ? errors : 'none');
  await b.close(); server.close();
})();
