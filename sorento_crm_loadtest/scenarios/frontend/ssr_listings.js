import http from 'k6/http';
import { sleep, group } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { ssr as ssrThresholds } from '../../lib/thresholds.js';
import { requireFeUrl } from '../../lib/env.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'ssr',
  thresholds: ssrThresholds,
  scenarioOverrides: { peakRps: 20, preAllocatedVUs: 20, maxVUs: 100 },
});

const PATHS = [
  '/',
  '/order-management/orders',
  '/complaint-management/complaints',
  '/inventory-management/stock',
];

const COOKIE = __ENV.FE_NEXTAUTH_COOKIE || '';

export function ssr() {
  const fe = requireFeUrl();
  const headers = COOKIE ? { Cookie: COOKIE } : {};
  for (const p of PATHS) {
    group(`GET ${p}`, () => {
      const res = http.get(`${fe}${p}`, { headers, tags: { name: `ssr_${p.replace(/\//g, '_') || '_root'}` } });
      isOk(res, `ssr ${p}`);
    });
  }
  sleep(1);
}

export default ssr;
