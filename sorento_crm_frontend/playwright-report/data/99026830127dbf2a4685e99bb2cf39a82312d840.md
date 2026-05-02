# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: portal-ai-extract.spec.ts >> Portal AI Extract >> drag samples → extract → review → confirm prefills the complaint form
- Location: e2e/portal-ai-extract.spec.ts:45:7

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('ai-extract-trigger')
Expected: visible
Timeout: 15000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByTestId('ai-extract-trigger')

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - alert [ref=e2]
  - generic [ref=e6]:
    - link "Back" [ref=e8] [cursor=pointer]:
      - /url: /portal
      - img [ref=e9]
      - text: Back
    - generic [ref=e11]:
      - heading "Complaint Information" [level=3] [ref=e13]
      - generic [ref=e15]:
        - generic [ref=e17]:
          - text: Customer name
          - textbox "Customer name" [ref=e19]:
            - /placeholder: Search debtors...
        - generic [ref=e21]:
          - text: Contact person
          - textbox "Contact person" [ref=e22]
        - generic [ref=e24]:
          - text: Contact number
          - textbox "Contact number" [ref=e25]
        - generic [ref=e27]:
          - text: Customer address
          - textbox "Customer address" [ref=e28]
        - generic [ref=e30]:
          - text: Customer type
          - combobox "Customer type" [ref=e31]:
            - generic: Select...
            - img [ref=e32]
        - generic [ref=e35]:
          - text: Delivery order number(s)
          - button "Search & select delivery orders" [ref=e37] [cursor=pointer]:
            - img [ref=e38]
            - text: Search & select delivery orders
        - generic [ref=e42]:
          - text: Complaint date
          - textbox "Complaint date" [ref=e43]: 2026-05-02
        - generic [ref=e45]:
          - text: Product code
          - textbox "Product code" [ref=e47]:
            - /placeholder: Search products...
        - generic [ref=e49]:
          - text: Product type
          - textbox "Product type" [ref=e50]
        - generic [ref=e52]:
          - text: Within warranty
          - combobox "Within warranty" [ref=e53]:
            - generic: Select...
            - img [ref=e54]
        - generic [ref=e57]:
          - text: Defects discovered
          - combobox "Defects discovered" [ref=e58]:
            - generic: Select...
            - img [ref=e59]
        - generic [ref=e62]:
          - text: Complaint type
          - combobox "Complaint type" [ref=e63]:
            - generic: Select...
            - img [ref=e64]
        - generic [ref=e67]:
          - text: Defect description
          - textbox "Defect description" [ref=e68]
        - generic [ref=e70]:
          - text: Salesperson
          - textbox "Salesperson" [ref=e71]: Jayson
        - generic [ref=e73]:
          - text: Project title
          - textbox "Project title" [ref=e74]
    - generic [ref=e75]:
      - heading "Attachments" [level=3] [ref=e77]
      - generic [ref=e80]:
        - img [ref=e81]
        - paragraph [ref=e84]: Drop a file here, paste a screenshot, or
        - generic [ref=e85]:
          - button "Choose file" [ref=e86] [cursor=pointer]:
            - img [ref=e87]
            - text: Choose file
          - button "Paste from clipboard" [ref=e89] [cursor=pointer]:
            - img [ref=e90]
            - text: Paste from clipboard
    - generic [ref=e93]:
      - button "Cancel" [ref=e94] [cursor=pointer]
      - button "Save as draft" [ref=e95] [cursor=pointer]
      - button "Submit" [ref=e96] [cursor=pointer]
  - region "Notifications alt+T"
