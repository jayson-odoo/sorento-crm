// Video 5 (Wed 18 Nov, Project CS): split one order line into two deliveries.
// Fake data only (seed_fake.py --part p2). Each step: en = on-screen caption, ms = Malay subtitle
// (machine-written, needs a native read), say = voice line (defaults to en), run = action.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).first();

// Replace a field's value the way a person does: click, select all, type.
const retype = async ({ page, click, sleep }, loc, text) => {
  await click(loc);
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type(text, { delay: 120 });
  await sleep(300);
};

export default {
  id: 'p2-split-delivery',
  title: 'Split a delivery',
  subtitle: 'Supply Chain > Project Demand > Fulfilment Planning',
  titleMs: 'Pecahkan penghantaran',
  intro: 'In this video you will split one order line into two deliveries on different dates.',
  user: { email: 'cs@example.com', password: 'Demo1234!' },
  warm: ['/project-sales/fulfilment-planning'],
  steps: [
    {
      en: 'Open Supply Chain, then Project Demand, then Fulfilment Planning.',
      ms: 'Buka Supply Chain, kemudian Project Demand, kemudian Fulfilment Planning.',
      run: async ({ page, click, sleep }) => {
        await click(menu(page, 'Supply Chain'));
        await click(menu(page, 'Project Demand'));
        await click(menu(page, 'Fulfilment Planning'));
        await page.getByRole('checkbox', { name: 'Select SO-DM-26001 for planning' }).waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Your project sales orders are listed here. Tick the order, then click Plan.',
      ms: 'Pesanan jualan projek anda disenaraikan di sini. Tandakan pesanan, kemudian klik Plan.',
      run: async ({ page, click, point }) => {
        await point(page.getByRole('row', { name: /SO-DM-26001/ }).first(), 1200);
        await click(page.getByRole('checkbox', { name: 'Select SO-DM-26001 for planning' }));
        await click(page.getByRole('button', { name: /^Plan SO-DM-26001/ }));
        await page.getByRole('heading', { name: /Planning 1 sales orders? together/ }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'This is the planning board for the order, one row for each line.',
      ms: 'Ini papan perancangan untuk pesanan itu, satu baris bagi setiap baris pesanan.',
      run: async ({ page, point }) => point(page.getByRole('row', { name: /SO-DM-26001 line 2/ }).first(), 1500),
    },
    {
      en: 'To deliver a line in parts, open the settings menu and choose Split delivery.',
      ms: 'Untuk menghantar satu baris secara berperingkat, buka menu tetapan dan pilih Split delivery.',
      run: async ({ page, click }) => {
        await click(page.getByRole('button', { name: 'Board actions' }));
        await click(page.getByRole('menuitem', { name: /Split delivery SO-DM-26001/ }));
        await page.getByRole('table', { name: 'Split delivery sheet' }).waitFor({ timeout: 30000 });
      },
    },
    {
      en: 'Find the line, here the basin mixer, and click Split.',
      ms: 'Cari baris itu, di sini pili sinki, dan klik Split.',
      run: async ({ page, click, point }) => {
        await point(page.getByRole('row', { name: /DM-BS-1001/ }).first(), 900);
        await click(page.getByRole('button', { name: 'Add a split to line 2' }));
      },
    },
    {
      en: 'Type how many go out on the first date.',
      ms: 'Taip bilangan yang dihantar pada tarikh pertama.',
      run: async (h) => retype(h, h.page.getByRole('textbox', { name: 'Quantity, line 2 split 1' }), '140'),
    },
    {
      en: 'Put the rest on the second part, with its own date.',
      ms: 'Letakkan bakinya pada bahagian kedua, dengan tarikhnya sendiri.',
      run: async (h) => {
        await retype(h, h.page.getByRole('textbox', { name: 'Quantity, line 2 split 2' }), '100');
        await retype(h, h.page.getByRole('textbox', { name: 'Date, line 2 split 2' }), '15/02/2027');
        await h.page.keyboard.press('Tab');
      },
    },
    {
      en: 'The balance must come to zero: both parts add up to the line.',
      ms: 'Baki mesti sifar: kedua-dua bahagian sama dengan jumlah baris.',
      run: async ({ page, point }) => {
        await point(page.getByRole('row', { name: /split 1 of line 2/ }).getByRole('cell').filter({ hasText: /^0/ }).first(), 1500);
      },
    },
    {
      en: 'Click Save.',
      ms: 'Klik Save.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('dialog').getByRole('button', { name: 'Save', exact: true }));
        await page.getByText('Splits saved').first().waitFor({ timeout: 30000 });
        await sleep(800);
      },
    },
    {
      en: 'The board shows the split, ready to confirm with your other decisions.',
      ms: 'Papan menunjukkan pecahan itu, sedia untuk disahkan bersama keputusan lain anda.',
      run: async ({ page, point }) => point(page.getByText(/Split edits to confirm/).first(), 1500),
    },
    {
      en: 'To see both parts, open the settings menu and choose View splits.',
      ms: 'Untuk melihat kedua-dua bahagian, buka menu tetapan dan pilih View splits.',
      run: async ({ page, click, point }) => {
        await click(page.getByRole('button', { name: 'Board actions' }));
        await click(page.getByRole('menuitem', { name: /View splits SO-DM-26001/ }));
        const sheet = page.getByRole('dialog').getByRole('table', { name: 'Split delivery sheet' });
        await sheet.waitFor({ timeout: 30000 });
        await point(sheet.getByRole('row').nth(1), 1200);
        await point(sheet.getByRole('row').nth(2), 1200);
      },
    },
    {
      en: 'One line, two deliveries, each on its own date.',
      ms: 'Satu baris, dua penghantaran, setiap satu pada tarikhnya sendiri.',
      run: async ({ page, click, sleep }) => {
        await sleep(800);
        await click(page.getByRole('dialog').getByRole('button', { name: 'Close', exact: true }).first());
      },
    },
  ],
};
