// Video 1 (Mon 16 Nov, sales): request price tags for a dealer.
// Fake data only (seed_fake.py). Each step: en = on-screen caption, ms = Malay subtitle
// (machine-written, needs a native read), say = voice line (defaults to en), run = action.
export default {
  id: 'p1-price-tag-request',
  title: 'Request price tags',
  subtitle: 'My Requests > Price Tag Request',
  titleMs: 'Mohon tanda harga',
  intro: 'In this video you will request price tags for a dealer, check the preview, and approve it.',
  user: { email: 'sales@example.com', password: 'Demo1234!' },
  warm: ['/dealer-kit/price-tag-requests'],
  steps: [
    {
      en: 'Open My Requests, then Price Tag Request.',
      ms: 'Buka My Requests, kemudian Price Tag Request.',
      run: async ({ nav }) => nav('Price Tag Request'),
    },
    {
      en: 'Your requests are listed here. Click Create to start a new one.',
      ms: 'Permohonan anda disenaraikan di sini. Klik Create untuk mula yang baharu.',
      run: async ({ page, click }) => click(page.getByRole('link', { name: 'Create', exact: true }).first()),
    },
    {
      en: 'Pick the dealer the tags are for. Type a few letters of the name to search.',
      ms: 'Pilih pengedar untuk tanda harga ini. Taip beberapa huruf nama untuk mencari.',
      run: async ({ page, click, sleep }) => {
        const combo = page.getByRole('combobox', { name: 'Customers' }).first();
        await click(combo);
        await page.keyboard.type('Lim Bina', { delay: 110 });
        await sleep(1200);
        await click(page.getByRole('option', { name: 'Lim Bina Hardware Sdn Bhd' }).first());
        await page.keyboard.press('Escape');
      },
    },
    {
      en: 'Choose how to add the items. Here we type them in ourselves.',
      ms: 'Pilih cara untuk menambah item. Di sini kita taip sendiri.',
      run: async ({ page, click }) => click(page.getByRole('button', { name: /Type the items/ }).first()),
    },
    {
      en: 'Add a line and search the product by name or code.',
      ms: 'Tambah baris dan cari produk mengikut nama atau kod.',
      say: 'Add a line, and search the product by name or code.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Add line', exact: true }));
        const item = page.getByRole('combobox', { name: 'Item for line 1' });
        await click(item);
        await page.keyboard.type('Basin', { delay: 110 });
        await sleep(1500);
        await click(page.getByRole('option', { name: 'DM-BS-1001' }).first());
      },
    },
    {
      en: 'The price fills in by itself. Set how many tags you need.',
      ms: 'Harga diisi secara automatik. Tetapkan bilangan tanda yang diperlukan.',
      run: async ({ page, click, sleep }) => {
        const qty = page.getByRole('spinbutton', { name: 'Quantity for line 1' });
        await click(qty);
        await page.keyboard.press('Control+A');
        await page.keyboard.type('4', { delay: 150 });
        await sleep(600);
      },
    },
    {
      en: 'Add a second product the same way.',
      ms: 'Tambah produk kedua dengan cara yang sama.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Add line', exact: true }));
        const item = page.getByRole('combobox', { name: 'Item for line 2' });
        await click(item);
        await page.keyboard.type('WC', { delay: 120 });
        await sleep(1500);
        await click(page.getByRole('option', { name: 'DM-WC-2002' }).first());
      },
    },
    {
      en: 'When the list is ready, click Preview to see the tags.',
      ms: 'Apabila senarai siap, klik Preview untuk melihat tanda harga.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Preview', exact: true }).last());
        await page.getByRole('button', { name: 'Approve', exact: true }).waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Check each tag: product, code and price. Use Back to edit to change anything.',
      ms: 'Semak setiap tanda: produk, kod dan harga. Guna Back to edit untuk membuat perubahan.',
      run: async ({ page, point }) => point(page.getByRole('button', { name: 'Back to edit', exact: true }), 1200),
    },
    {
      en: 'All good? Click Approve. The request is sent and saved to your list.',
      ms: 'Semua betul? Klik Approve. Permohonan dihantar dan disimpan dalam senarai anda.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Approve', exact: true }));
        await sleep(2500);
      },
    },
    {
      en: 'Open Price Tag Request again any time to follow its status.',
      ms: 'Buka Price Tag Request semula pada bila-bila masa untuk menyemak statusnya.',
      run: async ({ nav, sleep }) => {
        await nav('Price Tag Request');
        await sleep(1500);
      },
    },
  ],
};
