import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { heavyWrite } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { externalHeaders } from '../../lib/auth.js';
import { unique } from '../../lib/data.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'externalCreate',
  thresholds: heavyWrite,
  scenarioOverrides: { peakRps: 20, preAllocatedVUs: 20, maxVUs: 100 },
});

let logged = false;

const CONTACT_ID = __ENV.LOADTEST_CONTACT_ID || '423512626';
const SPACE_ID = __ENV.LOADTEST_SPACE_ID || '364817';

export function externalCreate() {
  const be = requireBeUrl();
  const body = {
    inquiry_number: unique('LOADTEST-SI'),
    salesperson: 'loadtest-sales',
    product_code: 'LOADTEST-SKU',
    item_description: `LOADTEST item VU=${__VU} ITER=${__ITER}`,
    project_customer: 'LOADTEST customer',
    project_name: `LOADTEST project ${__VU}-${__ITER}`,
    quantity: '1',
    delivery_date: '2026-12-31',
    contact_id: CONTACT_ID,
    space_id: SPACE_ID,
    remark: 'LOADTEST stress run',
    user_confirmed: true,
  };
  const res = http.post(
    `${be}/api/v1/external/stock-inquiries/`,
    JSON.stringify(body),
    { headers: externalHeaders(), tags: { name: 'external_stock_inquiry_create' } },
  );
  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[external_stock_inquiry_create] status=${res.status} body=${(res.body || '').toString().slice(0, 300)}`);
  }
  isOk(res, 'external_stock_inquiry_create');
  sleep(1);
}

export default externalCreate;
