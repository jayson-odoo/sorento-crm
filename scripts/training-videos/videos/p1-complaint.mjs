// Video 3 (Mon 16 Nov, sales): file a complaint for a dealer.
// Fake data only (seed_fake.py). Each step: en = on-screen caption, ms = Malay subtitle
// (machine-written, needs a native read), say = voice line (defaults to en), run = action.
const choose = async ({ page, click, sleep }, field, option) => {
  await click(page.getByRole('combobox', { name: field }));
  await sleep(500);
  await click(page.getByRole('option', { name: option, exact: true }).first());
};

export default {
  id: 'p1-complaint',
  title: 'File a complaint',
  subtitle: 'My Requests > Complaint',
  titleMs: 'Buat aduan',
  intro: 'In this video you will file a complaint about a delivered product, and find it again later.',
  user: { email: 'sales@example.com', password: 'Demo1234!' },
  warm: ['/complaint-management/complaints', '/complaint-management/complaints/new'],
  steps: [
    {
      en: 'Open My Requests, then Complaint.',
      ms: 'Buka My Requests, kemudian Complaint.',
      run: async ({ page, nav, sleep }) => {
        await nav('Complaint');
        await page.getByRole('heading', { name: 'Complaints', level: 1 }).waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Your complaints are listed here. Click Create to file a new one.',
      ms: 'Aduan anda disenaraikan di sini. Klik Create untuk membuat aduan baharu.',
      run: async ({ page, click, point }) => {
        // The list area: its empty state on a clean seed, else the first card.
        await point(page.getByRole('main').getByText(/No complaint submissions yet|CMP-/).first(), 1500);
        await click(page.getByRole('link', { name: 'Create', exact: true }).first());
        await page.getByRole('heading', { name: 'Create Complaint', level: 1 }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'Start with the delivery order. Click Search delivery orders to see your recent ones.',
      ms: 'Mula dengan pesanan penghantaran. Klik Search delivery orders untuk melihat pesanan terkini anda.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Search delivery orders' }));
        await page.getByRole('dialog').getByText('DO-DM-26101').first().waitFor({ timeout: 30000 });
        await sleep(600);
      },
    },
    {
      en: 'Tick the delivery order with the problem, then click Add selected.',
      ms: 'Tandakan pesanan penghantaran yang bermasalah, kemudian klik Add selected.',
      run: async ({ page, click }) => {
        const dlg = page.getByRole('dialog');
        await click(dlg.getByRole('listitem').filter({ hasText: 'DO-DM-26101' }).first());
        await click(dlg.getByRole('button', { name: 'Add selected', exact: true }));
      },
    },
    {
      en: 'Keep only the product with the problem, and click Proceed.',
      ms: 'Kekalkan hanya produk yang bermasalah, dan klik Proceed.',
      run: async ({ page, click }) => {
        const dlg = page.getByRole('dialog', { name: 'Confirm products' });
        await click(dlg.getByRole('listitem').filter({ hasText: 'DM-WC-2002' }).first());
        await click(dlg.getByRole('button', { name: 'Proceed', exact: true }));
        await dlg.waitFor({ state: 'hidden', timeout: 30000 });
      },
    },
    {
      en: 'The customer and product fill in by themselves. Add the contact person and their number.',
      ms: 'Pelanggan dan produk diisi secara automatik. Tambah orang untuk dihubungi dan nombor mereka.',
      run: async ({ page, point, type }) => {
        await point(page.getByRole('textbox', { name: 'Customer name*' }), 900);
        await type(page.getByRole('textbox', { name: 'Contact person*' }), 'Alan Lim');
        await type(page.getByRole('textbox', { name: 'Contact number*' }), '012-000 1201', { delay: 80 });
      },
    },
    {
      en: 'Choose the customer type, and whether the item is still under warranty.',
      ms: 'Pilih jenis pelanggan, dan sama ada item masih dalam waranti.',
      run: async (h) => {
        await choose(h, 'Customer type*', 'Dealer');
        await choose(h, 'Within warranty*', 'Yes');
      },
    },
    {
      en: 'Say when the defect was found, and what kind of complaint it is.',
      ms: 'Nyatakan bila kecacatan ditemui, dan jenis aduan.',
      run: async (h) => {
        await choose(h, 'Defects discovered*', 'During installation');
        await choose(h, 'Complaint type*', 'Product defect');
      },
    },
    {
      en: 'Describe the defect in a few words.',
      ms: 'Terangkan kecacatan dalam beberapa perkataan.',
      run: async ({ page, type }) => {
        await type(
          page.getByRole('textbox', { name: 'Defect description*' }),
          'Basin mixer leaks at the base after installation.',
          { delay: 45 },
        );
      },
    },
    {
      en: 'Check the product line and type how many are affected.',
      ms: 'Semak baris produk dan taip bilangan yang terjejas.',
      run: async ({ page, type, sleep }) => {
        await type(page.getByRole('spinbutton').first(), '1', { delay: 150 });
        await sleep(400);
      },
    },
    {
      en: 'Click Submit complaint, and confirm. Your team is notified straight away.',
      ms: 'Klik Submit complaint, dan sahkan. Pasukan anda dimaklumkan serta-merta.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Submit complaint', exact: true }));
        const confirm = page.getByRole('alertdialog');
        await confirm.waitFor({ timeout: 30000 });
        await sleep(600);
        await click(confirm.getByRole('button', { name: 'Submit complaint', exact: true }));
        await page.getByRole('heading', { name: 'Complaints', level: 1 }).waitFor({ timeout: 60000 });
        await sleep(1200);
      },
    },
    {
      en: 'Your complaint is now on your list. Click it to open the record.',
      ms: 'Aduan anda kini dalam senarai anda. Klik untuk membuka rekod.',
      run: async ({ page, click, point, sleep }) => {
        const card = page.getByRole('main').getByRole('link', { name: /CMP-/ }).first();
        await point(card, 1500);
        await click(card);
        await page.getByRole('heading', { name: 'Complaint', exact: true, level: 1 }).waitFor({ timeout: 60000 });
        await sleep(1200);
      },
    },
    {
      en: 'Here you can follow its status and see everything you sent.',
      ms: 'Di sini anda boleh menyemak statusnya dan melihat semua yang anda hantar.',
      run: async ({ page, point, sleep }) => {
        await point(page.getByRole('main').getByText('Submitted', { exact: true }).first(), 1200);
        await page.mouse.wheel(0, 500);
        await sleep(1500);
        await page.mouse.wheel(0, -500);
        await sleep(800);
      },
    },
  ],
};
