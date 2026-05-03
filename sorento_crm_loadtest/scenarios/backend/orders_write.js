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

let logged = false;

export function createOrder() {
  const be = requireBeUrl();
  const body = {
    order_number: unique('LOADTEST-ORD'),
    remarks: `LOADTEST VU=${__VU} ITER=${__ITER}`,
  };
  const res = http.post(
    `${be}/api/v1/order-management/orders/`,
    JSON.stringify(body),
    { headers: authHeaders(), tags: { name: 'orders_create' } },
  );
  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[orders_create] POST ${be}/api/v1/order-management/orders/ status=${res.status} body=${(res.body || '').toString().slice(0, 300)}`);
  }
  isOk(res, 'orders_create');
  sleep(1);
}

export default createOrder;
