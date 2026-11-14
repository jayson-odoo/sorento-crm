// Video 6 (Wed 18 Nov, Project CS): order inquiries and their states, view only.
// Recorded as CS (the menu entry needs projects.projects.view, config/menu.config.tsx Order
// Inquiries). Confirm and Reject on a row are purchasing's grant, never CS's
// (sorento_crm_backend/app/api/v1/projects/order_inquiries.py, ACKNOWLEDGE), so this video only
// shows their result: seed_fake.py --part p2 rejects Tower B line 1 through the real route.
// Each step: en = on-screen caption, ms = Malay subtitle (machine-written, needs a native read),
// say = voice line (defaults to en), run = action.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).last();

const wcRow = (page) => page.getByRole('row', { name: /DM-WC-2002/ }).first();

export default {
  id: 'p2-order-inquiry',
  title: 'Order inquiries',
  subtitle: 'Procurement > Supply Chain > Order Inquiries',
  titleMs: 'Pertanyaan pesanan',
  intro: 'In this video you will follow your order inquiries, read each line\'s state, and find a rejected line again.',
  user: { email: 'cs@example.com', password: 'Demo1234!' },
  warm: ['/project-sales/order-inquiries', '/project-sales/fulfilment-planning'],
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
      en: 'Each order inquiry asks purchasing to buy for one sales order.',
      ms: 'Setiap pertanyaan pesanan meminta bahagian pembelian membeli untuk satu pesanan jualan.',
      run: async ({ page, point }) => point(page.getByRole('row', { name: /OI-2611-0001/ }).first(), 1500),
    },
    {
      en: 'Switch between All, Outstanding and Completed to see them by state.',
      ms: 'Tukar antara All, Outstanding dan Completed untuk melihatnya mengikut keadaan.',
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
      en: 'Each line shows the product and the quantity asked for.',
      ms: 'Setiap baris menunjukkan produk dan kuantiti yang diminta.',
      run: async ({ page, point }) => {
        await wcRow(page).waitFor({ timeout: 30000 });
        await point(wcRow(page).getByRole('cell', { name: 'DM-WC-2002', exact: true }), 1200);
        await point(wcRow(page).getByRole('cell', { name: '120', exact: true }).first(), 1200);
      },
    },
    {
      en: 'Further across is each line\'s state, such as Done or Rejected.',
      ms: 'Di hujung kanan ialah keadaan setiap baris, seperti Done atau Rejected.',
      run: async ({ page, point }) => {
        await point(page.getByRole('cell', { name: /^Done/ }).first(), 1300);
        await point(page.getByRole('cell', { name: /^Rejected/ }).first(), 1300);
      },
    },
    {
      en: 'Purchasing confirms or rejects each line, and a rejection always comes with their reason.',
      ms: 'Bahagian pembelian mengesahkan atau menolak setiap baris, dan penolakan sentiasa disertakan sebab.',
      run: async ({ page, point, sleep }) => {
        await point(page.getByRole('cell', { name: /^Rejected/ }).first(), 2500);
        await sleep(500);
      },
    },
    {
      en: 'A rejected line comes back to you on the planning board. Open Fulfilment Planning.',
      ms: 'Baris yang ditolak kembali kepada anda di papan perancangan. Buka Fulfilment Planning.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('menu').first().getByRole('button', { name: 'Supply Chain', exact: true }).first());
        await click(menu(page, 'Project Demand'));
        await click(menu(page, 'Fulfilment Planning'));
        await page.getByRole('checkbox', { name: 'Select SO-DM-26002 for planning' }).waitFor({ timeout: 60000 });
        await sleep(600);
      },
    },
    {
      en: 'Tick the order and click Plan.',
      ms: 'Tandakan pesanan dan klik Plan.',
      run: async ({ page, click }) => {
        await click(page.getByRole('checkbox', { name: 'Select SO-DM-26002 for planning' }));
        await click(page.getByRole('button', { name: /^Plan SO-DM-26002/ }));
        await page.getByRole('row', { name: /SO-DM-26002 line 1/ }).first().waitFor({ timeout: 60000 });
      },
    },
    {
      en: 'The rejected line is here, waiting for you to decide how to supply it again.',
      ms: 'Baris yang ditolak ada di sini, menunggu anda memutuskan cara membekalkannya semula.',
      run: async ({ page, point, sleep }) => {
        await point(page.getByRole('row', { name: /SO-DM-26002 line 1/ }).first(), 2000);
        await sleep(1000);
      },
    },
  ],
};
