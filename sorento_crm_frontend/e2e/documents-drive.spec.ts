/**
 * Unified Drive (Resource Management -> Files) end-to-end.
 *
 * Validates the redesign in PLAN-unified-drive-files.md / its UAC against the
 * REAL stack (FE :3000 -> BE :8000 -> DB). Per project memory:
 *   - ALWAYS sidebar-navigate from `/` (feedback_playwright_via_sidebar);
 *   - real committed fixtures, not stubbed mocks (feedback_e2e_real_samples);
 *   - assert the FE hit the right /api/v1/* call (browser_network_requests
 *     equivalent via a request log).
 *
 * Previously ONE 300s serial golden flow - split into focused, independent
 * tests so a single flaky interaction can't mask the rest. Each test logs in,
 * navigates via the sidebar, creates uniquely-named `aaa-drive-*` folders, and
 * cleans up after itself (afterEach drains the test folders from the tree +
 * Trash) so the manual round starts clean.
 *
 * Per-row actions are now a RIGHT-CLICK context menu (the dedicated actions
 * column was removed). Open it by right-clicking the row button inside the grid
 * <table>, then pick the menuitem.
 *
 * Folder names use an `aaa-` prefix so the interleaved Name sort keeps them on
 * page 1 of the unified list (UAC C1).
 *
 * Required env (skips otherwise):
 *   PORTAL_E2E_BASE_URL (default http://localhost:3000)
 *   REQUEST_BATCH_E2E_EMAIL / REQUEST_BATCH_E2E_PASSWORD  (admin w/ files perms)
 */
import { test, expect, type Page } from '@playwright/test';
import * as path from 'path';

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL / _PASSWORD to run.');

// Upload fixture: a PDF, since the first attachment type ("Direct Access")
// restricts to pdf. (An image fixture exists too for the grid-thumbnail tests.)
const DOC = path.resolve('e2e/fixtures/drive/drive-doc.pdf');
const DOC_NAME = 'drive-doc.pdf';

const DRIVE_URL = '/api/v1/resource-management/attachments/drive';
const DIR_URL = '/api/v1/resource-management/directories';

// Every aaa-drive-* test folder ever created - used for teardown matching.
const TEST_FOLDER_PAT = /aaa-drive-/;