```

# Test source

```ts
  1   | /**
  2   |  * AI Extract end-to-end against the running stack.
  3   |  *
  4   |  * Prerequisites (driven by env vars):
  5   |  *   PORTAL_E2E_BASE_URL    base URL of the Next.js portal (default http://localhost:3000)
  6   |  *   PORTAL_E2E_TOKEN       a valid X-Portal-Token for an already-onboarded portal contact
  7   |  *
  8   |  * Backend prerequisites:
  9   |  *   - sorento_crm_backend running with valid AIAssistantConfig.api_key_ciphertext
  10  |  *     (provider can be 'openai' or 'anthropic'; the spec runs identically for both).
  11  |  *   - PyMuPDF installed in the backend venv.
  12  |  *
  13  |  * The fixtures committed in e2e/fixtures/ai-extract/ are:
  14  |  *   - image-01.png … image-07.png  (defect photos / DO screenshots / message captures)
  15  |  *   - PS202603-0071_WATER_CARE.pdf
  16  |  *   - 20260415153447847.pdf
  17  |  */
  18  | import { test, expect, Page } from '@playwright/test';
  19  | import path from 'path';
  20  | 
  21  | const FIXTURES = path.resolve(__dirname, 'fixtures', 'ai-extract');
  22  | const FIXTURE_FILES = [
  23  |   'image-01.png',
  24  |   'image-02.png',
  25  |   'image-03.png',
  26  |   'image-04.png',
  27  |   'image-05.png',
  28  |   'image-06.png',
  29  |   'image-07.png',
  30  |   'PS202603-0071_WATER_CARE.pdf',
  31  |   '20260415153447847.pdf',
  32  | ].map((f) => path.join(FIXTURES, f));
  33  | 
  34  | const TOKEN = process.env.PORTAL_E2E_TOKEN;
  35  | 
  36  | test.describe('Portal AI Extract', () => {
  37  |   test.beforeEach(async ({ page }) => {
  38  |     test.skip(
  39  |       !TOKEN,
  40  |       'Set PORTAL_E2E_TOKEN to a valid portal token to run the AI Extract e2e.',
  41  |     );
  42  |     await seedPortalToken(page, TOKEN!);
  43  |   });
  44  | 
  45  |   test('drag samples → extract → review → confirm prefills the complaint form', async ({ page }) => {
  46  |     await page.goto('/portal/complaint/new');
> 47  |     await expect(page.getByTestId('ai-extract-trigger')).toBeVisible();
      |                                                          ^ Error: expect(locator).toBeVisible() failed
  48  | 
  49  |     await page.getByTestId('ai-extract-trigger').click();
  50  |     await expect(page.getByTestId('ai-extract-dialog')).toBeVisible();
  51  | 
  52  |     await page.getByTestId('ai-extract-file-input').setInputFiles(FIXTURE_FILES);
  53  | 
  54  |     await page.getByTestId('ai-extract-run').click();
  55  | 
  56  |     await expect(page.getByTestId('ai-extract-review')).toBeVisible({
  57  |       timeout: 90_000,
  58  |     });
  59  | 
  60  |     // High-confidence assertions: at least one of the expected DO numbers
  61  |     // should appear in the extracted delivery_order_number row.
  62  |     const doRow = page.getByTestId('ai-extract-field-delivery_order_number');
  63  |     await expect(doRow).toBeVisible();
  64  |     const doText = (await doRow.textContent()) ?? '';
  65  |     expect(/PS202603-0071|PO2509-013/.test(doText)).toBeTruthy();
  66  | 
  67  |     // Customer name and address should be non-empty when the model picked them up.
  68  |     const optional = ['customer_name', 'customer_address', 'product_code', 'defect_description'] as const;
  69  |     for (const f of optional) {
  70  |       const row = page.getByTestId(`ai-extract-field-${f}`);
  71  |       if (await row.isVisible()) {
  72  |         const txt = ((await row.textContent()) ?? '').trim();
  73  |         expect(txt.length).toBeGreaterThan(0);
  74  |       }
  75  |     }
  76  | 
  77  |     // Drop salesperson if it was guessed (rarely correct from an arbitrary photo).
  78  |     const salesperson = page.getByTestId('ai-extract-field-salesperson');
  79  |     if (await salesperson.isVisible()) {
  80  |       await page.getByTestId('ai-extract-drop-salesperson').click();
  81  |       await expect(salesperson).toHaveCount(0);
  82  |     }
  83  | 
  84  |     await page.getByTestId('ai-extract-confirm').click();
  85  |     await expect(page.getByTestId('ai-extract-dialog')).toHaveCount(0);
  86  | 
  87  |     // After confirm, the live form should now have a non-empty defect description.
  88  |     const description = page.getByLabel(/Defect description/i);
  89  |     if (await description.isVisible()) {
  90  |       await expect(description).not.toHaveValue('');
  91  |     }
  92  |   });
  93  | });
  94  | 
  95  | async function seedPortalToken(page: Page, token: string) {
  96  |   await page.addInitScript((t: string) => {
  97  |     try {
  98  |       window.sessionStorage.setItem('sorento.portalToken', t);
  99  |     } catch {
  100 |       // Some browsers throw when sessionStorage is locked down; ignore in init.
  101 |     }
  102 |   }, token);
  103 | }
  104 | 
```