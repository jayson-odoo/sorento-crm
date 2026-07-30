import { test, expect, type Page } from '@playwright/test';

import { purgeSelections } from './dealerKitCleanup';

/**
 * The room designer, in a real browser.
 *
 * WebGL is the reason this is an E2E and not a component test: jsdom has no
 * canvas context, so the 3D view cannot be exercised anywhere else.
 */

const EMAIL = process.env.REQUEST_BATCH_E2E_EMAIL;
const PASSWORD = process.env.REQUEST_BATCH_E2E_PASSWORD;

test.skip(!EMAIL || !PASSWORD, 'Set REQUEST_BATCH_E2E_EMAIL/PASSWORD to run the designer flow');

async function tap(page: Page, locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.dispatchEvent('click');
}

/**
 * Open a Radix trigger without waiting for actionability.
 *
 * Three approaches were tried here and only this one is reliable.
 * `page.keyboard.press` waits on PAGE state and `locator.press` waits on
 * ELEMENT actionability, and this layout's dev-ingest fetch never resolves, so
 * under load either can outlive the whole test. A dispatched `keydown` skips
 * the wait but carries no default action, so the button never turns it into a
 * click and the popover stays shut. Radix opens on POINTER events, so those are
 * what gets dispatched - no waiting, and the real handler runs.
 */
async function openTrigger(locator: ReturnType<Page['locator']>) {
  await expect(locator).toBeVisible({ timeout: 20_000 });
  await locator.dispatchEvent('pointerdown', { button: 0, isPrimary: true, bubbles: true });
  await locator.dispatchEvent('mousedown', { button: 0, bubbles: true });
  await locator.dispatchEvent('click', { button: 0, bubbles: true });
}

async function login(page: Page) {
  await page.goto('/');
  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 20_000 });
  await email.fill(EMAIL!);
  await page.locator('input[type="password"], input[name="password"]').first().fill(PASSWORD!);
  await page.getByRole('button', { name: /continue|sign in|log in/i }).click();
  await page.waitForURL((url) => !/\/sign-?in/.test(url.toString()), { timeout: 30_000 });
}

async function openDesigner(page: Page) {
  await page.goto('/', { waitUntil: 'commit' });
  const group = page.getByRole('button', { name: /dealer kit/i }).first();
  await expect(group, 'Dealer Kit sidebar group should render').toBeVisible({ timeout: 20_000 });
  if ((await group.getAttribute('aria-expanded')) !== 'true') {
    await group.dispatchEvent('click');
  }
  const link = page.getByRole('link', { name: /room designer/i }).first();
  await expect(link).toBeVisible({ timeout: 15_000 });
  const href = await link.getAttribute('href');
  await page.goto(href!, { waitUntil: 'commit' });
}

/**
 * Every selection this run creates, so the teardown can delete exactly those.
 * The dev database is a copy of production; a suite that leaves rows behind
 * makes the real lists unreadable within a few runs.
 */
const createdSelections: string[] = [];

