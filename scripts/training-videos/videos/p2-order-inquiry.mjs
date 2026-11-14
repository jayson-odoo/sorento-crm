// Video 6 (Wed 18 Nov, Project CS): order inquiries, their states, and how purchasing answers.
// Recorded as the purchasing user: Confirm and Reject on a row are purchasing's grant, never
// CS's (sorento_crm_backend/app/api/v1/projects/order_inquiries.py, ACKNOWLEDGE).
// Fake data only (seed_fake.py --part p2). Each step: en = on-screen caption, ms = Malay subtitle
// (machine-written, needs a native read), say = voice line (defaults to en), run = action.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).last();

// The first row still to order. Rejecting one rewrites that order's plan, so a re-run picks
// whichever row is still open; a clean final take wants a freshly seeded --part p2 database.
const rejectable = (page) => page.getByRole('checkbox', { name: /^Select .+ on SO-DM-2600[12]$/ }).first();

export default {
  id: 'p2-order-inquiry',
  title: 'Order inquiries',
  subtitle: 'Procurement > Supply Chain > Order Inquiries',
  titleMs: 'Pertanyaan pesanan',
  intro: 'In this video you will see order inquiries and their states, and how purchasing confirms or rejects a line.',
  user: { email: 'purchasing@example.com', password: 'Demo1234!' },
  warm: ['/project-sales/order-inquiries'],
  steps: [
    {
      en: 'Open Procurement, then Supply Chain, then Order Inquiries.',
      ms: 'Buka Procurement, kemudian Supply Chain, kemudian Order Inquiries.',
      run: async ({ page, click, sleep }) => {
        await click(menu(page, 'Procurement'));
        await click(menu(page, 'Supply Chain'));
        await click(menu(page, 'Order Inquiries'));
        await page.getByRole('row', { name: /OI-2611-0001/ }).first().waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Each order inquiry asks purchasing to buy for one sales order. Outstanding ones are shown first.',
      ms: 'Setiap pertanyaan pesanan meminta pembelian untuk satu pesanan jualan. Yang belum selesai ditunjukkan dahulu.',
      run: async ({ page, point }) => point(page.getByRole('row', { name: /OI-2611-0001/ }).first(), 1500),
    },
    {
      en: 'Switch between All, Outstanding and Completed to see inquiries in each state.',
      ms: 'Tukar antara All, Outstanding dan Completed untuk melihat pertanyaan dalam setiap keadaan.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('radio', { name: 'Completed', exact: true }));
        await sleep(1200);
        await click(page.getByRole('radio', { name: 'All', exact: true }));
        await page.getByRole('row', { name: /OI-2611-0002/ }).first().waitFor({ timeout: 30000 });
      },
    },
    {
      en: 'Open an inquiry to see its lines.',
      ms: 'Buka pertanyaan untuk melihat baris-barisnya.',
      run: async ({ page, click }) => {
        await click(page.getByRole('cell', { name: 'OI-2611-0002', exact: true }).first());
        await page.getByRole('heading', { name: 'OI-2611-0002' }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'Each line shows its quantity, delivery date and its own state, such as Done.',
      ms: 'Setiap baris menunjukkan kuantiti, tarikh penghantaran dan keadaannya sendiri, seperti Done.',
      run: async ({ page, point }) => {
        await point(page.getByRole('cell', { name: /^Done/ }).first(), 1300);
        await point(page.getByRole('cell', { name: /^Done/ }).last(), 1300);
      },
    },
    {
      en: 'Use the arrows to move to the other inquiry.',
      ms: 'Guna anak panah untuk beralih ke pertanyaan lain.',
      run: async ({ page, click }) => {
        await click(page.getByRole('button', { name: 'Previous order inquiry' }));
        await page.getByRole('heading', { name: 'OI-2611-0001' }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'To take a line on, tick it and click Confirm.',
      ms: 'Untuk menerima satu baris, tandakan dan klik Confirm.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('checkbox', { name: 'Select DM-WC-2002' }));
        await click(page.getByRole('button', { name: /^Confirm \(1\)/ }));
        await sleep(2500);
      },
    },
    {
      en: 'To refuse a line, go back to the list and switch to Lines.',
      ms: 'Untuk menolak satu baris, kembali ke senarai dan tukar ke Lines.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('link', { name: 'Back to order inquiries' }));
        await click(page.getByRole('button', { name: 'Lines', exact: true }));
        await rejectable(page).waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Tick the line, open Actions and choose Reject selected.',
      ms: 'Tandakan baris itu, buka Actions dan pilih Reject selected.',
      run: async ({ page, click }) => {
        await click(rejectable(page));
        await click(page.getByRole('button', { name: 'Actions', exact: true }));
        await click(page.getByRole('menuitem', { name: /Reject selected/ }));
        await page.getByRole('alertdialog').waitFor({ timeout: 30000 });
      },
    },
    {
      en: 'A reason is required, so CS knows why. Then click Reject row.',
      ms: 'Sebab diperlukan, supaya CS tahu mengapa. Kemudian klik Reject row.',
      run: async ({ page, type, click, sleep }) => {
        const dlg = page.getByRole('alertdialog');
        await type(dlg.getByRole('textbox'), 'Supplier has stopped this model.', { delay: 45 });
        await click(dlg.getByRole('button', { name: 'Reject row', exact: true }));
        await dlg.waitFor({ state: 'hidden', timeout: 30000 });
        await sleep(1500);
      },
    },
    {
      en: 'The line is rejected, and CS decides it again on the planning board.',
      ms: 'Baris itu ditolak, dan CS membuat keputusan semula di papan perancangan.',
      run: async ({ page, point, sleep }) => {
        await point(page.getByRole('table').first(), 1500);
        await sleep(800);
      },
    },
  ],
};
