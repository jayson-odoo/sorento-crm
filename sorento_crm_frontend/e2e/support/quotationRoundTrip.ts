/**
 * Shared scaffolding for the two quotation round-trip specs.
 *
 * Both specs need the SAME starting position: an ISSUED quotation, with a scope and a priced
 * line, that this run owns outright. That is about sixty clicks of setup, and copying it into
 * two files would let the two copies drift - which matters more than usual here, because the
 * setup is also the thing that guarantees neither spec touches production data.
 *
 * Lives under `e2e/support/` rather than beside the specs so Playwright's default `testMatch`
 * (`**\/*.@(spec|test).*`) never collects it as a test file.
 *
 * WHY IT BUILDS ITS OWN PROJECT
 * -----------------------------
 * The dev database is a copy of PRODUCTION. Requesting changes on, or issuing, a real
 * salesperson's quotation would be a write against real work. So each run registers its own
 * `ZZT ...` project, quotes inside it, and deletes the project at the end - which cascades
 * (`project_quotation_documents.project_id ON DELETE CASCADE`) and takes the document, its
 * scopes, versions, lines, issues and signatures with it.
 *
 * That cascade is the ONLY way to clean up: `DELETE /quotation-documents/{id}` refuses an
 * issued document outright ("Withdraw it instead", 422 `quotation_document_issued`), and no
 * withdraw route exists. Deleting the owning project is the supported exit.
 *
 * WHY EVERY CLICK IS `dispatchEvent('click')`
 * -------------------------------------------
 * Inside the `(protected)` layout Playwright's real `locator.click()` never returns - it
 * performs the action and then blocks in its post-action wait, well past its own timeout
 * (measured: a 6s-timeout click settled after 128s). Established repo workaround, already
 * commented in `request-batch-regressions.spec.ts` and `scm-policies.spec.ts`. A dispatched
 * click bubbles to React's root listener, so every plain button and menu item works.
 *
 * The one thing it cannot do is open a Radix dropdown: `DropdownMenuTrigger` opens on
 * `pointerdown` / Enter, not on click. Those go through `openMenu`, which focuses the trigger
 * and presses Enter - the keyboard path the component already supports.
 */
import { expect, type Locator, type Page } from '@playwright/test';

/** Spec-specific first, then the pair every other spec in this directory uses. */
export const EMAIL = process.env.QUOTATION_E2E_EMAIL ?? process.env.REQUEST_BATCH_E2E_EMAIL;
export const PASSWORD =
  process.env.QUOTATION_E2E_PASSWORD ?? process.env.REQUEST_BATCH_E2E_PASSWORD;

export async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

/** Assert the control is really there, then activate it. See the docblock on the click hang. */
export async function press(target: Locator) {
  await expect(target).toBeVisible({ timeout: 20_000 });
  await target.dispatchEvent('click');
}

/** Radix opens a dropdown on pointerdown or Enter; a dispatched click does neither. */
export async function openMenu(page: Page, trigger: Locator) {
  await expect(trigger).toBeVisible({ timeout: 20_000 });
  await trigger.focus();
  await page.keyboard.press('Enter');
}

/**
 * Radix tabs select on mousedown / focus / Enter - again, never on a dispatched click. Focus
 * alone is enough under the default automatic activation; Enter covers a manual one.
 */
export async function selectTab(page: Page, tab: Locator) {
  await expect(tab).toBeVisible({ timeout: 20_000 });
  await tab.focus();
  await page.keyboard.press('Enter');
  await expect(tab).toHaveAttribute('data-state', 'active', { timeout: 10_000 });
}

/**
 * Project Sales -> Pipeline, by clicking the sidebar from `/`.
 *
 * Never a deep `page.goto`: the group has to be found, expanded and its leaf clicked, which is
 * what catches a missing menu entry, a wrong `moduleKey` or a permission gate. `exact: true`
 * matters - "Project Sales Admin" is a separate group whose name the loose match hits first.
 */
export async function gotoPipelineViaSidebar(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: 'Project Sales', exact: true }).first();
  await expect(group).toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }
  await press(page.getByRole('link', { name: /^pipeline$/i }).first());
  await page.waitForURL(/project-sales\/pipeline/, { timeout: 30_000 });
}

export type IssuedQuotation = {
  /** `/project-sales/{id}` - where the teardown goes to delete everything. */
  projectUrl: string;
  /** `/project-sales/{id}/quotation-documents/{id}` - only for asserting where we are. */
  documentUrl: string;
  projectTitle: string;
  scopeLabel: string;
  /** "SRT/Q/2026/0142 (R1)" - the chip label and the counter-sign page's Our Ref. */
  ourRef: string;
};

/**
 * Register a project, quote one scope with one priced line, sign it, issue R1.
 *
 * Every name it writes starts with `ZZT` so anything that escapes teardown is recognisable as
 * test residue rather than someone's work.
 *
 * Reached by clicking through: sidebar -> Pipeline -> Register project -> the project's own
 * Quotations tab -> Add a quotation. The router carries us to each new record, so nothing here
 * needs a deep URL either.
 */
