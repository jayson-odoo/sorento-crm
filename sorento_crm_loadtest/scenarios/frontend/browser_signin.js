import { browser } from 'k6/browser';
import { check } from 'k6';
import { browser as browserThresholds } from '../../lib/thresholds.js';
import { requireFeUrl } from '../../lib/env.js';

const EMAIL = __ENV.LOADTEST_USER_EMAIL || 'loadtest@sorento.local';
const PASSWORD = __ENV.LOADTEST_USER_PASSWORD || 'changeme';

export const options = {
  scenarios: {
    browser: {
      executor: 'shared-iterations',
      iterations: Number(__ENV.BROWSER_ITERATIONS || 5),
      vus: Number(__ENV.BROWSER_VUS || 2),
      maxDuration: '5m',
      options: { browser: { type: 'chromium' } },
      exec: 'signin',
      tags: { profile: __ENV.PROFILE || 'smoke' },
    },
  },
  thresholds: browserThresholds,
};

export async function signin() {
  const fe = requireFeUrl();
  const ctx = await browser.newContext();
  const page = await ctx.newPage();

  try {
    await page.goto(`${fe}/signin`, { waitUntil: 'networkidle' });
    await page.locator('input[name="email"]').type(EMAIL);
    await page.locator('input[name="password"]').type(PASSWORD);
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle' }),
      page.locator('button[type="submit"]').click(),
    ]);
    check(page, {
      'signed in': (p) => !p.url().includes('/signin'),
    });
  } finally {
    await page.close();
    await ctx.close();
  }
}

export default signin;
