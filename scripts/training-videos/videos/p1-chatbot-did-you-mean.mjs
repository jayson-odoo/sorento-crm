// Video 4 (sales): the chatbot's "did you mean" offers and a stock answer, in the Chatbot Console.
// SPEC ONLY until a live run is cleared: sending calls the live model. Dry-run checked up to the
// first send (contact picked, question typed). The bot's wording is unknown before a live run, so
// the steps wait for a new reply instead of asserting its text.
// Fake data only (seed_fake.py: Ravi Kumar, 300-K003, products DM-*). Each step: en = on-screen
// caption, ms = Malay subtitle (machine-written, needs a native read), say = voice line, run = action.
const menu = (page, name) =>
  page.getByRole('menu').first().getByRole('button', { name, exact: true })
    .or(page.getByRole('menu').first().getByRole('link', { name, exact: true })).last();

// Every message in the thread carries one "Message actions" button.
const messages = (page) => page.getByRole('button', { name: 'Message actions' });

// Send what is in the composer, then wait for the bot's reply: the user's message plus at least
// one more. The reply text is never asserted.
async function sendAndWait({ page, click, sleep }) {
  const before = await messages(page).count();
  await click(page.getByRole('button', { name: 'Send message' }));
  await page.waitForFunction(
    (n) => document.querySelectorAll('[aria-label="Message actions"]').length >= n,
    before + 2,
    { timeout: 180000 },
  );
  await page.getByRole('button', { name: 'Sending' }).waitFor({ state: 'detached', timeout: 180000 }).catch(() => {});
  await sleep(1500);
}

export default {
  id: 'p1-chatbot-did-you-mean',
  title: 'Chatbot: did you mean',
  subtitle: 'System > Messaging > Chatbot Console',
  titleMs: 'Chatbot: adakah anda maksudkan',
  intro: 'In this video you will see how the chatbot handles a mistyped product code, and answers with stock.',
  user: { email: 'admin@example.com', password: 'Demo1234!' },
  warm: ['/system-management/chatbot-console'],
  steps: [
    {
      en: 'Open System, then Messaging, then Chatbot Console.',
      ms: 'Buka System, kemudian Messaging, kemudian Chatbot Console.',
      run: async ({ page, click, sleep }) => {
        await click(menu(page, 'System'));
        await click(menu(page, 'Messaging'));
        await click(menu(page, 'Chatbot Console'));
        await page.getByRole('heading', { name: 'Chatbot Console', level: 1 }).waitFor({ timeout: 60000 });
        await sleep(800);
      },
    },
    {
      en: 'Pick the test contact. Messages here are a test and never reach WhatsApp.',
      ms: 'Pilih kenalan ujian. Mesej di sini hanya ujian dan tidak sampai ke WhatsApp.',
      run: async ({ page, click, sleep }) => {
        await click(page.getByRole('combobox').filter({ hasText: 'Pick a contact' }).first());
        await page.keyboard.type('Ravi', { delay: 110 });
        await sleep(1200);
        await click(page.getByRole('option', { name: /Ravi Kumar/ }).first());
        await sleep(1500);
      },
    },
    {
      en: 'Ask for stock the way a customer might, here with a typo in the product code.',
      ms: 'Tanya stok seperti pelanggan, di sini dengan kesilapan pada kod produk.',
      run: async ({ page, type }) =>
        type(page.getByRole('textbox', { name: 'Ask, or attach voice/image' }), 'stock DM-BS-101', { delay: 90 }),
    },
    {
      en: 'Send it. The bot does not know that code, so it offers the closest matches.',
      ms: 'Hantar. Bot tidak mengenali kod itu, jadi ia menawarkan padanan yang paling hampir.',
      run: async (h) => sendAndWait(h),
    },
    {
      en: 'Read the offers it gives.',
      ms: 'Baca tawaran yang diberikan.',
      run: async ({ page, point }) => point(messages(page).last(), 2500),
    },
    {
      en: 'Answer with the one you meant.',
      ms: 'Jawab dengan yang anda maksudkan.',
      run: async (h) => {
        await h.type(h.page.getByRole('textbox', { name: 'Ask, or attach voice/image' }), 'DM-BS-1001', { delay: 90 });
        await sendAndWait(h);
      },
    },
    {
      en: 'The bot now answers with the stock for that product.',
      ms: 'Bot kini menjawab dengan stok untuk produk itu.',
      run: async ({ page, point, sleep }) => {
        await point(messages(page).last(), 2500);
        await sleep(1500);
      },
    },
  ],
};
