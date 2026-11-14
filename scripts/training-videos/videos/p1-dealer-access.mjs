// Video 2 (Mon 16 Nov, sales): give a dealer's people access to your accounts.
// Fake data only (seed_fake.py). Each step: en = on-screen caption, ms = Malay subtitle
// (machine-written, needs a native read), say = voice line (defaults to en), run = action.
export default {
  id: 'p1-dealer-access',
  title: 'Manage dealer contacts',
  subtitle: 'My Work > Dealer access',
  titleMs: 'Urus kenalan pengedar',
  intro: 'In this video you will give a dealer\'s staff access to your accounts, and change it later.',
  user: { email: 'sales@example.com', password: 'Demo1234!' },
  warm: ['/sales/dealer-access'],
  steps: [
    {
      en: 'Open Dealer access under My Work.',
      ms: 'Buka Dealer access di bawah My Work.',
      run: async ({ page, nav, sleep }) => {
        await nav('Dealer access');
        await page.getByRole('heading', { name: 'Dealer access', level: 1 }).waitFor({ timeout: 60000 });
        await sleep(1200);
      },
    },
    {
      en: 'Everyone who can use your accounts is listed here, with their phone, accounts and access.',
      ms: 'Semua orang yang boleh menggunakan akaun anda disenaraikan di sini, bersama telefon, akaun dan akses mereka.',
      run: async ({ page, point }) => point(page.getByRole('table').first(), 1500),
    },
    {
      en: 'To add someone, click Add people.',
      ms: 'Untuk menambah seseorang, klik Add people.',
      run: async ({ page, click }) => click(page.getByRole('button', { name: 'Add people', exact: true })),
    },
    {
      en: 'Choose which of your accounts they may use. Search by name or code.',
      ms: 'Pilih akaun anda yang boleh mereka gunakan. Cari mengikut nama atau kod.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('combobox', { name: 'My accounts' }).first());
        await page.keyboard.type('Lim Bina', { delay: 110 });
        await sleep(1200);
        await click(page.getByRole('option', { name: /Lim Bina Hardware/ }).first());
        await page.keyboard.press('Escape');
        await sleep(400);
      },
    },
    {
      en: 'Type the person\'s name and mobile number.',
      ms: 'Taip nama dan nombor telefon bimbit orang itu.',
      run: async ({ page, type }) => {
        const dlg = page.getByRole('dialog');
        await type(dlg.getByLabel('Name', { exact: true }).first(), 'Hafiz Rahman');
        await type(dlg.getByLabel('Phone 1'), '120001401', { delay: 90 });
      },
    },
    {
      en: 'Set their access: Business Owner for the boss, Employee for staff.',
      ms: 'Tetapkan akses: Business Owner untuk pemilik, Employee untuk pekerja.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('combobox', { name: 'Access 1' }));
        await sleep(500);
        await click(page.getByRole('option', { name: 'Business Owner', exact: true }).first());
      },
    },
    {
      en: 'Adding several people at once? Click Add person for each one.',
      ms: 'Menambah beberapa orang sekaligus? Klik Add person untuk setiap orang.',
      run: async ({ page, click, type }) => {
        const dlg = page.getByRole('dialog');
        await click(dlg.getByRole('button', { name: 'Add person', exact: true }));
        await type(dlg.getByLabel('Name', { exact: true }).nth(1), 'Nora Aziz');
        await type(dlg.getByLabel('Phone 2'), '120001402', { delay: 90 });
      },
    },
    {
      en: 'Click Save. They can now use the chatbot and forms for these accounts.',
      ms: 'Klik Save. Mereka kini boleh menggunakan chatbot dan borang untuk akaun ini.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('dialog').getByRole('button', { name: 'Save', exact: true }));
        await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 30000 });
        await sleep(1500);
      },
    },
    {
      en: 'To change someone\'s accounts or access, click their row.',
      ms: 'Untuk menukar akaun atau akses seseorang, klik baris mereka.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('cell', { name: 'Nora Aziz', exact: true }).first());
        await sleep(800);
      },
    },
    {
      en: 'Make the change and click Save.',
      ms: 'Buat perubahan dan klik Save.',
      run: async ({ page, click, sleep }) => {
        const dlg = page.getByRole('dialog');
        await click(dlg.getByRole('combobox', { name: 'Access' }));
        await sleep(500);
        await click(page.getByRole('option', { name: 'Business Owner', exact: true }).first());
        await click(dlg.getByRole('button', { name: 'Save', exact: true }));
        await dlg.waitFor({ state: 'hidden', timeout: 30000 });
        await sleep(1200);
      },
    },
    {
      en: 'To take access away, click the three dots on their row and choose Unlink.',
      ms: 'Untuk menarik balik akses, klik tiga titik pada baris mereka dan pilih Unlink.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('button', { name: 'Nora Aziz actions' }).first());
        await sleep(500);
        await click(page.getByRole('menuitem', { name: /Unlink from 300-L001/ }).first(), { hold: 900 });
      },
    },
    {
      en: 'You have a few seconds to press Cancel. After that, their access is removed.',
      ms: 'Anda ada beberapa saat untuk menekan Cancel. Selepas itu, akses mereka dikeluarkan.',
      run: async ({ page, sleep }) => {
        await page.getByRole('cell', { name: 'Nora Aziz', exact: true }).waitFor({ state: 'detached', timeout: 30000 });
        await sleep(1500);
      },
    },
  ],
};
