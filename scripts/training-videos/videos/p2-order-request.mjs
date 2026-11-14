// Video 8 (Wed 18 Nov, Project CS): raise an Order Request (the spare part request) and have the
// CS manager approve it. Chloe (CS: create + view) raises it; Mona Manager (CS manager: view, and
// the only member of the Form SLA level "Order Request") edits a quantity and approves, which
// raises it to purchasing as an order inquiry. seed_fake.py --part p3 sets up the grants, the
// level and its team, and removes the requests an earlier take raised.
// Each step: en = on-screen caption, ms = Malay subtitle (machine-written, needs a native read),
// say = voice line (defaults to en), run = action.
// .last(): Procurement holds its own Supply Chain group, after the top-level one of that name.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).last();

const openOrderRequests = async ({ page, click, sleep }) => {
  await click(menu(page, 'Procurement'));
  await click(menu(page, 'Supply Chain'));
  await click(menu(page, 'Order Requests'));
  await page.getByRole('heading', { name: 'Order Requests', level: 1 }).waitFor({ timeout: 60000 });
  await sleep(800);
};

// A searchable select: open it, type to narrow the list, pick the option.
const pick = async ({ page, click, sleep }, combo, search, option) => {
  await click(combo);
  await sleep(300);
  if (search) await page.keyboard.type(search, { delay: 90 });
  await sleep(600);
  await click(page.getByRole('option', { name: option }).first());
};

// Replace a field's value the way a person does: click, select all, type.
const retype = async ({ page, click, sleep }, loc, text) => {
  await click(loc);
  await page.keyboard.press('ControlOrMeta+A');
  await page.keyboard.type(text, { delay: 120 });
  await sleep(300);
};