export async function createIssuedQuotation(
  page: Page,
  tag: string,
  /**
   * Called the instant the project exists, before anything else can fail.
   *
   * Teardown cannot wait for the return value: a setup that breaks half-way through pricing
   * would then leave the project behind with no url to delete it by.
   */
  onProjectCreated?: (projectUrl: string) => void,
): Promise<IssuedQuotation> {
  const stamp = Date.now();
  const projectTitle = `ZZT ${tag} ${stamp}`;
  const scopeLabel = `ZZT Scope ${stamp}`;

  await gotoPipelineViaSidebar(page);

  await press(page.getByRole('button', { name: /register project/i }));
  const register = page.getByRole('dialog');
  await expect(register.getByText('Register a project')).toBeVisible({ timeout: 15_000 });
  // Title is the ONLY required field, so the project stays free of any real developer,
  // architect or contractor party.
  await register.locator('#project-title').fill(projectTitle);
  await press(register.getByRole('button', { name: /register project/i }));
  await page.waitForURL(/project-sales\/[0-9a-f-]{36}(\?|$)/, { timeout: 30_000 });
  const projectUrl = page.url();
  onProjectCreated?.(projectUrl);

  await press(page.getByRole('button', { name: /^quotations$/i }));
  await press(page.getByRole('button', { name: /add a quotation/i }));
  await page.waitForURL(/quotation-documents\/[0-9a-f-]{36}/, { timeout: 30_000 });
  const documentUrl = page.url();

  // A scope. `issue` refuses a document with none (422 quotation_document_no_scopes).
  await press(page.getByRole('button', { name: /add a scope/i }).first());
  const scopeDialog = page.getByRole('dialog');
  await expect(scopeDialog.getByText('Add a scope')).toBeVisible({ timeout: 15_000 });
  await scopeDialog.locator('#quotation-name-field').fill(scopeLabel);
  await press(scopeDialog.getByRole('button', { name: /^add$/i }));
  await expect(page.getByTestId('quotation-scope-strip')).toBeVisible({ timeout: 20_000 });

  // One priced line, through the edit session the salesperson uses. Off-catalog (no product),
  // which is a real state the line editor supports and keeps the spec off the product catalog.
  await openMenu(page, page.getByRole('button', { name: /quotation actions/i }));
  await press(page.getByRole('menuitem', { name: /edit quotation/i }));
  await press(page.getByRole('button', { name: /add a line/i }));
  // `describeRow` names an unsaved row by its position, so the cells are "<column> on line 1".
  await page.getByLabel('Description on line 1').fill('ZZT supply and install');
  await page.getByLabel('Qty on line 1').fill('2');
  await page.getByLabel('Unit price on line 1').fill('1250.00');
  await press(page.getByRole('button', { name: /^save$/i }));
  // The server's own arithmetic coming back, not the browser's: 2 x 1250.00. Waiting on this
  // rather than on a toast is what proves the line actually landed before we issue.
  await expect(page.getByText('RM 2,500.00').first()).toBeVisible({ timeout: 30_000 });

  // Sign. Type mode is the keyboard-reachable capture path; Draw needs pointer strokes.
  await press(page.getByRole('button', { name: /^sign$/i }));
  const signDialog = page.getByRole('dialog');
  await expect(signDialog.getByText('Sign this quotation')).toBeVisible({ timeout: 15_000 });
  await selectTab(page, signDialog.getByRole('tab', { name: /^type$/i }));
  await signDialog.getByLabel('Full name').fill('ZZT Signer');
  await press(signDialog.getByRole('button', { name: /apply signature/i }));
  // AC-H1: no signature, no issue. The CTA only goes live once the ink is stored.
  const issue = page.getByRole('button', { name: /^issue r1$/i });
  await expect(issue).toBeEnabled({ timeout: 30_000 });
  await press(issue);

  // The printer chip is titled after the revision, and it only renders once one exists - so
  // its title is both the proof that R1 landed and the reference the customer will quote back.
  const chip = page.locator('button[title^="View downloads for"]');
  await expect(chip).toBeVisible({ timeout: 30_000 });
  const ourRef = ((await chip.getAttribute('title')) ?? '').replace(
    /^View downloads for\s+/,
    '',
  );

  return { projectUrl, documentUrl, projectTitle, scopeLabel, ourRef };
}

/**
 * Teardown. Deleting the project is what removes the issued quotation: the document's own
 * delete route refuses an issued one, and the FK cascade does not.
 *
 * Best-effort by design - a teardown that throws would replace the real failure with its own.
 */
export async function deleteProject(page: Page, projectUrl: string) {
  await page.goto(projectUrl, { waitUntil: 'commit' });
  await openMenu(page, page.getByRole('button', { name: /project actions/i }));
  await press(page.getByRole('menuitem', { name: /delete project/i }));
  const confirm = page.getByRole('dialog');
  await expect(confirm.getByText('Confirm delete')).toBeVisible({ timeout: 15_000 });
  await press(confirm.getByRole('button', { name: /^delete$/i }));
  await page.waitForURL(/project-sales\/(pipeline|projects)/, { timeout: 30_000 });
}
