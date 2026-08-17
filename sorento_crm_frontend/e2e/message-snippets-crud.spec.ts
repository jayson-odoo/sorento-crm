/**
 * Message Snippets CRUD (PLAN-conversation-intervention-tickets.md slice S4.4,
 * UAC AC-L4). Sidebar -> SLA Management -> Message Snippets -> Add snippet
 * (modal) -> row appears -> edit -> delete via ConfirmDeleteDialog, each step
 * pinned to the real `/api/v1/sla-management/message-snippets` write.
 *
 * Env (test skipped without EMAIL/PASSWORD):
 *   PORTAL_E2E_BASE_URL=http://localhost:3000   (default in playwright.config)
 *   MESSAGE_SNIPPETS_E2E_EMAIL / MESSAGE_SNIPPETS_E2E_PASSWORD, falling back to
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD. The account needs
 *   `sla_management.message_snippets.{view,add,edit,delete}`.
 *
 * Marker: every row this spec creates is named `E2E-P4-...`. The test deletes
 * its own row through the UI as part of the flow; `afterAll` runs a best-effort
 * API sweep (same session, via `page.request` against the Next.js proxy) for
 * anything the UI flow left behind on a failed run.
 */
import { test, expect, type Page } from '@playwright/test';

const EMAIL = process.env.MESSAGE_SNIPPETS_E2E_EMAIL ?? process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD =
  process.env.MESSAGE_SNIPPETS_E2E_PASSWORD ?? process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(
  !EMAIL || !PASSWORD,
  'Set MESSAGE_SNIPPETS_E2E_* (or REQUEST_BATCH_E2E_*) env vars to run this spec.',
);

const MARKER = 'E2E-P4-';
const RUN_ID = Date.now().toString(36);
const SNIPPET_NAME = `${MARKER}Snippet ${RUN_ID}`;
const SNIPPET_NAME_EDITED = `${MARKER}Snippet ${RUN_ID} edited`;
const SNIPPET_SHORTCUT = `e2ep4${RUN_ID}`;
const SNIPPET_BODY = 'Hi $contact_name, this is an automated E2E-P4 test snippet.';

const SNIPPETS_API = '/api/v1/sla-management/message-snippets';

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /sign in|log in|continue/i }).click();
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
}

/** Sidebar click-through, never a deep link (project convention). */
async function gotoMessageSnippets(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: /SLA Management/i }).first().click();
  await page.getByRole('link', { name: /Message Snippets/i }).first().click();
  await expect(page).toHaveURL(/\/sla-management\/message-snippets$/, { timeout: 20_000 });
}

/** Best-effort API sweep for anything the UI flow failed to delete. */
async function sweepLeftoverSnippets(page: Page) {
  try {
    const listResp = await page.request.get(
      `${SNIPPETS_API}?query=${encodeURIComponent(MARKER)}&limit=100`,
    );
    if (!listResp.ok()) return;
    let body: { data?: { id: string; name: string }[] } | null = null;
    try {
      body = await listResp.json();
    } catch {
      return;
    }
    const rows = body?.data ?? [];
    for (const row of rows) {
      if (row.name?.startsWith(MARKER)) {
        await page.request.delete(`${SNIPPETS_API}/${encodeURIComponent(row.id)}`).catch(() => {});
      }
    }
  } catch {
    // best-effort - never fail the suite on teardown
  }
}

test.describe('Message Snippets CRUD (AC-L4)', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test.afterAll(async () => {
    await sweepLeftoverSnippets(page);
    await page.close();
  });

  test('create, edit and delete a snippet via the modal', async () => {
    await gotoMessageSnippets(page);

    // ---- Create ----
    await page.getByRole('button', { name: /add snippet/i }).click();
    const createDialog = page.getByRole('dialog').filter({ hasText: 'Add snippet' });
    await expect(createDialog).toBeVisible();

    await createDialog.locator('#snippet-name').fill(SNIPPET_NAME);
    await createDialog.locator('#snippet-shortcut').fill(SNIPPET_SHORTCUT);
    await createDialog.locator('#snippet-body').fill(SNIPPET_BODY);

    const createResponse = page.waitForResponse(
      (res) => res.url().endsWith(SNIPPETS_API) && res.request().method() === 'POST',
      { timeout: 20_000 },
    );
    await createDialog.getByRole('button', { name: /^create snippet$/i }).click();
    const createResult = await createResponse;
    expect(createResult.ok()).toBeTruthy();
    await expect(createDialog).not.toBeVisible({ timeout: 10_000 });

    // ---- Row appears (search narrows to our marker) ----
    await page.getByLabel('Search snippets').fill(SNIPPET_NAME);
    const row = page.getByRole('row', { name: new RegExp(SNIPPET_NAME, 'i') }).first();
    await expect(row).toBeVisible({ timeout: 15_000 });
    await expect(row.getByText(`/${SNIPPET_SHORTCUT}`)).toBeVisible();

    // ---- Edit ----
    await row.getByRole('button', { name: `Edit ${SNIPPET_NAME}` }).click();
    const editDialog = page.getByRole('dialog').filter({ hasText: 'Edit snippet' });
    await expect(editDialog).toBeVisible();
    await editDialog.locator('#snippet-name').fill(SNIPPET_NAME_EDITED);

    const updateResponse = page.waitForResponse(
      (res) =>
        res.url().includes(`${SNIPPETS_API}/`) && res.request().method() === 'PUT',
      { timeout: 20_000 },
    );
    await editDialog.getByRole('button', { name: /^save changes$/i }).click();
    const updateResult = await updateResponse;
    expect(updateResult.ok()).toBeTruthy();
    await expect(editDialog).not.toBeVisible({ timeout: 10_000 });

    await page.getByLabel('Search snippets').fill(SNIPPET_NAME_EDITED);
    const editedRow = page.getByRole('row', { name: new RegExp(SNIPPET_NAME_EDITED, 'i') }).first();
    await expect(editedRow).toBeVisible({ timeout: 15_000 });

    // ---- Delete via ConfirmDeleteDialog (standard copy, hard delete) ----
    await editedRow.getByRole('button', { name: `Delete ${SNIPPET_NAME_EDITED}` }).click();
    const confirmDialog = page.getByRole('dialog').filter({ hasText: 'Confirm delete' });
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByText(/cannot be undone/i)).toBeVisible();
    await expect(confirmDialog.getByText(SNIPPET_NAME_EDITED)).toBeVisible();

    const deleteResponse = page.waitForResponse(
      (res) =>
        res.url().includes(`${SNIPPETS_API}/`) && res.request().method() === 'DELETE',
      { timeout: 20_000 },
    );
    await confirmDialog.getByRole('button', { name: /^delete$/i }).click();
    const deleteResult = await deleteResponse;
    expect(deleteResult.ok()).toBeTruthy();
    await expect(confirmDialog).not.toBeVisible({ timeout: 10_000 });

    await expect(
      page.getByRole('row', { name: new RegExp(SNIPPET_NAME_EDITED, 'i') }),
    ).toHaveCount(0);
  });
});
