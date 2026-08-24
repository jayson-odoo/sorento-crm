/**
 * Bookmarkable portal links - public states (no credentials required).
 *
 * The authed golden path (token link → slug redirect → device trust →
 * logout) needs a live OTP/WhatsApp loop, so it is covered by pytest at the
 * service layer and by manual MCP verification; this spec pins the
 * unauthenticated FE↔BE round-trips.
 */
import { expect, test } from '@playwright/test';

test.describe('portal slug links - public states', () => {
  test('plain /portal with no session shows the link-request card', async ({ page }) => {
    await page.goto('/portal');
    await expect(page.getByText('No portal session on this device.')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Get your portal link' })).toBeVisible();
  });

  test('unknown slug 404s via slug-info and shows "not recognized"', async ({ page }) => {
    const slugInfoCall = page.waitForResponse(
      (res) =>
        res.url().includes('/api/v1/public/portal/slug-info/ZZZZUNKNOWN') &&
        res.status() === 404,
    );
    await page.goto('/portal/c/ZZZZUNKNOWN');
    // Entry page bounces to the slug verify page, which queries slug-info.
    await slugInfoCall;
    await expect(page).toHaveURL(/\/portal\/c\/ZZZZUNKNOWN\/verify/);
    await expect(page.getByText('This portal link is not recognized.')).toBeVisible();
  });

  test('slug URL with stale foreign session clears it (slug wins)', async ({ page }) => {
    await page.goto('/portal');
    await page.evaluate(() => {
      window.localStorage.setItem('sorento.portalToken', 'stale-token');
      window.localStorage.setItem('sorento.portalSlug', 'OTHERSLUG1');
    });
    await page.goto('/portal/c/ZZZZUNKNOWN');
    await expect(page).toHaveURL(/\/portal\/c\/ZZZZUNKNOWN\/verify/);
    const cleared = await page.evaluate(() => ({
      token: window.localStorage.getItem('sorento.portalToken'),
      slug: window.localStorage.getItem('sorento.portalSlug'),
    }));
    expect(cleared.token).toBeNull();
    expect(cleared.slug).toBeNull();
  });
});