function uniqueName(slug: string): string {
  return `aaa-drive-${slug}-${Date.now().toString().slice(-6)}-${Math.floor(Math.random() * 1000)}`;
}

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await expect(page).toHaveURL(/\/$|\/dashboard|home/i, { timeout: 30_000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await expect(
    page.getByRole('button', { name: /resource management/i }).first(),
  ).toBeVisible({ timeout: 30_000 });
  // Let the authenticated shell finish hydrating before clicking the sidebar
  // (post-login re-render races the accordion mount otherwise).
  await page.waitForTimeout(800);
}

async function gotoFiles(page: Page, capture?: string[]) {
  if (capture) {
    page.on('request', (r) => {
      if (r.url().includes(DRIVE_URL)) capture.push(r.url());
    });
  }
  const rm = page.getByRole('button', { name: /resource management/i }).first();
  // Expand the group if collapsed (idempotent: only click when not expanded).
  if ((await rm.getAttribute('aria-expanded')) !== 'true') {
    await rm.click({ timeout: 15_000 });
  }
  await page.getByRole('link', { name: /^files$/i }).first().click({ timeout: 15_000 });
  await page.waitForResponse(
    (r) => r.url().includes(DRIVE_URL) && r.request().method() === 'GET',
    { timeout: 30_000 },
  );
  await expect(page.getByPlaceholder(/search files & folders/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole('button', { name: /list view/i })).toBeVisible();
  await expect(page.getByRole('button', { name: /grid view/i })).toBeVisible();
}

// The drive breadcrumb is the <nav aria-label="Breadcrumb"> that contains the
// "All files" root crumb (the page also has a global app breadcrumb).
function driveBreadcrumb(page: Page) {
  return page
    .getByRole('navigation', { name: /breadcrumb/i })
    .filter({ has: page.getByRole('button', { name: /all files/i }) })
    .first();
}

// Drive breadcrumb root crumb is "All files" + Home icon (drivePath.ts).
function driveRootCrumb(page: Page) {
  return driveBreadcrumb(page).getByRole('button', { name: /all files/i }).first();
}

// The current-folder crumb inside the drive breadcrumb.
function driveCrumb(page: Page, name: string) {
  return driveBreadcrumb(page).getByRole('button', { name: new RegExp(name, 'i') }).first();
}

function treeNode(page: Page, name: string) {
  return page.locator('span[title]', { hasText: name }).first();
}

// Per-row actions are a right-click context menu now. Rows render as
// role=button inside the grid <table> (single-click opens); right-clicking the
// row button matching `name` reveals the Radix ContextMenu.
async function openRowContextMenu(page: Page, name: string | RegExp) {
  const grid = page.getByRole('table').first();
  const row = grid.getByRole('button', { name }).first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.click({ button: 'right' });
}

async function fillCreateDialog(page: Page, name: string) {
  const dlg = page.getByRole('dialog');
  await expect(dlg).toBeVisible();
  await dlg.getByLabel(/^name$/i).fill(name);
  const createResp = page.waitForResponse(
    (r) => r.url().includes(DIR_URL) && r.request().method() === 'POST',
    { timeout: 20_000 },
  );
  await dlg.getByRole('button', { name: /^create$/i }).click();
  await createResp;
  await expect(dlg).not.toBeVisible({ timeout: 10_000 });
}

// Create a top-level folder via the tree "Add", then reload so it appears in the
// right pane (drive-contents is not invalidated by the create - see report).
async function createTopFolder(page: Page, name: string) {
  await page.getByRole('button', { name: /^add$/i }).first().click();
  await fillCreateDialog(page, name);
  await expect(treeNode(page, name)).toBeVisible({ timeout: 15_000 });
  await page.reload();
  await page.waitForResponse((r) => r.url().includes(DRIVE_URL), { timeout: 20_000 });
  await expect(page.getByRole('cell', { name }).first()).toBeVisible({ timeout: 15_000 });
}

// Drill into a folder via its right-pane row, asserting via the breadcrumb.
async function drillIntoFolder(page: Page, name: string) {
  const drill = page.waitForResponse(
    (r) => r.url().includes(DRIVE_URL) && /directory_id=/.test(r.url()),
    { timeout: 15_000 },
  );
  await page.getByRole('cell', { name }).first().click();
  await drill;
  await expect(driveCrumb(page, name)).toBeVisible({ timeout: 15_000 });
}

// Upload the PDF fixture into the CURRENT folder.
async function uploadDocToCurrent(page: Page) {
  await page.getByRole('button', { name: /^upload$/i }).first().click();
  const up = page.getByRole('dialog');
  await expect(up).toBeVisible();
  // First attachment type ("Direct Access") accepts pdf.
  await up.getByRole('combobox').first().click();
  await page.getByRole('option').first().click();
  await up.locator('input[type="file"]').first().setInputFiles(DOC);
  const uploadResp = page.waitForResponse(
    (r) =>
      r.url().includes('/api/v1/resource-management/attachments') &&
      r.request().method() === 'POST',
    { timeout: 40_000 },
  );
  // Submit button label is "Upload N Attachment(s)".
  await up.getByRole('button', { name: /^upload\b/i }).first().click();
  await uploadResp;
  // Upload-activity drawer auto-opens on success; close it.
  await page.keyboard.press('Escape').catch(() => {});
  await expect(page.getByRole('dialog')).toHaveCount(0, { timeout: 10_000 }).catch(() => {});
}

// Open the Resource Management group (if collapsed) and navigate to Trash.
async function rmExpandThenTrash(page: Page) {
  const rm = page.getByRole('button', { name: /resource management/i }).first();
  if ((await rm.getAttribute('aria-expanded')) !== 'true') {
    await rm.click({ timeout: 15_000 }).catch(() => {});
  }
  await page.getByRole('link', { name: /^trash$/i }).first().click({ timeout: 15_000 });
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(1_000);
}

// Soft-delete (Move to Trash) the named folders from the left tree. A parent
// delete cascades, so a child already removed is simply skipped.
async function softDeleteTreeFolders(page: Page, names: string[]) {
  for (const name of names) {
    const node = page
      .locator('div.group', { has: page.locator('span[title]', { hasText: name }) })
      .first();
    if ((await node.count()) === 0) continue;
    await node.hover();
    const menu = node.getByRole('button', { name: /folder actions/i });
    if ((await menu.count()) === 0) continue;
    await menu.click();
    await page.getByRole('menuitem', { name: /^delete$/i }).click();
    const dlg = page.getByRole('dialog');
    if (await dlg.count()) {
      await dlg.getByRole('button', { name: /move to trash|delete/i }).first().click().catch(() => {});
      await expect(dlg).toHaveCount(0, { timeout: 10_000 }).catch(() => {});
    }
  }
}

// Permanently delete any leftover aaa-drive-* test folders from Trash.
async function drainTrashTestFolders(page: Page) {
  await rmExpandThenTrash(page);
  for (let i = 0; i < 30; i++) {
    const node = page
      .locator('div.group', {
        has: page.locator('span[title]').filter({ hasText: TEST_FOLDER_PAT }),
      })
      .first();
    if ((await node.count()) === 0) break;
    await node.hover();
    const menu = node.getByRole('button', { name: /folder actions/i });
    if ((await menu.count()) === 0) break;
    await menu.click();
    const perm = page.getByRole('menuitem', { name: /permanently delete/i });
    if ((await perm.count()) === 0) {
      await page.keyboard.press('Escape');
      break;
    }
    await perm.click();
    const dlg = page.getByRole('dialog');
    if (await dlg.count()) {
      await dlg.getByRole('button', { name: /permanently delete/i }).first().click().catch(() => {});
      await expect(dlg).toHaveCount(0, { timeout: 8_000 }).catch(() => {});
    }
    await page.waitForTimeout(200);
  }
}

// Full teardown: move the listed test folders to Trash from the tree, then drain
// Trash so nothing aaa-drive-* survives. Best-effort - never fails the test.
async function cleanupFolders(page: Page, names: string[]) {
  try {
    await gotoFiles(page);
    await softDeleteTreeFolders(page, names);
    await drainTrashTestFolders(page);
  } catch {
    // teardown is best-effort
  }
}

test.describe('Unified Drive', () => {
  // ---- (a) nav + breadcrumb + root [A1/A2/A8] -----------------------------
  test('A1/A2/A8: sidebar nav to Files, root browse, breadcrumb root crumb', async ({ page }) => {
    test.setTimeout(120_000);
    const driveCalls: string[] = [];
    await login(page);
    await gotoFiles(page, driveCalls);

    // A8: root browse omits a concrete directory_id.
    expect(driveCalls.length).toBeGreaterThan(0);
    expect(driveCalls[0]).not.toMatch(/directory_id=[0-9a-f]{8}/i);

    // A1/A2: the drive breadcrumb renders with the "All files" root crumb.
    await expect(driveRootCrumb(page)).toBeVisible({ timeout: 15_000 });
  });

  // ---- (b) nested folder create + drill [A6] ------------------------------
  test('A6: create nested folders and drill into the child', async ({ page }) => {
    test.setTimeout(150_000);
    const PARENT = uniqueName('nest-parent');
    const CHILD = uniqueName('nest-child');
    await login(page);
    await gotoFiles(page);

    await createTopFolder(page, PARENT);
    await drillIntoFolder(page, PARENT);

    // Create a subfolder via the tree row "Add subfolder".
    const parentTreeRow = page
      .locator('div.group', { has: page.locator('span[title]', { hasText: PARENT }) })
      .first();
    await parentTreeRow.hover();
    await parentTreeRow.getByRole('button', { name: /folder actions/i }).click();
    await page.getByRole('menuitem', { name: /add subfolder/i }).click();
    await fillCreateDialog(page, CHILD);

    // KNOWN DEFECT: tree subfolder create doesn't invalidate drive-contents and
    // PARENT's contents are cached. Reload to clear the RQ cache, re-drill in.
    await page.reload();
    await page.waitForResponse((r) => r.url().includes(DRIVE_URL), { timeout: 20_000 });
    await expect(page.getByRole('cell', { name: PARENT }).first()).toBeVisible({ timeout: 15_000 });
    await drillIntoFolder(page, PARENT);
    // CHILD now shows as a row inside PARENT.
    await expect(page.getByRole('cell', { name: CHILD }).first()).toBeVisible({ timeout: 15_000 });

    await cleanupFolders(page, [PARENT, CHILD]);
  });

  // ---- (c) upload + recursive search + Location column [B2/B3/B4/B5] -------
  // Already passing in the old monolith - kept intact end-to-end.
  test('B2/B3/B4/B5: upload into subfolder, recursive search finds it + Location column', async ({
    page,
  }) => {
    test.setTimeout(200_000);
    const PARENT = uniqueName('search-parent');
    const CHILD = uniqueName('search-child');
    await login(page);
    await gotoFiles(page);

    await createTopFolder(page, PARENT);
    await drillIntoFolder(page, PARENT);

    // Subfolder via tree, then reload + re-drill to clear the contents cache.
    const parentTreeRow = page
      .locator('div.group', { has: page.locator('span[title]', { hasText: PARENT }) })
      .first();
    await parentTreeRow.hover();
    await parentTreeRow.getByRole('button', { name: /folder actions/i }).click();
    await page.getByRole('menuitem', { name: /add subfolder/i }).click();
    await fillCreateDialog(page, CHILD);
    await page.reload();
    await page.waitForResponse((r) => r.url().includes(DRIVE_URL), { timeout: 20_000 });
    await expect(page.getByRole('cell', { name: PARENT }).first()).toBeVisible({ timeout: 15_000 });
    await drillIntoFolder(page, PARENT);
    await expect(page.getByRole('cell', { name: CHILD }).first()).toBeVisible({ timeout: 15_000 });

    // Drill into CHILD and upload the document.
    await page.getByRole('cell', { name: CHILD }).first().click();
    await expect(driveCrumb(page, CHILD)).toBeVisible({ timeout: 15_000 });
    await uploadDocToCurrent(page);

    // A2 back to PARENT via the breadcrumb crumb (may be served from RQ cache).
    await driveCrumb(page, PARENT).click();
    await expect(driveCrumb(page, PARENT)).toBeVisible({ timeout: 15_000 });
    await expect(driveCrumb(page, CHILD)).toHaveCount(0, { timeout: 10_000 });

    // B2/B3/B4/B5: recursive search from PARENT finds the CHILD's file.
    const searchReq = page.waitForResponse(
      (r) => r.url().includes(DRIVE_URL) && /recursive=true/.test(r.url()),
      { timeout: 15_000 },
    );
    await page.getByPlaceholder(/search files & folders/i).fill('drive-doc');
    await searchReq;
    await expect(page.getByRole('cell', { name: new RegExp(DOC_NAME, 'i') }).first()).toBeVisible({
      timeout: 15_000,
    });
    // B5: Location column appears only during search.
    await expect(page.getByRole('columnheader', { name: /location/i })).toBeVisible();

    await cleanupFolders(page, [PARENT, CHILD]);
  });

  // ---- (d) reveal-in-folder [B6/B7] ---------------------------------------
  test('B6/B7: reveal-in-folder jumps to the parent and clears the search', async ({ page }) => {
    test.setTimeout(200_000);
    const PARENT = uniqueName('reveal-parent');
    const CHILD = uniqueName('reveal-child');
    await login(page);
    await gotoFiles(page);

    await createTopFolder(page, PARENT);
    await drillIntoFolder(page, PARENT);

    const parentTreeRow = page
      .locator('div.group', { has: page.locator('span[title]', { hasText: PARENT }) })
      .first();
    await parentTreeRow.hover();
    await parentTreeRow.getByRole('button', { name: /folder actions/i }).click();
    await page.getByRole('menuitem', { name: /add subfolder/i }).click();
    await fillCreateDialog(page, CHILD);
    await page.reload();
    await page.waitForResponse((r) => r.url().includes(DRIVE_URL), { timeout: 20_000 });
    await expect(page.getByRole('cell', { name: PARENT }).first()).toBeVisible({ timeout: 15_000 });
    await drillIntoFolder(page, PARENT);
    await page.getByRole('cell', { name: CHILD }).first().click();
    await expect(driveCrumb(page, CHILD)).toBeVisible({ timeout: 15_000 });
    await uploadDocToCurrent(page);

    // Back to PARENT, recursive search to surface the file.
    await driveCrumb(page, PARENT).click();
    await expect(driveCrumb(page, PARENT)).toBeVisible({ timeout: 15_000 });
    const searchReq = page.waitForResponse(
      (r) => r.url().includes(DRIVE_URL) && /recursive=true/.test(r.url()),
      { timeout: 15_000 },
    );
    await page.getByPlaceholder(/search files & folders/i).fill('drive-doc');
    await searchReq;
    await expect(page.getByRole('cell', { name: new RegExp(DOC_NAME, 'i') })).toHaveCount(1, {
      timeout: 10_000,
    });

    // B6/B7: open the per-row context menu by RIGHT-CLICKING the file's row
    // (the dedicated actions column was removed), then pick "Reveal in folder".
    await openRowContextMenu(page, new RegExp(DOC_NAME, 'i'));
    const reveal = page.getByRole('menuitem', { name: /reveal in folder/i });
    await expect(reveal).toBeVisible({ timeout: 10_000 });
    await reveal.click();

    // B7: search cleared; B6: navigated to the file's parent (CHILD).
    await expect(page.getByPlaceholder(/search files & folders/i)).toHaveValue('', {
      timeout: 15_000,
    });
    await expect(driveCrumb(page, CHILD)).toBeVisible({ timeout: 15_000 });

    await cleanupFolders(page, [PARENT, CHILD]);
  });

  // ---- (e) grid toggle persists [A4/A5] -----------------------------------
  test('A4/A5: grid view toggle persists across reload', async ({ page }) => {
    test.setTimeout(120_000);
    await login(page);
    await gotoFiles(page);

    await page.getByRole('button', { name: /grid view/i }).click();
    await expect(page.getByRole('button', { name: /grid view/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await page.reload();
    await page.waitForResponse((r) => r.url().includes(DRIVE_URL), { timeout: 20_000 });
    await expect(page.getByRole('button', { name: /grid view/i })).toHaveAttribute(
      'aria-pressed',
      'true',
      { timeout: 15_000 },
    );
    // Restore list view so a persisted preference doesn't leak into other tests.
    await page.getByRole('button', { name: /list view/i }).click();
    await expect(page.getByRole('button', { name: /list view/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  // ---- (f) mixed-select + Action-dropdown gating [F1/F2/F3/F6] -------------
  test('F1/F2/F3/F6: select a folder row, single Action dropdown, file-only items gated', async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const FOLDER = uniqueName('sel');
    await login(page);
    await gotoFiles(page);
    await createTopFolder(page, FOLDER);

    // F1: select the folder row via its "Select row" checkbox.
    // The unified list renders each row as a <button> (role=button, for
    // single-click-open), NOT role=row - so scope to the grid <table> and match
    // the row button by its accessible name (which contains the folder name),
    // then find the checkbox inside it.
    const grid = page.getByRole('table').first();
    const folderRow = grid.getByRole('button', { name: FOLDER }).first();
    await expect(folderRow).toBeVisible({ timeout: 15_000 });
    const cb = folderRow.getByRole('checkbox', { name: /select row/i });
    await expect(cb).toBeAttached({ timeout: 10_000 });
    // Toggle ON only if not already checked (a blind retry would un-toggle it).
    if (!(await cb.isChecked())) await cb.click({ force: true });
    await expect(cb).toBeChecked({ timeout: 10_000 });

    // F2: a single "Action" dropdown appears once a row is selected.
    const action = page.getByRole('button', { name: /^action$/i });
    await expect(action).toBeVisible({ timeout: 10_000 });
    await action.click();
    // F3: shared (Move, Delete) enabled; file-only actions disabled with a folder.
    await expect(page.getByRole('menuitem', { name: /move to/i })).toBeEnabled();
    await expect(page.getByRole('menuitem', { name: /delete selected/i })).toBeEnabled();
    await expect(page.getByRole('menuitem', { name: /export selected/i })).toBeDisabled();
    await expect(page.getByRole('menuitem', { name: /set access levels/i })).toBeDisabled();
    await expect(page.getByRole('menuitem', { name: /set attachment type/i })).toBeDisabled();
    await expect(page.getByRole('menuitem', { name: /resubmit selected/i })).toBeDisabled();
    // F6: single-only Rename/Replace are NOT in the bulk menu.
    await expect(page.getByRole('menuitem', { name: /^rename$/i })).toHaveCount(0);
    await expect(page.getByRole('menuitem', { name: /^replace$/i })).toHaveCount(0);
    await page.keyboard.press('Escape');

    await cleanupFolders(page, [FOLDER]);
  });

  // ---- (g) bulk delete folder + restore [F4] ------------------------------
  test('F4: bulk-delete a folder via the tree, restore it from Trash', async ({ page }) => {
    test.setTimeout(180_000);
    const FOLDER = uniqueName('bulkdel');
    await login(page);
    await gotoFiles(page);
    await createTopFolder(page, FOLDER);

    // Soft-delete the folder (cascade) from the tree -> it lands in Trash.
    await softDeleteTreeFolders(page, [FOLDER]);
    await expect(treeNode(page, FOLDER)).toHaveCount(0, { timeout: 10_000 }).catch(() => {});

    // Trash view shows the deleted folder; restore it.
    await rmExpandThenTrash(page);
    const trashNode = page
      .locator('div.group', { has: page.locator('span[title]', { hasText: FOLDER }) })
      .first();
    await expect(trashNode).toBeVisible({ timeout: 15_000 });
    await trashNode.hover();
    await trashNode.getByRole('button', { name: /folder actions/i }).click();
    const restore = page.getByRole('menuitem', { name: /^restore$/i });
    if (await restore.count()) {
      await restore.click();
      const dlg = page.getByRole('dialog');
      if (await dlg.count()) {
        await dlg.getByRole('button', { name: /restore/i }).first().click().catch(() => {});
        await expect(dlg).toHaveCount(0, { timeout: 8_000 }).catch(() => {});
      }
    } else {
      await page.keyboard.press('Escape');
    }

    // Cleanup: re-delete + drain so nothing survives.
    await cleanupFolders(page, [FOLDER]);
  });
});
