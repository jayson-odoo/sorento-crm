import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { heavyWrite } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { authHeaders } from '../../lib/auth.js';
import { unique } from '../../lib/data.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'createOrder',
  thresholds: heavyWrite,
  scenarioOverrides: { peakRps: 10, preAllocatedVUs: 20, maxVUs: 100 },
});

export function createOrder() {
  const be = requireBeUrl();
  const ref = unique('LOADTEST-ORD');
  const body = {
    customer_name: ref,
    notes: `LOADTEST VU=${__VU} ITER=${__ITER}`,
    items: [{ description: 'loadtest item', quantity: 1, unit_price: 1.0 }],
  };
  const res = http.post(
    `${be}/api/v1/order-management/orders`,
    JSON.stringify(body),
    { headers: authHeaders(), tags: { name: 'orders_create' } },
  );
  isOk(res, 'orders_create');
  sleep(1);
}

export default createOrder;
