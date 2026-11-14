// Video 7 (Wed 18 Nov, Project CS): read an approved order change notice and mark it done.
// Recorded as CS, who holds view + process (Mark done) on notices, never create or approve.
// seed_fake.py --part p3 walks OCN26-0001 to Approved through the real routes (Aina Admin raises
// and sends it for approval, Farid Manager approves), plus two more notices for the list.
// Each step: en = on-screen caption, ms = Malay subtitle (machine-written, needs a native read),
// say = voice line (defaults to en), run = action.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).first();

const NOTICE = 'OCN26-0001';
const lineRow = (page, code) => page.getByRole('row', { name: new RegExp(`^${code}`) }).first();

export default {
  id: 'p2-order-change-notice',
  title: 'Order change notices',
  subtitle: 'Project Sales Admin > Order Change Notices',
  titleMs: 'Notis perubahan pesanan',
  intro: 'In this video you will read an approved order change notice, then mark it done once the change is arranged.',
  user: { email: 'cs@example.com', password: 'Demo1234!' },
  warm: ['/procurement-management/order-change-notices'],
  steps: [
    {
      en: 'Open Project Sales Admin, then Order Change Notices.',
      ms: 'Buka Project Sales Admin, kemudian Order Change Notices.',
      run: async ({ page, click, sleep }) => {
        await click(menu(page, 'Project Sales Admin'));
        await click(menu(page, 'Order Change Notices'));
        await page.getByRole('row', { name: new RegExp(NOTICE) }).first().waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Each notice asks to change a confirmed order: bring it forward, swap a product, cancel or delay.',
      ms: 'Setiap notis meminta perubahan pada pesanan yang telah disahkan: awalkan, tukar produk, batal atau tangguh.',
      run: async ({ page, point }) => {
        await point(page.getByRole('cell', { name: 'Exchange', exact: true }).first(), 1000);
        await point(page.getByRole('cell', { name: 'Delay', exact: true }).first(), 1000);
        await point(page.getByRole('cell', { name: 'Cancellation', exact: true }).first(), 1000);
      },
    },
    {
      en: 'Customer service acts on a notice once management has approved it. Open the notice.',
      ms: 'Khidmat pelanggan bertindak selepas pengurusan meluluskan notis. Buka notis itu.',
      run: async ({ page, click }) => {
        await click(page.getByRole('cell', { name: NOTICE, exact: true }).first());
        await page.getByRole('heading', { name: new RegExp(`^${NOTICE}`) }).waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'The header shows the notice number, its status, Approved, and the customer\'s PO.',
      ms: 'Bahagian atas menunjukkan nombor notis, statusnya, Approved, dan PO pelanggan.',
      run: async ({ page, point }) => {
        await point(page.getByRole('heading', { name: new RegExp(`^${NOTICE}`) }), 1800);
        await point(page.getByText(/^Lim Bina Hardware Sdn Bhd, PO/).first(), 1200);
      },
    },
    {
      en: 'Read the type of change and its risk. This is an exchange, which is high risk.',
      ms: 'Baca jenis perubahan dan risikonya. Ini pertukaran, yang berisiko tinggi.',
      run: async ({ page, point }) => {
        await point(page.getByText('Exchange', { exact: true }).first(), 1200);
        await point(page.getByText('Risk: High', { exact: true }).first(), 1500);
      },
    },
    {
      en: 'The lines say what changes. The chrome mixer goes from 40 to 0, and the matte black one from 0 to 40.',
      ms: 'Baris-baris menunjukkan apa yang berubah. Pili krom dari 40 kepada 0, dan yang hitam matte dari 0 kepada 40.',
      run: async ({ page, point }) => {
        const one = lineRow(page, 'DM-BS-1001');
        const two = lineRow(page, 'DM-BS-1002');
        await one.scrollIntoViewIfNeeded();
        await point(one.getByRole('cell').nth(1), 900);
        await point(one.getByRole('cell').nth(2), 900);
        await point(two.getByRole('cell').nth(1), 900);
        await point(two.getByRole('cell').nth(2), 900);
      },
    },
    {
      en: 'The dates show when it was due and when it is due now: the new mixer moves to 5 January.',
      ms: 'Tarikh menunjukkan bila ia sepatutnya dihantar dan bila sekarang: pili baharu dianjak ke 5 Januari.',
      run: async ({ page, point }) => {
        const two = lineRow(page, 'DM-BS-1002');
        await point(two.getByRole('cell', { name: '15/12/2026' }), 1200);
        await point(two.getByRole('cell', { name: '05/01/2027' }), 1500);
      },
    },
    {
      en: 'Below the lines is management\'s decision: approved, with their remarks.',
      ms: 'Di bawah baris ialah keputusan pengurusan: diluluskan, bersama catatan mereka.',
      run: async ({ page, point }) => {
        await point(page.getByText('Farid Manager', { exact: true }).first(), 1200);
        await point(page.getByText('Agreed with the customer.', { exact: true }).first(), 1200);
      },
    },
    {
      en: 'When you have arranged the change, click Mark done.',
      ms: 'Apabila anda telah menguruskan perubahan itu, klik Mark done.',
      run: async ({ page, click }) => {
        await page.mouse.wheel(0, -2000);
        await click(page.getByRole('button', { name: 'Mark done', exact: true }).first());
        await page.getByRole('dialog').waitFor({ timeout: 30000 });
      },
    },
    {
      en: 'Add a short comment for the team, then confirm.',
      ms: 'Tambah komen ringkas untuk pasukan, kemudian sahkan.',
      run: async ({ page, type, click, sleep }) => {
        const box = page.getByRole('dialog').getByRole('textbox').first();
        await type(box, 'Exchange booked with the warehouse for 5 January.', { delay: 45 });
        await sleep(400);
        await click(page.getByRole('dialog').getByRole('button', { name: 'Mark done', exact: true }));
        await page.getByRole('heading', { name: new RegExp(`^${NOTICE}\\s*Done`) }).waitFor({ timeout: 60000 });
        await sleep(600);
      },
    },
    {
      en: 'The notice is now Done, and your comment is on it for everyone to see.',
      ms: 'Notis kini Done, dan komen anda ada padanya untuk dilihat semua.',
      run: async ({ page, point }) => {
        await point(page.getByRole('heading', { name: new RegExp(`^${NOTICE}`) }), 1500);
        await point(page.getByText('Exchange booked with the warehouse for 5 January.').first(), 1800);
      },
    },
    {
      en: 'Open the History tab: every step is recorded, with who did it and when.',
      ms: 'Buka tab History: setiap langkah direkodkan, dengan siapa dan bila.',
      run: async ({ page, click, point, sleep }) => {
        await page.mouse.wheel(0, -2000);
        await click(page.getByRole('tab', { name: 'History', exact: true }));
        const panel = page.getByRole('tabpanel', { name: 'History' });
        await panel.getByText(/Done/).first().waitFor({ timeout: 30000 });
        await sleep(500);
        await point(panel.getByText(/Done/).first(), 2200);
      },
    },
    {
      en: 'Further down are the earlier steps: who raised it, who sent it for approval and who approved it.',
      ms: 'Di bawah ialah langkah-langkah awal: siapa yang membuatnya, menghantarnya untuk kelulusan dan meluluskannya.',
      run: async ({ page, point, sleep }) => {
        const panel = page.getByRole('tabpanel', { name: 'History' });
        await point(panel.getByText(/Farid Manager/).first(), 1800);
        await point(panel.getByText(/Aina Admin/).last(), 1800);
        await sleep(600);
      },
    },
  ],
};