test.describe('Dealer Kit room designer', () => {
  // Each test logs in fresh AND now does real server round trips (the design is
  // persisted, not local state), so the default 90s is not enough headroom.
  test.describe.configure({ timeout: 180_000 });

  test.beforeEach(async ({ page }) => {
    page.on('response', (response) => {
      if (
        response.request().method() === 'POST' &&
        /\/dealer-kit\/selections$/.test(response.url()) &&
        response.status() === 201
      ) {
        response
          .json()
          .then((body: { id?: string }) => body?.id && createdSelections.push(body.id))
          .catch(() => undefined);
      }
    });
    await login(page);
  });

  test.afterAll(async ({ browser }, testInfo) => {
    await purgeSelections(browser, createdSelections, testInfo.project.use.baseURL);
  });

  test('opens from the sidebar with a room and no products', async ({ page }) => {
    await openDesigner(page);

    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.locator('[data-dk-room-plan]')).toBeVisible();
    // The starting room is 4m x 3m, and the area is derived, never stored.
    // The figure appears on the plan overlay and in the summary.
    await expect(page.getByText(/12\.0 m/).first()).toBeVisible();
    await expect(page.getByText(/nothing placed yet/i)).toBeVisible();
  });

  test('adding a product puts a box in the room', async ({ page }) => {
    await openDesigner(page);

    // Keyboard, not a real mouse click: mouse.click wedges against this
    // layout's never-resolving dev-ingest fetch under load, which made this
    // pass alone and flake in a full run.
    const combobox = page.getByRole('combobox').first();
    await expect(combobox).toBeVisible({ timeout: 20_000 });
    await openTrigger(combobox);

    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');

    await tap(page, page.getByRole('button', { name: /add product to room/i }));

    // It appears on the plan as a real polygon, not a list entry only.
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 20_000 });
    // And the estimate is stated rather than hidden (AC-V2).
    await expect(page.getByText(/sizes are estimated/i)).toBeVisible();
  });

  test('the 3D view renders a WebGL canvas', async ({ page }) => {
    await openDesigner(page);

    // Radix tabs activate on arrow keys, and keyboard avoids the real-mouse
    // path entirely - a synthetic click does not move a Radix tab, and
    // page.mouse.click wedges against this layout's never-resolving fetch.
    const planTab = page.getByRole('tab', { name: /^plan$/i });
    await expect(planTab).toBeVisible({ timeout: 20_000 });
    await openTrigger(page.getByRole('tab', { name: /^3d$/i }));

    const scene = page.locator('[data-dk-room-scene] canvas');
    await expect(scene).toBeVisible({ timeout: 20_000 });

    // A canvas that exists but never got a context is the failure worth
    // catching: it looks identical to a working one in a screenshot.
    const hasContext = await scene.evaluate(
      (node) => Boolean((node as HTMLCanvasElement).getContext('webgl2') ||
        (node as HTMLCanvasElement).getContext('webgl')),
    );
    expect(hasContext).toBe(true);
  });

  test('wall lengths are shown live in millimetres', async ({ page }) => {
    await openDesigner(page);

    // AC-R1: a user reshaping a room must see the dimensions, not just an area.
    // Without these, "roughly right" is how a worktop gets ordered 200mm short.
    await expect(page.getByText('4000 mm').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText('3000 mm').first()).toBeVisible();
  });

  test('a dragged wall follows the cursor instead of running away', async ({ page }) => {
    await openDesigner(page);

    const plan = page.locator('[data-dk-room-plan]');
    await expect(plan).toBeVisible({ timeout: 20_000 });
    const wall = page.locator('[data-dk-room-wall="1"]');
    await expect(wall).toBeAttached({ timeout: 20_000 });

    // Millimetres per screen pixel, read off the SVG itself. Asserting a raw mm
    // figure would only be true at one window size.
    const viewBox = (await plan.getAttribute('viewBox')) ?? '';
    const planBox = (await plan.boundingBox())!;
    const mmPerPx = Number(viewBox.split(' ')[2]) / planBox.width;

    const lengths = async () =>
      (await page.locator('[data-dk-room-plan] text').allTextContents())
        .filter((text) => text.endsWith(' mm'))
        .map((text) => Number(text.replace(' mm', '')));

    const before = (await lengths())[0];
    const wallBox = (await wall.boundingBox())!;
    const fromX = wallBox.x + wallBox.width / 2;
    const fromY = wallBox.y + wallBox.height / 2;
    const dragPx = 60;

    await page.mouse.move(fromX, fromY);
    await page.mouse.down();
    // In several steps ON PURPOSE. The bug this guards only appeared with more
    // than one pointermove: each move re-measured against an already-moved
    // room, so a 60px drag came out as several metres.
    await page.mouse.move(fromX + dragPx / 3, fromY, { steps: 5 });
    await page.mouse.move(fromX + (dragPx * 2) / 3, fromY, { steps: 5 });
    await page.mouse.move(fromX + dragPx, fromY, { steps: 5 });
    await page.mouse.up();

    const after = (await lengths())[0];
    const expected = before + dragPx * mmPerPx;

    expect(after).not.toBe(before);
    // Generous but nowhere near the failure: amplification overshot by 5x-10x,
    // while an honest drag lands within a grid step or two of the cursor.
    expect(Math.abs(after - expected)).toBeLessThan(Math.max(200, expected * 0.15));
  });

  test('typing a wall length makes the wall exactly that long', async ({ page }) => {
    await openDesigner(page);

    // The trust-builder: a dealer arrives with a tape measure, and 3050 has to
    // mean 3050 rather than "about 3050 after a snap".
    const label = page.locator('[data-dk-wall-label="0"]');
    await expect(label).toBeAttached({ timeout: 20_000 });
    // DOUBLE click: a single click selects the wall (which is how you choose
    // where a door goes), and opening an input on every click made the number
    // impossible to simply look at.
    await label.dispatchEvent('dblclick', { bubbles: true });

    const input = page.locator('[data-dk-wall-input="0"]');
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill('3050');
    await input.press('Enter');

    await expect(page.locator('[data-dk-room-plan] text').first()).toHaveText('3050 mm');
  });

  test('a product dragged at a wall backs onto it, and undo puts it back', async ({ page }) => {
    await openDesigner(page);

    const combobox = page.getByRole('combobox').first();
    await openTrigger(combobox);
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));

    const box = page.locator('[data-dk-plan-box]').first();
    await expect(box).toBeVisible({ timeout: 30_000 });
    await box.click();

    const points = () => page.locator('[data-dk-plan-box] polygon').first().getAttribute('points');
    const before = await points();

    const plan = page.locator('[data-dk-room-plan]');
    const planBox = (await plan.boundingBox())!;
    const boxBox = (await box.boundingBox())!;
    await page.mouse.move(boxBox.x + boxBox.width / 2, boxBox.y + boxBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(planBox.x + 40, planBox.y + planBox.height / 2, { steps: 10 });
    await page.mouse.up();

    // Flush against the left wall: the room starts at x=0, so the footprint's
    // leftmost corner has to land there rather than merely near it.
    await expect
      .poll(async () => {
        const xs = ((await points()) ?? '')
          .split(' ')
          .map((pair) => Number(pair.split(',')[0]));
        return Math.min(...xs);
      }, { timeout: 10_000 })
      .toBe(0);

    // Clearance chips only exist once something is against a wall - they are
    // the "will the next one fit" answer.
    await expect(page.locator('[data-dk-clearance] text').first()).toBeVisible();

    await page.getByRole('button', { name: 'Undo' }).click();
    await expect.poll(points, { timeout: 10_000 }).toBe(before);
  });

  test('a door is stamped into the chosen wall and survives a save', async ({ page }) => {
    await openDesigner(page);

    // Openings belong to a WALL, so choosing one comes first. Selecting happens
    // on pointerdown, the same gesture that drags a wall.
    const wall = page.locator('[data-dk-room-wall="0"]');
    await expect(wall).toBeAttached({ timeout: 20_000 });
    await wall.dispatchEvent('pointerdown', { bubbles: true });
    await expect(page.locator('[data-dk-wall-selected]')).toBeAttached();

    await tap(page, page.getByRole('button', { name: /^door$/i }));
    await expect(page.locator('[data-dk-opening-kind="door"]')).toBeAttached({ timeout: 10_000 });

    // A door is not a product: it has no price and no line.
    await expect(page.getByText(/nothing placed yet/i)).toBeVisible();

    const saved = page.waitForResponse(
      (response) =>
        /\/dealer-kit\/selections\/[^/]+\/room$/.test(response.url()) && response.ok(),
    );
    await tap(page, page.getByRole('button', { name: /save design/i }));
    const body = await (await saved).json();
    expect(body.room.openings).toHaveLength(1);
    expect(body.room.openings[0].kind).toBe('door');
    expect(body.lines).toHaveLength(0);

    await page.reload({ waitUntil: 'commit' });
    await expect(page.locator('[data-dk-opening-kind="door"]')).toBeAttached({ timeout: 30_000 });
  });

  test('the summary prices the design and re-asks the server when a line comes off', async ({
    page,
  }) => {
    await openDesigner(page);

    const combobox = page.getByRole('combobox').first();
    await openTrigger(combobox);
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 30_000 });

    const summaryLink = page.getByRole('link', { name: /^summary$/i });
    await expect(summaryLink).toBeVisible({ timeout: 10_000 });
    const href = await summaryLink.getAttribute('href');
    await page.goto(href!, { waitUntil: 'commit' });

    await expect(page.locator('[data-dk-quote-line]').first()).toBeVisible({ timeout: 30_000 });
    const subtotal = page.locator('[data-dk-quote-subtotal]');
    const before = (await subtotal.innerText()).trim();

    // Unticking must produce a REQUEST. If the figure changed without one, the
    // browser did the arithmetic - which is the thing this screen must never do.
    const requoted = page.waitForRequest((request) => /\/quote$/.test(request.url()));
    const tickable = page.locator('[data-dk-quote-line] button[role=checkbox]:not([disabled])');
    const count = await tickable.count();
    if (count === 0) {
      // Everything in this design is unsellable, so there is nothing to untick
      // and nothing to assert beyond the page having rendered.
      expect(before).toContain('0.00');
      return;
    }
    await tickable.first().click();
    await requoted;

    // The observable is the line coming OFF, not the figure moving: whichever
    // product the picker offered first may be priced at zero, and asserting on
    // the number would then be asserting on the catalogue.
    await expect(tickable.first()).toHaveAttribute('data-state', 'unchecked', {
      timeout: 15_000,
    });
    if (!before.endsWith('0.00')) {
      await expect(subtotal).not.toHaveText(before, { timeout: 15_000 });
    }

    // And the line is still on the page: unticking is not deleting.
    await expect(page.locator('[data-dk-quote-line]').first()).toBeVisible();
  });

  test('finishes apply per surface, and one undo takes back one edit', async ({ page }) => {
    await openDesigner(page);

    const floor = () =>
      page.locator('[data-dk-room-plan] path.stroke-foreground').getAttribute('fill');
    const wall = () => page.locator('[data-dk-wall-finish="0"]').getAttribute('stroke');
    await expect(page.locator('[data-dk-room-plan]')).toBeVisible({ timeout: 20_000 });

    const startFloor = await floor();
    const startWall = await wall();

    await tap(page, page.locator('[data-dk-floor-finish="timber"]'));
    await expect.poll(floor, { timeout: 10_000 }).not.toBe(startFloor);
    // The floor is its own surface: changing it leaves the walls alone.
    expect(await wall()).toBe(startWall);

    await page.locator('[data-dk-room-wall="0"]').dispatchEvent('pointerdown', { bubbles: true });
    await tap(page, page.locator('[data-dk-wall-finish-swatch="charcoal"]'));
    await expect.poll(wall, { timeout: 10_000 }).not.toBe(startWall);
    const timberFloor = await floor();

    // One undo takes back the wall and NOT the floor. Snapshots are taken
    // before a change, so without care the first undo swallows two edits -
    // which is exactly what it did until the designer learnt to take the edit
    // in hand off first.
    await tap(page, page.getByRole('button', { name: 'Undo' }));
    await expect.poll(wall, { timeout: 10_000 }).toBe(startWall);
    expect(await floor()).toBe(timberFloor);

    await tap(page, page.getByRole('button', { name: 'Undo' }));
    await expect.poll(floor, { timeout: 10_000 }).toBe(startFloor);

    await tap(page, page.getByRole('button', { name: 'Redo' }));
    await expect.poll(floor, { timeout: 10_000 }).toBe(timberFloor);
  });

  test('the plan can be panned, zoomed and fitted back', async ({ page }) => {
    await openDesigner(page);

    const plan = page.locator('[data-dk-room-plan]');
    await expect(plan).toBeVisible({ timeout: 20_000 });
    const viewBox = () => plan.getAttribute('viewBox');
    const start = await viewBox();

    const box = (await plan.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -400);
    await expect.poll(viewBox, { timeout: 10_000 }).not.toBe(start);
    const zoomed = await viewBox();

    // Shift-drag pans, for the same reason middle-drag does: the left button is
    // already "grab the thing under the cursor".
    await page.keyboard.down('Shift');
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2 + 60, { steps: 8 });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await expect.poll(viewBox, { timeout: 10_000 }).not.toBe(zoomed);

    await page.locator('[data-dk-reset-view]').click();
    await expect.poll(viewBox, { timeout: 10_000 }).toBe(start);
  });

  test('a door can be dragged onto a different wall', async ({ page }) => {
    await openDesigner(page);

    // From a known room: the designer reopens the last design, whose walls may
    // have been reshaped by an earlier test, and "which wall is nearest" is
    // only meaningful against a room this test chose.
    await tap(page, page.getByRole('button', { name: /new design/i }));
    await expect(page.locator('[data-dk-room-plan]')).toBeVisible({ timeout: 20_000 });

    await page.locator('[data-dk-room-wall="0"]').dispatchEvent('pointerdown', { bubbles: true });
    await tap(page, page.getByRole('button', { name: /^door$/i }));
    const opening = page.locator('[data-dk-opening]').first();
    await expect(opening).toBeAttached({ timeout: 10_000 });

    // Which wall it is on, read off the plan: a door on the top wall is drawn
    // horizontally, one on a side wall vertically.
    const isHorizontal = async () => {
      const line = opening.locator('line').first();
      const y1 = Number(await line.getAttribute('y1'));
      const y2 = Number(await line.getAttribute('y2'));
      return Math.abs(y2 - y1) < 1;
    };
    expect(await isHorizontal()).toBe(true);

    const plan = page.locator('[data-dk-room-plan]');
    const planBox = (await plan.boundingBox())!;
    // The door's own grab area, not the group's box - the group also contains
    // the swing arc, whose centre is out in the middle of the room.
    const openingBox = (await opening.locator('line').first().boundingBox())!;
    await page.mouse.move(openingBox.x + openingBox.width / 2, openingBox.y + openingBox.height / 2);
    await page.mouse.down();
    // Round the corner and down the left-hand side, in stages with a breath
    // between them: on a cold server the whole drag can otherwise land inside
    // one busy frame and only the last position is ever seen.
    await page.mouse.move(planBox.x + planBox.width / 3, planBox.y + 40, { steps: 8 });
    await page.waitForTimeout(150);
    await page.mouse.move(planBox.x + 60, planBox.y + planBox.height / 3, { steps: 8 });
    await page.waitForTimeout(150);
    await page.mouse.move(planBox.x + 60, planBox.y + planBox.height / 2, { steps: 8 });
    await page.waitForTimeout(150);
    await page.mouse.up();

    // Dragging a door round a corner is a thing people do - the plan was right
    // and the wall was wrong - and refusing meant deleting it and stamping a
    // new one.
    await expect.poll(isHorizontal, { timeout: 20_000 }).toBe(false);
  });

  test('a product can be dragged in the 3D view', async ({ page }) => {
    await openDesigner(page);

    const combobox = page.getByRole('combobox').first();
    await openTrigger(combobox);
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 30_000 });

    /** The placed box's centre in the plan, in millimetres. */
    const centre = async () => {
      const points = await page
        .locator('[data-dk-plan-box] polygon')
        .first()
        .getAttribute('points');
      const corners = (points ?? '')
        .trim()
        .split(/\s+/)
        .map((pair) => pair.split(',').map(Number));
      const sum = corners.reduce((total, [x, y]) => [total[0] + x, total[1] + y], [0, 0]);
      return { x: sum[0] / corners.length, y: sum[1] / corners.length };
    };
    const before = await centre();

    await openTrigger(page.getByRole('tab', { name: /^3d$/i }));
    const canvas = page.locator('[data-dk-room-scene] canvas');
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    const box = (await canvas.boundingBox())!;
    // Held on to so the drag can be checked for the failure that actually
    // shipped: the scene used to be rebuilt whenever `boxes` changed, so the
    // FIRST pointermove of a drag replaced the canvas. The move landed, the
    // drag then died silently and the camera snapped back to its opening
    // framing - which read as the view refocusing itself when you touched
    // anything. If this handle is still connected afterwards, nothing was torn
    // down mid-gesture.
    const canvasHandle = (await canvas.elementHandle())!;

    // Where the selected product actually is on screen. The scene is a canvas,
    // so there is no element to aim at; it publishes the projected position of
    // the selection for exactly this.
    const scene = page.locator('[data-dk-room-scene]');
    await expect(scene).toHaveAttribute('data-dk-selected-at', /\d+,\d+/, { timeout: 20_000 });
    const [atX, atY] = ((await scene.getAttribute('data-dk-selected-at')) ?? '0,0')
      .split(',')
      .map(Number);

    // Dragged across the FLOOR: being told to switch views to move a product
    // you are looking at is what makes a tool feel like a form.
    //
    // A SHORT first hop and a long second one, deliberately: a drag that dies
    // after its first move still moves the product a little, so a test that
    // only asks "did it move" passes on the broken build. Nearly all of the
    // distance here is in moves that only a drag which is still alive can see.
    await page.mouse.move(box.x + atX, box.y + atY);
    await page.mouse.down();
    await page.mouse.move(box.x + atX - 6, box.y + atY + 4, { steps: 3 });
    await page.waitForTimeout(120);
    await page.mouse.move(box.x + atX - 80, box.y + atY + 50, { steps: 10 });
    await page.waitForTimeout(120);
    await page.mouse.move(box.x + atX - 150, box.y + atY + 90, { steps: 10 });
    await page.waitForTimeout(120);
    await page.mouse.up();

    expect(await canvasHandle.evaluate((node) => node.isConnected)).toBe(true);

    await openTrigger(page.getByRole('tab', { name: /^plan$/i }));
    // The plan is the same state seen from above, so the move shows there too -
    // and by a distance only the whole gesture could account for.
    await expect
      .poll(
        async () => {
          const after = await centre();
          return Math.hypot(after.x - before.x, after.y - before.y);
        },
        { timeout: 15_000 },
      )
      .toBeGreaterThan(400);
  });

  test('a door can be slid along its wall from the 3D view', async ({ page }) => {
    await openDesigner(page);

    const wall = page.locator('[data-dk-room-wall="0"]');
    await expect(wall).toBeAttached({ timeout: 20_000 });
    await wall.dispatchEvent('pointerdown', { bubbles: true });
    await tap(page, page.getByRole('button', { name: /^door$/i }));
    const door = page.locator('[data-dk-opening-kind="door"]');
    await expect(door).toBeAttached({ timeout: 10_000 });

    /** Where the hole starts along its wall, in millimetres. */
    const offset = async () =>
      Number(await door.locator('line').nth(1).getAttribute('x1'));
    const before = await offset();

    await openTrigger(page.getByRole('tab', { name: /^3d$/i }));
    const canvas = page.locator('[data-dk-room-scene] canvas');
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    const box = (await canvas.boundingBox())!;
    const canvasHandle = (await canvas.elementHandle())!;

    // An opening is an ABSENCE - no geometry, nothing on screen to aim at - so
    // the scene publishes where each one currently projects to.
    const scene = page.locator('[data-dk-room-scene]');
    await expect(scene).toHaveAttribute('data-dk-openings-at', /.+:\d+:\d+,\d+/, {
      timeout: 20_000,
    });
    const [atX, atY] = ((await scene.getAttribute('data-dk-openings-at')) ?? '')
      .split(';')[0]
      .split(':')[2]
      .split(',')
      .map(Number);

    await page.mouse.move(box.x + atX, box.y + atY);
    await page.mouse.down();
    await page.mouse.move(box.x + atX + 8, box.y + atY, { steps: 3 });
    await page.waitForTimeout(120);
    await page.mouse.move(box.x + atX + 70, box.y + atY + 10, { steps: 10 });
    await page.waitForTimeout(120);
    await page.mouse.move(box.x + atX + 130, box.y + atY + 20, { steps: 10 });
    await page.waitForTimeout(120);
    await page.mouse.up();

    expect(await canvasHandle.evaluate((node) => node.isConnected)).toBe(true);

    await openTrigger(page.getByRole('tab', { name: /^plan$/i }));
    await expect
      .poll(async () => Math.abs((await offset()) - before), { timeout: 15_000 })
      .toBeGreaterThan(300);
  });

  test('a door dragged across the room in 3D lands on the wall it was taken to', async ({
    page,
  }) => {
    await openDesigner(page);

    // From a known room, for the same reason the plan version of this test
    // starts from one: "which wall is nearest" only means something against a
    // room this test chose.
    await tap(page, page.getByRole('button', { name: /new design/i }));
    await expect(page.locator('[data-dk-room-plan]')).toBeVisible({ timeout: 20_000 });

    await page.locator('[data-dk-room-wall="0"]').dispatchEvent('pointerdown', { bubbles: true });
    await tap(page, page.getByRole('button', { name: /^door$/i }));
    await expect(page.locator('[data-dk-opening]').first()).toBeAttached({ timeout: 10_000 });

    await openTrigger(page.getByRole('tab', { name: /^3d$/i }));
    const canvas = page.locator('[data-dk-room-scene] canvas');
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    const box = (await canvas.boundingBox())!;
    const scene = page.locator('[data-dk-room-scene]');

    /** The first opening, as the scene currently sees it: wall, and where it projects. */
    const state = async () => {
      const raw = ((await scene.getAttribute('data-dk-openings-at')) ?? '').split(';')[0];
      const [, wall, at] = raw.split(':');
      const [x, y] = (at ?? '0,0').split(',').map(Number);
      return { wall: Number(wall), x, y };
    };
    await expect(scene).toHaveAttribute('data-dk-openings-at', /.+:\d+:\d+,\d+/, {
      timeout: 20_000,
    });
    const start = await state();

    // Right and toward the viewer, which on this camera is across the room
    // toward the near-right corner and then down the right-hand wall. Stepped,
    // and stopped as soon as the door has changed walls, because the exact
    // pixel where one wall stops being the nearest depends on the camera.
    await page.mouse.move(box.x + start.x, box.y + start.y);
    await page.mouse.down();
    let landed = start.wall;
    for (let step = 1; step <= 10 && landed === start.wall; step += 1) {
      await page.mouse.move(box.x + start.x + step * 30, box.y + start.y + step * 22, {
        steps: 4,
      });
      await page.waitForTimeout(90);
      landed = (await state()).wall;
    }
    await page.mouse.up();

    // Dragging a door round a corner is a thing people do, in either view. The
    // 3D view used to refuse: an opening could only slide along the wall it
    // started on, so crossing meant going back to the plan.
    expect(landed).not.toBe(start.wall);

    // And the plan agrees, because there is one room, not two.
    await openTrigger(page.getByRole('tab', { name: /^plan$/i }));
    const line = page.locator('[data-dk-opening] line').first();
    await expect
      .poll(
        async () =>
          Math.abs(
            Number(await line.getAttribute('y2')) - Number(await line.getAttribute('y1')),
          ) < 1,
        { timeout: 15_000 },
      )
      .toBe(false);
  });

  test('a design the server no longer has does not brick the designer', async ({ page }) => {
    await openDesigner(page);

    // The last design is remembered in this browser. Point it at something the
    // server will never return - a deleted design, or one belonging to a
    // company the user has switched away from - and the designer must recover
    // rather than 404 on every action until storage is cleared by hand.
    await page.evaluate(() =>
      window.localStorage.setItem(
        'dealer-kit:last-selection',
        '00000000-0000-0000-0000-0000000000ff',
      ),
    );
    await page.reload({ waitUntil: 'commit' });

    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/nothing placed yet/i)).toBeVisible({ timeout: 20_000 });

    const remembered = await page.evaluate(() =>
      window.localStorage.getItem('dealer-kit:last-selection'),
    );
    expect(remembered).toBeNull();

    // And the designer still works afterwards.
    const combobox = page.getByRole('combobox').first();
    await openTrigger(combobox);
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 30_000 });
  });

  test('a design survives a reload', async ({ page }) => {
    await openDesigner(page);

    const combobox = page.getByRole('combobox').first();
    await expect(combobox).toBeVisible({ timeout: 20_000 });
    await openTrigger(combobox);
    const option = page.getByRole('option').first();
    await expect(option).toBeVisible({ timeout: 20_000 });
    // The code is the option's first line. Splitting the whole textContent on a
    // separator does not work: the option renders code and name as two stacked
    // spans, so its text is the two run together with nothing between them.
    const chosen = ((await option.locator('span span').first().textContent()) ?? '').trim();
    await option.dispatchEvent('click');
    await tap(page, page.getByRole('button', { name: /add product to room/i }));

    // Wait for the box to exist before saving. Saving mid-write is a no-op -
    // the button is disabled while the line request is in flight - and a
    // synthetic click on a disabled button fails silently, which looks exactly
    // like a broken save.
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 30_000 });

    // The line comes back from the SERVER, so its presence proves the write
    // landed rather than that local state changed (AC-T3).
    const saved = page.waitForResponse(
      (response) =>
        /\/dealer-kit\/selections\/[^/]+\/room$/.test(response.url()) && response.ok(),
    );
    await tap(page, page.getByRole('button', { name: /save design/i }));
    const body = await (await saved).json();
    expect(body.roomAreaSqm).toBe(12);
    expect(body.lines.length).toBeGreaterThan(0);
    // A line never carries a price of its own - it is resolved per viewer.
    expect(body.lines[0]).not.toHaveProperty('unitPrice');

    await page.reload({ waitUntil: 'commit' });
    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    // Reopened from the server, not from memory: the product is still there.
    // Targeted at the panel row rather than any text match - the plan box
    // carries an SVG <title> with the same label for its hover tooltip, and a
    // loose getByText picks that hidden node first.
    await expect(
      page.getByRole('button', { name: `Select ${chosen}` }).first(),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.locator('[data-dk-plan-box]').first()).toBeVisible({ timeout: 20_000 });
  });

});

// A separate describe with test.use: setViewportSize mid-test wedges against
// the protected layout's never-resolving dev-ingest fetch, which is why the
// builder spec does it this way too.
test.describe('Dealer Kit room designer at 375px', () => {
  test.use({ viewport: { width: 375, height: 800 } });

  test('does not scroll the body sideways', async ({ page }) => {
    await login(page);
    await page.goto('/dealer-kit/design', { waitUntil: 'commit' });

    await expect(page.getByRole('heading', { name: /room designer/i })).toBeVisible({
      timeout: 20_000,
    });
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