export default {
  id: 'p2-order-request',
  title: 'Order requests',
  subtitle: 'Procurement > Supply Chain > Order Requests',
  titleMs: 'Permintaan pesanan',
  intro: 'In this video you will raise an order request for parts, and see your manager approve it.',
  user: { email: 'cs@example.com', password: 'Demo1234!' },
  users: { manager: { email: 'manager@example.com', password: 'Demo1234!' } },
  warm: ['/procurement-management/spare-part-requests', '/procurement-management/spare-part-requests/new'],
  steps: [
    {
      en: 'Open Procurement, then Supply Chain, then Order Requests.',
      ms: 'Buka Procurement, kemudian Supply Chain, kemudian Order Requests.',
      run: openOrderRequests,
    },
    {
      en: 'Click Create.',
      ms: 'Klik Create.',
      run: async ({ page, click }) => {
        await click(page.getByRole('button', { name: 'Create', exact: true }).or(
          page.getByRole('link', { name: 'Create', exact: true })).first());
        await page.getByRole('heading', { name: 'New Order Request' }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'The currency is already Malaysian ringgit. Type the date you need the parts by.',
      ms: 'Mata wang sudah ringgit Malaysia. Taip tarikh anda memerlukan alat ganti itu.',
      run: async (h) => {
        await h.point(h.page.getByRole('combobox', { name: 'Currency *' }), 1000);
        await retype(h, h.page.getByRole('textbox', { name: 'Needed by' }), '15/12/2026');
        await h.page.keyboard.press('Tab');
      },
    },
    {
      en: 'Choose the location the parts go to, and say why you need them.',
      ms: 'Pilih lokasi alat ganti itu dihantar, dan nyatakan sebabnya.',
      run: async (h) => {
        await pick(h, h.page.getByRole('combobox', { name: 'Default location' }), 'Main', /Main Warehouse/);
        await h.type(h.page.getByRole('textbox', { name: 'Reason' }),
          'Replacement mixers for the showroom display.', { delay: 45 });
      },
    },
    {
      en: 'Add the first product: search by code or name, then type the quantity and unit price.',
      ms: 'Tambah produk pertama: cari mengikut kod atau nama, kemudian taip kuantiti dan harga seunit.',
      run: async (h) => {
        await pick(h, h.page.getByRole('combobox', { name: 'Product for line 1' }), 'DM-BS-1001', /DM-BS-1001/);
        await retype(h, h.page.getByRole('spinbutton', { name: 'Qty for line 1' }), '6');
        await retype(h, h.page.getByRole('spinbutton', { name: 'Unit price for line 1' }), '123.45');
      },
    },
    {
      en: 'Click Add product for the next one.',
      ms: 'Klik Add product untuk produk seterusnya.',
      run: async (h) => {
        await h.click(h.page.getByRole('button', { name: 'Add product', exact: true }));
        await pick(h, h.page.getByRole('combobox', { name: 'Product for line 2' }), 'DM-SH-3003', /DM-SH-3003/);
        await retype(h, h.page.getByRole('spinbutton', { name: 'Qty for line 2' }), '2');
        await retype(h, h.page.getByRole('spinbutton', { name: 'Unit price for line 2' }), '689.50');
        await h.page.keyboard.press('Tab');
      },
    },
    {
      en: 'Check the totals, then click Submit.',
      ms: 'Semak jumlahnya, kemudian klik Submit.',
      run: async ({ page, click, point }) => {
        await point(page.getByText('RM 2,119.70').first(), 1200);
        await click(page.getByRole('button', { name: 'Submit', exact: true }));
        await page.getByRole('heading', { name: /^OR-\d{4}-\d{4}/ }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'Your request has its OR number and waits for your manager\'s approval.',
      ms: 'Permintaan anda mendapat nombor OR dan menunggu kelulusan pengurus anda.',
      run: async ({ page, point }) => {
        await point(page.getByRole('heading', { name: /^OR-\d{4}-\d{4}/ }), 2200);
      },
    },
    {
      en: 'Now Mona, the customer service manager, signs in and opens Order Requests.',
      ms: 'Kini Mona, pengurus khidmat pelanggan, log masuk dan membuka Order Requests.',
      run: async (h) => {
        await h.signInAs('manager');
        await openOrderRequests(h);
      },
    },
    {
      en: 'She opens the request waiting for her.',
      ms: 'Dia membuka permintaan yang menunggunya.',
      run: async ({ page, click }) => {
        await click(page.getByRole('cell', { name: /^OR-\d{4}-\d{4}$/ }).first());
        await page.getByRole('heading', { name: /^OR-\d{4}-\d{4}/ }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'A manager can change a line before approving. Here she cuts the mixers from 6 to 4.',
      ms: 'Pengurus boleh mengubah baris sebelum meluluskan. Di sini dia mengurangkan pili dari 6 kepada 4.',
      run: async (h) => {
        const row = h.page.getByRole('row', { name: /DM-BS-1001/ }).first();
        await retype(h, row.getByRole('spinbutton').first(), '4');
        await h.page.keyboard.press('Tab');
        await h.sleep(1200);
      },
    },
    {
      en: 'Click Approve. The window lists her changes; add a note and approve.',
      ms: 'Klik Approve. Tetingkap menyenaraikan perubahannya; tambah nota dan luluskan.',
      run: async ({ page, click, point, type }) => {
        await click(page.getByRole('button', { name: 'Approve', exact: true }).first());
        const dialog = page.getByRole('dialog');
        await dialog.waitFor({ timeout: 30000 });
        await point(dialog.getByText('Your changes').first(), 1500);
        await type(dialog.getByRole('textbox').first(), 'Four is enough for the display.', { delay: 45 });
        await click(dialog.getByRole('button', { name: 'Approve', exact: true }));
        await dialog.waitFor({ state: 'hidden', timeout: 30000 });
      },
    },
    {
      en: 'The request is Approved, and its lines go to purchasing to order.',
      ms: 'Permintaan itu diluluskan, dan baris-barisnya dihantar kepada bahagian pembelian untuk dipesan.',
      run: async ({ page, point, sleep }) => {
        await page.getByRole('link', { name: 'Raised to purchasing' }).waitFor({ timeout: 60000 });
        await sleep(500);
        await point(page.getByRole('heading', { name: /^OR-\d{4}-\d{4}/ }), 1500);
        await point(page.getByRole('cell', { name: /^To order/ }).first(), 1500);
      },
    },
    {
      en: 'Click Raised to purchasing to open the order inquiry purchasing works from.',
      ms: 'Klik Raised to purchasing untuk membuka pertanyaan pesanan yang digunakan oleh bahagian pembelian.',
      run: async ({ page, click, point, sleep }) => {
        await click(page.getByRole('link', { name: 'Raised to purchasing' }));
        const oi = page.getByRole('heading', { name: /^OI-\d{4}-\d{4}$/ });
        await oi.waitFor({ timeout: 60000 });
        await sleep(600);
        await point(oi, 1500);
        await point(page.getByRole('link', { name: /^Order request OR-/ }), 2000);
      },
    },
  ],
};
